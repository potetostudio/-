"""Play the actual stored HTML, including nested HTML examples and wrappers."""
from html import escape
from test_studio import StudioBrowserCase

GAME = '''<!DOCTYPE html><html><head data-app="original"><style>button{margin-top:70px}</style><title>Real game</title></head><body>
<div id="game"></div><script>
const example = '<!DOCTYPE html><html><head><title>Export example</title></head><body>Example only</body></html>';
const other = '</body>';
document.getElementById('game').innerHTML='<button id="play" style="margin-top:70px">Start</button><span id="score">0</span>';
document.getElementById('play').onclick=()=>{document.getElementById('score').textContent='1';};
</script></body></html>'''


class PlaybackTests(StudioBrowserCase):
    def open_game(self, code, public=False):
        self.page.evaluate("""({code,public}) => {
          if(public){galleryTab='public';publicApps=[{_docId:'game',uid:'other',title:'Real game',code}];}
          else{galleryTab='my';apps=[{id:'game',urlId:'game',uid:'test',title:'Real game',code}];}
          renderGallery();
        }""", {'code':code,'public':public})
        self.page.locator('.gc-title',has_text='Real game').click()
        self.page.wait_for_function("document.getElementById('app-pv').srcdoc.length>0")
        return self.page.frame_locator('#app-pv')

    def test_my_and_public_games_with_html_templates_are_playable(self):
        for public in [False, True]:
            with self.subTest(public=public):
                frame=self.open_game(GAME,public)
                frame.locator('#play').click()
                self.assertEqual(frame.locator('#score').inner_text(),'1')
                self.assertTrue(self.page.locator('#app-playback-error').is_hidden())
                self.assertEqual(frame.locator('body').evaluate('el=>el.ownerDocument.compatMode'),'CSS1Compat')
                self.assertEqual(frame.locator('head').get_attribute('data-app'),'original')
                self.page.evaluate("galleryTab='my';nav('gallery')")

    def test_edit_and_play_execute_the_same_source(self):
        self.page.evaluate("code=>{apps=[{id:'game',urlId:'game',uid:'test',title:'Real game',code}];editMyApp('game')}",GAME)
        self.page.frame_locator('#sif').locator('#play').click()
        self.assertEqual(self.page.frame_locator('#sif').locator('#score').inner_text(),'1')
        self.page.evaluate("backToGallery();openApp('game')")
        self.page.frame_locator('#app-pv').locator('#play').click()
        self.assertEqual(self.page.frame_locator('#app-pv').locator('#score').inner_text(),'1')
        self.assertIn(GAME,self.page.locator('#ct').input_value())

    def test_fake_head_tag_in_javascript_is_not_an_injection_target(self):
        code='''<!doctype html><html><body><button id="play" style="margin-top:70px">Start</button><script>const sample='<head>example</head>';document.getElementById('play').onclick=()=>{document.body.dataset.played='yes';};</script></body></html>'''
        frame=self.open_game(code)
        frame.locator('#play').click()
        self.assertEqual(frame.locator('body').get_attribute('data-played'),'yes')

    def test_html_inside_comments_strings_and_textareas_is_preserved(self):
        code='''<!doctype html><!-- <!DOCTYPE html><html><body>Comment</body></html> -->
<html><head></head><body><textarea id="source">&lt;!DOCTYPE html&gt;&lt;body&gt;Example&lt;/body&gt;</textarea>
<button id="play" style="margin-top:70px">Play</button><script>const data='<!DOCTYPE html>example</body>';
document.getElementById('play').onclick=()=>{document.body.dataset.played='yes'};</script></body></html>'''
        self.assertEqual(self.page.evaluate('code=>normalizeGalleryPreviewCode(code)',code),code)
        frame=self.open_game(code,True)
        frame.locator('#play').click(timeout=2000)
        self.assertEqual(frame.locator('body').get_attribute('data-played'),'yes')
        self.assertIn('<!DOCTYPE html>',frame.locator('#source').input_value())

    def test_verified_legacy_wrapper_decodes_its_embedded_html(self):
        wrapper='<html><body><textarea id="code-area">'+escape(GAME)+'</textarea><iframe id="game-frame"></iframe><script>function runGame(){ URL.createObjectURL(new Blob([])); }</script></body></html>'
        self.assertEqual(self.page.evaluate('code=>normalizeGalleryPreviewCode(code)',wrapper),GAME)
        frame=self.open_game(wrapper)
        frame.locator('#play').click()
        self.assertEqual(frame.locator('#score').inner_text(),'1')

    def test_application_errors_are_visible_instead_of_a_silent_blank_page(self):
        frame=self.open_game('<!doctype html><html><head><script>throw new Error("game startup failed");</script></head><body></body></html>',True)
        panel=self.page.locator('#app-playback-error')
        panel.wait_for(state='visible')
        self.assertIn('game startup failed',self.page.locator('#app-playback-error-text').inner_text())
        self.assertEqual(self.page.locator('#app-pv').get_attribute('sandbox'),'allow-scripts allow-forms allow-pointer-lock')
        self.page.locator('button[onclick="reloadPlayingApp()"]').click()
        self.assertTrue(self.page.evaluate('playingAppCode.includes("game startup failed")'))
        self.page.locator('#app-playback-error-text').wait_for(state='visible')

    def test_unrelated_messages_and_previous_playback_errors_are_ignored(self):
        frame=self.open_game('<button id="play" style="margin-top:70px">Working</button>')
        frame.locator('#play').wait_for()
        self.page.evaluate("window.postMessage({type:'__poteto_err__',token:activePlaybackToken,msg:'fake'},'*')")
        self.assertTrue(self.page.locator('#app-playback-error').is_hidden())
        self.page.evaluate('window.oldPlaybackToken=activePlaybackToken;reloadPlayingApp()')
        self.page.wait_for_function('activePlaybackToken!==oldPlaybackToken')
        self.page.frame_locator('#app-pv').locator('#play').wait_for()
        self.page.locator('#app-pv').content_frame.locator('body').evaluate("el=>parent.postMessage({type:'__poteto_err__',token:'stale',msg:'old error'},'*')")
        self.assertTrue(self.page.locator('#app-playback-error').is_hidden())

    def test_empty_saved_code_shows_a_clear_message(self):
        self.page.evaluate("apps=[{id:'empty',title:'Empty',code:''}];openApp('empty')")
        self.assertTrue(self.page.locator('#app-playback-error').is_visible())
        self.assertIn('コードが保存されていません',self.page.locator('#app-playback-error-text').inner_text())

    def test_repeated_opening_renders_and_plays_after_returning_to_either_gallery(self):
        code='''<!doctype html><html><head></head><body><textarea>Example only</textarea><button id="play" style="margin-top:70px">Start</button><script>document.getElementById('play').onclick=()=>{document.body.dataset.played='yes'};</script></body></html>'''
        for public in [False, True, False, True]:
            frame=self.open_game(code,public)
            frame.locator('#play').click()
            self.assertEqual(frame.locator('body').get_attribute('data-played'),'yes')
            self.assertGreater(frame.locator('html').bounding_box()['width'],0)
            self.page.evaluate("galleryTab='my';goBack()")

    def test_canvas_game_renders_and_accepts_controls_from_both_galleries(self):
        code=self.page.evaluate("getTemplate('breakout')")
        for public in [False, True]:
            frame=self.open_game(code,public)
            canvas=frame.locator('canvas')
            canvas.wait_for(state='visible')
            self.assertGreater(canvas.bounding_box()['width'],0)
            canvas.click()
            self.page.keyboard.down('ArrowRight')
            self.assertEqual(canvas.evaluate('el=>window.pv'),7)
            self.page.keyboard.up('ArrowRight')
            self.assertGreater(canvas.evaluate("el=>el.getContext('2d').getImageData(0,0,1,1).data[3]"),0)
            self.assertTrue(self.page.locator('#app-playback-error').is_hidden())
            self.page.evaluate("galleryTab='my';goBack()")
