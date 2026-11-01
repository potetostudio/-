// Local drafts and account-scoped caches. No credentials are persisted here.
var guestMode = false;
var accountRevision = 0;
var accountInitialized = false;
var editingAppId = null;
var draftTimer = null;
var draftState = 'idle';
var cloudState = 'idle';
var lastCloudCode = null;
var cloudSaveSequence = 0;
var retryCloudSave = null;
var restoringDraft = false;
var cloudWriteQueues = new Map();
var streamIntervals = new Set();
var previewSequence = 0;
var accountStorageLoading=false;
var accountStorageReady=Promise.resolve();
var workNavigationRevision=0;
var workEditSequence=0;

function accountKey(name, uid) {
  if (uid === undefined) uid = curUser ? curUser.uid : null;
  return 'pt_v2_' + name + '_' + (uid ? 'user_' + uid : 'guest');
}
function readLocalText(key, fallback) {
  try {var value=localStorage.getItem(key);return value===null ? fallback : value;}catch(e){return fallback;}
}
function writeLocalText(key, value) {
  try {localStorage.setItem(key,value);return true;}catch(e){draftState='error';renderSaveState();return false;}
}
function readLocalJson(key, fallback) { return readLocalRecord(key,fallback); }
function writeLocalJson(key, value) {
  if(writeLocalRecord(key,value))return true;
  draftState='error';renderSaveState();return false;
}
function persistApps() { return writeLocalJson(accountKey('apps'), apps); }
function persistProfile() { return writeLocalJson(accountKey('profile'), prof); }
function sameAccount(uid, revision) {
  return !!curUser && curUser.uid === uid && revision === accountRevision;
}
function renderSaveState() {
  var el = document.getElementById('studio-save-status');
  if (!el) return;
  var draftLabels = { idle:'作業内容をこの端末に自動保存します', pending:'自動保存中…', saved:'自動保存済み（この端末）', error:'自動保存できません。閉じる前にコードを書き出してください' };
  var cloudLabels = { saving:'クラウド保存中…', saved:'クラウド保存済み', dirty:'クラウドに未反映の変更があります', error:'クラウド保存失敗（再試行できます）' };
  setUiText(el, function() { return t(accountStorageLoading ? '保存した作業を読み込んでいます…' : draftLabels[draftState]) + (cloudLabels[cloudState] ? ' · ' + t(cloudLabels[cloudState]) : ''); });
  el.classList.toggle('error', draftState === 'error' || cloudState === 'error');
  document.getElementById('editing-notice').hidden = !editingAppId;
  document.getElementById('guest-login').hidden = !!curUser;
  document.getElementById('retry-cloud-save').hidden = cloudState !== 'error' || !retryCloudSave;
}
function captureStudioDraft() {
  var view = document.getElementById('view-studio');
  if (!view || !view.classList.contains('active')) return null;
  var workspace = document.getElementById('workspace').style.display === 'flex';
  var code = workspace ? (cpOpen ? document.getElementById('ct').value : cur) : document.getElementById('lp-code').value;
  var app=editingAppId ? findMyAppByKey(editingAppId) : null;
  return { version:2, code:code, fileName:workspace ? '' : codeInputFileName,
    editingAppId:editingAppId, modified:!app || app.code!==code,
    title:chooseWorkTitle(code,document.getElementById('shtitle').value,codeInputFileName),
    versions:compactWorkVersions(code), updatedAt:Date.now() };
}
function compactWorkVersions(code) {
  var budget=256*1024, result=[], previous=null;
  vers.slice(0,10).forEach(function(version) {
    if(!version || typeof version.code!=='string' || version.code===previous)return;
    previous=version.code;
    var item={id:version.id,label:version.label,type:version.type};
    if(version.code===code)item.usesCurrentCode=true;
    else {if(version.code.length>budget)return;item.code=version.code;budget-=version.code.length;}
    result.push(item);
  });
  return result;
}
function workVersions(record) {
  return Array.isArray(record.versions) ? record.versions.map(function(version) {
    return version && Object.assign({},version,{code:version.usesCurrentCode ? record.code : version.code});
  }).filter(function(version){return version && typeof version.code==='string';}) : [];
}
function sameWork(a,b) {
  return a && ['code','fileName','editingAppId','modified','title','versions'].every(function(key){return JSON.stringify(a[key])===JSON.stringify(b[key]);});
}
function flushStudioDraft() {
  clearTimeout(draftTimer);draftTimer=null;
  if(restoringDraft || accountStorageLoading)return true;
  var draft=captureStudioDraft();
  if(draft && cloudState==='saved' && draft.code!==lastCloudCode)cloudState='dirty';
  if(!draft || !draft.code.trim()){renderSaveState();return true;}
  if(!sameWork(readLocalJson(accountKey('draft'),null),draft))writeLocalJson(accountKey('draft'),draft);
  if(draft.editingAppId) {
    var key=accountKey('work_'+draft.editingAppId);
    if(!sameWork(readLocalJson(key,null),draft))writeLocalJson(key,draft);
  }
  renderSaveState();
  return !localSaveStatus().error;
}
function scheduleStudioDraft() {
  if(restoringDraft || accountStorageLoading)return;
  var next=captureStudioDraft();
  if(!next || sameWork(readLocalJson(accountKey('draft'),null),next))return;
  if(draftState!=='pending'){draftState='pending';renderSaveState();}
  clearTimeout(draftTimer);draftTimer=setTimeout(flushStudioDraft,350);
}
function restoreStudioDraft() {
  if(accountStorageLoading)return false;
  var draft=readLocalJson(accountKey('draft'),null);
  if(!draft || ![1,2].includes(draft.version) || typeof draft.code!=='string' || !draft.code.trim()){renderSaveState();return false;}
  var app=draft.editingAppId ? findMyAppByKey(draft.editingAppId) : null;
  if(app && draft.modified===false && draft.code!==app.code)draft=Object.assign({},draft,{code:app.code,title:app.title,versions:[]});
  restoringDraft=true;
  document.getElementById('lp-code').value=draft.code;
  codeInputFileName=typeof draft.fileName==='string' ? draft.fileName : '';
  editingAppId=app ? draft.editingAppId : null;
  if(editingAppId && findMyAppByKey(editingAppId).pendingCloud)cloudState='dirty';
  document.getElementById('shtitle').value=chooseWorkTitle(draft.code,draft.title,draft.fileName);
  vers=workVersions(draft);restoringDraft=false;
  notifyLocalSaveState();return true;
}
function setWorkLoading(loading) {
  ['lp-code','ct'].forEach(function(id){var field=document.getElementById(id);if(field)field.readOnly=loading;});
  document.querySelectorAll('button[onclick="launchStudio()"],#code-file-button,#code-clear-button,#code-undo-button').forEach(function(button){button.disabled=loading;});
}
async function hydrateAccountWork(revision) {
  try {await loadLocalRecords(['apps','profile','draft','gallery'].map(function(name){return accountKey(name);}));}
  catch(e){console.warn('Saved work unavailable:',e);}
  if(revision!==accountRevision)return;
  var stored=readLocalJson(accountKey('apps'),null);
  if(Array.isArray(stored))apps=stored.filter(function(app){return app && typeof app.code==='string' && (!app.uid || (curUser && app.uid===curUser.uid));});
  else if(apps.length)persistApps(); // Migrate positively owned legacy records.
  var profile=readLocalJson(accountKey('profile'),null);
  if(profile && typeof profile==='object')prof={name:typeof profile.name==='string' ? profile.name : '',avatar:typeof profile.avatar==='string' ? profile.avatar : ''};
  restoreGalleryPreferences();
  accountStorageLoading=false;setWorkLoading(false);
  if(document.getElementById('view-studio').classList.contains('active')) {
    if(document.getElementById('workspace').style.display==='flex')flushStudioDraft();
    else restoreStudioDraft();
  }
  renderGallery();renderSaveState();
}
function resetAccountState(user) {
  if (accountInitialized) { flushStudioDraft(); persistApps(); persistProfile(); }
  stopGalleryThumbnails(true);
  accountRevision++; cloudSaveSequence++; clearTimeout(draftTimer);draftTimer=null;
  streamIntervals.forEach(function(id) {clearInterval(id);});streamIntervals.clear();
  stopThinking();showBuildLoading(false);
  var bar=document.getElementById('stream-bar');bar.style.width='0';bar.classList.remove('active');
  document.querySelectorAll('#app button').forEach(function(button) {button.disabled=false;});
  retryCloudSave = null; cloudState = 'idle'; lastCloudCode=null; draftState = 'idle';
  if (cvsUnsubscribe) { cvsUnsubscribe(); cvsUnsubscribe = null; }
  stopCommentsListener();
  curUser = user; guestMode = false; appBootstrapped = false; accountInitialized = true;
  var cached = readLocalJson(accountKey('apps'), null);
  if (!Array.isArray(cached)) {
    // Migrate only positively owned entries. Leave the legacy cache intact.
    var legacy = readLocalJson('pt_apps', []);
    cached = user && Array.isArray(legacy) ? legacy.filter(function(a) { return a && a.uid === user.uid; }) : [];
  }
  apps = cached.filter(function(a) { return a && typeof a.code === 'string' && (!a.uid || (user && a.uid === user.uid)); });
  var profile = readLocalJson(accountKey('profile'), {}) || {};
  prof = { name:typeof profile.name === 'string' ? profile.name : '', avatar:typeof profile.avatar === 'string' ? profile.avatar : '' };
  _titleCallback = null;
  lastError = ''; _renameAppId = null; _editCommentId = null;
  geminiKey = ''; aiMode = 'local'; publicApps = []; galleryTab = 'my';
  restoreGalleryPreferences();
  cvsChats = []; cvsCurDocId = null; cvHistory = []; cvOllamaMessages = []; cvCode = ''; cvPendingImg = ''; cvPendingMime = '';
  chatHistory = []; wsOllamaMessages = []; editingAppId = null;
  sharedGatePayload = null; forkCode = ''; curAppId = null; curPublicDocId = null; surl = '';
  clearAppPreview(); resetS();
  ['sif','cv-iframe'].forEach(function(id) { var f=document.getElementById(id); f.srcdoc=''; f.removeAttribute('src'); });
  ['gemini-key-input','pname','auth-pw','auth-gate-pw','lp-code','ct','chat-inp','cv-inp','shtitle','app-comment-input','edit-comment-input','rename-app-input'].forEach(function(id) { var el=document.getElementById(id); if(el)el.value=''; });
  ['gemini-key-status','chat-msgs','cv-msgs','app-comments-list','cv-code-body','toast'].forEach(function(id) { var el=document.getElementById(id); if(el)el.textContent=''; });
  document.querySelectorAll('.mo.on').forEach(function(el) { el.classList.remove('on'); });
  var avatar=document.getElementById('avimg'); avatar.removeAttribute('src'); avatar.style.display='none';
  document.getElementById('cv-code-modal') && cvCloseCode();
  document.getElementById('image-create-options').open=false;
  document.getElementById('ai-create-options').open=false;
  accountStorageLoading=true;setWorkLoading(true);
  updateNavBadge();renderGallery();renderSaveState();
  accountStorageReady=hydrateAccountWork(accountRevision);
  return accountStorageReady;
}
async function startGuestMode() {
  if (curUser) return;
  var revision=accountRevision;await accountStorageReady;if(revision!==accountRevision || curUser)return;
  guestMode = true; updateAuthGate(); nav('studio');
}
async function editMyApp(id) {
  var revision=accountRevision, navigation=workNavigationRevision, request=++workEditSequence;
  await accountStorageReady;if(revision!==accountRevision || navigation!==workNavigationRevision || request!==workEditSequence)return;
  var app=findMyAppByKey(id);
  if(!app || (app.uid && (!curUser || app.uid!==curUser.uid)))return;
  var key=app.urlId || app.id;
  await loadLocalRecords([accountKey('work_'+key)]);
  if(revision!==accountRevision || navigation!==workNavigationRevision || request!==workEditSequence)return;
  app=findMyAppByKey(key);if(!app)return;
  var work=readLocalJson(accountKey('work_'+key),null);
  var legacy=readLocalJson(accountKey('draft'),null);
  if(!work && legacy && String(legacy.editingAppId)===String(key))work=legacy;
  if(work && (typeof work.code!=='string' || (work.modified===false && work.code!==app.code)))work=null;
  var code=work ? work.code : app.code,title=app.title;
  nav('studio');startWS(code,title,'original',true,key);
  if(work){vers=workVersions(work);renderHist();}
  showCP();flushStudioDraft();
}
async function saveStudioApp(title) {
  title=chooseWorkTitle(cur,title,codeInputFileName);
  if (cpOpen && document.getElementById('workspace').style.display === 'flex' && document.getElementById('ct').value!==cur) applyCode();
  var uid = curUser ? curUser.uid : null, revision = accountRevision;
  var app = editingAppId ? findMyAppByKey(editingAppId) : null;
  if (app && app.uid && app.uid !== uid) return false;
  if (!app) {
    var id=generateId(10);
    app={id:id,urlId:id,likes:0,createdAt:Date.now(),uid:uid || ''}; apps.push(app);
  }
  Object.assign(app,{title:title,code:cur,author:prof.name || '',avatar:prof.avatar || '',pendingCloud:!!uid,updatedAt:Date.now()});
  editingAppId=app.urlId || app.id; isTemplate=false;
  var appId=editingAppId, savedCode=cur;
  persistApps();flushStudioDraft();
  var localOK=await waitForLocalWrites([accountKey('apps'),accountKey('draft'),accountKey('work_'+appId)]);
  if(revision!==accountRevision)return false;
  if (uid) return await autoSaveToFirestore(title,appId,savedCode);
  cloudState='idle';renderSaveState();return localOK;
}
function saveCurrentWork() {
  var app = editingAppId ? findMyAppByKey(editingAppId) : null;
  if (app) return saveStudioApp(app.title);
  requireTitle(function(title) { saveStudioApp(title); });
}
async function retryLastCloudSave() {
  if (!retryCloudSave || !curUser || retryCloudSave.uid !== curUser.uid) return false;
  var snapshot=retryCloudSave;
  if(editingAppId===snapshot.id && document.getElementById('view-studio').classList.contains('active') && document.getElementById('workspace').style.display==='flex')return await saveStudioApp(snapshot.payload.label);
  return await writeCloudSnapshot(snapshot);
}
async function writeCloudSnapshot(snapshot) {
  var uid=snapshot.uid, revision=accountRevision, sequence=++cloudSaveSequence;
  if (!sameAccount(uid,revision)) return false;
  cloudState='saving'; renderSaveState();
  try {
    var queueKey=uid+'/'+snapshot.id;
    var previous=cloudWriteQueues.get(queueKey) || Promise.resolve();
    var write=previous.catch(function() {}).then(function() {
      if (!sameAccount(uid,revision)) return;
      return db.collection('users').doc(uid).collection('apps').doc(snapshot.id).set(snapshot.payload,{merge:true});
    });
    cloudWriteQueues.set(queueKey,write);
    try { await write; } finally { if(cloudWriteQueues.get(queueKey)===write)cloudWriteQueues.delete(queueKey); }
    if (!sameAccount(uid,revision)) return false;
    var local=apps.find(function(app){return String(app.urlId || app.id)===String(snapshot.id);});
    if(local && local.code===snapshot.payload.code){local.pendingCloud=false;local.savedAt=new Date(snapshot.payload.updatedAt).getTime();persistApps();}
    if (sequence===cloudSaveSequence) {
      lastCloudCode=snapshot.payload.code;
      var currentDraft=captureStudioDraft();
      cloudState=currentDraft && currentDraft.code!==lastCloudCode ? 'dirty' : 'saved';
      retryCloudSave=null;renderSaveState();
    }
    return true;
  } catch(e) {
    if (!sameAccount(uid,revision)) return false;
    if (sequence===cloudSaveSequence) { cloudState='error'; retryCloudSave=snapshot; renderSaveState(); }
    return false;
  }
}
function setupStudioPersistence() {
  openLocalDatabase();
  ['lp-code','ct','shtitle'].forEach(function(id) { document.getElementById(id).addEventListener('input', scheduleStudioDraft); });
  new MutationObserver(scheduleStudioDraft).observe(document.getElementById('sif'),{attributes:true,attributeFilter:['srcdoc']});
  window.addEventListener('beforeunload',function(e) { flushStudioDraft();if(localSaveStatus().error){e.preventDefault();e.returnValue='';} });
  document.addEventListener('visibilitychange',function() { if(document.hidden)flushStudioDraft(); });
  renderSaveState();
}

async function guardAccountPromise(revision, promise) {
  try {
    var value=await promise;
    if (revision!==accountRevision) throw new Error('Account changed');
    return value;
  } catch(e) {
    if (revision!==accountRevision) throw new Error('Account changed');
    throw e;
  }
}
