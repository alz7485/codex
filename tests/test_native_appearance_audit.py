import copy
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window,Item
from e3d_designer.model import Form,Gadget
from e3d_designer.runtime_preview import RuntimePreview
from e3d_designer.quick_editor import MiniProperties


class NativeAppearanceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json');self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def load(self):
        self.w.form=Form(size_explicit=False,gadgets=[Gadget(kind='option',name='Choice',label='',width=2,
            items=['A long choice using an automatic native width'])])
        self.w.selected=None;self.w.history=[];self.w.future=[];self.w.dirty=False;self.w.refresh();self.app.processEvents()
    def item(self):return next(item for item in self.w.scene.items() if isinstance(item,Item))
    def resize_form(self,delta,escape=False,back=False):
        start=self.w.view.mapFromScene(self.w.form_item.handles()['width'].center());end=start+delta
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(self.w.view.viewport(),end,30)
        if back:QTest.mouseMove(self.w.view.viewport(),start,30);end=start
        if escape:QTest.keyClick(self.w.view.viewport(),Qt.Key_Escape)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
    def test_auto_form_handle_changes_visible_size_from_the_visible_start(self):
        self.load();before=self.w.form.dumps();old=self.w.form_item.body_rect().width()
        self.assertGreater(old,self.w.form.width*10)
        self.resize_form(QPoint(10,0))
        self.assertAlmostEqual(self.w.form_item.body_rect().width(),old+10)
        self.assertTrue(self.w.form.size_explicit);self.assertEqual(len(self.w.history),1)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)
        self.assertEqual(self.w.form_item.body_rect().width(),old)
        self.w.redo();self.assertAlmostEqual(self.w.form_item.body_rect().width(),old+10)
    def test_escape_restores_auto_form_source_visible_size_and_redo(self):
        self.load();before=self.w.form.dumps();old=self.w.form_item.body_rect();future=Form(title='Redo');self.w.future=[future]
        self.resize_form(QPoint(10,0),escape=True)
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.form_item.body_rect(),old)
        self.assertEqual(self.w.history,[]);self.assertEqual(self.w.future,[future]);self.assertFalse(self.w.dirty)
    def test_drag_back_to_origin_preserves_automatic_size_and_source(self):
        self.load();before=self.w.form.dumps();old=self.w.form_item.body_rect();future=Form(title='Redo');self.w.future=[future]
        self.resize_form(QPoint(20,0),back=True)
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.form_item.body_rect(),old)
        self.assertEqual(self.w.history,[]);self.assertEqual(self.w.future,[future]);self.assertFalse(self.w.dirty)
    def test_automatic_option_width_is_readonly_until_explicit_width_is_enabled(self):
        self.load();self.w.choose_row(0);self.app.processEvents();before=self.w.form.dumps()
        self.assertNotIn('width',self.item().handles());self.assertFalse(self.w.fields['width'].isEnabled())
        self.assertIn('OPTION',self.w.fields['width'].toolTip())
        self.w.option_width_check.setChecked(True);self.app.processEvents()
        self.assertIn('width',self.item().handles());self.assertTrue(self.w.fields['width'].isEnabled())
        self.w.fields['width'].setValue(8);self.app.processEvents()
        self.assertIn('Width 8',self.w.form.pml());self.assertGreater(self.item().boundingRect().width(),80)
        self.w.undo();self.w.undo();self.assertEqual(self.w.form.dumps(),before)
        self.assertNotIn('width',self.item().handles())
    def test_mini_editor_can_enable_explicit_width_without_changing_automatic_source_on_cancel(self):
        self.load();before=self.w.form.dumps();dialog=MiniProperties(self.w,self.w.form,0)
        try:
            self.assertFalse(dialog.fields['width'].isEnabled());dialog.option_width.setChecked(True)
            self.assertTrue(dialog.fields['width'].isEnabled());dialog.fields['width'].setValue(8);dialog.accept()
            self.assertEqual(dialog.result_form.named('Choice').width,8)
            self.assertTrue(dialog.result_form.named('Choice').option_width_explicit)
            self.assertEqual(self.w.form.dumps(),before)
        finally:dialog.close();dialog.deleteLater()
    def test_reference_resolves_each_geometry_once_per_pass_and_never_reuses_previous_form(self):
        gadgets=[Gadget(name='Base',width=3)]
        for i in range(1,35):
            previous=gadgets[-1].name
            gadgets.append(Gadget(name=f'Item{i}',layout_mode='RELATIVE',xref=previous,yref=previous,
                xedge='XMIN',yedge='YMIN',xoffset=0,yoffset=0,width=3))
        form=Form(gadgets=gadgets);before=form.dumps();counts=Counter();original=Form.geometry
        def resolve(model,g,*args,**kwargs):
            memo=kwargs.get('_memo')
            if memo is None or id(g) not in memo:counts[g.name]+=1
            return original(model,g,*args,**kwargs)
        preview=RuntimePreview(self.w)
        try:
            with patch.object(Form,'geometry',resolve):preview.set_form(form)
            self.assertLessEqual(max(counts.values()),2)
            self.assertEqual(form.dumps(),before);self.assertEqual(preview.controls['Item34'].x(),20)
            form.named('Base').x=5;preview.set_form(form)
            self.assertEqual(preview.controls['Item34'].x(),50)
        finally:preview.close();preview.deleteLater()

    def test_large_invalid_choice_initial_still_previews_without_integer_overflow(self):
        for kind in ('option','combo'):
            with self.subTest(kind=kind):
                form=Form(gadgets=[Gadget(kind=kind,name='Choice',items=['A'],initial='999999999999999999999')])
                self.w.form=copy.deepcopy(form);self.w.refresh();self.w.runtime_action.setChecked(True);self.app.processEvents()
                self.assertTrue(self.w.runtime_dialog.isVisible());self.assertTrue(self.w.runtime_dialog.preview_warning)
                self.assertEqual(self.w.runtime_dialog.controls['Choice'].entry.currentIndex(),-1)
                self.assertEqual(self.w.form,form);self.assertIsNotNone(self.item()._control_pixmap)
                with self.assertRaises(ValueError):self.w.form.pml()
                self.w.runtime_action.setChecked(False)

    def test_slider_preview_handles_finite_limits_whose_difference_overflows(self):
        preview=RuntimePreview(self.w)
        try:
            for value,expected in ((-1e308,0),(-5e307,250),(0,500),(5e307,750),(1e308,1000)):
                with self.subTest(value=value):
                    form=Form(gadgets=[Gadget(kind='slider',name='Slider',slider_min=-1e308,slider_max=1e308,slider_value=value)])
                    before=form.dumps();preview.set_form(form)
                    self.assertEqual(preview.controls['Slider'].value(),expected)
                    self.assertEqual(form.dumps(),before);self.assertEqual(preview.preview_warning,'')
        finally:preview.close();preview.deleteLater()
