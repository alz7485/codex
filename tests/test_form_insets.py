import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtWidgets import QApplication,QStyle
from PySide6.QtTest import QTest
from e3d_designer.app import Window,Item
from e3d_designer.model import Form,Gadget
from e3d_designer.appearance import FORM_MARGIN,FORM_BACKGROUND,default_form_font


class FormInsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def load(self,form):
        self.w.form=form;self.w.selected=None;self.w.refresh();self.app.processEvents()
    def preview(self):
        if self.w.runtime_action.isChecked():self.w.runtime_action.setChecked(False)
        self.w.runtime_action.setChecked(True);self.app.processEvents();return self.w.runtime_dialog
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def test_form_padding_and_border_keep_zero_origin_and_manual_size_source(self):
        self.load(Form(width=30,height=10,gadgets=[Gadget(name='Run',x=0,y=0,width=4,label='計測')]))
        before=self.w.form.dumps();code=self.w.form.pml();p=self.preview()
        inner=self.w.form_item.body_rect();outer=self.w.form_item.frame_rect()
        self.assertEqual(inner.topLeft().toTuple(),(0,0));self.assertEqual(self.item('Run').pos().toTuple(),(0,0))
        self.assertEqual(outer.topLeft().toTuple(),(-FORM_MARGIN,-FORM_MARGIN))
        self.assertEqual(outer.size().toSize(),p.client.size());self.assertEqual(p.surface.pos().toTuple(),(FORM_MARGIN,FORM_MARGIN))
        self.assertEqual(p.surface.size().toTuple(),(300,260));self.assertEqual(p.controls['Run'].pos().toTuple(),(0,0))
        self.assertEqual(p.surface.palette().window().color().name(),FORM_BACKGROUND)
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.form.pml(),code);self.assertEqual(self.w.history,[])
    def test_measure_form_automatic_client_uses_same_extent_and_padding_in_both_views(self):
        form=Form.loads((Path(__file__).parents[1]/'examples/measure-layout.json').read_text())
        self.load(form);before=self.w.form.dumps();p=self.preview();body=self.w.form_item.body_rect();outer=self.w.form_item.frame_rect()
        self.assertAlmostEqual(body.width(),p.surface.width(),delta=.5);self.assertAlmostEqual(body.height(),p.surface.height(),delta=.5)
        self.assertAlmostEqual(outer.width(),p.client.width(),delta=.5);self.assertAlmostEqual(outer.height(),p.client.height(),delta=.5)
        for name in ('Button1','Digits','Label1'):
            self.assertEqual(self.item(name).boundingRect().size().toSize(),p.controls[name].size())
        self.assertEqual(self.w.form.dumps(),before);self.assertFalse(self.w.form.size_explicit)
    def test_compact_buttons_fit_the_measurement_arrow_pitch_and_keep_text_readable(self):
        self.load(Form(gadgets=[Gadget(name='A',label='▲',x=0,y=0,width=1.2),Gadget(name='B',label='▼',x=2,y=0,width=1.2),
            Gadget(name='Run',label='計測',x=5,y=0,width=4)]));p=self.preview()
        self.assertLessEqual(p.controls['A'].width(),p.controls['B'].x()-p.controls['A'].x())
        button=p.controls['Run'];self.assertEqual(button.style().pixelMetric(QStyle.PM_ButtonMargin),4)
        self.assertGreaterEqual(button.width(),button.fontMetrics().horizontalAdvance(button.text())+8)
        self.assertEqual(self.w.form.named('Run').width,4)
    def test_outer_handle_gesture_changes_content_size_by_delta_and_undo_restores_padding(self):
        self.load(Form(width=30,height=10,gadgets=[Gadget(name='Run',x=0,y=0,width=4)]));before=self.w.form.dumps();rect=self.w.form_item.frame_rect()
        start=self.w.view.mapFromScene(self.w.form_item.handles()['width'].center());end=start+QPoint(10,0)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        self.assertEqual(self.w.form.width,31);self.assertEqual(self.w.form_item.frame_rect().width(),rect.width()+10)
        self.assertEqual(self.w.form.named('Run').x,0);self.w.undo();self.assertEqual(self.w.form.dumps(),before)
        self.assertEqual(self.w.form_item.frame_rect(),rect)
    def test_reference_window_resize_does_not_stretch_the_form_client_border(self):
        self.load(Form(size_explicit=False,gadgets=[Gadget(name='Run',x=0,y=0,width=4)]));p=self.preview();size=p.client.size();origin=p.surface.pos()
        p.resize(p.width()+200,p.height()+150);self.app.processEvents()
        self.assertEqual(p.client.size(),size);self.assertEqual(p.surface.pos(),origin)
    def test_resize_to_inferred_source_dimensions_still_commits_manual_size(self):
        self.load(Form(size_explicit=False,gadgets=[Gadget(name='Run',x=0,y=0,width=4)]))
        before=self.w.form.dumps();size=self.w.form.width,self.w.form.height;body=self.w.form_item.body_rect()
        start=self.w.view.mapFromScene(self.w.form_item.handles()['both'].center())
        end=start+QPoint(round(size[0]*10-body.width()),round(size[1]*26-body.height()))
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        self.assertEqual((self.w.form.width,self.w.form.height),size);self.assertTrue(self.w.form.size_explicit)
        self.assertEqual(len(self.w.history),1);self.assertIn('Size 5 2',self.w.form.pml())
        self.w.undo();self.assertEqual(self.w.form.dumps(),before);self.assertFalse(self.w.form.size_explicit)
    def test_default_japanese_font_has_medium_weight_and_user_font_remains_authoritative(self):
        font=default_form_font();available=QFontDatabase.families()
        family=next((f for f in ('MS UI Gothic','MS Gothic','Noto Sans CJK JP') if f in available),QApplication.font().family())
        self.assertEqual(font.family(),family);self.assertEqual(font.pointSizeF(),9);self.assertEqual(font.weight(),QFont.Medium)
        self.load(Form(gadgets=[Gadget(kind='paragraph',name='Label',label='距離',x=0,y=0)]));before=self.w.form.dumps()
        custom=QFont(font);custom.setPointSizeF(10);custom.setWeight(QFont.Normal);self.w.set_display_font(custom);p=self.preview()
        self.assertEqual(p.controls['Label'].font(),custom);self.assertEqual(self.w.appearance.preview_font,custom)
        self.assertEqual(self.w.form.dumps(),before)
