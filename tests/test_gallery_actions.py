"""Distinct primary actions and readable, keyboard-accessible card menus."""
from test_studio import StudioBrowserCase


class GalleryActionTests(StudioBrowserCase):
    def setUp(self):
        super().setUp()
        self.page.evaluate("nav('gallery')")

    def test_primary_edit_is_labeled_and_opens_editor_without_playback(self):
        edit=self.page.locator('[data-app-id="testID"] .gc-edit')
        self.assertEqual(edit.inner_text(), '編集する')
        self.assertGreaterEqual(edit.bounding_box()['height'], 44)
        self.assertEqual(self.page.locator('.gc-actions button').count(), 2)
        edit.click()
        self.page.locator('#ct').wait_for(state='visible')
        self.assertEqual(self.page.evaluate('editingAppId'), 'testID')
        self.assertFalse(self.page.locator('#view-app').is_visible())

    def test_more_menu_lists_labeled_actions_and_rename_works(self):
        trigger=self.page.locator('.gc-more')
        trigger.click()
        self.assertEqual(trigger.get_attribute('aria-expanded'), 'true')
        self.assertEqual(self.page.get_by_role('menuitem').all_text_contents(), ['名前を変更','複製する','削除する'])
        self.page.get_by_role('menuitem',name='名前を変更',exact=True).click()
        self.assertFalse(self.page.locator('#gallery-action-menu').is_visible())
        self.assertEqual(trigger.get_attribute('aria-expanded'), 'false')
        self.page.locator('#rename-app-input').fill('A clear name')
        self.page.evaluate('submitRenameApp()')
        self.assertEqual(self.page.locator('.gc-title').inner_text(), 'A clear name')
        self.assertTrue(self.page.locator('#view-gallery').is_visible())

    def test_delete_is_separate_and_cancel_keeps_app(self):
        self.page.locator('.gc-more').click()
        delete=self.page.get_by_role('menuitem',name='削除する',exact=True)
        self.assertIn('gc-menu-danger',delete.get_attribute('class'))
        self.assertNotEqual(delete.evaluate('el=>getComputedStyle(el).color'),self.page.get_by_role('menuitem',name='名前を変更').evaluate('el=>getComputedStyle(el).color'))
        self.page.once('dialog',lambda dialog:dialog.dismiss())
        delete.click()
        self.assertEqual(self.page.evaluate('apps.length'),1)
        self.assertTrue(self.page.locator('#view-gallery').is_visible())
        self.assertFalse(self.page.locator('#gallery-action-menu').is_visible())

    def test_keyboard_menu_navigation_escape_and_outside_click(self):
        trigger=self.page.locator('.gc-more')
        trigger.focus()
        self.page.keyboard.press('ArrowDown')
        self.assertTrue(self.page.get_by_role('menuitem',name='名前を変更').evaluate('el=>el===document.activeElement'))
        self.page.keyboard.press('ArrowDown')
        self.assertTrue(self.page.get_by_role('menuitem',name='複製する').evaluate('el=>el===document.activeElement'))
        self.page.keyboard.press('End')
        self.assertTrue(self.page.get_by_role('menuitem',name='削除する').evaluate('el=>el===document.activeElement'))
        self.page.keyboard.press('Escape')
        self.assertTrue(trigger.evaluate('el=>el===document.activeElement'))
        trigger.click()
        self.page.locator('#skw').click()
        self.assertFalse(self.page.locator('#gallery-action-menu').is_visible())
        trigger.click()
        self.page.keyboard.press('Tab')
        self.assertFalse(self.page.locator('#gallery-action-menu').is_visible())
        self.assertFalse(self.page.evaluate("document.getElementById('gallery-action-menu').contains(document.activeElement)"))

    def test_menu_closes_on_navigation_and_another_card_menu_replaces_it(self):
        self.page.evaluate("apps.push({id:'other',title:'Other',code:'<h1>Other</h1>'});renderGallery()")
        first=self.page.locator('[data-app-id="testID"] .gc-more')
        second=self.page.locator('[data-app-id="other"] .gc-more')
        first.click()
        second.click()
        self.assertEqual(first.get_attribute('aria-expanded'),'false')
        self.assertEqual(second.get_attribute('aria-expanded'),'true')
        self.page.evaluate("nav('studio')")
        self.assertFalse(self.page.locator('#gallery-action-menu').is_visible())

    def test_small_mobile_menu_is_visible_unclipped_and_localized(self):
        self.page.set_viewport_size({'width':320,'height':568})
        self.page.evaluate("setLanguage('en')")
        edit=self.page.locator('.gc-edit')
        pin=self.page.locator('.gc-pin')
        self.assertEqual(edit.inner_text(),'Edit')
        self.assertEqual(pin.inner_text(),'Pin')
        self.assertGreaterEqual(edit.bounding_box()['height'],44)
        self.assertGreaterEqual(pin.bounding_box()['height'],40)
        self.assertTrue(pin.evaluate("el=>el.getBoundingClientRect().bottom<=el.closest('.gc').querySelector('.gc-thumb').getBoundingClientRect().bottom"))
        pin.click()
        self.assertEqual(self.page.locator('.gc-pin').inner_text(),'Pinned')
        self.page.locator('.gc-more').click()
        menu=self.page.locator('#gallery-action-menu')
        box=menu.bounding_box()
        self.assertGreaterEqual(box['x'],8)
        self.assertLessEqual(box['x']+box['width'],312)
        self.assertGreaterEqual(box['y'],8)
        self.assertLessEqual(box['y']+box['height'],560)
        self.assertEqual(self.page.get_by_role('menuitem').all_text_contents(),['Rename','Duplicate','Delete'])
        self.assertTrue(all(item.bounding_box()['height']>=44 for item in self.page.get_by_role('menuitem').all()))
