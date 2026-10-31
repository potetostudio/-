"""Meaningful names, real DOM/Canvas posters, and direct gallery navigation."""
from urllib.parse import unquote
from test_studio import StudioBrowserCase


class GalleryUITests(StudioBrowserCase):
    def test_pasted_html_title_becomes_work_and_draft_title(self):
        self.page.evaluate("nav('studio')")
        self.page.locator('#lp-code').fill('<!doctype html><title>星空パズル &amp; Moon</title><h1>Play</h1>')
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.assertEqual(self.page.locator('#shtitle').input_value(),'星空パズル & Moon')
        self.assertEqual(self.page.evaluate('vers[0].label'),'星空パズル & Moon')
        self.page.evaluate('flushStudioDraft()')
        self.assertEqual(self.page.evaluate("readLocalJson(accountKey('draft'),{}).title"),'星空パズル & Moon')
        self.page.reload()
        self.page.evaluate("resetAccountState({uid:'test'});nav('studio')")
        self.assertEqual(self.page.locator('#shtitle').input_value(),'星空パズル & Moon')

    def test_file_name_and_heading_are_used_without_generic_name(self):
        self.assertEqual(self.page.evaluate("inferAppTitle('<h1>Start</h1>','weather.html')"),'weather')
        self.assertEqual(self.page.evaluate("inferAppTitle('<title>Document</title><h1>My timer</h1>','index.html')"),'My timer')
        self.assertEqual(self.page.evaluate("inferAppTitle('console.log(1)','hello.js')"),'hello')
        self.assertEqual(self.page.evaluate("chooseWorkTitle('<title>Auto</title>','Custom title','')"),'Custom title')
        self.assertNotEqual(self.page.evaluate("chooseWorkTitle('console.log(1)','貼り付けコード','')"),'貼り付けコード')

    def test_old_generic_names_change_locally_and_custom_names_stay(self):
        self.page.evaluate("""() => {
          apps=[{id:'old',title:'貼り付けコード',code:'<title>Old game</title>'},
            {id:'named',title:'My chosen name',code:'<title>Different</title>'}];
          renderGallery();
        }""")
        self.assertEqual(self.page.evaluate('apps.map(a=>a.title)'),['Old game','My chosen name'])
        self.assertEqual(self.page.evaluate('Object.keys(store)'),[])
        self.assertEqual(self.page.evaluate("readLocalJson(accountKey('apps'),[])[0].title"),'Old game')

    def test_imported_file_title_is_used_and_explicit_rename_is_preserved(self):
        self.page.evaluate("nav('studio')")
        self.page.locator('#code-file-input').set_input_files({
            'name':'download.html','mimeType':'text/html','buffer':b'<title>Downloaded game</title><h1>Game</h1>'})
        self.page.wait_for_function("document.getElementById('lp-code').value.includes('Downloaded game')")
        self.page.locator('button[onclick="launchStudio()"]').click()
        self.assertEqual(self.page.locator('#shtitle').input_value(),'Downloaded game')
        self.page.evaluate("saveStudioApp('Renamed by me');editMyApp(editingAppId)")
        self.assertEqual(self.page.locator('#shtitle').input_value(),'Renamed by me')

    def test_gallery_shows_script_free_image_of_rendered_dom_and_canvas(self):
        self.page.evaluate("""() => {
          apps=[{id:'canvas',title:'Canvas app',code:'<!doctype html><html><head><style>body{background:rgb(20,40,80);color:white;margin:0}h1{margin:0}</style></head><body><h1>Canvas app</h1><canvas width="120" height="80"></canvas><script>var c=document.querySelector("canvas");var x=c.getContext("2d");x.fillStyle="red";x.fillRect(0,0,120,80);<\\/script></body></html>'}];
          nav('gallery');
        }""")
        self.page.wait_for_function("document.querySelector('.gc-preview')?.complete && document.querySelector('.gc-preview').naturalWidth>0")
        src=self.page.locator('.gc-preview').get_attribute('src')
        svg=unquote(src.split(',',1)[1])
        self.assertIn('Canvas app',svg)
        self.assertIn('data:image/png',svg)
        self.assertNotIn('<script',svg)
        self.assertEqual(self.page.locator('.gc-thumb iframe').count(),0)
        self.assertEqual(self.page.evaluate('galleryThumbnailJobs.size'),0)
        self.page.locator('.gc-preview').click()
        self.assertEqual(self.page.locator('#app-ttl').text_content(),'Canvas app')

    def test_cached_preview_is_reused_and_changes_invalidate_it(self):
        self.page.evaluate("apps=[{id:'app',title:'First',code:'<h1>First</h1>'}];nav('gallery')")
        self.page.wait_for_function("document.querySelector('.gc-preview')?.complete")
        before=self.page.locator('.gc-preview').get_attribute('src')
        self.page.evaluate('renderGallery()')
        self.assertEqual(self.page.locator('.gc-preview').get_attribute('src'),before)
        self.assertEqual(self.page.evaluate('galleryThumbnailJobs.size'),0)
        self.page.evaluate("apps[0].code='<h1>Second</h1>';renderGallery()")
        self.page.wait_for_function("document.querySelector('.gc-preview')?.complete")
        after=self.page.locator('.gc-preview').get_attribute('src')
        self.assertNotEqual(before,after)
        self.assertIn('Second',unquote(after.split(',',1)[1]))

    def test_thumbnail_sandbox_has_no_parent_access_or_api_key(self):
        self.page.evaluate("""() => {
          geminiKey='private-test-key';window.probe='safe';
          apps=[{id:'test',title:'Sandbox',code:'<h1>Safe</h1><script>try{parent.probe="unsafe"}catch(e){}<\\/script>'}];
          nav('gallery');
        }""")
        self.page.locator('.gc-preview-frame').wait_for(state='attached')
        frame=self.page.locator('.gc-preview-frame')
        self.assertEqual(frame.get_attribute('sandbox'),'allow-scripts')
        self.assertNotIn('private-test-key',frame.get_attribute('srcdoc'))
        self.assertIn("connect-src 'none'",frame.get_attribute('srcdoc'))
        self.page.wait_for_function("document.querySelector('.gc-preview')?.complete")
        self.assertEqual(self.page.evaluate('probe'),'safe')
        self.page.evaluate("resetAccountState({uid:'other'})")
        self.assertEqual(self.page.evaluate('galleryThumbnailCache.size'),0)

    def test_public_thumbnails_do_not_execute_published_scripts(self):
        self.page.evaluate("""() => {
          galleryTab='public';publicApps=[{_docId:'public',uid:'other',title:'Public',code:'<h1>Static view</h1><script>document.body.innerHTML="UNTRUSTED SCRIPT RAN";<\\/script>'}];
          renderGallery();
        }""")
        self.page.wait_for_function("document.querySelector('.gc-preview')?.complete")
        svg=unquote(self.page.locator('.gc-preview').get_attribute('src').split(',',1)[1])
        self.assertIn('Static view',svg)
        self.assertNotIn('UNTRUSTED SCRIPT RAN',svg)

    def test_editor_back_returns_directly_to_gallery_and_preserves_unsaved_draft(self):
        self.page.evaluate("""() => {
          apps=[{id:'edit',urlId:'edit',uid:'test',title:'Edit me',code:'<h1>Saved</h1>'}];editMyApp('edit');
        }""")
        self.page.locator('#ct').fill('<h1>Not saved to gallery</h1>')
        back=self.page.locator('#wsbar button[onclick="backToGallery()"]')
        self.assertIn('ギャラリーに戻る',back.inner_text())
        back.click()
        self.assertTrue(self.page.locator('#view-gallery').evaluate("el=>el.classList.contains('active')"))
        self.assertEqual(self.page.evaluate('apps[0].code'),'<h1>Saved</h1>')
        self.assertEqual(self.page.evaluate("readLocalJson(accountKey('draft'),{}).code"),'<h1>Not saved to gallery</h1>')
        self.assertEqual(self.page.locator('#sif').get_attribute('srcdoc'),'')
        self.assertFalse(self.page.locator('#app').evaluate("el=>el.classList.contains('game-active')"))
        self.page.evaluate("nav('studio')")
        self.assertEqual(self.page.locator('#lp-code').input_value(),'<h1>Not saved to gallery</h1>')

    def test_english_back_and_preview_messages(self):
        self.page.evaluate("setLanguage('en');nav('studio');startWS('<h1>Demo</h1>','Pasted code','original')")
        self.assertEqual(self.page.locator('#wsbar button[onclick="backToGallery()"] span').inner_text(),'Back to gallery')
        self.assertEqual(self.page.locator('#shtitle').input_value(),'Demo')

    def test_preview_parsing_never_fetches_external_images_or_runs_public_handlers(self):
        requests=[]
        self.page.on('request',lambda request: requests.append(request.url) if 'thumbnail-test.invalid' in request.url else None)
        self.page.evaluate("""() => {
          galleryTab='public';publicApps=[{_docId:'external',title:'Static',code:'<html><body style="background:teal" onload="document.body.textContent=\\'PUBLIC HANDLER RAN\\'"><h1>Static content</h1><img src="https://thumbnail-test.invalid/image.png" onerror="document.body.textContent=\\'PUBLIC HANDLER RAN\\'"></body></html>'}];renderGallery();
        }""")
        self.page.wait_for_function("document.querySelector('.gc-preview')?.complete")
        self.assertEqual(requests,[])
        svg=unquote(self.page.locator('.gc-preview').get_attribute('src').split(',',1)[1])
        self.assertIn('Static content',svg)
        self.assertNotIn('PUBLIC HANDLER RAN',svg)
        self.assertIn('background: teal',svg)

    def test_canvas_css_background_is_preserved_in_poster(self):
        self.page.evaluate("""() => {
          apps=[{id:'paint',title:'Paint',code:'<style>body{background:teal}canvas{background:white;display:block;border:2px solid red}</style><canvas width="200" height="100"></canvas>'}];nav('gallery');
        }""")
        self.page.wait_for_function("document.querySelector('.gc-preview')?.complete")
        svg=unquote(self.page.locator('.gc-preview').get_attribute('src').split(',',1)[1])
        self.assertIn('background-color: rgb(255, 255, 255)',svg)
        self.assertIn('border: 2px solid rgb(255, 0, 0)',svg)
        self.assertIn('data:image/png',svg)
