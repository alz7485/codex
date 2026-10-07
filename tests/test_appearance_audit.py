import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLabel
from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.model import Form,Gadget,Menu,MenuItem
from e3d_designer.runtime_preview import RuntimePreview


class AppearanceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.preview=RuntimePreview()
    def tearDown(self):
        self.preview.close();self.preview.deleteLater();self.app.processEvents();self.temp.cleanup()
    def show(self,form):
        self.preview.set_form(form,[self.folder]);self.preview.show();self.app.processEvents()
        return self.preview.controls

    def test_narrow_and_zero_tagwid_do_not_expand_the_input_field(self):
        widths=[]
        for tagwid in ('0','1','10'):
            form=Form(gadgets=[Gadget(kind='combo',name='Choice',label='Long label',
                combo_tagwid=tagwid,width=10,items=['A'])])
            before=form.dumps();control=self.show(form)['Choice']
            self.assertEqual(control.findChild(QLabel).width(),int(tagwid)*10)
            widths.append(control.entry.width())
            self.assertEqual(form.dumps(),before)
        self.assertEqual(widths,[widths[0]]*3)

    def test_window_resize_keeps_form_origin_at_top_left_with_and_without_menu(self):
        for menus in ([],[Menu(name='File',label='A long menu title',items=[MenuItem('Run','SAVEWORK')])]):
            with self.subTest(menu=bool(menus)):
                self.show(Form(size_explicit=False,gadgets=[Gadget(width=4)],menus=menus))
                origin=self.preview.surface.mapTo(self.preview,QPoint(0,0))
                self.preview.resize(self.preview.width()+200,self.preview.height()+200);self.app.processEvents()
                self.assertEqual(self.preview.surface.mapTo(self.preview,QPoint(0,0)),origin)

    def test_image_choices_keep_largest_native_image_after_selection_change(self):
        for name,width,height in (('small.png',20,10),('large.png',70,40)):
            image=QImage(width,height,QImage.Format_RGB32);image.fill(Qt.red);image.save(str(self.folder/name))
        form=Form(gadgets=[Gadget(kind='option',name='Images',label='',display_mode='PIXMAP',
            items=['small.png','large.png'],width=70,height=40,initial='2')])
        before=form.dumps();entry=self.show(form)['Images'].entry
        self.assertEqual(entry.iconSize().toTuple(),(70,40))
        self.assertEqual(entry.currentIndex(),1)
        for index,size in ((0,(20,10)),(1,(70,40))):
            entry.setCurrentIndex(index)
            self.assertEqual(entry.currentData(Qt.DecorationRole).actualSize(entry.iconSize()).toTuple(),size)
        self.assertEqual(form.dumps(),before)

    def test_large_preview_values_report_errors_without_overflow_or_model_changes(self):
        for attributes in ({'combo_tagwid':'1000000000'},{'combo_scroll':'2147483648'},{'x':-1000000000},{'x':-1e308}):
            with self.subTest(attributes=attributes):
                form=Form(gadgets=[Gadget(kind='combo',name='Choice',label='Choice',items=['A'],**attributes)])
                before=form.dumps()
                with self.assertRaisesRegex(ValueError,'参考表示'):self.preview.set_form(form)
                self.assertEqual(form.dumps(),before)

    def test_vector_image_choice_uses_file_dimensions(self):
        (self.folder/'image.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="45" height="30"><rect width="45" height="30" fill="red"/></svg>')
        form=Form(gadgets=[Gadget(kind='option',name='Images',label='',display_mode='PIXMAP',
            items=['missing.png','image.svg'],width=45,height=30,initial='2')])
        self.assertEqual(self.show(form)['Images'].entry.iconSize().toTuple(),(45,30))


class AutomaticFormEditingAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.form=Form(size_explicit=False,gadgets=[Gadget(kind='list',name='Part',label='Part',x=0,y=0,width=6,height=3)])
        self.w.selected=0;self.w.refresh();self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def item(self,name='Part'):
        return next(item for item in self.w.scene.items() if isinstance(item,Item) and item.gadget.name==name)
    def drag(self,start,delta,escape=False):
        end=start+delta
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,pos=start)
        QTest.mouseMove(self.w.view.viewport(),end,30)
        if escape:QTest.keyClick(self.w.view,Qt.Key_Escape)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,pos=end);self.app.processEvents()

    def test_drag_beyond_current_auto_form_grows_it_and_undo_restores_it(self):
        before=self.w.form.dumps();start=self.w.view.mapFromScene(self.item().mapToScene(QPointF(25,30)))
        self.drag(start,QPoint(6*SX,2*SY))
        self.assertEqual((self.w.form.named('Part').x,self.w.form.named('Part').y),(6,2))
        self.assertEqual((self.w.form.width,self.w.form.height),(13,6));self.assertFalse(self.w.form.size_explicit)
        self.assertEqual(len(self.w.history),1)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_resize_handle_grows_auto_form_and_escape_restores_it(self):
        before=self.w.form.dumps();item=self.item()
        start=self.w.view.mapFromScene(item.mapToScene(item.handles()['both'].center()))
        self.drag(start,QPoint(4*SX,2*SY),escape=True)
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[])
        item=self.item();start=self.w.view.mapFromScene(item.mapToScene(item.handles()['both'].center()))
        self.drag(start,QPoint(4*SX,2*SY))
        self.assertEqual((self.w.form.named('Part').width,self.w.form.named('Part').height),(10,5))
        self.assertEqual((self.w.form.width,self.w.form.height),(11,6));self.assertFalse(self.w.form.size_explicit)
        # The inferred source size retains its safety allowance; the visible
        # client uses the control extent and adds its border padding separately.
        self.assertEqual(self.w.form_item.body_rect().width(),10*SX)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_empty_auto_form_can_add_standard_size_parts_and_radio_group(self):
        for kind in ('button','frame','rtoggle'):
            with self.subTest(kind=kind):
                self.w.form=Form(size_explicit=False);self.w.selected=None;self.w.refresh()
                before=self.w.form.dumps();self.w.add(kind);self.app.processEvents()
                self.assertGreater(len(self.w.form.gadgets),0)
                self.assertGreaterEqual(self.w.form.gadgets[0].width,18)
                self.assertFalse(self.w.form.size_explicit);self.w.form.validate()
                self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_fixed_frame_limits_still_apply_inside_auto_form(self):
        self.w.form=Form(size_explicit=False,gadgets=[Gadget(kind='frame',name='Group',x=0,y=0,width=6,height=4),
            Gadget(kind='list',name='Part',parent='Group',x=0,width=6,height=3,y=1)])
        self.w.selected=1;self.w.refresh();self.app.processEvents();before=self.w.form.dumps();item=self.item()
        start=self.w.view.mapFromScene(item.mapToScene(item.handles()['width'].center()))
        self.drag(start,QPoint(4*SX,0))
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[])

    def test_auto_form_maximum_and_manual_form_clamp_remain_enforced(self):
        item=self.item();item.setPos(1000*SX,1000*SY)
        self.assertEqual(item.pos(),QPointF(293*SX,296*SY))
        old=copy.deepcopy(self.w.form);self.w.move_committed(old,'Part',293,296);self.app.processEvents()
        self.assertEqual((self.w.form.width,self.w.form.height),(300,300))
        self.assertFalse(self.w.move_selection(.5,.5))
        self.w.form=Form(width=7,height=4,gadgets=[Gadget(kind='list',name='Part',x=0,y=0,width=6,height=3)])
        self.w.selected=0;self.w.refresh();self.item().setPos(50*SX,50*SY)
        self.assertEqual(self.item().pos(),QPointF(SX,SY))

    def test_preview_range_error_is_shown_in_main_window_and_recovery_works(self):
        self.w.form=Form(gadgets=[Gadget(kind='combo',name='Choice',label='Choice',combo_tagwid='1000000000')])
        self.w.refresh();before=self.w.form.dumps();history=list(self.w.history)
        self.w.runtime_action.trigger();self.app.processEvents()
        self.assertFalse(self.w.runtime_action.isChecked());self.assertFalse(self.w.runtime_dialog.isVisible())
        self.assertIn('参考表示',self.w.statusBar().currentMessage())
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,history)
        self.w.form.named('Choice').combo_tagwid='1'
        self.w.runtime_action.trigger();self.app.processEvents();self.assertTrue(self.w.runtime_dialog.isVisible())
