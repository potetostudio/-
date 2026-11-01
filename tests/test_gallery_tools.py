"""Undo, independent private duplicates, and account-scoped gallery organization."""
from test_studio import StudioBrowserCase


class GalleryToolsTests(StudioBrowserCase):
    def titles(self):
        return self.page.locator('#gg .gc-title').all_text_contents()

    def seed_gallery(self):
        self.page.evaluate("""()=>{
          apps=[
            {id:'a',title:'Alpha',code:'<h1>A</h1>',createdAt:100,updatedAt:300},
            {id:'b',title:'Beta',code:'<h1>B</h1>',createdAt:300,updatedAt:200},
            {id:'c',title:'Charlie',code:'<h1>C</h1>',createdAt:200,updatedAt:100}];
          nav('gallery');
        }""")

    def test_undo_restores_code_file_type_and_durable_work_without_running(self):
        self.page.evaluate("nav('studio')")
        self.page.locator('#code-file-input').set_input_files({
            'name':'theme.css','mimeType':'text/css','buffer':b'body{background:red}'})
        self.page.wait_for_function("codeInputFileName==='theme.css'")
        self.page.locator('#code-clear-button').click()
        self.assertEqual(self.page.locator('#lp-code').input_value(), '')
        self.page.locator('#code-clear-button').click()
        self.page.locator('#code-undo-button').click()
        self.assertEqual(self.page.locator('#lp-code').input_value(), 'body{background:red}')
        self.assertEqual(self.page.evaluate('codeInputFileName'), 'theme.css')
        self.assertFalse(self.page.locator('#code-undo-button').is_visible())
        self.assertFalse(self.page.locator('#sif').get_attribute('srcdoc'))
        self.page.evaluate("waitForLocalWrites([accountKey('draft')])")
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState({uid:'test'});updateAuthGate();nav('studio')}")
        self.assertEqual(self.page.evaluate('codeInputFileName'), 'theme.css')
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.assertEqual(self.page.frame_locator('#sif').locator('body').evaluate('el=>getComputedStyle(el).backgroundColor'), 'rgb(255, 0, 0)')

    def test_undo_restores_existing_edit_target_and_versions(self):
        self.page.evaluate("async()=>{await editMyApp('testID');backToGallery();nav('studio')}")
        before=self.page.evaluate('vers')
        self.page.locator('#code-clear-button').click()
        self.page.locator('#code-undo-button').click()
        self.assertEqual(self.page.evaluate('editingAppId'), 'testID')
        self.assertEqual(self.page.evaluate('vers'), before)
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.assertTrue(self.page.evaluate("saveStudioApp('Original work')"))
        self.assertEqual(self.page.evaluate('apps.length'), 1)

    def test_new_input_and_account_switch_invalidate_undo(self):
        self.page.evaluate("nav('studio')")
        self.page.locator('#lp-code').fill('Old input')
        self.page.locator('#code-clear-button').click()
        self.page.locator('#lp-code').fill('Replacement')
        self.assertFalse(self.page.locator('#code-undo-button').is_visible())
        self.page.evaluate('undoCodeClear()')
        self.assertEqual(self.page.locator('#lp-code').input_value(), 'Replacement')
        self.page.locator('#code-clear-button').click()
        self.page.evaluate("async()=>{await resetAccountState({uid:'other'});nav('studio');undoCodeClear()}")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '')
        self.assertIsNone(self.page.evaluate('codeClearUndo'))

    def test_import_after_clear_discards_undo(self):
        self.page.evaluate("nav('studio')")
        self.page.locator('#lp-code').fill('<h1>Old</h1>')
        self.page.locator('#code-clear-button').click()
        self.page.locator('#code-file-input').set_input_files({
            'name':'new.html','mimeType':'text/html','buffer':b'<h1>New file</h1>'})
        self.page.wait_for_function("codeInputFileName==='new.html'")
        self.assertFalse(self.page.locator('#code-undo-button').is_visible())
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>New file</h1>')

    def test_duplicate_button_creates_new_private_app_and_editing_keeps_original(self):
        self.page.evaluate("""()=>{
          apps[0].likes=7;store['gallery/testID']={uid:'test',isPublic:true,likes:7,code:apps[0].code};
          nav('gallery');
        }""")
        self.page.locator('[data-app-id="testID"] .gc-more').click()
        self.page.get_by_role('menuitem',name='複製する',exact=True).click()
        self.page.wait_for_function("apps.length===2 && !apps[1].pendingCloud")
        copy_id=self.page.evaluate('apps[1].id')
        self.assertNotEqual(copy_id, 'testID')
        self.assertEqual(self.page.evaluate('apps[1].title'), 'Test appのコピー')
        self.assertEqual(self.page.evaluate('apps[1].likes'), 0)
        self.assertEqual(self.page.evaluate('apps[1].code'), '<h1>Saved code</h1>')
        self.assertEqual(self.page.evaluate('editingAppId'), None)
        self.assertTrue(self.page.locator('#view-gallery').is_visible())
        self.page.evaluate('id=>editMyApp(id)', copy_id)
        self.page.locator('#ct').fill('<h1>Copy edited</h1>')
        self.assertTrue(self.page.evaluate('saveCurrentWork()'))
        self.assertEqual(self.page.evaluate('apps[0].code'), '<h1>Saved code</h1>')
        self.assertEqual(self.page.evaluate("store['gallery/testID'].code"), '<h1>Saved code</h1>')
        self.assertEqual(self.page.evaluate("Object.keys(store).filter(key=>key.startsWith('gallery/'))"), ['gallery/testID'])

    def test_repeated_duplicates_have_unique_names_and_respect_length(self):
        self.page.evaluate("apps[0].title='A'.repeat(100);setLanguage('en')")
        self.assertTrue(self.page.evaluate("duplicateMyApp('testID')"))
        self.assertTrue(self.page.evaluate("duplicateMyApp('testID')"))
        names=self.page.evaluate('apps.map(app=>app.title)')
        self.assertEqual(len(set(names)), 3)
        self.assertTrue(names[1].endswith(' (copy)'))
        self.assertTrue(names[2].endswith(' (copy) 2'))
        self.assertTrue(all(len(name)<=100 for name in names))

    def test_failed_duplicate_cloud_save_retains_copy_and_retries_same_id(self):
        self.page.evaluate("failWrites='unavailable'")
        self.assertFalse(self.page.evaluate("duplicateMyApp('testID')"))
        self.assertEqual(self.page.evaluate('apps.length'), 2)
        self.assertTrue(self.page.evaluate('apps[1].pendingCloud'))
        copy_id=self.page.evaluate('apps[1].id')
        self.page.evaluate('failWrites=false')
        self.assertTrue(self.page.evaluate('retryLastCloudSave()'))
        self.assertEqual(self.page.evaluate('apps.length'), 2)
        self.assertEqual(self.page.evaluate('apps[1].id'), copy_id)
        self.assertFalse(self.page.evaluate('apps[1].pendingCloud'))
        self.assertTrue(self.page.evaluate('key=>!!store["users/test/apps/"+key]', copy_id))

    def test_guest_duplicate_survives_reload(self):
        self.page.evaluate("""async()=>{
          await resetAccountState(null);await startGuestMode();
          apps=[{id:'guest',title:'Guest',code:'<h1>Guest</h1>'}];nav('gallery');
          await duplicateMyApp('guest');
        }""")
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState(null);await startGuestMode();nav('gallery')}")
        self.assertEqual(self.page.evaluate('apps.length'), 2)
        self.assertEqual(set(self.page.evaluate('apps.map(app=>app.title)')), {'Guest','Guestのコピー'})

    def test_slow_duplicate_double_click_and_account_switch_are_safe(self):
        self.page.evaluate("""()=>{
          db={collection:()=>({doc:()=>({collection:()=>({doc:()=>({set:()=>new Promise(resolve=>{window.finishSave=resolve})})})})})};
          window.firstCopy=duplicateMyApp('testID');window.secondCopy=duplicateMyApp('testID');
        }""")
        self.page.wait_for_function("typeof finishSave==='function'")
        self.assertEqual(self.page.evaluate('apps.length'), 2)
        self.assertFalse(self.page.evaluate('secondCopy'))
        self.page.evaluate("async()=>{await resetAccountState({uid:'other'});messages=[];finishSave();await firstCopy}")
        self.assertEqual(self.page.evaluate('apps'), [])
        self.assertEqual(self.page.evaluate('messages'), [])

    def test_sorting_pins_and_search_do_not_mutate_saved_array_order(self):
        self.seed_gallery()
        self.assertEqual(self.titles(), ['Alpha','Beta','Charlie'])
        self.page.locator('#gallery-sort').select_option('created')
        self.assertEqual(self.titles(), ['Beta','Charlie','Alpha'])
        self.page.locator('#gallery-sort').select_option('name')
        self.assertEqual(self.titles(), ['Alpha','Beta','Charlie'])
        self.page.locator('[data-app-id="c"] .gc-pin').click()
        self.assertEqual(self.titles(), ['Charlie','Alpha','Beta'])
        self.assertEqual(self.page.locator('[data-app-id="c"] .gc-pin').get_attribute('aria-pressed'), 'true')
        self.page.locator('#skw').fill('Alpha')
        self.assertEqual(self.titles(), ['Alpha'])
        self.page.locator('#skw').fill('')
        self.page.locator('[data-app-id="c"] .gc-pin').click()
        self.assertEqual(self.titles(), ['Alpha','Beta','Charlie'])
        self.assertEqual(self.page.evaluate('apps.map(app=>app.id)'), ['a','b','c'])
        self.assertEqual(self.page.evaluate('Object.keys(store)'), [])

    def test_preferences_survive_reload_and_are_separate_per_account(self):
        self.page.evaluate("async()=>{await resetAccountState({uid:'test'})}")
        self.seed_gallery()
        self.page.evaluate("persistApps();setGallerySort('name');toggleGalleryPin('c');waitForLocalWrites([accountKey('apps'),accountKey('gallery')])")
        self.page.evaluate("async()=>{await resetAccountState({uid:'other'});nav('gallery')}")
        self.assertEqual(self.page.evaluate('galleryPreferences'), {'sort':'updated','pinned':[]})
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState({uid:'test'});nav('gallery')}")
        self.assertEqual(self.page.locator('#gallery-sort').input_value(), 'name')
        self.assertEqual(self.titles(), ['Charlie','Alpha','Beta'])

    def test_saved_updates_and_cloud_refresh_reorder_without_losing_pins(self):
        self.seed_gallery()
        self.page.evaluate("toggleGalleryPin('b')")
        self.page.evaluate("editMyApp('c')")
        self.page.locator('#ct').fill('<h1>Updated C</h1>')
        self.assertTrue(self.page.evaluate('saveCurrentWork()'))
        self.page.evaluate('backToGallery()')
        self.assertEqual(self.titles(), ['Beta','Charlie','Alpha'])
        self.page.evaluate("""async()=>{
          cloudDocs=[{id:'a',data:()=>({label:'Alpha',code:'<h1>New cloud</h1>',updatedAt:new Date(Date.now()+5000)})}];
          await loadUserApps();
        }""")
        self.assertEqual(self.titles(), ['Beta','Alpha','Charlie'])

    def test_creation_order_survives_cloud_cache_rebuild_after_editing(self):
        self.seed_gallery()
        self.page.evaluate("editMyApp('a')")
        self.page.locator('#ct').fill('<h1>Recently edited Alpha</h1>')
        self.assertTrue(self.page.evaluate('saveCurrentWork()'))
        self.assertEqual(self.page.evaluate("store['users/test/apps/a'].createdAt.getTime()"), 100)
        self.page.evaluate("""async()=>{
          cloudDocs=[{id:'a',data:()=>store['users/test/apps/a']},
            {id:'b',data:()=>({label:'Beta',code:'<h1>B</h1>',createdAt:new Date(300),updatedAt:new Date(50)})}];
          apps=[];await loadUserApps();backToGallery();setGallerySort('created');
        }""")
        self.assertEqual(self.titles(), ['Beta','Alpha'])
        self.page.locator('#gallery-sort').select_option('updated')
        self.assertEqual(self.titles(), ['Alpha','Beta'])

    def test_public_cards_do_not_get_private_actions_and_foreign_ids_are_rejected(self):
        self.page.evaluate("""()=>{
          apps=[{id:'foreign',uid:'another',title:'Foreign',code:'secret'}];
          galleryTab='public';publicApps=[{_docId:'public',uid:'another',title:'Public',code:'<h1>Public</h1>'}];renderGallery();
        }""")
        self.assertFalse(self.page.locator('#gallery-sort-control').is_visible())
        self.assertEqual(self.page.locator('.gc-pin,.gc-duplicate').count(), 0)
        self.assertFalse(self.page.evaluate("duplicateMyApp('foreign')"))
        self.page.evaluate("toggleGalleryPin('foreign')")
        self.assertEqual(self.page.evaluate('galleryPreferences.pinned'), [])
        self.assertEqual(self.page.evaluate('Object.keys(store)'), [])

    def test_my_sort_control_is_hidden_during_public_loading(self):
        self.seed_gallery()
        self.page.evaluate("""()=>{
          db={collection:()=>({where:()=>({limit:()=>({get:()=>new Promise(resolve=>{window.finishPublicLoad=resolve})})})})};
          switchGalleryTab('public');
        }""")
        self.assertFalse(self.page.locator('#gallery-sort-control').is_visible())
        self.page.evaluate("finishPublicLoad({forEach(){}})")
        self.page.wait_for_function("document.getElementById('g-empty').style.display==='block'")
        self.page.evaluate("switchGalleryTab('my')")
        self.assertTrue(self.page.locator('#gallery-sort-control').is_visible())

    def test_mobile_controls_fit_and_labels_switch_language(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.seed_gallery()
        self.page.evaluate("setLanguage('en')")
        self.assertEqual(self.page.locator('#gallery-sort option:checked').inner_text(), 'Recently updated')
        self.page.locator('[data-app-id="a"] .gc-more').click()
        self.assertEqual(self.page.get_by_role('menuitem',name='Duplicate',exact=True).inner_text(), 'Duplicate')
        self.page.keyboard.press('Escape')
        self.page.locator('[data-app-id="a"] .gc-pin').click()
        self.assertEqual(self.page.locator('[data-app-id="a"] .gc-pin').get_attribute('aria-label'), 'Unpin')
        self.assertTrue(self.page.locator('#view-gallery').is_visible())
        self.assertTrue(self.page.locator('.gc').first.evaluate("card=>Array.from(card.querySelectorAll('.gc-actions button')).every(button=>button.getBoundingClientRect().right<=card.getBoundingClientRect().right)"))
        self.assertTrue(self.page.locator('#gallery-sort').is_visible())
        self.page.evaluate("nav('studio')")
        self.page.locator('#lp-code').fill('Undo me')
        self.page.locator('#code-clear-button').click()
        self.assertEqual(self.page.locator('#code-undo-button').inner_text(), 'Undo')
