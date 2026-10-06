import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.model import Form,Gadget


class DragTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close()
        self.app.processEvents();self.temp.cleanup()
    def load(self,form,selected=None):
        self.w.form=form;self.w.selected=selected;self.w.history=[];self.w.future=[];self.w.dirty=False
        self.w.refresh();self.app.processEvents()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def gesture(self,item,delta,button=Qt.LeftButton,escape=False,handle=None):
        point=item.handles()[handle].center() if handle else item.boundingRect().center()
        start=self.w.view.mapFromScene(item.mapToScene(point));end=start+delta
        QTest.mousePress(self.w.view.viewport(),button,Qt.NoModifier,start);self.app.processEvents()
        QTest.mouseMove(self.w.view.viewport(),end,30)
        if escape:
            QTest.keyClick(self.w.view.viewport(),Qt.Key_Escape);self.app.processEvents()
            # Holding the mouse after cancellation must not resume the gesture.
            QTest.mouseMove(self.w.view.viewport(),end+QPoint(10,26),30)
        QTest.mouseRelease(self.w.view.viewport(),button,Qt.NoModifier,end);self.app.processEvents()
    def test_relative_dependency_drop_restores_scene_model_and_history(self):
        self.load(Form(gadgets=[Gadget(name='Source',x=2,y=2,width=8),
            Gadget(kind='frame',name='Target',width=30,height=12,layout_mode='RELATIVE',
                xref='Source',yref='Source',xedge='XMAX',yedge='YMIN',xoffset=2)]))
        original=self.w.form.dumps()
        with patch.object(sys,'excepthook') as exceptions:
            self.gesture(self.item('Source'),QPoint(12*SX,2*SY))
        exceptions.assert_not_called()
        self.assertEqual(self.w.form.dumps(),original)
        self.assertEqual(self.item('Source').pos(),QPoint(2*SX,2*SY))
        self.assertEqual(self.w.history,[]);self.assertFalse(self.w.dirty)
        self.assertIn('配置参照',self.w.statusBar().currentMessage())
    def test_existing_invalid_auto_layout_drop_is_rejected_without_exception(self):
        self.load(Form(gadgets=[Gadget(name='Auto',x=2,y=2,layout_mode='AUTO')]))
        with patch.object(sys,'excepthook') as exceptions:
            self.w.move_committed(copy.deepcopy(self.w.form),'Auto',5,5)
            self.app.processEvents()
        exceptions.assert_not_called();self.assertEqual(self.w.history,[])
        self.assertEqual((self.w.form.named('Auto').x,self.w.form.named('Auto').y),(2,2))
    def test_right_and_middle_button_drag_do_not_modify_objects(self):
        for button in (Qt.RightButton,Qt.MiddleButton):
            with self.subTest(button=button):
                self.load(Form(gadgets=[Gadget(name='Run',x=2,y=2,width=8)]))
                original=self.w.form.dumps()
                self.gesture(self.item('Run'),QPoint(30,78),button)
                self.assertEqual(self.w.form.dumps(),original)
                self.assertEqual(self.item('Run').pos(),QPoint(2*SX,2*SY))
                self.assertEqual(self.w.history,[]);self.assertFalse(self.w.dirty)
    def test_secondary_button_does_not_end_active_left_drag(self):
        self.load(Form(gadgets=[Gadget(name='Run',x=2,y=2,width=8)]))
        item=self.item('Run');start=self.w.view.mapFromScene(item.mapToScene(item.boundingRect().center()))
        middle=start+QPoint(10,26);end=start+QPoint(30,78)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(self.w.view.viewport(),middle,30)
        QTest.mousePress(self.w.view.viewport(),Qt.RightButton,Qt.NoModifier,middle)
        QTest.mouseRelease(self.w.view.viewport(),Qt.RightButton,Qt.NoModifier,middle)
        self.app.processEvents()
        self.assertEqual(self.w.history,[])
        QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        self.assertEqual((self.w.form.named('Run').x,self.w.form.named('Run').y),(5,5))
        self.assertEqual(len(self.w.history),1)

    def test_secondary_release_does_not_commit_gadget_or_form_resize(self):
        for selected in (None,0):
            with self.subTest(selected=selected):
                self.load(Form(width=35,height=12,gadgets=[Gadget(name='Run',x=2,y=2,width=8)]),selected)
                item=self.w.form_item if selected is None else self.item('Run')
                start=self.w.view.mapFromScene(item.mapToScene(item.handles()['width'].center()))
                middle=start+QPoint(10,0);end=start+QPoint(20,0)
                QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
                QTest.mouseMove(self.w.view.viewport(),middle,30)
                QTest.mousePress(self.w.view.viewport(),Qt.RightButton,Qt.NoModifier,middle)
                QTest.mouseRelease(self.w.view.viewport(),Qt.RightButton,Qt.NoModifier,middle)
                self.app.processEvents();self.assertEqual(self.w.history,[])
                QTest.mouseMove(self.w.view.viewport(),end,30)
                QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
                self.assertEqual(self.w.form.width if selected is None else self.w.form.named('Run').width,37 if selected is None else 10)
                self.assertEqual(len(self.w.history),1)

    def test_rejected_frame_move_restores_child_preview_positions(self):
        self.load(Form(gadgets=[Gadget(kind='frame',name='Source',x=2,y=2,width=8,height=5),
            Gadget(name='Child',parent='Source',x=1,y=1,width=2,height=1),
            Gadget(kind='frame',name='Target',width=30,height=12,layout_mode='RELATIVE',
                xref='Source',yref='Source',xedge='XMAX',yedge='YMIN',xoffset=2)]))
        original=self.w.form.dumps();positions={i.gadget.name:i.pos() for i in self.w.scene.items() if isinstance(i,Item)}
        with patch.object(sys,'excepthook') as exceptions:
            self.gesture(self.item('Source'),QPoint(12*SX,2*SY))
        exceptions.assert_not_called();self.assertEqual(self.w.form.dumps(),original)
        for name,pos in positions.items():self.assertEqual(self.item(name).pos(),pos)
        self.assertEqual(self.w.history,[]);self.assertFalse(self.w.dirty)

    def test_escape_frame_move_restores_descendants_and_preserves_redo(self):
        self.load(Form(height=30,gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=10,y=3,width=40,height=20,
            tabs=[Gadget(kind='frame',name='Page')]),
            Gadget(kind='frame',name='Inner',parent='Page',x=2,y=3,width=20,height=10),
            Gadget(name='Run',parent='Inner',x=2,y=2,width=8)]))
        original=self.w.form.dumps();positions={i.gadget.name:i.pos() for i in self.w.scene.items() if isinstance(i,Item)}
        redo=Form(title='Redo');self.w.future=[redo]
        self.gesture(self.item('Inner'),QPoint(30,78),escape=True)
        self.assertEqual(self.w.form.dumps(),original)
        for name,pos in positions.items():self.assertEqual(self.item(name).pos(),pos)
        self.assertEqual(self.w.history,[]);self.assertEqual(self.w.future,[redo]);self.assertFalse(self.w.dirty)
        # The next normal drag still commits, and Undo restores local coordinates.
        self.gesture(self.item('Run'),QPoint(20,52))
        self.assertEqual((self.w.form.named('Run').x,self.w.form.named('Run').y),(4,4))
        self.w.undo();self.assertEqual(self.w.form.dumps(),original)
    def test_escape_gadget_resize_restores_size_and_following_geometry(self):
        self.load(Form(gadgets=[Gadget(name='Run',x=2,y=2,width=8),
            Gadget(name='Follower',layout_mode='RELATIVE',xref='Run',yref='Run',xedge='XMAX',xoffset=2)]),0)
        original=self.w.form.dumps();follower=self.item('Follower').pos()
        self.gesture(self.item('Run'),QPoint(30,0),escape=True,handle='width')
        self.assertEqual(self.w.form.dumps(),original);self.assertEqual(self.item('Follower').pos(),follower)
        self.assertEqual(self.w.fields['width'].value(),8)
        self.assertEqual(self.w.history,[]);self.assertFalse(self.w.dirty)
    def test_escape_form_resize_restores_boundary_and_properties(self):
        self.load(Form(width=35,height=12,gadgets=[Gadget(name='Run',x=2,y=2,width=8)]))
        original=self.w.form.dumps()
        self.gesture(self.w.form_item,QPoint(20,26),escape=True,handle='both')
        self.assertEqual(self.w.form.dumps(),original)
        self.assertEqual((self.w.form_item._width,self.w.form_item._height),(35,12))
        self.assertEqual((self.w.fw.value(),self.w.fh.value()),(35,12))
        self.assertEqual(self.w.history,[]);self.assertFalse(self.w.dirty)
