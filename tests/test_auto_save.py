"""Automatic work recovery through the normal Create/Edit navigation."""
from test_studio import StudioBrowserCase, FIXTURE


class AutoSaveTests(StudioBrowserCase):
    def test_create_restores_work_and_returns_without_resume_button(self):
        self.page.evaluate("nav('studio')")
        self.assertEqual(self.page.locator('#resume-draft').count(), 0)
        self.page.locator('#lp-code').fill('<title>Continue me</title><h1>Work</h1>')
        self.page.wait_for_function("draftState==='saved'")
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState({uid:'test'});updateAuthGate();nav('studio')}")
        self.assertIn('Continue me', self.page.locator('#lp-code').input_value())
        self.assertEqual(self.page.locator('#sif').get_attribute('srcdoc'), '')
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.page.locator('#wsbar button[onclick="backToGallery()"]').click()
        self.assertTrue(self.page.locator('#view-gallery').evaluate("el=>el.classList.contains('active')"))

    def test_edit_recovers_each_apps_unapplied_changes_after_reload(self):
        self.page.evaluate("""async()=>{
          apps=['one','two'].map(id=>({id,urlId:id,uid:'test',title:id,code:'<h1>'+id+'</h1>'}));
          persistApps();await editMyApp('one');
        }""")
        self.page.locator('#ct').fill('<h1>One in progress</h1>')
        self.page.locator('#wsbar button[onclick="backToGallery()"]').click()
        self.page.evaluate("editMyApp('two')")
        self.page.locator('#ct').fill('<h1>Two in progress</h1>')
        self.page.locator('#wsbar button[onclick="backToGallery()"]').click()
        self.page.evaluate("waitForLocalWrites([accountKey('apps'),accountKey('draft'),accountKey('work_one'),accountKey('work_two')])")
        self.assertEqual(self.page.evaluate('Object.keys(store)'), [])
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState({uid:'test'});updateAuthGate();nav('gallery')}")
        for key, expected in [('one', 'One in progress'), ('two', 'Two in progress')]:
            self.page.evaluate('id=>editMyApp(id)', key)
            self.assertEqual(self.page.locator('#ct').input_value(), '<h1>'+expected+'</h1>')
            self.page.locator('#wsbar button[onclick="backToGallery()"]').click()
        self.assertEqual(self.page.evaluate('apps.map(a=>a.code)'), ['<h1>one</h1>', '<h1>two</h1>'])

    def test_storage_failure_never_traps_editor_and_memory_keeps_work(self):
        self.page.evaluate("""async()=>{
          await openLocalDatabase();
          localDatabase.transaction=()=>{throw Error('quota')};
          Storage.prototype.setItem=()=>{throw Error('quota')};
          apps=[{id:'one',title:'One',code:'<h1>Saved</h1>'}];
          await editMyApp('one');
        }""")
        self.page.locator('#ct').fill('<h1>Keep this edit</h1>')
        self.page.evaluate("async()=>{flushStudioDraft();await waitForLocalWrites([accountKey('draft'),accountKey('work_one')])}")
        self.assertIn('自動保存できません', self.page.locator('#studio-save-status').text_content())
        self.page.locator('#wsbar button[onclick="backToGallery()"]').click()
        self.assertTrue(self.page.locator('#view-gallery').evaluate("el=>el.classList.contains('active')"))
        self.page.evaluate("editMyApp('one')")
        self.assertEqual(self.page.locator('#ct').input_value(), '<h1>Keep this edit</h1>')

    def test_unavailable_stores_do_not_report_guest_save_success(self):
        self.page.add_init_script("""indexedDB.open=()=>{throw Error('blocked')};
          Storage.prototype.setItem=()=>{throw Error('blocked')};""")
        self.page.reload()
        self.page.evaluate(FIXTURE)
        self.page.evaluate("async()=>{await resetAccountState(null);await startGuestMode();startWS('<p>Keep</p>','Keep','original')}")
        self.assertFalse(self.page.evaluate("saveStudioApp('Keep')"))
        self.assertIn('自動保存できません', self.page.locator('#studio-save-status').text_content())
        self.page.locator('#wsbar button[onclick="backToGallery()"]').click()
        self.assertTrue(self.page.locator('#view-gallery').evaluate("el=>el.classList.contains('active')"))

    def test_failed_write_keeps_newer_memory_work_when_old_database_is_readable(self):
        self.page.evaluate("""async()=>{
          await editMyApp('testID');
          await waitForLocalWrites([accountKey('draft'),accountKey('work_testID')]);
          var transaction=localDatabase.transaction.bind(localDatabase);
          localDatabase.transaction=(name,mode)=>{if(mode==='readwrite')throw Error('quota');return transaction(name,mode)};
          Storage.prototype.setItem=()=>{throw Error('quota')};
        }""")
        self.page.locator('#ct').fill('<h1>Newest work in memory</h1>')
        self.page.evaluate("async()=>{flushStudioDraft();await waitForLocalWrites([accountKey('draft'),accountKey('work_testID')]);backToGallery();await editMyApp('testID')}")
        self.assertEqual(self.page.locator('#ct').input_value(), '<h1>Newest work in memory</h1>')

    def test_legacy_work_migrates_without_losing_code_or_history(self):
        self.page.evaluate("""async()=>{
          localStorage.setItem(accountKey('draft'),JSON.stringify({version:1,code:'<h1>Legacy</h1>',
            title:'Legacy work',updatedAt:123,versions:[{id:1,code:'<h1>Before</h1>',label:'Before'}]}));
          await resetAccountState({uid:'test'});nav('studio');
          await waitForLocalWrites([accountKey('draft')]);
        }""")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>Legacy</h1>')
        self.assertIsNone(self.page.evaluate("localStorage.getItem(accountKey('draft'))"))
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState({uid:'test'});nav('studio')}")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>Legacy</h1>')
        self.assertEqual(self.page.evaluate('vers[0].code'), '<h1>Before</h1>')

    def test_large_code_saves_and_recovers_without_duplicate_history(self):
        self.page.evaluate("""async()=>{
          await resetAccountState(null);await startGuestMode();
          var code='<h1>Large app</h1><!--'+'x'.repeat(3*1024*1024)+'-->';
          document.getElementById('lp-code').value=code;
          vers=Array.from({length:10},(_,id)=>({id,code,label:'Large',type:'original'}));
          flushStudioDraft();await waitForLocalWrites([accountKey('draft')]);
        }""")
        self.assertEqual(self.page.evaluate("readLocalJson(accountKey('draft')).versions.length"), 1)
        self.assertLess(self.page.evaluate("JSON.stringify(readLocalJson(accountKey('draft')).versions).length"), 200)
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState(null);await startGuestMode()}")
        self.assertTrue(self.page.evaluate("document.getElementById('lp-code').value.startsWith('<h1>Large app</h1>')"))
        self.assertGreater(self.page.evaluate("document.getElementById('lp-code').value.length"), 3*1024*1024)
        self.assertEqual(self.page.evaluate("vers[0].code===document.getElementById('lp-code').value"), True)

    def test_pending_edit_does_not_reopen_after_navigating_away(self):
        self.page.evaluate("""()=>{
          window.hydrationFinished=accountStorageReady;
          accountStorageReady=new Promise(resolve=>{window.finishLoading=resolve});
          window.editing=editMyApp('testID');nav('gallery');finishLoading();
        }""")
        self.page.evaluate('editing')
        self.assertTrue(self.page.locator('#view-gallery').evaluate("el=>el.classList.contains('active')"))
        self.assertEqual(self.page.evaluate('editingAppId'), None)

    def test_changes_during_slow_cloud_save_are_recovered_on_next_edit(self):
        self.page.evaluate("""async()=>{
          nav('studio');startWS('<h1>First</h1>','Work','original');showCP();
          db={collection:()=>({doc:()=>({collection:()=>({doc:()=>({set:()=>new Promise(resolve=>{window.finishSave=resolve})})})})})};
          window.saving=saveStudioApp('Work');
        }""")
        self.page.wait_for_function("typeof finishSave==='function'")
        self.page.locator('#ct').fill('<h1>Changed while saving</h1>')
        self.page.evaluate("async()=>{flushStudioDraft();finishSave();await saving}")
        self.page.locator('#wsbar button[onclick="backToGallery()"]').click()
        self.page.evaluate('editMyApp(editingAppId)')
        self.assertEqual(self.page.locator('#ct').input_value(), '<h1>Changed while saving</h1>')

    def test_unmodified_snapshot_does_not_replace_newer_saved_code(self):
        self.page.evaluate("""async()=>{
          await editMyApp('testID');backToGallery();
          apps[0].code='<h1>Newer saved code</h1>';apps[0].savedAt=Date.now()+1000;
          nav('studio');
        }""")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>Newer saved code</h1>')
        self.page.evaluate("""async()=>{
          nav('gallery');
          await editMyApp('testID');
        }""")
        self.assertEqual(self.page.locator('#ct').input_value(), '<h1>Newer saved code</h1>')

    def test_legacy_fallback_survives_reload_when_indexeddb_is_blocked(self):
        self.page.add_init_script("indexedDB.open=()=>{throw Error('blocked')}")
        self.page.reload()
        self.page.evaluate(FIXTURE)
        self.page.evaluate("nav('studio')")
        self.page.locator('#lp-code').fill('<h1>Fallback work</h1>')
        self.page.wait_for_function("draftState==='saved'")
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState({uid:'test'});nav('studio')}")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>Fallback work</h1>')
