// IndexedDB stores large work/code records. The memory cache keeps navigation
// safe even if both persistent browser stores are unavailable.
var localRecordCache=new Map();
var localRecordVersions=new Map();
var localRecordWrites=new Map();
var localRecordTimes=new Map();
var localDatabase=null;
var localDatabasePromise=null;

function openLocalDatabase() {
  if(localDatabase)return Promise.resolve(localDatabase);
  if(localDatabasePromise)return localDatabasePromise;
  localDatabasePromise=new Promise(function(resolve) {
    var settled=false;
    function finish(db){if(settled){if(db)db.close();return;}settled=true;resolve(db);}
    try {
      var request=indexedDB.open('poteto-studio-local-v1',1);
      request.onupgradeneeded=function(){if(!request.result.objectStoreNames.contains('records'))request.result.createObjectStore('records');};
      request.onsuccess=function(){
        var db=request.result;
        if(settled){db.close();return;}
        db.onversionchange=function(){db.close();if(localDatabase===db){localDatabase=null;localDatabasePromise=null;}};
        localDatabase=db;finish(db);
      };
      request.onerror=function(){finish(null);};
      request.onblocked=function(){finish(null);};
    } catch(e){finish(null);}
  });
  return localDatabasePromise;
}
function decodeLocalRecord(raw) {
  var record=typeof raw==='string' ? JSON.parse(raw) : raw;
  if(record && record.__potetoLocalRecord===1)return {value:record.value,time:Number(record.savedAt) || 0};
  return {value:record,time:record && Number(record.updatedAt) || 0};
}
function readLocalRecord(key,fallback) {
  if(localRecordCache.has(key))return localRecordCache.get(key);
  try {var raw=localStorage.getItem(key);return raw===null ? fallback : decodeLocalRecord(raw).value;}
  catch(e){return fallback;}
}
function localSaveStatus() {
  var owner=typeof curUser!=='undefined' && curUser ? curUser.uid : null;
  var pending=false,error=false;
  localRecordWrites.forEach(function(write){if(write.owner===owner){pending=pending || write.pending;error=error || write.error;}});
  return {pending:pending,error:error};
}
function notifyLocalSaveState() {
  if(typeof renderSaveState!=='function')return;
  var state=localSaveStatus();
  draftState=state.error ? 'error' : state.pending || draftTimer!==null ? 'pending' : 'saved';
  renderSaveState();
}
function writeLocalRecord(key,value,recordOwner) {
  var serialized,snapshot;
  try {serialized=JSON.stringify(value);snapshot=JSON.parse(serialized);}
  catch(e){return false;}
  localRecordCache.set(key,snapshot);
  var version=(localRecordVersions.get(key) || 0)+1;
  localRecordVersions.set(key,version);
  var owner=arguments.length>=3 ? recordOwner : typeof curUser!=='undefined' && curUser ? curUser.uid : null;
  var savedAt=Math.max(Date.now(),(localRecordTimes.get(key) || 0)+1);
  localRecordTimes.set(key,savedAt);
  serialized=JSON.stringify({__potetoLocalRecord:1,savedAt:savedAt,value:snapshot});
  var resolveWrite;
  var completion=new Promise(function(resolve){resolveWrite=resolve;});
  localRecordWrites.set(key,{version:version,owner:owner,pending:true,error:false,completion:completion});
  notifyLocalSaveState();
  function complete(ok) {
    resolveWrite(ok);
    var current=localRecordWrites.get(key);
    if(current && current.version===version){current.pending=false;current.error=!ok;notifyLocalSaveState();}
  }
  function fallback() {
    try {localStorage.setItem(key,serialized);complete(true);}
    catch(e){complete(false);}
  }
  function put(db) {
    if(!db){fallback();return;}
    try {
      // Transactions on the same object store are serialized in creation order.
      var transaction=db.transaction('records','readwrite');
      transaction.objectStore('records').put(serialized,key);
      transaction.oncomplete=function(){
        try {var raw=localStorage.getItem(key);if(raw===null || decodeLocalRecord(raw).time<=savedAt)localStorage.removeItem(key);}catch(e){}
        complete(true);
      };
      transaction.onabort=function(){fallback();};
      transaction.onerror=function(){};
    } catch(e){fallback();}
  }
  if(localDatabase)put(localDatabase);
  else openLocalDatabase().then(put,fallback);
  return true; // Accepted into memory; the status stays Saving until committed.
}
async function loadLocalRecords(keys) {
  var versions=keys.map(function(key){return localRecordVersions.get(key) || 0;});
  var owner=typeof curUser!=='undefined' && curUser ? curUser.uid : null;
  var db=await openLocalDatabase();
  if(!db)return;
  await new Promise(function(resolve) {
    try {
      var migrations=[];
      var transaction=db.transaction('records','readonly');
      keys.forEach(function(key,index) {
        var request=transaction.objectStore('records').get(key);
        request.onsuccess=function(){
          if((localRecordVersions.get(key) || 0)!==versions[index])return;
          var persisted=null,legacy=null;
          try {if(request.result!==undefined)persisted=decodeLocalRecord(request.result);}catch(e){}
          try {var raw=localStorage.getItem(key);if(raw!==null)legacy=decodeLocalRecord(raw);}catch(e){}
          var chosen=legacy && (!persisted || legacy.time>persisted.time) ? legacy : persisted;
          if(!chosen)return;
          // A failed write may leave newer work in memory than either store.
          if(localRecordCache.has(key) && (localRecordTimes.get(key) || 0)>chosen.time)return;
          localRecordCache.set(key,chosen.value);localRecordTimes.set(key,chosen.time);
          if(chosen===legacy)migrations.push({key:key,value:chosen.value,version:versions[index]});
        };
      });
      transaction.oncomplete=function(){
        migrations.forEach(function(record){if((localRecordVersions.get(record.key) || 0)===record.version)writeLocalRecord(record.key,record.value,owner);});
        resolve();
      };
      transaction.onabort=resolve;transaction.onerror=function(){};
    } catch(e){resolve();}
  });
}

async function waitForLocalWrites(keys) {
  var promises=keys.map(function(key){var write=localRecordWrites.get(key);return write ? write.completion : Promise.resolve(true);});
  var results=await Promise.all(promises);
  return results.every(function(ok){return ok;});
}
