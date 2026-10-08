import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from shiboken6 import isValid
from PySide6.QtCore import Qt,QCoreApplication,QEvent,QRectF
from PySide6.QtGui import QFont,QFontMetrics
from PySide6.QtWidgets import QApplication,QLabel
from e3d_designer.app import Window,Item
from e3d_designer.model import Form,Gadget


class NativeEditorAppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json');self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def load(self,form):
        self.w.form=form;self.w.selected=None;self.w.history=[];self.w.future=[];self.w.dirty=False
        self.w.refresh();self.app.processEvents()
    def item(self,name):return next(item for item in self.w.scene.items() if isinstance(item,Item) and item.gadget.name==name)
    def preview(self):
        if self.w.runtime_action.isChecked():self.w.runtime_action.setChecked(False)
        self.w.runtime_action.setChecked(True);self.app.processEvents();return self.w.runtime_dialog

    def test_button_and_choice_geometry_and_fonts_match_reference_without_changing_mac(self):
        self.load(Form(gadgets=[Gadget(name='Run',label='計測',width=4),
            Gadget(kind='option',name='Choice',label='種類',width=2,option_width_explicit=True,items=['1','2'],initial='2',y=3),
            Gadget(kind='combo',name='Combo',label='Type',width=5,combo_tagwid='2',items=['A'],y=5),
            Gadget(kind='text',name='Value',label='距離',width=8,initial='123.4',y=7)]))
        before=self.w.form.dumps();code=self.w.form.pml();preview=self.preview()
        for g in self.w.form.gadgets:
            with self.subTest(kind=g.kind):
                item=self.item(g.name);control=preview.controls[g.name]
                self.assertEqual(item.boundingRect().size().toSize(),control.size())
                self.assertIsNotNone(item._control_pixmap)
                self.assertEqual(control.font(),self.w.appearance.preview_font)
                if hasattr(control,'entry'):self.assertEqual(control.entry.font(),self.w.appearance.preview_font)
        self.assertEqual(preview.controls['Choice'].entry.currentText(),'2')
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.form.pml(),code)
        self.assertEqual(self.w.history,[]);self.assertFalse(self.w.dirty)

    def test_short_button_and_auto_choice_get_native_padding_instead_of_fixed_insets(self):
        self.load(Form(size_explicit=False,gadgets=[Gadget(name='Pin',label='PIN消',width=4,x=0,y=0),
            Gadget(kind='option',name='Choice',label='',width=2,items=['Longer option content'],y=2)]))
        preview=self.preview();button=preview.controls['Pin']
        self.assertGreaterEqual(button.width(),QFontMetrics(button.font()).horizontalAdvance('PIN消')+8)
        for name in ('Pin','Choice'):
            item=self.item(name)
            self.assertGreater(item.boundingRect().width(),self.w.form.named(name).width*10)
            self.assertGreaterEqual(self.w.form_item.body_rect().right(),item.sceneBoundingRect().right())
        self.assertEqual(self.item('Choice').boundingRect().width(),preview.controls['Choice'].sizeHint().width())

    def test_font_dialog_cancel_and_apply_keep_model_and_update_open_reference(self):
        self.load(Form(gadgets=[Gadget(name='Run',label='Label',width=4)]))
        before=self.w.form.dumps();self.preview();font=QFont(self.w.appearance.preview_font);font.setPointSizeF(11)
        with patch('e3d_designer.app.QFontDialog.getFont',return_value=(font,False)):
            self.w.display_font_button.click()
        self.assertNotEqual(self.w.appearance.preview_font,font)
        with patch('e3d_designer.app.QFontDialog.getFont',return_value=(font,True)):
            self.w.display_font_button.click();self.app.processEvents()
        self.assertEqual(self.w.appearance.preview_font,font)
        self.assertEqual(self.w.runtime_dialog.controls['Run'].font(),font)
        self.assertTrue(self.w.runtime_dialog.isVisible());self.assertEqual(self.w.form.dumps(),before)
        self.assertEqual(self.w.history,[]);self.assertFalse(self.w.dirty)

    def test_initial_value_error_allows_static_preview_with_visible_reason(self):
        self.load(Form(gadgets=[Gadget(kind='text',name='Value',value_type='REAL',initial='unfinished')]))
        before=copy.deepcopy(self.w.form);preview=self.preview()
        self.assertTrue(preview.isVisible());self.assertTrue(self.w.runtime_action.isChecked())
        self.assertEqual(preview.controls['Value'].entry.text(),'unfinished')
        self.assertIn('REAL',preview.preview_warning)
        self.assertTrue(any('MAC出力前に修正' in label.text() for label in preview.form_root.findChildren(QLabel)))
        self.assertEqual(self.w.form,before)
        with self.assertRaises(ValueError):self.w.form.pml()
        self.w.form.gadgets[0].initial='1.2';self.w.refresh();preview=self.preview()
        self.assertEqual(preview.preview_warning,'');self.assertEqual(preview.controls['Value'].entry.text(),'1.2')

    def test_callback_error_allows_preview_but_geometry_error_still_reports_reason(self):
        self.load(Form(gadgets=[Gadget(name='Run',command='unfinished\ncommand')]))
        preview=self.preview();self.assertTrue(preview.isVisible());self.assertIn('CALL',preview.preview_warning)
        self.w.runtime_action.setChecked(False);self.w.form.width=1
        self.w.runtime_action.setChecked(True);self.app.processEvents()
        self.assertFalse(self.w.runtime_action.isChecked());self.assertIn('参考表示を開けません',self.w.statusBar().currentMessage())
        self.w.form.width=70;preview=self.preview();self.assertTrue(preview.isVisible())

    def test_deleted_dialog_is_recreated_and_offscreen_minimized_window_recovers(self):
        self.load(Form(gadgets=[Gadget(name='Run')]))
        old=self.preview();old.setAttribute(Qt.WA_DeleteOnClose);old.close()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
        self.assertFalse(isValid(old))
        preview=self.preview();self.assertIsNot(preview,old);self.assertTrue(preview.isVisible())
        preview.move(-10000,-10000);preview.showMinimized();self.w.toggle_runtime_preview(True);self.app.processEvents()
        self.assertFalse(preview.isMinimized());self.assertTrue(preview.isVisible())
        self.assertTrue(self.w.screen().availableGeometry().contains(preview.frameGeometry()))

    def test_large_reference_fits_whole_form_with_accessible_title_and_no_source_changes(self):
        self.load(Form(width=300,height=300,gadgets=[Gadget(name='Far',x=270,y=270)]))
        before=self.w.form.dumps();preview=self.preview()
        available=self.w.screen().availableGeometry()
        self.assertTrue(preview.isVisible());self.assertLessEqual(preview.width(),available.width())
        self.assertLessEqual(preview.height(),available.height())
        view=preview.form_view
        self.assertFalse(view.horizontalScrollBar().isVisible())
        self.assertFalse(view.verticalScrollBar().isVisible())
        self.assertLess(view.display_scale,1)
        self.assertTrue(QRectF(view.viewport().rect()).adjusted(-1,-1,1,1).contains(
            view.viewportTransform().mapRect(view.sceneRect())))
        self.assertEqual(self.w.form.dumps(),before)

    def test_one_click_recovers_hidden_minimized_or_offscreen_preview(self):
        self.load(Form(gadgets=[Gadget(name='Run')]))
        for state in ('hidden','minimized','offscreen'):
            with self.subTest(state=state):
                preview=self.preview()
                if state=='hidden':preview.hide()
                elif state=='minimized':preview.showMinimized()
                else:preview.move(-10000,-10000)
                self.app.processEvents();self.w.runtime_action.trigger();self.app.processEvents()
                self.assertTrue(self.w.runtime_action.isChecked());self.assertTrue(preview.isVisible())
                self.assertFalse(preview.isMinimized())
                self.assertTrue(self.w.screen().availableGeometry().contains(preview.frameGeometry()))
                self.w.runtime_action.trigger();self.app.processEvents()
                self.assertFalse(self.w.runtime_action.isChecked());self.assertFalse(preview.isVisible())

    def test_labels_have_no_entry_border_and_keep_transparency_and_explicit_background(self):
        self.load(Form(gadgets=[Gadget(kind='paragraph',name='Label',label='Label',width=8),
            Gadget(kind='paragraph',name='Colored',label='Label',background='4',width=8,y=3),
            Gadget(kind='toggle',name='Check',label='Enabled',initial='TRUE',y=5)]))
        plain=self.item('Label')._control_pixmap.toImage();colored=self.item('Colored')._control_pixmap.toImage()
        self.assertEqual(plain.pixelColor(plain.width()-2,2).alpha(),0)
        self.assertEqual(colored.pixelColor(colored.width()-2,2).alpha(),255)
        self.assertIsNotNone(self.item('Check')._control_pixmap)

    def test_repeated_snapshot_deletion_does_not_destroy_later_control_styles(self):
        self.load(Form(gadgets=[Gadget(kind='text',name='Value',label='Value',initial='123'),Gadget(kind='option',name='Choice',items=['A','B'],y=3)]))
        before=self.w.form.dumps()
        for _ in range(4):
            self.w.refresh()
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
            self.w.resize_preview()
            self.assertIsNotNone(self.item('Value')._control_pixmap)
            self.assertIsNotNone(self.item('Choice')._control_pixmap)
        self.assertEqual(self.w.form.dumps(),before)
