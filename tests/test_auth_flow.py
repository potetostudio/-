"""Sign-in UI must advance independently of optional cache/backend work."""
from test_studio import StudioBrowserCase


class AuthFlowTests(StudioBrowserCase):
    def setUp(self):
        super().setUp()
        self.page.set_default_timeout(3000)
        self.page.evaluate("""async()=>{
          await testAuthListener(null);
          window.testUser={uid:'test',email:'user@example.test'};
          window.authFailure=null;
          function signedIn(){
            window.authTask=testAuthListener(testUser);
            authTask.catch(error=>{window.authFailure=error.message});
            return Promise.resolve({user:testUser});
          }
          auth={signInWithEmailAndPassword:signedIn,createUserWithEmailAndPassword:signedIn};
        }""")

    def login(self, signup=False):
        self.page.locator('#auth-gate-email').fill('user@example.test')
        self.page.locator('#auth-gate-pw').fill('test-password')
        action='doSignup()' if signup else 'doLogin()'
        self.page.locator('#auth-gate button[onclick="'+action+'"]').click()

    def assert_signed_in(self):
        self.page.wait_for_function("!isAuthGateVisible()")
        self.assertTrue(self.page.locator('#view-gallery').is_visible())
        self.assertEqual(self.page.locator('#app').evaluate('el=>getComputedStyle(el).visibility'), 'visible')
        self.assertEqual(self.page.locator('#auth-status').text_content(), '✓ user@example.test')
        self.assertIsNone(self.page.evaluate('authFailure'))

    def test_login_button_reaches_gallery(self):
        self.login()
        self.page.evaluate('authTask')
        self.assert_signed_in()

    def test_login_advances_while_saved_work_is_still_loading(self):
        self.page.evaluate("()=>{loadLocalRecords=()=>new Promise(resolve=>{window.finishCache=resolve})}")
        self.login()
        self.page.wait_for_function("messages.includes('ログインしました')")
        self.assert_signed_in()
        self.assertTrue(self.page.evaluate('accountStorageLoading'))
        self.page.evaluate('finishCache();authTask')
        self.assertFalse(self.page.evaluate('accountStorageLoading'))

    def test_shared_link_network_wait_does_not_cover_app_with_login(self):
        self.page.evaluate("""()=>{
          history.replaceState(null,'','/?id=shared');
          var collection=db.collection;
          db.collection=name=>name==='apps' ? {doc:()=>({get:()=>new Promise(resolve=>{window.finishShare=resolve})})} : collection(name);
        }""")
        self.login()
        self.page.wait_for_function("typeof finishShare==='function'")
        self.assert_signed_in()
        self.page.evaluate('finishShare({exists:false});authTask')

    def test_late_shared_link_does_not_replace_a_screen_the_user_opened(self):
        self.page.evaluate("""()=>{
          history.replaceState(null,'','/?id=shared');
          var collection=db.collection;
          db.collection=name=>name==='apps' ? {doc:()=>({get:()=>new Promise(resolve=>{window.finishShare=resolve})})} : collection(name);
        }""")
        self.login()
        self.page.wait_for_function("typeof finishShare==='function'")
        self.assert_signed_in()
        self.page.evaluate("nav('studio')")
        self.page.evaluate("finishShare({exists:true,data:()=>({code:'<h1>Shared</h1>',title:'Shared'})});authTask")
        self.assertTrue(self.page.locator('#view-studio').is_visible())
        self.assertEqual(self.page.locator('#app-pv').get_attribute('srcdoc'), '')

    def test_signup_advances_while_saved_work_is_still_loading(self):
        self.page.evaluate("()=>{loadLocalRecords=()=>new Promise(resolve=>{window.finishCache=resolve})}")
        self.login(signup=True)
        self.assert_signed_in()
        self.page.evaluate('finishCache();authTask')

    def test_cache_failure_does_not_leave_login_or_editor_locked(self):
        self.page.evaluate("()=>{loadLocalRecords=async()=>{throw Error('Cache unavailable')}}")
        self.login()
        self.page.wait_for_function('!accountStorageLoading')
        self.assert_signed_in()
        self.page.evaluate("nav('studio')")
        self.page.locator('#lp-code').fill('<h1>Still usable</h1>')

    def test_chat_subscription_failure_does_not_abort_login(self):
        self.page.evaluate("()=>{cvsSubscribe=()=>{throw Error('Chat unavailable')}}")
        self.login()
        self.page.evaluate('authTask.catch(()=>{})')
        self.assert_signed_in()

    def test_late_cache_callback_after_logout_cannot_reopen_app(self):
        self.page.evaluate("()=>{loadLocalRecords=()=>new Promise(resolve=>{window.cacheResolvers=(window.cacheResolvers || []).concat(resolve)})}")
        self.login()
        self.assert_signed_in()
        self.page.evaluate("()=>{window.logoutTask=testAuthListener(null)}")
        self.page.wait_for_function('isAuthGateVisible()')
        self.page.evaluate('cacheResolvers.forEach(resolve=>resolve());Promise.all([authTask,logoutTask])')
        self.assertTrue(self.page.evaluate('isAuthGateVisible()'))
        self.assertEqual(self.page.locator('#app').evaluate('el=>getComputedStyle(el).visibility'), 'hidden')
        self.assertIsNone(self.page.evaluate('curUser'))

    def test_pending_offline_edits_are_loaded_before_cloud_records_merge(self):
        self.page.evaluate("""async()=>{
          writeLocalJson(accountKey('apps','test'),[{id:'offline',urlId:'offline',uid:'test',
            title:'Offline work',code:'<h1>Unsynced</h1>',pendingCloud:true}]);
          await waitForLocalWrites([accountKey('apps','test')]);
          cloudDocs=[{id:'offline',data:()=>({label:'Server work',code:'<h1>Old cloud</h1>',updatedAt:new Date()})}];
          var load=loadLocalRecords;
          loadLocalRecords=keys=>new Promise(resolve=>{window.finishCache=()=>resolve(load(keys))});
        }""")
        self.login()
        self.assert_signed_in()
        self.page.evaluate('finishCache();authTask')
        self.page.wait_for_function("getPaths.includes('users/test/apps')")
        self.assertEqual(self.page.evaluate("apps.find(app=>app.id==='offline').code"), '<h1>Unsynced</h1>')

    def test_failed_authentication_keeps_login_gate_closed_to_app(self):
        self.page.evaluate("()=>{auth.signInWithEmailAndPassword=async()=>{throw {code:'auth/wrong-password'}}}")
        self.login()
        self.page.locator('#auth-gate-err').wait_for(state='visible')
        self.assertTrue(self.page.evaluate('isAuthGateVisible()'))
        self.assertIsNone(self.page.evaluate('curUser'))
        self.assertNotIn('ログインしました', self.page.evaluate('messages'))
