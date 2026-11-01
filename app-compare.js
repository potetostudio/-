// Stage and run two isolated apps before explicitly updating the saved app.
var appComparisonSession=null;
var appComparisonRequest=0;

function currentComparison(session) {
  return appComparisonSession===session && session.revision===accountRevision;
}
function comparisonMessage(id,message,error) {
  var node=document.getElementById(id);
  setUiText(node,function(){return t(message);});node.classList.toggle('comparison-error',!!error);
}
function stopComparisonFrames() {
  ['old','new'].forEach(function(side){
    var frame=document.getElementById('compare-frame-'+side);
    if(frame){var empty=frame.cloneNode(false);empty.removeAttribute('srcdoc');empty.removeAttribute('src');empty.hidden=true;frame.replaceWith(empty);}
    var error=document.getElementById('compare-error-'+side);error.hidden=true;error.textContent='';
    document.getElementById('compare-placeholder-'+side).hidden=false;
  });
}
function closeAppComparison(restoreFocus) {
  appComparisonRequest++;
  var session=appComparisonSession;appComparisonSession=null;
  var dialog=document.getElementById('app-compare-dialog');
  if(!dialog)return;
  if(!session && !dialog.open)return;
  if(dialog.open)dialog.close();
  stopComparisonFrames();
  document.getElementById('compare-code-input').value='';
  document.getElementById('compare-file-input').value='';
  document.getElementById('compare-file-zone').classList.remove('drag');
  ['compare-app-title','compare-file-status','compare-result'].forEach(function(id){var node=document.getElementById(id);node.textContent='';uiTextBindings.delete(node);});
  if(session && restoreFocus!==false){
    var card=Array.from(document.querySelectorAll('#gg .gc')).find(function(node){return node.dataset.appId===session.id;});
    if(card)card.querySelector('.gc-more').focus({preventScroll:true});
  }
}
function syncComparisonControls(session) {
  var locked=session.saving || session.applied;
  document.getElementById('compare-file-button').disabled=locked;
  document.getElementById('compare-paste-button').disabled=locked;
  document.getElementById('compare-code-input').readOnly=locked;
  document.getElementById('compare-run').disabled=session.saving || session.reading || session.pasteDirty || !session.candidate;
  document.querySelectorAll('.compare-restart').forEach(function(button){button.disabled=session.saving || !session.started;});
  var apply=document.getElementById('compare-apply');
  apply.disabled=session.saving || session.reading || session.pasteDirty || !session.started || session.candidate===session.baseCode;
  var label=session.applied ? '保存を再試行' : 'この新しい版で更新';
  apply.querySelector('span').setAttribute('data-i18n',label);apply.querySelector('span').textContent=t(label);
}
async function openAppComparison(id) {
  closeAppComparison(false);
  var request=++appComparisonRequest,revision=accountRevision,navigation=workNavigationRevision;
  await accountStorageReady;
  if(request!==appComparisonRequest || revision!==accountRevision || navigation!==workNavigationRevision)return false;
  var app=findMyAppByKey(id);
  if(!app || typeof app.code!=='string' || (app.uid && (!curUser || app.uid!==curUser.uid)))return false;
  var session={id:String(app.urlId || app.id),revision:revision,baseCode:app.code,candidate:'',fileName:'',read:0,reading:false,pasteDirty:false,started:false,saving:false,applied:false};
  appComparisonSession=session;
  document.getElementById('compare-app-title').textContent=app.title || '';
  document.getElementById('compare-paste-options').open=false;
  var oldLabel=document.getElementById('compare-old-label');oldLabel.setAttribute('data-i18n','現在の保存版');oldLabel.textContent=t('現在の保存版');
  comparisonMessage('compare-file-status','新しいファイルを選ぶか、コードを貼り付けてください');
  comparisonMessage('compare-result','比較するまでは作品は更新されません');
  syncComparisonControls(session);
  document.getElementById('app-compare-dialog').showModal();
  document.getElementById('compare-file-button').focus();
  return true;
}
function setComparisonCandidate(session,code,fileName) {
  if(!currentComparison(session) || session.saving || session.applied)return;
  session.candidate=wrapCode(code,String(fileName || '').split('.').pop().toLowerCase());
  session.reading=false;session.pasteDirty=false;
  if(fileName)document.getElementById('compare-code-input').value='';
  session.fileName=fileName || '';session.started=false;stopComparisonFrames();
  setUiText(document.getElementById('compare-file-status'),function(){return t('読み込み済み: ')+(fileName || t('貼り付けたコード'));});
  document.getElementById('compare-file-status').classList.remove('comparison-error');
  comparisonMessage('compare-result',session.candidate===session.baseCode ? '保存版と同じコードです' : '比較するまでは作品は更新されません');
  syncComparisonControls(session);
}
async function readComparisonFiles(files) {
  var session=appComparisonSession;
  if(!session || session.saving || session.applied)return false;
  var list=Array.from(files || []);
  if(!list.length)return false;
  var sequence=++session.read;
  function fail(message){if(currentComparison(session) && sequence===session.read){session.reading=false;comparisonMessage('compare-file-status',message,true);syncComparisonControls(session);}return false;}
  if(list.length!==1)return fail('ファイルは1つずつ読み込んでください');
  var file=list[0];
  if(!/\.(html?|js|css|txt)$/i.test(file.name))return fail('HTML / CSS / JS / TXT ファイルを選択してください');
  if(file.size>5*1024*1024)return fail('ファイルは5MB以下にしてください');
  session.reading=true;syncComparisonControls(session);
  comparisonMessage('compare-file-status','ファイルを読み込んでいます…');
  try {
    var code=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
    if(!currentComparison(session) || sequence!==session.read || session.saving || session.applied)return false;
    if(!code.trim() || code.includes('\0'))return fail('空のファイルやバイナリファイルは読み込めません');
    setComparisonCandidate(session,code,file.name);return true;
  } catch(e){return fail('ファイルを読み込めませんでした。UTF-8のテキストファイルを選択してください');}
}
function useComparisonPaste() {
  var session=appComparisonSession;
  if(!session || session.saving || session.applied)return;
  var code=document.getElementById('compare-code-input').value;
  if(!code.trim() || code.includes('\0')){comparisonMessage('compare-file-status','空のファイルやバイナリファイルは読み込めません',true);return;}
  if(new TextEncoder().encode(code).length>5*1024*1024){comparisonMessage('compare-file-status','ファイルは5MB以下にしてください',true);return;}
  session.read++;setComparisonCandidate(session,code,'');
}
function restartComparisonPane(side) {
  var session=appComparisonSession;
  if(!session || !session.started || session.saving || !['old','new'].includes(side))return;
  var previous=document.getElementById('compare-frame-'+side),frame=previous.cloneNode(false);
  // Attach a visible fresh frame so the browser creates a rendering context.
  frame.hidden=false;frame.removeAttribute('srcdoc');frame.removeAttribute('src');previous.replaceWith(frame);
  frame._comparisonToken=generateId(16);
  document.getElementById('compare-placeholder-'+side).hidden=true;
  document.getElementById('compare-error-'+side).hidden=true;
  var code=side==='old' ? session.baseCode : session.candidate;
  frame.srcdoc=injectPreviewPrelude(normalizeGalleryPreviewCode(code),errorRelayFor(frame._comparisonToken));
}
function runAppComparison() {
  var session=appComparisonSession;
  if(!session || !session.candidate || session.saving || session.reading || session.pasteDirty)return;
  session.started=true;
  restartComparisonPane('old');restartComparisonPane('new');
  comparisonMessage('compare-result',session.applied ? '保存を再試行できます' : session.candidate===session.baseCode ? '保存版と同じコードです' : '左右を操作して確認し、よければ更新してください');
  syncComparisonControls(session);
}
function withComparisonHistory(versions,backup,currentCode) {
  if(!backup || backup.version!==1 || typeof backup.code!=='string')return versions;
  var result=versions.slice();
  function add(code,label,id){if(typeof code==='string' && code!==currentCode && !result.some(function(item){return item.code===code;}))result.push({id:id || backup.updatedAt,label:label,code:code,type:'original'});}
  if(backup.work && backup.work.code!==backup.code)add(backup.work.code,t('更新前の編集中コード'));
  add(backup.code,t('更新前の保存版'));
  if(backup.work)workVersions(backup.work).forEach(function(version){add(version.code,version.label,version.id);});
  return result.slice(0,20);
}
async function applyAppComparison() {
  var session=appComparisonSession;
  if(!session || session.saving || session.reading || session.pasteDirty || !session.started || !session.candidate || session.candidate===session.baseCode)return false;
  session.saving=true;session.read++;syncComparisonControls(session);
  comparisonMessage('compare-result','更新内容を保存しています…');
  try {
    var app=findMyAppByKey(session.id);
    if(!app || (app.uid && (!curUser || app.uid!==curUser.uid))){comparisonMessage('compare-result','比較中に保存版が変わりました。閉じて開き直してください。',true);return false;}
    if(app.code!==(session.applied ? session.candidate : session.baseCode)){
      comparisonMessage('compare-result','比較中に保存版が変わりました。閉じて開き直してください。',true);return false;
    }
    var backupKey=accountKey('before_update_'+session.id),workKey=accountKey('work_'+session.id),draftKey=accountKey('draft'),appsKey=accountKey('apps');
    if(!session.applied) {
      await loadLocalRecords([workKey]);
      if(!currentComparison(session))return false;
      app=findMyAppByKey(session.id);
      if(!app || app.code!==session.baseCode){comparisonMessage('compare-result','比較中に保存版が変わりました。閉じて開き直してください。',true);return false;}
      var work=readLocalJson(workKey,null);
      writeLocalJson(backupKey,{version:1,appId:session.id,code:app.code,work:work && typeof work.code==='string' ? work : null,updatedAt:Date.now()});
      var backupOK=await waitForLocalWrites([backupKey]);
      if(!currentComparison(session))return false;
      if(!backupOK){comparisonMessage('compare-result','更新前の版を保存できません。コードを書き出してから再試行してください。',true);return false;}
      app=findMyAppByKey(session.id);
      if(!app || app.code!==session.baseCode){comparisonMessage('compare-result','比較中に保存版が変わりました。閉じて開き直してください。',true);return false;}
      session.applied=true;
      Object.assign(app,{code:session.candidate,updatedAt:Date.now(),pendingCloud:!!curUser});
      session.work={version:2,code:session.candidate,fileName:'',editingAppId:session.id,title:app.title,modified:false,
        versions:[{id:Date.now(),label:app.title,type:'original',usesCurrentCode:true}],updatedAt:Date.now()};
    }
    persistApps();writeLocalJson(workKey,session.work);
    var draft=readLocalJson(draftKey,null),keys=[appsKey,workKey];
    if(draft && String(draft.editingAppId)===session.id){writeLocalJson(draftKey,session.work);keys.push(draftKey);}
    renderGallery();
    var localOK=await waitForLocalWrites(keys);
    if(session.revision!==accountRevision)return false;
    app=findMyAppByKey(session.id);
    if(!app || app.code!==session.candidate){if(currentComparison(session))comparisonMessage('compare-result','比較中に保存版が変わりました。閉じて開き直してください。',true);return false;}
    var saved=curUser ? await autoSaveToFirestore(app.title,session.id,session.candidate) : localOK;
    if(session.revision!==accountRevision)return false;
    if(saved){
      renderGallery();
      if(currentComparison(session))closeAppComparison();
      T(t('作品を更新しました'));return true;
    }
    if(currentComparison(session)) {
      var oldLabel=document.getElementById('compare-old-label');oldLabel.setAttribute('data-i18n','更新前の版');oldLabel.textContent=t('更新前の版');
      comparisonMessage('compare-result',curUser ? 'クラウド保存に失敗しました。保存を再試行できます。' : '端末への保存に失敗しました。保存を再試行してください。',true);
    }
    return false;
  } finally {
    session.saving=false;if(currentComparison(session))syncComparisonControls(session);
  }
}
function setupAppComparison() {
  var dialog=document.getElementById('app-compare-dialog'),picker=document.getElementById('compare-file-input'),zone=document.getElementById('compare-file-zone');
  dialog.addEventListener('cancel',function(event){event.preventDefault();closeAppComparison();});
  dialog.addEventListener('close',function(){if(!dialog.open && appComparisonSession)closeAppComparison(false);});
  picker.addEventListener('change',function(){var files=Array.from(picker.files);picker.value='';readComparisonFiles(files);});
  document.getElementById('compare-code-input').addEventListener('input',function(){
    var session=appComparisonSession;if(!session || session.applied)return;
    session.pasteDirty=true;comparisonMessage('compare-file-status','貼り付けたコードを読み込んでください');syncComparisonControls(session);
  });
  zone.addEventListener('dragover',function(event){if(Array.from(event.dataTransfer.types).includes('Files')){event.preventDefault();zone.classList.add('drag');}});
  zone.addEventListener('dragleave',function(event){if(!zone.contains(event.relatedTarget))zone.classList.remove('drag');});
  zone.addEventListener('drop',function(event){
    if(!Array.from(event.dataTransfer.types).includes('Files'))return;
    event.preventDefault();zone.classList.remove('drag');
    var directory=Array.from(event.dataTransfer.items || []).some(function(item){var entry=item.webkitGetAsEntry && item.webkitGetAsEntry();return entry && entry.isDirectory;});
    if(directory){readComparisonFiles([null,null]);return;}
    readComparisonFiles(event.dataTransfer.files);
  });
}
window.addEventListener('message',function(event) {
  if(!appComparisonSession || !event.data || event.data.type!=='__poteto_err__')return;
  ['old','new'].forEach(function(side){
    var frame=document.getElementById('compare-frame-'+side);
    if(event.source!==frame.contentWindow || event.data.token!==frame._comparisonToken)return;
    var error=document.getElementById('compare-error-'+side);error.textContent=String(event.data.msg || '').slice(0,600);error.hidden=false;
  });
});
