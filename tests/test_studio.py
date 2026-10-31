"""Browser regressions: python3 -m unittest discover -s tests -v
Requires Python Playwright and Chromium (CHROMIUM_PATH overrides /usr/bin/chromium).
Firebase is an in-memory test double; these tests never contact production services.
"""
import os
import re
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = Path(__file__).resolve().parents[1].joinpath('index.html').read_text()
HTML = HTML.replace('<script src="./i18n.js"></script>', '<script>\n' + Path(__file__).resolve().parents[1].joinpath('i18n.js').read_text() + '</script>')
# Replace only the external SDKs. Execute the application's real inline code.
HTML = HTML.replace('<script src="./studio-state.js"></script>', '<script>\n' + Path(__file__).resolve().parents[1].joinpath('studio-state.js').read_text() + '</script>')
HTML = HTML.replace('<script src="./gallery-ui.js"></script>', '<script>\n' + Path(__file__).resolve().parents[1].joinpath('gallery-ui.js').read_text() + '</script>')
HTML = HTML.replace('<script src="./local-store.js"></script>', '<script>\n' + Path(__file__).resolve().parents[1].joinpath('local-store.js').read_text() + '</script>')
HTML = re.sub(r'<script src="[^"]+"></script>', '', HTML)
HTML = HTML.replace('<script>\n', '''<script>
window.firebase = {
  initializeApp() {}, firestore() { return {}; },
  auth() { return { onAuthStateChanged() {} }; }
};
</script><script>\n''', 1)

FIXTURE = """() => {
  localStorage.clear();
  window.store = {};
  window.failWrites = false;
  window.messages = [];
  window.cloudDocs = [];
  window.getPaths = [];
  function ref(path) {
    return {
      collection: name => ref(path + '/' + name),
      doc: id => ref(path + '/' + id),
      orderBy: () => ref(path), limit: () => ref(path),
      onSnapshot: fn => { Promise.resolve().then(() => fn({forEach() {}})); return () => {}; },
      get: async () => {
        getPaths.push(path);
        if (path === 'users/test/apps') return {forEach: fn => cloudDocs.forEach(fn)};
        return {exists: !!store[path], data: () => store[path]};
      },
      set: async (data, options) => {
        if (failWrites) throw {code: failWrites};
        store[path] = options && options.merge ? Object.assign({}, store[path], data) : data;
      },
      update: async data => {
        if (failWrites) throw {code: failWrites};
        Object.assign(store[path], data);
      }
    };
  }
  db = {collection: name => ref(name)};
  curUser = {uid: 'test'};
  prof = {name: 'tester', avatar: ''};
  apps = []; publicApps = []; curPublicDocId = null;
  T = text => messages.push(text);
  document.getElementById('shtitle').value = 'Test app';
  document.getElementById('publish-confirm-author-input').value = 'tester';
  cur = '<h1>Saved code</h1>';
  // An existing private copy avoids unrelated automatic save behavior in publish tests.
  apps = [{id: 'testID', urlId: 'testID', code: cur, title: 'Test app', uid: 'test'}];
  updateAuthGate();
}"""


class StudioBrowserCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(
            executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'),
            args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.route('**/*', lambda route: route.abort())
        self.page.route('http://studio.test/', lambda route: route.fulfill(
            body=HTML, content_type='text/html'))
        self.page.goto('http://studio.test/')
        self.page.evaluate(FIXTURE)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])


class StudioTests(StudioBrowserCase):
    def test_public_preview_runs_but_cannot_access_parent_or_key(self):
        self.page.evaluate("""() => {
          geminiKey = 'test-only-key';
          window.probe = 'safe';
          injectAndSet(document.getElementById('app-pv'),
            '<html><body><script>try { parent.probe="unsafe"; } catch(e) {}' +
            'document.body.dataset.ran="yes";<\\/script></body></html>');
        }""")
        frame = self.page.frame_locator('#app-pv')
        frame.locator('body[data-ran="yes"]').wait_for(state='attached')
        self.assertEqual(self.page.evaluate('window.probe'), 'safe')
        self.assertNotIn('test-only-key', self.page.locator('#app-pv').get_attribute('srcdoc'))

    def test_published_link_loads_saved_gallery_code(self):
        self.page.evaluate('async () => { await doPublishToGallery(); }')
        self.assertIn('source=gallery', self.page.evaluate('surl'))
        self.assertIn('gallery/testID', self.page.evaluate('Object.keys(store)'))
        loaded = self.page.evaluate("""async () => {
          history.replaceState(null, '', '/?id=testID&source=gallery');
          return await loadShared();
        }""")
        self.assertTrue(loaded)
        self.page.wait_for_function("document.getElementById('app-pv').srcdoc.includes('Saved code')")
        self.assertEqual(self.page.evaluate('curPublicDocId'), 'testID')

    def test_old_share_links_keep_loading_apps_collection(self):
        loaded = self.page.evaluate("""async () => {
          store['apps/old'] = {title:'Old share',code:'<p>Old code</p>'};
          history.replaceState(null, '', '/?id=old');
          return await loadShared();
        }""")
        self.assertTrue(loaded)
        self.assertEqual(self.page.locator('#app-ttl').inner_text(), 'Old share')
        self.assertEqual(self.page.evaluate('getPaths'), ['apps/old'])

    def test_old_public_link_falls_back_to_gallery(self):
        loaded = self.page.evaluate("""async () => {
          store['gallery/old'] = {isPublic:true,title:'Public share',code:'<p>Public code</p>'};
          history.replaceState(null, '', '/?id=old');
          return await loadShared();
        }""")
        self.assertTrue(loaded)
        self.assertEqual(self.page.locator('#app-ttl').inner_text(), 'Public share')

    def test_explicit_gallery_link_avoids_share_id_collision(self):
        self.page.evaluate("""() => {
          store['apps/same'] = {title:'Unrelated share',code:'<p>wrong</p>'};
          store['gallery/same'] = {isPublic:true,title:'Public app',code:'<p>right</p>'};
          history.replaceState(null, '', '/?id=same&source=gallery');
        }""")
        self.assertTrue(self.page.evaluate('loadShared()'))
        self.assertEqual(self.page.locator('#app-ttl').inner_text(), 'Public app')
        self.assertNotIn('apps/same', self.page.evaluate('getPaths'))

    def test_nonpublic_gallery_link_is_rejected(self):
        self.page.evaluate("""() => {
          store['gallery/private'] = {isPublic:false,title:'Private',code:'<p>private</p>'};
          history.replaceState(null, '', '/?id=private&source=gallery');
        }""")
        self.assertFalse(self.page.evaluate('loadShared()'))
        self.assertEqual(self.page.locator('#app-pv').get_attribute('srcdoc'), None)

    def test_failed_publish_does_not_report_success_or_leave_editor(self):
        for code in ['permission-denied', 'unavailable']:
            with self.subTest(code=code):
                self.page.evaluate("""code => {
                  failWrites = code; messages = []; window.navigations = [];
                  nav = v => navigations.push(v);
                  surl = '';
                }""", code)
                self.page.evaluate('doPublishToGallery()')
                messages = self.page.evaluate('messages')
                self.assertTrue(any('失敗' in text for text in messages))
                self.assertFalse(any('公開しました' in text for text in messages))
                self.assertEqual(self.page.evaluate('navigations'), [])
                self.assertEqual(self.page.evaluate('surl'), '')

    def test_id_collision_returns_actual_published_id(self):
        self.page.evaluate("""() => {
          store['gallery/testID'] = {uid:'another-user',title:'Keep me'};
        }""")
        self.page.evaluate('doPublishToGallery()')
        new_id = self.page.evaluate("new URL(surl).searchParams.get('id')")
        self.assertNotEqual(new_id, 'testID')
        self.assertEqual(self.page.evaluate('store["gallery/testID"].title'), 'Keep me')
        self.assertEqual(self.page.evaluate('store[' + repr('gallery/') + '+' + repr(new_id) + '].uid'), 'test')
        self.assertEqual(self.page.evaluate('apps[0].urlId'), new_id)

    def test_loaded_ids_and_legacy_duplicate_ids_open_correct_app(self):
        self.page.evaluate("""async () => {
          Date.now = () => 123456789;
          apps = [{id:123, urlId:'alpha', title:'Cached alpha', code:'<p>alpha</p>'},
                  {id:123, urlId:'beta', title:'Cached beta', code:'<p>beta</p>'}];
          cloudDocs = ['alpha','beta','12abc','12def'].map(id => ({
            id, data:() => ({label:id,code:'<p>'+id+'</p>'}), ref:{delete:async()=>{}}
          }));
          await loadUserApps();
          updateAuthGate();
          nav('gallery');
        }""")
        ids = self.page.evaluate('apps.map(a=>a.id)')
        self.assertEqual(len(set(ids)), 4)
        for title, key in [('Cached beta','beta'),('12abc','12abc'),('12def','12def')]:
            self.page.evaluate("nav('gallery')")
            self.page.locator('.gc-title', has_text=title).click()
            self.assertEqual(self.page.locator('#app-ttl').inner_text(), title)
            self.assertEqual(self.page.evaluate('curAppId'), key)
            self.assertEqual(self.page.evaluate('forkCode'), '<p>'+key+'</p>')


if __name__ == '__main__':
    unittest.main()
