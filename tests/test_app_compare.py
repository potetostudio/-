"""Interactive isolated old/new previews and guarded updates of existing apps."""
from test_studio import StudioBrowserCase


OLD='''<!doctype html><title>Original</title><h1>Old app</h1><button id="count">0</button>
<canvas width="80" height="40"></canvas><script>
document.querySelector('#count').onclick=function(){this.textContent=Number(this.textContent)+1};
var c=document.querySelector('canvas');c.getContext('2d').fillRect(0,0,30,30);
try{parent.probe='unsafe'}catch(e){}
</script>'''
NEW=OLD.replace('Original','Replacement').replace('Old app','New app').replace('+1','+2')


class AppCompareTests(StudioBrowserCase):
    def setUp(self):
        super().setUp()
        self.page.evaluate("""code=>{
          apps[0].code=code;apps[0].createdAt=123;apps[0].likes=9;
          store['users/test/apps/testID']={code,isPublic:true};
          store['gallery/testID']={uid:'test',isPublic:true,code,likes:9};
          window.probe='safe';geminiKey='viewer-secret';nav('gallery');
        }""", OLD)

    def open_compare(self):
        self.page.locator('[data-app-id="testID"] .gc-more').click()
        self.page.get_by_role('menuitem',name='ファイルで更新・比較',exact=True).click()
        self.page.locator('#app-compare-dialog').wait_for(state='visible')

    def choose(self,code=NEW,name='new.html'):
        self.page.locator('#compare-file-input').set_input_files({
            'name':name,'mimeType':'text/plain','buffer':code.encode() if isinstance(code,str) else code})
        self.page.wait_for_function("!appComparisonSession.reading")

    def run_compare(self):
        self.page.locator('#compare-run').click()
        self.page.frame_locator('#compare-frame-old').locator('h1').wait_for()
        self.page.frame_locator('#compare-frame-new').locator('h1').wait_for()

    def test_both_apps_run_independently_without_parent_access_or_viewer_key(self):
        self.open_compare();self.choose()
        self.assertTrue(self.page.locator('#compare-apply').is_disabled())
        self.assertFalse(self.page.locator('#compare-frame-new').get_attribute('srcdoc'))
        self.assertEqual(self.page.evaluate('apps[0].code'),OLD)
        self.run_compare()
        old=self.page.frame_locator('#compare-frame-old');new=self.page.frame_locator('#compare-frame-new')
        self.assertEqual(old.locator('h1').inner_text(),'Old app')
        self.assertEqual(new.locator('h1').inner_text(),'New app')
        old.locator('#count').click();new.locator('#count').click()
        self.assertEqual(old.locator('#count').inner_text(),'1')
        self.assertEqual(new.locator('#count').inner_text(),'2')
        self.assertEqual(new.locator('canvas').evaluate("el=>el.getContext('2d').getImageData(2,2,1,1).data[3]"),255)
        self.assertEqual(self.page.evaluate('probe'),'safe')
        for side in ['old','new']:
            frame=self.page.locator('#compare-frame-'+side)
            self.assertEqual(frame.get_attribute('sandbox'),'allow-scripts allow-forms allow-pointer-lock')
            self.assertNotIn('viewer-secret',frame.get_attribute('srcdoc'))
        self.page.evaluate("restartComparisonPane('old')")
        self.assertEqual(old.locator('#count').inner_text(),'0')
        self.assertEqual(new.locator('#count').inner_text(),'2')
        self.assertEqual(self.page.evaluate('apps[0].code'),OLD)

    def test_update_keeps_id_name_creation_likes_pins_and_public_version(self):
        self.page.evaluate("async()=>{await editMyApp('testID');backToGallery()}")
        self.page.evaluate("toggleGalleryPin('testID')")
        self.open_compare();self.choose();self.run_compare()
        self.assertTrue(self.page.evaluate('applyAppComparison()'))
        self.assertFalse(self.page.locator('#app-compare-dialog').is_visible())
        self.assertEqual(self.page.evaluate('apps.length'),1)
        self.assertEqual(self.page.evaluate('apps[0].id'),'testID')
        self.assertEqual(self.page.evaluate('apps[0].title'),'Test app')
        self.assertEqual(self.page.evaluate('apps[0].createdAt'),123)
        self.assertEqual(self.page.evaluate('apps[0].likes'),9)
        self.assertEqual(self.page.evaluate('apps[0].code'),NEW)
        self.assertEqual(self.page.evaluate("store['users/test/apps/testID'].code"),NEW)
        self.assertTrue(self.page.evaluate("store['users/test/apps/testID'].isPublic"))
        self.assertEqual(self.page.evaluate("store['gallery/testID'].code"),OLD)
        self.assertEqual(self.page.evaluate('galleryPreferences.pinned'),['testID'])
        self.assertFalse(self.page.locator('#compare-frame-old').get_attribute('srcdoc'))
        self.page.evaluate("editMyApp('testID')")
        self.assertEqual(self.page.evaluate('code=>vers.find(version=>version.code===code).label',OLD),'更新前の保存版')

    def test_previous_saved_and_unapplied_work_are_recoverable_after_reload(self):
        self.page.evaluate("editMyApp('testID')")
        self.page.locator('#ct').fill('<h1>Unapplied work</h1>')
        self.page.evaluate("backToGallery()")
        self.open_compare();self.choose();self.run_compare()
        self.assertTrue(self.page.evaluate('applyAppComparison()'))
        self.page.evaluate("waitForLocalWrites([accountKey('apps'),accountKey('work_testID'),accountKey('before_update_testID'),accountKey('draft')])")
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState({uid:'test'});updateAuthGate();await editMyApp('testID')}")
        self.assertEqual(self.page.locator('#ct').input_value(),NEW)
        history=self.page.evaluate('vers.map(version=>version.code)')
        self.assertIn(OLD,history)
        self.assertIn('<h1>Unapplied work</h1>',history)
        self.page.evaluate('code=>restoreV(vers.findIndex(version=>version.code===code))',OLD)
        self.assertEqual(self.page.locator('#ct').input_value(),OLD)

    def test_close_and_navigation_cancel_stale_reads_and_stop_frames(self):
        self.open_compare();self.choose();self.run_compare()
        self.page.evaluate("""()=>{
          window.readingUpdate=readComparisonFiles([{name:'late.html',size:1,arrayBuffer:()=>new Promise(resolve=>{window.finishRead=resolve})}]);
        }""")
        self.assertTrue(self.page.locator('#compare-apply').is_disabled())
        self.page.evaluate("nav('studio');finishRead(new TextEncoder().encode('<h1>Late</h1>').buffer);readingUpdate")
        self.assertIsNone(self.page.evaluate('appComparisonSession'))
        self.assertFalse(self.page.locator('#compare-frame-old').get_attribute('srcdoc'))
        self.assertFalse(self.page.locator('#compare-frame-new').get_attribute('srcdoc'))
        self.assertEqual(self.page.evaluate('apps[0].code'),OLD)

    def test_invalid_files_do_not_modify_or_save_app(self):
        self.open_compare()
        for name,data in [('bad.zip',b'zip'),('empty.txt',b''),('binary.txt',b'a\0b'),('bad.txt',b'\xff'),('large.html',b'x'*(5*1024*1024+1))]:
            with self.subTest(name=name):
                self.choose(data,name)
                self.assertTrue(self.page.locator('#compare-file-status').evaluate("el=>el.classList.contains('comparison-error')"))
                self.assertTrue(self.page.locator('#compare-apply').is_disabled())
                self.assertEqual(self.page.evaluate('apps[0].code'),OLD)
        self.assertFalse(self.page.evaluate("readComparisonFiles([new File(['a'],'a.html'),new File(['b'],'b.html')])"))

    def test_failed_backup_blocks_replacement_without_changing_original(self):
        self.open_compare();self.choose();self.run_compare()
        self.page.evaluate("""async()=>{
          await openLocalDatabase();var transaction=localDatabase.transaction.bind(localDatabase);
          localDatabase.transaction=(name,mode)=>{if(mode==='readwrite')throw Error('quota');return transaction(name,mode)};
          Storage.prototype.setItem=()=>{throw Error('quota')};
        }""")
        self.assertFalse(self.page.evaluate('applyAppComparison()'))
        self.assertIn('更新前の版を保存できません',self.page.locator('#compare-result').inner_text())
        self.assertEqual(self.page.evaluate('apps[0].code'),OLD)
        self.assertEqual(self.page.evaluate("store['users/test/apps/testID'].code"),OLD)
        self.assertTrue(self.page.locator('#app-compare-dialog').is_visible())

    def test_cloud_retry_keeps_original_backup_and_reuses_same_app(self):
        self.open_compare();self.choose();self.run_compare()
        self.page.evaluate("failWrites='unavailable'")
        self.assertFalse(self.page.evaluate('applyAppComparison()'))
        self.assertEqual(self.page.evaluate('apps[0].code'),NEW)
        self.assertEqual(self.page.evaluate("readLocalJson(accountKey('before_update_testID')).code"),OLD)
        self.assertIn('保存を再試行',self.page.locator('#compare-apply').inner_text())
        self.page.evaluate('failWrites=false')
        self.assertTrue(self.page.evaluate('applyAppComparison()'))
        self.assertEqual(self.page.evaluate('apps.length'),1)
        self.assertEqual(self.page.evaluate("readLocalJson(accountKey('before_update_testID')).code"),OLD)

    def test_saved_code_conflict_and_deleted_app_cannot_be_overwritten(self):
        self.open_compare();self.choose();self.run_compare()
        self.page.evaluate("apps[0].code='<h1>Changed elsewhere</h1>'")
        self.assertFalse(self.page.evaluate('applyAppComparison()'))
        self.assertIn('保存版が変わりました',self.page.locator('#compare-result').inner_text())
        self.page.evaluate('apps=[]')
        self.assertFalse(self.page.evaluate('applyAppComparison()'))
        self.assertEqual(self.page.evaluate('apps'),[])
        self.assertEqual(self.page.evaluate("store['users/test/apps/testID'].code"),OLD)

    def test_pending_read_cannot_save_previous_candidate_and_latest_file_wins(self):
        self.open_compare();self.choose();self.run_compare()
        self.page.evaluate("""()=>{
          window.pending=readComparisonFiles([{name:'slow.html',size:1,arrayBuffer:()=>new Promise(resolve=>{window.finishRead=resolve})}]);
        }""")
        self.assertFalse(self.page.evaluate('applyAppComparison()'))
        self.choose('<!doctype html><h1>Latest</h1>','latest.html')
        self.page.evaluate("finishRead(new TextEncoder().encode('<h1>Stale</h1>').buffer);pending")
        self.assertIn('Latest',self.page.evaluate('appComparisonSession.candidate'))
        self.assertTrue(self.page.locator('#compare-apply').is_disabled())

    def test_runtime_error_is_reported_only_for_matching_frame_and_token(self):
        self.page.evaluate("setupErrCapture();lastError='Unrelated editor state'")
        self.open_compare();self.choose('<!doctype html><script>throw Error("New side error")</script>')
        self.page.locator('#compare-run').click()
        self.page.locator('#compare-error-new').wait_for(state='visible')
        self.assertIn('New side error',self.page.locator('#compare-error-new').inner_text())
        self.assertFalse(self.page.locator('#compare-error-old').is_visible())
        self.assertEqual(self.page.evaluate('lastError'),'Unrelated editor state')
        self.page.evaluate("window.postMessage({type:'__poteto_err__',token:'wrong',msg:'Forged'},'*')")
        self.assertNotIn('Forged',self.page.locator('#compare-error-new').inner_text())

    def test_pasted_code_and_mobile_equal_split_work_in_english(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.page.evaluate("setLanguage('en');openAppComparison('testID')")
        self.page.locator('#compare-paste-options summary').click()
        self.page.locator('#compare-code-input').fill(NEW)
        self.page.locator('#compare-paste-button').click()
        self.page.locator('#compare-paste-options summary').click()
        self.run_compare()
        self.assertEqual(self.page.locator('#compare-run').inner_text(),'Run side by side')
        old=self.page.locator('#compare-frame-old').bounding_box();new=self.page.locator('#compare-frame-new').bounding_box()
        self.assertAlmostEqual(old['width'],new['width'],delta=1)
        self.assertAlmostEqual(old['height'],new['height'],delta=1)
        self.assertAlmostEqual(old['y'],new['y'],delta=1)
        self.assertGreater(new['x'],old['x'])
        self.assertLessEqual(new['x']+new['width'],390)
        self.page.keyboard.press('Escape')
        self.assertFalse(self.page.locator('#app-compare-dialog').is_visible())

    def test_account_switch_cancels_read_and_clears_comparison_code(self):
        self.open_compare()
        self.page.evaluate("""()=>{
          window.pending=readComparisonFiles([{name:'old.html',size:1,arrayBuffer:()=>new Promise(resolve=>{window.finishRead=resolve})}]);
        }""")
        self.page.evaluate("async()=>{await resetAccountState({uid:'other'});finishRead(new TextEncoder().encode('<h1>Previous user</h1>').buffer);await pending}")
        self.assertIsNone(self.page.evaluate('appComparisonSession'))
        self.assertFalse(self.page.locator('#app-compare-dialog').is_visible())
        self.assertEqual(self.page.locator('#compare-code-input').input_value(),'')
        self.assertEqual(self.page.evaluate('apps'),[])

    def test_foreign_app_cannot_be_opened(self):
        self.page.evaluate("apps[0].uid='another-user'")
        self.assertFalse(self.page.evaluate("openAppComparison('testID')"))
        self.assertFalse(self.page.locator('#app-compare-dialog').is_visible())

    def test_guest_large_previous_version_survives_update_and_reload_untruncated(self):
        large='<!doctype html><h1>Large previous app</h1><!--'+'x'*350000+'-->'
        self.page.evaluate("""async code=>{
          await resetAccountState(null);await startGuestMode();
          apps=[{id:'guest',title:'Guest app',code}];persistApps();nav('gallery');await openAppComparison('guest');
        }""",large)
        self.choose();self.run_compare()
        self.assertTrue(self.page.evaluate('applyAppComparison()'))
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState(null);await startGuestMode();await editMyApp('guest')}")
        self.assertEqual(self.page.locator('#ct').input_value(),NEW)
        self.assertTrue(self.page.evaluate('code=>vers.some(version=>version.code===code)',large))
        self.assertEqual(self.page.evaluate('apps.length'),1)

    def test_drop_stages_file_and_paste_edits_require_reload_before_saving(self):
        self.open_compare()
        self.page.locator('#compare-file-zone').evaluate("""zone=>{
          var files=new DataTransfer();files.items.add(new File(['<!doctype html><h1>Dropped</h1>'],'drop.html',{type:'text/html'}));
          var event=new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:files});zone.dispatchEvent(event);
          window.dropHandled=event.defaultPrevented;
        }""")
        self.page.wait_for_function("appComparisonSession.fileName==='drop.html'")
        self.assertTrue(self.page.evaluate('dropHandled'))
        self.assertFalse(self.page.locator('#compare-frame-new').get_attribute('srcdoc'))
        self.run_compare()
        self.page.locator('#compare-paste-options summary').click()
        self.page.locator('#compare-code-input').fill('<h1>Not loaded yet</h1>')
        self.assertTrue(self.page.locator('#compare-apply').is_disabled())
        self.assertFalse(self.page.evaluate('applyAppComparison()'))
        self.assertEqual(self.page.evaluate('apps[0].code'),OLD)
        self.page.locator('#compare-paste-button').click()
        self.assertTrue(self.page.locator('#compare-apply').is_disabled())
        self.page.locator('#compare-run').click()
        self.assertFalse(self.page.locator('#compare-apply').is_disabled())

    def test_closing_and_reopening_compares_fresh_frames(self):
        for expected in ['First replacement','Second replacement']:
            self.open_compare();self.choose('<!doctype html><h1>'+expected+'</h1>');self.run_compare()
            self.assertEqual(self.page.frame_locator('#compare-frame-new').locator('h1').inner_text(),expected)
            self.page.keyboard.press('Escape')
            self.assertIsNone(self.page.evaluate('appComparisonSession'))
        self.assertEqual(self.page.evaluate('apps[0].code'),OLD)

    def test_slow_save_cannot_restore_previous_account_ui(self):
        self.open_compare();self.choose();self.run_compare()
        self.page.evaluate("""()=>{
          db={collection:()=>({doc:()=>({collection:()=>({doc:()=>({set:()=>new Promise(resolve=>{window.finishSave=resolve})})})})})};
          window.savingUpdate=applyAppComparison();
        }""")
        self.page.wait_for_function("typeof finishSave==='function'")
        self.page.evaluate("async()=>{await resetAccountState({uid:'other'});messages=[];finishSave();await savingUpdate}")
        self.assertEqual(self.page.evaluate('apps'),[])
        self.assertEqual(self.page.evaluate('messages'),[])
        self.assertIsNone(self.page.evaluate('appComparisonSession'))
        self.assertEqual(self.page.locator('#compare-app-title').inner_text(),'')
