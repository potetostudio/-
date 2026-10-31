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
function readLocalJson(key, fallback) {
  try {
    var raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch (e) { return fallback; }
}
function writeLocalJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; }
  catch (e) { draftState = 'error'; renderSaveState(); return false; }
}
function persistApps() { return writeLocalJson(accountKey('apps'), apps); }
function persistProfile() { return writeLocalJson(accountKey('profile'), prof); }
function sameAccount(uid, revision) {
  return !!curUser && curUser.uid === uid && revision === accountRevision;
}
function renderSaveState() {
  var el = document.getElementById('studio-save-status');
  if (!el) return;
  var draftLabels = { idle:'下書きはこの端末に保存されます', pending:'下書き保存中…', saved:'下書き保存済み（この端末）', error:'端末への保存に失敗しました。コードを書き出してください' };
  var cloudLabels = { saving:'クラウド保存中…', saved:'クラウド保存済み', dirty:'クラウドに未反映の変更があります', error:'クラウド保存失敗（再試行できます）' };
  setUiText(el, function() { return t(draftLabels[draftState]) + (cloudLabels[cloudState] ? ' · ' + t(cloudLabels[cloudState]) : ''); });
  el.classList.toggle('error', draftState === 'error' || cloudState === 'error');
  document.getElementById('editing-notice').hidden = !editingAppId;
  document.getElementById('guest-login').hidden = !!curUser;
  document.getElementById('retry-cloud-save').hidden = cloudState !== 'error' || !retryCloudSave;
  var draft = readLocalJson(accountKey('draft'), null);
  document.getElementById('resume-draft').hidden = !draft || typeof draft.code !== 'string' || !draft.code.trim();
}
function captureStudioDraft() {
  var view = document.getElementById('view-studio');
  if (!view || !view.classList.contains('active')) return null;
  var workspace = document.getElementById('workspace').style.display === 'flex';
  var code = workspace ? (cpOpen ? document.getElementById('ct').value : cur) : document.getElementById('lp-code').value;
  return { version:1, code:code, fileName:workspace ? '' : codeInputFileName,
    editingAppId:editingAppId, title:chooseWorkTitle(code,document.getElementById('shtitle').value,codeInputFileName),
    versions:vers.slice(0,10), updatedAt:Date.now() };
}
function flushStudioDraft() {
  clearTimeout(draftTimer);
  if (restoringDraft) return true;
  var draft = captureStudioDraft();
  if (draft && cloudState==='saved' && draft.code!==lastCloudCode)cloudState='dirty';
  if (!draft || !draft.code.trim()) return true; // Never erase a recoverable draft with an empty navigation reset.
  if (!writeLocalJson(accountKey('draft'), draft)) return false;
  draftState = 'saved'; renderSaveState(); return true;
}
function scheduleStudioDraft() {
  if (restoringDraft) return;
  var next=captureStudioDraft();
  if (!next) return;
  var previous=readLocalJson(accountKey('draft'),null);
  if (previous && ['code','fileName','editingAppId','title','versions'].every(function(k) { return JSON.stringify(previous[k])===JSON.stringify(next[k]); })) return;
  if (draftState !== 'pending') {draftState = 'pending'; renderSaveState();}
  clearTimeout(draftTimer); draftTimer = setTimeout(flushStudioDraft, 350);
}
function restoreStudioDraft() {
  var draft = readLocalJson(accountKey('draft'), null);
  if (!draft || draft.version !== 1 || typeof draft.code !== 'string' || !draft.code.trim()) { renderSaveState(); return false; }
  restoringDraft = true;
  document.getElementById('lp-code').value = draft.code;
  codeInputFileName = typeof draft.fileName === 'string' ? draft.fileName : '';
  editingAppId = draft.editingAppId && findMyAppByKey(draft.editingAppId) ? draft.editingAppId : null;
  if(editingAppId && findMyAppByKey(editingAppId).pendingCloud)cloudState='dirty';
  document.getElementById('shtitle').value = chooseWorkTitle(draft.code,draft.title,draft.fileName);
  vers = Array.isArray(draft.versions) ? draft.versions.filter(function(v) { return v && typeof v.code === 'string'; }) : [];
  draftState = 'saved'; restoringDraft = false; renderSaveState();
  return true; // Restoration never executes source code automatically.
}
function resumeStudioDraft() { nav('studio'); }
function resetAccountState(user) {
  if (accountInitialized) { flushStudioDraft(); persistApps(); persistProfile(); }
  stopGalleryThumbnails(true);
  accountRevision++; cloudSaveSequence++; clearTimeout(draftTimer);
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
  updateNavBadge(); persistApps(); renderGallery(); renderSaveState();
}
function startGuestMode() {
  if (curUser) return;
  guestMode = true; updateAuthGate(); nav('studio');
}
function editMyApp(id) {
  var app = findMyAppByKey(id);
  if (!app || (app.uid && (!curUser || app.uid !== curUser.uid))) return;
  var code = app.code, title = app.title, key = app.urlId || app.id;
  nav('studio');
  document.getElementById('shtitle').value = title;
  startWS(code, title, 'original', true, key);
  showCP(); flushStudioDraft();
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
  Object.assign(app,{title:title,code:cur,author:prof.name || '',avatar:prof.avatar || '',pendingCloud:!!uid});
  editingAppId=app.urlId || app.id; isTemplate=false;
  if (!persistApps() || !flushStudioDraft()) return false;
  if (uid) return await autoSaveToFirestore(title, editingAppId);
  cloudState='idle'; renderSaveState(); return revision === accountRevision;
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
  ['lp-code','ct','shtitle'].forEach(function(id) { document.getElementById(id).addEventListener('input', scheduleStudioDraft); });
  new MutationObserver(scheduleStudioDraft).observe(document.getElementById('sif'),{attributes:true,attributeFilter:['srcdoc']});
  window.addEventListener('beforeunload',function(e) { if (!flushStudioDraft()) { e.preventDefault();e.returnValue=''; } });
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
