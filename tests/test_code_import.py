"""Local code file import through real browser file APIs and drop events."""
from test_studio import StudioBrowserCase


class CodeImportTests(StudioBrowserCase):
    def setUp(self):
        super().setUp()
        self.page.evaluate("nav('studio')")

    def choose(self, name, source, mime='text/plain'):
        self.page.locator('#code-file-input').set_input_files({
            'name': name, 'mimeType': mime,
            'buffer': source.encode() if isinstance(source, str) else source,
        })
        self.page.wait_for_function("!document.getElementById('code-file-status').textContent.startsWith('ファイルを読み込み中: ')")

    def test_picker_imports_utf8_without_running_or_saving(self):
        code = '<!DOCTYPE html><html><body><h1>こんにちは</h1></body></html>'
        self.choose('claude.HTML', '\ufeff'+code, 'application/octet-stream')
        self.assertEqual(self.page.locator('#lp-code').input_value(), code)
        self.assertIn('claude.HTML', self.page.locator('#code-file-status').inner_text())
        self.assertEqual(self.page.evaluate('Object.keys(store)'), [])
        self.assertEqual(self.page.locator('#sif').get_attribute('srcdoc'), None)
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.page.frame_locator('#sif').locator('h1').wait_for()
        self.assertEqual(self.page.frame_locator('#sif').locator('h1').inner_text(), 'こんにちは')

    def test_drop_into_textarea_imports_file_and_stays_on_page(self):
        self.page.locator('#lp-code').evaluate("""el => {
          const data = new DataTransfer();
          data.items.add(new File(['<h1>Dropped app</h1>'], 'app.html', {type:'text/html'}));
          el.dispatchEvent(new DragEvent('dragover', {bubbles:true,cancelable:true,dataTransfer:data}));
          window.wasHighlighted=document.getElementById('code-drop-zone').classList.contains('drag');
          const drop=new DragEvent('drop', {bubbles:true,cancelable:true,dataTransfer:data});
          el.dispatchEvent(drop);
          window.dropPrevented=drop.defaultPrevented;
        }""")
        self.page.wait_for_function("document.getElementById('lp-code').value.includes('Dropped app')")
        self.assertTrue(self.page.evaluate('wasHighlighted && dropPrevented'))
        self.assertFalse(self.page.locator('#code-drop-zone').evaluate("el=>el.classList.contains('drag')"))
        self.assertEqual(self.page.url, 'http://studio.test/')

    def test_replace_cancel_and_confirm_and_same_file_reselection(self):
        self.page.locator('#lp-code').fill('existing code')
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        self.choose('app.html', '<h1>New</h1>')
        self.assertEqual(self.page.locator('#lp-code').input_value(), 'existing code')
        self.assertEqual(self.page.locator('#code-file-input').input_value(), '')
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.choose('app.html', '<h1>New</h1>')
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>New</h1>')
        self.choose('app.html', '<h1>New</h1>')
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>New</h1>')

    def test_invalid_files_preserve_existing_input(self):
        self.page.locator('#lp-code').fill('keep me')
        for name, data in [('archive.zip', b'zip'), ('empty.txt', b''),
                           ('binary.txt', b'a\x00b'), ('invalid.txt', b'\xff\xfe'),
                           ('large.html', b'a'*(5*1024*1024+1))]:
            with self.subTest(name=name):
                self.choose(name, data)
                self.assertEqual(self.page.locator('#lp-code').input_value(), 'keep me')
                self.assertIn('error', self.page.locator('#code-file-status').get_attribute('class'))
        self.assertFalse(self.page.evaluate("importCodeFiles([new File(['a'],'a.html'),new File(['b'],'b.html')])"))
        self.assertEqual(self.page.locator('#lp-code').input_value(), 'keep me')

    def test_plain_javascript_executes_only_after_run(self):
        self.choose('hello.js', 'console.log("File script ran")', 'text/javascript')
        self.assertEqual(self.page.evaluate('Object.keys(store)'), [])
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.page.wait_for_function("document.getElementById('sif').srcdoc.includes('File script ran')")
        self.assertIn('File script ran', self.page.frame_locator('#sif').locator('#out').inner_text())

    def test_css_runs_and_can_be_reopened_without_double_wrapping(self):
        self.choose('theme.css', 'body { background: rgb(12, 34, 56); }', 'text/css')
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.page.wait_for_function("document.getElementById('sif').srcdoc.includes('<style>body')")
        body = self.page.frame_locator('#sif').locator('body')
        self.assertEqual(body.evaluate('el=>getComputedStyle(el).backgroundColor'), 'rgb(12, 34, 56)')
        self.page.evaluate('backToStudio()')
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.assertEqual(self.page.evaluate("cur.match(/<!DOCTYPE html>/g).length"), 1)
        self.assertEqual(body.evaluate('el=>getComputedStyle(el).backgroundColor'), 'rgb(12, 34, 56)')

    def test_english_labels_status_and_filename_are_plain_text(self):
        self.page.evaluate("setLanguage('en')")
        self.assertEqual(self.page.locator('#code-file-button').inner_text(), 'Choose file')
        self.choose('<img onerror=alert(1)>.txt', '<p>保存</p>')
        self.assertEqual(self.page.locator('#code-file-status').inner_text(), 'Imported: <img onerror=alert(1)>.txt')
        self.assertEqual(self.page.locator('#code-file-status img').count(), 0)
        self.page.evaluate("setLanguage('ja')")
        self.assertEqual(self.page.locator('#code-file-status').inner_text(), '読み込み済み: <img onerror=alert(1)>.txt')
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<p>保存</p>')

    def test_failed_read_and_stale_read_preserve_current_state(self):
        self.assertFalse(self.page.evaluate("importCodeFiles([{name:'bad.txt',size:1,arrayBuffer:async()=>{throw new Error('unreadable')}}])"))
        self.assertEqual(self.page.locator('#lp-code').input_value(), '')
        self.page.evaluate("""() => {
          window.pendingImport=importCodeFiles([{name:'old.html',size:1,
            arrayBuffer:()=>new Promise(resolve=>{window.finishRead=resolve})}]);
        }""")
        self.choose('new.html', '<h1>Newest</h1>')
        self.page.evaluate("finishRead(new TextEncoder().encode('<h1>Old</h1>').buffer); pendingImport")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<h1>Newest</h1>')
        self.assertIn('new.html', self.page.locator('#code-file-status').inner_text())

    def test_javascript_html_strings_do_not_terminate_script(self):
        self.choose('strings.js', 'console.log("<script>example</script>")')
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.assertIn('<script>example</script>', self.page.frame_locator('#sif').locator('#out').inner_text())

    def test_reset_cancels_pending_file_read(self):
        self.page.evaluate("""() => {
          window.pendingImport=importCodeFiles([{name:'old.html',size:1,
            arrayBuffer:()=>new Promise(resolve=>{window.finishRead=resolve})}]);
          resetS();
        }""")
        self.page.evaluate("finishRead(new TextEncoder().encode('<p>Old</p>').buffer); pendingImport")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '')
        self.assertEqual(self.page.locator('#code-file-status').text_content(), '')

    def test_clear_stays_empty_after_navigation_and_reload(self):
        self.page.locator('#lp-code').fill('<h1>Old recovered code</h1>')
        self.page.wait_for_function("draftState==='saved'")
        self.page.locator('#lp-code').fill('<h1>Newer input with autosave pending</h1>')
        self.page.locator('#code-clear-button').click()
        self.assertEqual(self.page.locator('#lp-code').input_value(), '')
        self.assertTrue(self.page.locator('#lp-code').evaluate('el=>el===document.activeElement'))
        self.page.evaluate("nav('gallery');nav('studio')")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '')
        self.page.evaluate("waitForLocalWrites([accountKey('draft')])")
        self.page.reload()
        self.page.evaluate("async()=>{await resetAccountState({uid:'test'});nav('studio')}")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '')

    def test_clear_detaches_existing_app_before_replacement_is_saved(self):
        self.page.evaluate("async()=>{await editMyApp('testID');backToGallery();nav('studio')}")
        self.assertEqual(self.page.evaluate('editingAppId'), 'testID')
        self.page.locator('#code-clear-button').click()
        self.page.locator('#lp-code').fill('<h1>Replacement app</h1>')
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.assertEqual(self.page.frame_locator('#sif').locator('h1').inner_text(), 'Replacement app')
        self.assertEqual(self.page.locator('#shtitle').input_value(), 'Replacement app')
        self.assertTrue(self.page.evaluate("saveStudioApp('Replacement app')"))
        self.assertNotEqual(self.page.evaluate('editingAppId'), 'testID')
        self.assertEqual(self.page.evaluate("apps.find(app=>app.id==='testID').code"), '<h1>Saved code</h1>')
        self.assertEqual(self.page.evaluate('apps.length'), 2)

    def test_clear_cancels_pending_import_and_resets_file_type_in_both_languages(self):
        self.choose('theme.css', 'body { color:red }')
        self.page.evaluate("""()=>{
          window.pendingImport=importCodeFiles([{name:'old.html',size:1,
            arrayBuffer:()=>new Promise(resolve=>{window.finishRead=resolve})}]);
          setLanguage('en');
        }""")
        self.assertEqual(self.page.locator('#code-clear-button').inner_text(), 'Clear all code')
        self.page.locator('#code-clear-button').click()
        self.page.evaluate("finishRead(new TextEncoder().encode('<h1>Late file</h1>').buffer);pendingImport")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '')
        self.assertEqual(self.page.evaluate('codeInputFileName'), '')
        self.assertEqual(self.page.locator('#code-file-status').inner_text(), 'All code cleared')
        self.page.evaluate("setLanguage('ja')")
        self.assertEqual(self.page.locator('#code-clear-button').inner_text(), 'コードをすべて削除')
        self.assertEqual(self.page.locator('#code-file-status').inner_text(), 'コードをすべて削除しました')
        self.page.locator('#lp-code').fill('<h1>New HTML</h1>')
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.assertEqual(self.page.frame_locator('#sif').locator('h1').inner_text(), 'New HTML')
