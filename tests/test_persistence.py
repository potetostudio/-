"""Draft recovery, guest use, account boundaries, and reliable explicit saves."""
from test_studio import StudioBrowserCase, HTML


class PersistenceTests(StudioBrowserCase):
    def test_input_draft_survives_reload_without_executing(self):
        self.page.evaluate("nav('studio')")
        self.page.locator('#lp-code').fill('<h1>Recovered input</h1>')
        self.page.wait_for_function("draftState==='saved'")
        self.page.reload()
        self.page.evaluate("resetAccountState({uid:'test'}); nav('studio')")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>Recovered input</h1>')
        self.assertEqual(self.page.locator('#sif').get_attribute('srcdoc'), '')
        self.assertIn('下書き保存済み', self.page.locator('#studio-save-status').text_content())

    def test_unapplied_editor_and_version_history_are_recoverable(self):
        self.page.evaluate("nav('studio'); startWS('<h1>Initial</h1>','Work','original'); showCP()")
        self.page.locator('#ct').fill('<h1>Applied</h1>')
        self.page.evaluate('applyCode()')
        self.page.locator('#ct').fill('<h1>Not yet applied</h1>')
        self.page.evaluate('flushStudioDraft()')
        self.page.reload()
        self.page.evaluate("resetAccountState({uid:'test'});nav('studio')")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>Not yet applied</h1>')
        self.assertGreaterEqual(self.page.evaluate('vers.length'), 2)
        self.assertEqual(self.page.locator('#sif').get_attribute('srcdoc'), '')

    def test_guest_can_run_save_locally_and_recover_without_firebase(self):
        page=self.context.new_page()
        page_errors=[]
        page.on('pageerror', lambda error: page_errors.append(str(error)))
        offline=HTML.replace('window.firebase = {','window.unusedFirebase = {')
        page.route('http://studio.test/',lambda route:route.fulfill(body=offline,content_type='text/html'))
        page.goto('http://studio.test/')
        page.locator('button[onclick="startGuestMode()"]').click()
        page.locator('#lp-code').fill('<h1>Guest app</h1>')
        page.locator('button[onclick="launchStudio()"]').click()
        self.assertEqual(page.frame_locator('#sif').locator('h1').inner_text(),'Guest app')
        self.assertTrue(page.evaluate("saveStudioApp('Guest title')"))
        page.reload()
        page.locator('button[onclick="startGuestMode()"]').click()
        self.assertIn('<h1>Guest app</h1>',page.locator('#lp-code').input_value())
        self.assertEqual(page.evaluate('apps[0].title'),'Guest title')
        page.evaluate('doPublishToGallery()')
        self.assertTrue(page.evaluate('curUser===null && guestMode'))
        self.assertEqual(page_errors,[])
        page.close()

    def test_account_switch_clears_credentials_views_and_separates_caches(self):
        self.page.evaluate("""() => {
          resetAccountState({uid:'alice'});nav('studio');
          apps=[{id:'alice-app',urlId:'alice-app',uid:'alice',code:'<p>Alice</p>',title:'Private'}];
          geminiKey='alice-secret';prof.name='Alice';
          document.getElementById('gemini-key-input').value=geminiKey;
          startWS('<p>Alice draft</p>','Alice','original');
          resetAccountState({uid:'bob'});nav('studio');
        }""")
        self.assertEqual(self.page.evaluate('apps'),[])
        self.assertEqual(self.page.evaluate('geminiKey'),'')
        self.assertEqual(self.page.locator('#gemini-key-input').input_value(),'')
        self.assertEqual(self.page.locator('#lp-code').input_value(),'')
        self.assertEqual(self.page.locator('#sif').get_attribute('srcdoc'),'')
        self.page.evaluate("resetAccountState({uid:'alice'});nav('studio')")
        self.assertEqual(self.page.evaluate('apps[0].title'),'Private')
        self.assertEqual(self.page.locator('#lp-code').input_value(),'<p>Alice draft</p>')
        self.page.evaluate('resetAccountState(null);startGuestMode()')
        self.assertEqual(self.page.evaluate('apps'),[])
        self.assertEqual(self.page.locator('#lp-code').input_value(),'')

    def test_late_settings_and_app_loads_cannot_leak_into_new_account(self):
        self.page.evaluate("""() => {
          resetAccountState({uid:'alice'});
          db={collection:()=>({doc:()=>({
            get:()=>new Promise(resolve=>{window.resolveSettings=resolve}),
            collection:()=>({orderBy:()=>({limit:()=>({get:()=>new Promise(resolve=>{window.resolveApps=resolve})})})})
          })})};
          window.settingsRequest=loadUserSettings();window.appsRequest=loadUserApps();
          resetAccountState({uid:'bob'});
          resolveSettings({exists:true,data:()=>({geminiApiKey:'alice-secret',authorName:'Alice'})});
          resolveApps({forEach:fn=>fn({id:'private',data:()=>({code:'Alice secret',label:'Private'})})});
        }""")
        self.page.evaluate('Promise.all([settingsRequest,appsRequest])')
        self.assertEqual(self.page.evaluate('geminiKey'),'')
        self.assertEqual(self.page.evaluate('prof.name'),'')
        self.assertEqual(self.page.evaluate('apps'),[])

    def test_loading_templates_never_deletes_user_documents(self):
        self.page.evaluate("""async () => {
          window.deleted=false;apps=[];
          cloudDocs=[{id:'saved-template',data:()=>({code:getTemplate('timer'),label:'My timer'}),
            ref:{delete:async()=>{window.deleted=true}}}];
          await loadUserApps();
        }""")
        self.assertFalse(self.page.evaluate('deleted'))
        self.assertEqual(self.page.evaluate('apps[0].title'),'My timer')

    def test_legacy_cache_is_preserved_and_only_owned_entries_are_migrated(self):
        self.page.evaluate("""() => {
          localStorage.setItem('pt_apps',JSON.stringify([
            {id:'alice',uid:'alice',title:'Alice',code:'A'},
            {id:'bob',uid:'bob',title:'Bob',code:'B'},
            {id:'unknown',title:'Unassigned',code:'C'}]));
          resetAccountState({uid:'alice'});
        }""")
        self.assertEqual(self.page.evaluate('apps.map(a=>a.id)'),['alice'])
        self.assertEqual(self.page.evaluate("JSON.parse(localStorage.getItem('pt_apps')).length"),3)

    def test_direct_edit_updates_one_id_and_preserves_public_metadata(self):
        self.page.evaluate("""() => {
          apps=[{id:'owned',urlId:'owned',uid:'test',title:'Original',code:'<h1>Old</h1>'}];
          store['users/test/apps/owned']={isPublic:true};
          editMyApp('owned');
        }""")
        self.page.locator('#ct').fill('<h1>Updated</h1>')
        self.assertTrue(self.page.evaluate('saveCurrentWork()'))
        self.assertEqual(self.page.evaluate('apps.length'),1)
        self.assertEqual(self.page.evaluate("store['users/test/apps/owned'].code"),'<h1>Updated</h1>')
        self.assertTrue(self.page.evaluate("store['users/test/apps/owned'].isPublic"))
        self.assertEqual(self.page.evaluate('editingAppId'),'owned')
        self.assertIn('クラウド保存済み',self.page.locator('#studio-save-status').text_content())

    def test_cloud_failure_retains_local_copy_and_retry_reports_success(self):
        self.page.evaluate("nav('studio');startWS('<p>Keep me</p>','Work','original');failWrites='unavailable'")
        self.assertFalse(self.page.evaluate("saveStudioApp('Retry app')"))
        self.assertEqual(self.page.evaluate("readLocalJson(accountKey('apps'),[])[1].code"),'<p>Keep me</p>')
        self.assertTrue(self.page.locator('#retry-cloud-save').is_visible())
        self.assertIn('クラウド保存失敗',self.page.locator('#studio-save-status').text_content())
        self.page.evaluate('failWrites=false')
        self.assertTrue(self.page.evaluate('retryLastCloudSave()'))
        self.assertTrue(self.page.locator('#retry-cloud-save').is_hidden())
        self.assertIn('クラウド保存済み',self.page.locator('#studio-save-status').text_content())

    def test_storage_quota_failure_is_visible_and_keeps_editor(self):
        self.page.evaluate("nav('studio')")
        self.page.locator('#lp-code').fill('<h1>Export this</h1>')
        self.page.evaluate("() => {Storage.prototype.setItem=function(){throw new Error('quota')};}")
        self.assertFalse(self.page.evaluate('flushStudioDraft()'))
        self.assertIn('保存に失敗',self.page.locator('#studio-save-status').text_content())
        self.assertEqual(self.page.locator('#lp-code').input_value(),'<h1>Export this</h1>')

    def test_failed_old_save_cannot_update_another_accounts_status(self):
        self.page.evaluate("""() => {
          resetAccountState({uid:'alice'});cur='<p>Alice</p>';
          db={collection:()=>({doc:()=>({collection:()=>({doc:()=>({set:()=>new Promise((resolve,reject)=>{window.rejectSave=reject})})})})})};
          window.saveRequest=autoSaveToFirestore('Alice','private');
        }""")
        self.page.wait_for_function("typeof rejectSave==='function'")
        self.page.evaluate("resetAccountState({uid:'bob'});rejectSave(new Error('offline'))")
        self.assertFalse(self.page.evaluate('saveRequest'))
        self.assertEqual(self.page.evaluate('cloudState'),'idle')
        self.assertEqual(self.page.evaluate('retryCloudSave'),None)

    def test_saves_for_same_app_are_written_in_order(self):
        self.page.evaluate("""() => {
          window.writes=[];
          db={collection:()=>({doc:()=>({collection:()=>({doc:()=>({set:async payload=>{
            writes.push(payload.code);
            if(writes.length===1)await new Promise(resolve=>{window.finishFirstSave=resolve});
          }})})})})};
          cur='first';window.firstSave=autoSaveToFirestore('Work','same');
          cur='second';window.secondSave=autoSaveToFirestore('Work','same');
        }""")
        self.page.wait_for_function("typeof finishFirstSave==='function'")
        self.assertEqual(self.page.evaluate('writes'),['first'])
        self.page.evaluate('finishFirstSave();Promise.all([firstSave,secondSave])')
        self.assertEqual(self.page.evaluate('writes'),['first','second'])

    def test_foreign_app_deletion_does_not_create_repair_documents(self):
        self.page.evaluate("store['gallery/foreign']={uid:'another-user',code:'Private'}")
        self.page.once('dialog',lambda dialog:dialog.accept())
        self.page.evaluate("delPublicApp('foreign')")
        self.assertEqual(self.page.evaluate('Object.keys(store)'),['gallery/foreign'])

    def test_late_ai_response_does_not_restore_previous_users_code(self):
        self.page.evaluate("""() => {
          resetAccountState({uid:'alice'});guestMode=false;nav('studio');
          aiMode='cloud';geminiKey='test-key';document.getElementById('agi').value='Private request';
          window.fetch=()=>new Promise(resolve=>{window.finishAI=resolve});
          window.generation=genFromPrompt();
          resetAccountState({uid:'bob'});
          finishAI({ok:true,json:async()=>({candidates:[{content:{parts:[{text:'```html\\n<h1>Alice code</h1>\\n```'}]}}]})});
        }""")
        self.page.evaluate('generation')
        self.assertEqual(self.page.evaluate('cur'),'')
        self.assertEqual(self.page.evaluate('apps'),[])
        self.assertNotIn('Alice code',self.page.locator('#sif').get_attribute('srcdoc') or '')

    def test_new_layout_prioritizes_import_and_keeps_optional_tools_closed(self):
        self.page.evaluate("nav('studio');setLanguage('en')")
        self.assertFalse(self.page.locator('#image-create-options').evaluate('el=>el.open'))
        self.assertFalse(self.page.locator('#ai-create-options').evaluate('el=>el.open'))
        self.assertTrue(self.page.locator('#code-drop-zone').is_visible())
        self.assertIn('Draft',self.page.locator('#studio-save-status').text_content())
        self.page.locator('#image-create-options summary').click()
        self.assertTrue(self.page.locator('#i2c-zone').is_visible())

    def test_new_edits_clear_saved_status_and_retry_uses_latest_code(self):
        self.page.evaluate("nav('studio');startWS('<p>First</p>','Work','original')")
        self.assertTrue(self.page.evaluate("saveStudioApp('Named')"))
        self.page.evaluate('showCP()')
        self.page.locator('#ct').fill('<p>Second</p>')
        self.page.evaluate('applyCode()')
        self.assertIn('未反映',self.page.locator('#studio-save-status').text_content())
        self.page.evaluate("failWrites='unavailable'")
        self.assertFalse(self.page.evaluate('saveCurrentWork()'))
        self.page.locator('#ct').fill('<p>Newest</p>')
        self.page.evaluate('failWrites=false')
        self.assertTrue(self.page.evaluate('retryLastCloudSave()'))
        key=self.page.evaluate('editingAppId')
        self.assertEqual(self.page.evaluate('store['+repr('users/test/apps/'+key)+'].code'),'<p>Newest</p>')

    def test_corrupt_caches_do_not_break_signin_or_overwrite_legacy_backup(self):
        self.page.evaluate("""() => {
          localStorage.setItem('pt_apps','not JSON');
          localStorage.setItem('pt_v2_profile_user_alice','null');
          localStorage.setItem('pt_v2_apps_user_alice','{}');
          resetAccountState({uid:'alice'});nav('studio');
        }""")
        self.assertEqual(self.page.evaluate('apps'),[])
        self.assertEqual(self.page.evaluate("localStorage.getItem('pt_apps')"),'not JSON')
        self.assertTrue(self.page.locator('#lp-code').is_visible())

    def test_fresh_cloud_content_updates_cache_but_pending_local_edits_survive(self):
        self.page.evaluate("""async () => {
          apps=[{id:'same',urlId:'same',title:'Old',code:'Old'}];
          cloudDocs=[{id:'same',data:()=>({label:'New',code:'New',updatedAt:new Date(2000)})}];
          await loadUserApps();
        }""")
        self.assertEqual(self.page.evaluate('apps[0].code'),'New')
        self.page.evaluate("""async () => {
          apps[0].code='Local unsynced';apps[0].pendingCloud=true;
          cloudDocs=[{id:'same',data:()=>({label:'Latest cloud',code:'Cloud',updatedAt:new Date(3000)})}];
          await loadUserApps();
        }""")
        self.assertEqual(self.page.evaluate('apps[0].code'),'Local unsynced')

    def test_queued_preview_and_fork_do_not_cross_account_boundaries(self):
        self.page.evaluate("""() => {
          resetAccountState({uid:'alice'});
          openPublicApp({_docId:'public',code:'<h1>Alice preview</h1>',title:'Preview'});
          forkApp();
          resetAccountState({uid:'bob'});
        }""")
        self.page.wait_for_function("document.getElementById('sif').srcdoc==='' && document.getElementById('app-pv').srcdoc===''")
        # Wait for a new browser task after both UI timers have expired.
        self.page.evaluate('() => new Promise(resolve=>setTimeout(resolve,150))')
        self.assertEqual(self.page.evaluate('cur'),'')
        self.assertNotIn('Alice preview',self.page.locator('#app-pv').get_attribute('srcdoc') or '')
        self.assertEqual(self.page.locator('#sif').get_attribute('srcdoc'),'')

    def test_fork_is_distinct_from_edit_and_preview_stops_when_leaving(self):
        self.page.evaluate("""() => {
          apps=[{id:'original',urlId:'original',uid:'test',title:'Original',code:'<h1>Original</h1>'}];
          openApp('original');
        }""")
        self.page.wait_for_function("document.getElementById('app-pv').srcdoc.includes('<h1>Original</h1>')")
        self.page.evaluate('forkApp()')
        self.page.wait_for_function("cur.includes('<h1>Original</h1>')")
        self.assertEqual(self.page.locator('#app-pv').get_attribute('srcdoc'),'')
        self.assertEqual(self.page.evaluate('editingAppId'),None)
        self.assertTrue(self.page.evaluate("saveStudioApp('Copy')"))
        self.assertEqual(self.page.evaluate('apps.length'),2)
        self.assertNotEqual(self.page.evaluate('editingAppId'),'original')

    def test_publishing_an_edited_app_updates_private_and_public_copies(self):
        self.page.evaluate("""() => {
          apps=[{id:'owned',urlId:'owned',uid:'test',title:'Original',code:'<h1>Old</h1>'}];
          store['gallery/owned']={uid:'test',title:'Original',isPublic:true,code:'<h1>Old</h1>',likes:7};
          editMyApp('owned');
        }""")
        self.page.locator('#ct').fill('<h1>Published edit</h1>')
        self.page.evaluate('applyCode();doPublishToGallery()')
        self.assertEqual(self.page.evaluate("store['users/test/apps/owned'].code"),'<h1>Published edit</h1>')
        self.assertEqual(self.page.evaluate("store['gallery/owned'].code"),'<h1>Published edit</h1>')
        self.assertEqual(self.page.evaluate("store['gallery/owned'].likes"),7)
        self.assertEqual(self.page.evaluate('apps.length'),1)

    def test_editing_during_a_slow_save_stays_marked_as_unsynced(self):
        self.page.evaluate("""() => {
          nav('studio');startWS('<p>Version one</p>','Work','original');showCP();
          db={collection:()=>({doc:()=>({collection:()=>({doc:()=>({set:()=>new Promise(resolve=>{window.finishSave=resolve})})})})})};
          window.saving=saveStudioApp('Slow save');
        }""")
        self.page.wait_for_function("typeof finishSave==='function'")
        self.page.locator('#ct').fill('<p>Version two</p>')
        self.page.evaluate('finishSave();saving')
        self.assertEqual(self.page.evaluate('cloudState'),'dirty')
        self.assertEqual(self.page.locator('#ct').input_value(),'<p>Version two</p>')
