import copy
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window,Item
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget


def frame(name='Group',**kwargs):
    return Gadget(kind='frame',name=name,width=20,height=10,frame_size_axes='WH',**kwargs)


class NegativeCoordinateAuditModelTests(unittest.TestCase):
    def test_negative_new_frame_position_is_not_lost_on_export(self):
        for x,y in ((-2,1),(2,-1),(-2,-1)):
            with self.subTest(x=x,y=y):
                f=Form(gadgets=[frame(x=x,y=y)]);before=f.dumps()
                code=f.pml();r=import_mac(code).form
                self.assertEqual(r.geometry(r.named('Group')),f.geometry(f.named('Group')))
                self.assertEqual(f.dumps(),before)
                self.assertEqual(import_mac(code,partial=True).form.dumps(),r.dumps())

    def test_nested_new_negative_frame_keeps_local_position(self):
        f=Form(width=80,height=60,gadgets=[Gadget(kind='frame',name='Outer',x=4,y=3,width=30,height=20,frame_at=True,frame_size_axes='WH'),
            frame(name='Inner',parent='Outer',x=-2,y=-1),Gadget(name='Child',parent='Inner',x=1,y=1,width=6)])
        r=import_mac(f.pml()).form
        for g in f.gadgets:self.assertEqual(r.geometry(r.named(g.name)),f.geometry(g))
        self.assertEqual(r.offset(r.named('Child')),f.offset(f.named('Child')))

    def test_detached_frame_copy_preserves_positive_absolute_position(self):
        f=Form(width=80,height=60,gadgets=[Gadget(kind='frame',name='Outer',x=4,y=3,width=30,height=20),
            Gadget(kind='frame',name='Inner',parent='Outer',x=2,y=2,width=10,height=8,frame_size_axes='WH'),
            Gadget(name='Child',parent='Inner',x=1,y=1,width=6)])
        original=f.dumps();cloned,index=clone_subtree(Form(),f,1)
        root=cloned.gadgets[index];self.assertTrue(root.frame_at);self.assertEqual((root.x,root.y),(6,5))
        r=import_mac(cloned.pml()).form
        self.assertEqual(r.geometry(r.named(root.name)),cloned.geometry(root));self.assertEqual(f.dumps(),original)


class NegativeCoordinateAuditGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show();self.load(Form(gadgets=[frame(x=4,y=3)]))
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def load(self,f,index=0):
        self.w.form=f;self.w.selected=index;self.w._multi_selection.clear();self.w.refresh();self.app.processEvents()
        self.w.history.clear();self.w.future.clear();self.w.dirty=False
    def item(self,name='Group'):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def assert_frame_position_roundtrip(self,name='Group'):
        f=self.w.form;r=import_mac(f.pml()).form
        self.assertEqual(r.geometry(r.named(name))[:2],f.geometry(f.named(name))[:2])

    def test_frame_property_position_edit_is_exported_and_undo_restores_flag(self):
        before=self.w.form.dumps()
        for x,y in ((-2,-1),(6,5)):
            self.w.fields['x'].setValue(x);self.w.fields['y'].setValue(y)
            self.assertTrue(self.w.form.named('Group').frame_at);self.assert_frame_position_roundtrip()
        for _ in range(4):self.w.undo()
        self.assertEqual(self.w.form.dumps(),before)

    def test_frame_label_edit_does_not_add_at_to_unchanged_old_declaration(self):
        self.w.fields['label'].setText('Edited');self.w.update_gadget()
        self.assertFalse(self.w.form.named('Group').frame_at)
        line=next(line for line in self.w.form.pml().splitlines() if 'Frame .Group' in line)
        self.assertNotIn(' At ',line)

    def test_frame_keyboard_movement_is_exported_and_undoable(self):
        before=self.w.form.dumps();self.w.move_selection(.5,.5)
        self.assertTrue(self.w.form.named('Group').frame_at);self.assert_frame_position_roundtrip()
        self.w.move_selection(-6,-6);self.assert_frame_position_roundtrip()
        self.w.undo();self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_frame_canvas_movement_is_exported(self):
        before=self.w.form.dumps();self.w.move_committed(copy.deepcopy(self.w.form),'Group',6,5);self.app.processEvents()
        self.assertTrue(self.w.form.named('Group').frame_at);self.assert_frame_position_roundtrip()
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_frame_tree_move_is_exported_in_destination_coordinates(self):
        self.load(Form(gadgets=[Gadget(kind='frame',name='Target',x=20,y=2,width=30,height=20,frame_at=True,frame_size_axes='WH'),
            frame(name='Moving',x=24,y=4)]),1)
        before=self.w.form.dumps();self.w.move_tree_gadget(1,'Target');self.app.processEvents()
        g=self.w.form.named('Moving');self.assertEqual((g.x,g.y,g.parent),(4,2,'Target'))
        self.assertTrue(g.frame_at);self.assert_frame_position_roundtrip('Moving')
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_negative_wide_or_tall_gadget_can_be_reparented_without_moving_absolute_position(self):
        for x,y,width,height in ((-10,2,20,3),(2,-3,4,8)):
            with self.subTest(x=x,y=y):
                self.load(Form(gadgets=[Gadget(kind='frame',name='Target',x=2,y=2,width=10,height=6,frame_at=True,frame_size_axes='WH'),
                    Gadget(kind='list',name='Moving',x=x,y=y,width=width,height=height)]),1)
                before=self.w.form.dumps();self.w.move_tree_gadget(1,'Target');self.app.processEvents()
                g=self.w.form.named('Moving');self.assertEqual(g.parent,'Target')
                ox,oy=self.w.form.offset(g);self.assertEqual((g.x+ox,g.y+oy),(x,y))
                self.assertEqual((g.width,g.height),(width,height));self.w.form.validate()
                r=import_mac(self.w.form.pml()).form;self.assertEqual(r.geometry(r.named('Moving')),self.w.form.geometry(g))
                self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_oversized_gadget_that_still_overflows_target_is_rejected_atomically(self):
        self.load(Form(gadgets=[Gadget(kind='frame',name='Target',x=2,y=2,width=10,height=6),
            Gadget(kind='list',name='Moving',x=-1,y=2,width=20,height=3)]),1)
        before=self.w.form.dumps();self.w.move_tree_gadget(1,'Target');self.app.processEvents()
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[]);self.assertFalse(self.w.dirty)

    def test_selected_invisible_interior_is_not_a_hit_target_but_border_and_handles_are(self):
        self.load(Form(gadgets=[Gadget(kind='list',name='Moving',x=-10,y=2,width=20,height=3)]))
        item=self.item('Moving')
        self.assertFalse(item.shape().contains(QPointF(50,39)))
        self.assertTrue(item.shape().contains(QPointF(1,39)))
        self.assertTrue(item.shape().contains(QPointF(150,39)))
        for handle in item.handles().values():self.assertTrue(item.shape().contains(handle.center()))
        item.setSelected(False);self.assertFalse(item.shape().contains(QPointF(1,39)))

    def test_clicking_invisible_interior_does_not_select_or_drag_object(self):
        self.load(Form(gadgets=[Gadget(kind='frame',name='Target',x=10,y=2,width=10,height=10,frame_at=True),
            Gadget(kind='list',name='Moving',parent='Target',x=-10,y=1,width=20,height=3)]),1)
        item=self.item('Moving');point=self.w.view.mapFromScene(item.mapToScene(QPointF(50,39)))
        self.assertIsNot(self.w.view.itemAt(point),item);before=self.w.form.dumps()
        end=point+type(point)(10,0)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,pos=point);QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,pos=end);self.app.processEvents()
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[])

    def test_outside_selection_border_is_draggable_and_cancel_restores_position(self):
        self.load(Form(gadgets=[Gadget(kind='list',name='Moving',x=-10,y=2,width=20,height=3)]))
        before=self.w.form.dumps();item=self.item('Moving')
        point=self.w.view.mapFromScene(item.mapToScene(QPointF(1,39)));end=point+type(point)(-10,0)
        self.assertIs(self.w.view.itemAt(point),item)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,pos=point);QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.keyClick(self.w.view.viewport(),Qt.Key_Escape)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,pos=end);self.app.processEvents()
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[])
