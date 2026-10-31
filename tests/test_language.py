"""UI localization regressions, sharing the offline browser fixture."""
from test_studio import StudioBrowserCase, HTML


class LanguageTests(StudioBrowserCase):
    # Reuse browser setup, not the inherited regression cases.
    def test_language_picker_is_available_before_login_and_persists(self):
        self.page.evaluate('curUser = null; updateAuthGate()')
        self.assertEqual(self.page.locator('html').get_attribute('lang'), 'ja')
        picker = self.page.locator('#auth-gate [data-language-select]')
        picker.select_option('en')
        self.assertEqual(self.page.locator('html').get_attribute('lang'), 'en')
        self.assertEqual(self.page.locator('#auth-gate button[onclick="doLogin()"]').inner_text(), 'Log in')
        self.assertEqual(self.page.locator('#auth-gate-pw').get_attribute('placeholder'), 'At least 6 characters')
        self.page.reload()
        self.assertEqual(self.page.locator('html').get_attribute('lang'), 'en')
        self.assertEqual(picker.input_value(), 'en')
        self.page.locator('#auth-gate button[onclick="doLogin()"]').click()
        self.assertEqual(self.page.locator('#auth-gate-err').inner_text(), 'Enter your email address and password.')
        picker.select_option('ja')
        self.assertEqual(self.page.locator('#auth-gate-err').inner_text(), 'メールアドレスとパスワードを入力してください。')
        self.assertEqual(self.page.evaluate("localStorage.getItem('pt_language')"), 'ja')

    def test_switch_preserves_user_data_code_and_ai_prompts(self):
        before = self.page.evaluate("""() => {
          nav('studio');
          document.getElementById('lp-code').value = '<p>保存</p>';
          apps = [{id:'user',urlId:'user',title:'保存',code:'<p>日本語</p>'}];
          addChatMsg('user','日本語のメッセージ');
          cvOllamaMessages = [{role:'user',content:'日本語の指示'}];
          return {code:cur,system:WS_CHAT_SYSTEM,template:getTemplate('timer')};
        }""")
        self.page.evaluate("setLanguage('en')")
        self.assertEqual(self.page.locator('#lp-code').input_value(), '<p>保存</p>')
        self.assertEqual(self.page.locator('.gc-title').text_content(), '保存')
        self.assertEqual(self.page.locator('.cm.user .cm-bubble').text_content(), '日本語のメッセージ')
        self.assertEqual(self.page.locator('.cm.user .cm-role').text_content(), 'You')
        after = self.page.evaluate("({code:cur,system:WS_CHAT_SYSTEM,template:getTemplate('timer')})")
        self.assertEqual(before, after)
        self.assertEqual(self.page.evaluate('cvOllamaMessages[0].content'), '日本語の指示')
        self.assertTrue(self.page.locator('#view-studio').evaluate("el=>el.classList.contains('active')"))
        self.page.evaluate("setLanguage('ja')")
        self.assertEqual(self.page.locator('.cm.user .cm-role').text_content(), 'あなた')

    def test_dynamic_ui_and_attributes_switch_both_ways(self):
        self.page.evaluate("""() => {
          galleryTab='public'; publicApps=[]; switchGalleryTab('public');
        }""")
        # switchGalleryTab starts a real app query against the in-memory fixture.
        self.page.evaluate("setLanguage('en'); clearChat(); renderCommentsList({empty:true,size:0})")
        self.page.locator('#chat-msgs [data-i18n]').wait_for(state='attached')
        self.page.wait_for_function("document.querySelector('#chat-msgs').textContent.includes('Chat history cleared')")
        self.assertEqual(self.page.locator('#skw').get_attribute('placeholder'), 'Search community apps...')
        self.assertEqual(self.page.locator('#g-empty-msg').text_content(), 'No published apps yet')
        self.page.wait_for_function("document.querySelector('#app-comments-list').textContent==='No comments yet'")
        self.page.evaluate("setLanguage('ja')")
        self.assertEqual(self.page.locator('#skw').get_attribute('placeholder'), 'みんなの作品を検索...')
        self.assertEqual(self.page.locator('#g-empty-msg').text_content(), '公開中の作品がまだありません')

    def test_cleared_errors_do_not_reappear_when_switching(self):
        self.page.evaluate("curUser=null;updateAuthGate();doLogin()")
        self.page.evaluate("document.getElementById('auth-gate-err').textContent='';setLanguage('en')")
        self.assertEqual(self.page.locator('#auth-gate-err').text_content(), '')

    def test_invalid_preference_falls_back_to_japanese(self):
        self.page.evaluate("localStorage.setItem('pt_language','unsupported')")
        self.page.reload()
        self.assertEqual(self.page.locator('html').get_attribute('lang'), 'ja')

    def test_language_works_without_firebase_or_storage(self):
        page = self.context.new_page()
        page.add_init_script("Object.defineProperty(Storage.prototype, 'setItem', {value(){throw new Error('disabled')}})")
        # Load just the real UI and language code, without the app's Firebase stub.
        no_sdk = HTML.replace('window.firebase = {', 'window.unusedFirebase = {')
        page.route('http://studio.test/', lambda route: route.fulfill(body=no_sdk,content_type='text/html'))
        page.goto('http://studio.test/')
        page.locator('#auth-gate [data-language-select]').select_option('en')
        self.assertEqual(page.locator('#auth-gate button[onclick="doLogin()"]').inner_text(), 'Log in')
        page.close()


    def test_settings_picker_syncs_and_mobile_login_fits(self):
        self.page.set_viewport_size({'width':375,'height':812})
        self.page.evaluate("curUser=null;updateAuthGate()")
        self.page.locator('#auth-gate [data-language-select]').select_option('en')
        bounds = self.page.locator('#auth-gate button[onclick="doLogin()"]').bounding_box()
        self.assertGreaterEqual(bounds['x'], 0)
        self.assertLessEqual(bounds['x'] + bounds['width'], 375)
        self.page.evaluate("curUser={uid:'test'};updateAuthGate();openSettings()")
        picker = self.page.locator('#sm [data-language-select]')
        self.assertEqual(picker.input_value(), 'en')
        picker.select_option('ja')
        self.assertEqual(self.page.locator('#nav [data-language-select]').input_value(), 'ja')
        self.assertEqual(self.page.locator('#sm .mt').text_content(), '設定✕')

    def test_all_marked_ui_strings_have_catalog_entries(self):
        missing = self.page.evaluate("""() => {
          const missing=[];
          document.querySelectorAll('*').forEach(el => {
            ['data-i18n','data-i18n-title','data-i18n-placeholder','data-i18n-aria-label'].forEach(attr => {
              const key=el.getAttribute(attr);
              if(key!==null && !Object.prototype.hasOwnProperty.call(UI_EN,key))missing.push(key);
            });
          });
          return missing;
        }""")
        self.assertEqual(missing, [])
