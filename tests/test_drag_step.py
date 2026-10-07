import copy
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QComboBox,QDoubleSpinBox
from e3d_designer.app import Window,Item
from e3d_designer.model import Form,Gadget


class DragStepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.clipboard().clear()
        self.app.processEvents();self.temp.cleanup()
    def load(self,form):
        self.w.form=form;self.w.selected=None;self.w._multi_selection.clear()
        self.w.history=[];self.w.future=[];self.w.dirty=False;self.w.refresh();self.app.processEvents()
    def item(self,name):return next(item for item in self.w.scene.items() if isinstance(item,Item) and item.gadget.name==name)
    def drag(self,name,delta,escape=False):
        item=self.item(name)
        start=self.w.view.mapFromScene(item.mapToScene(item.boundingRect().center()));end=start+delta
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(self.w.view.viewport(),end,30)
        if escape:QTest.keyClick(self.w.view.viewport(),Qt.Key_Escape)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
    def preset(self,value):self.w.drag_step_combo.setCurrentIndex(self.w.drag_step_combo.findData(value))

    def test_default_presets_and_custom_spin_synchronize_without_changing_design(self):
        w=self.w;before=w.form.dumps()
        self.assertIsInstance(w.drag_step_combo,QComboBox);self.assertIsInstance(w.drag_step_spin,QDoubleSpinBox)
        self.assertEqual(w.drag_step,.1);self.assertEqual(w.drag_step_combo.currentData(),.1)
        self.assertTrue(w.drag_step_combo.isVisible());self.assertTrue(w.drag_step_spin.isVisible())
        self.preset(.5);self.assertEqual(w.drag_step,.5)
        w.drag_step_spin.setValue(.3);self.assertEqual(w.drag_step_combo.currentText(),'任意')
        w.drag_step_spin.stepUp();self.assertEqual(w.drag_step,.4)
        w.drag_step_spin.stepUp();self.assertEqual(w.drag_step_combo.currentData(),.5)
        w.drag_step_spin.setValue(0);self.assertEqual(w.drag_step,.1)
        w.refresh();self.assertEqual(w.drag_step,.1)
        self.assertEqual(w.form.dumps(),before);self.assertFalse(w.dirty);self.assertEqual(w.history,[])

    def test_default_drag_snaps_distance_from_start_without_jumping_to_grid(self):
        self.load(Form(gadgets=[Gadget(name='Run',x=1.25,y=2.25,width=8)]))
        before=self.w.form.dumps();self.drag('Run',QPoint(3,13))
        self.assertEqual((self.w.form.named('Run').x,self.w.form.named('Run').y),(1.55,2.75))
        self.assertEqual(len(self.w.history),1)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)
        self.w.redo();self.assertEqual(self.w.form.named('Run').x,1.55)

    def test_custom_step_applies_to_both_axes_and_group_spacing(self):
        self.load(Form(gadgets=[Gadget(name='A',x=2.25,y=2.2,width=8),Gadget(name='B',x=20.4,y=3.4,width=8)]))
        self.w.drag_step_spin.setValue(.3);self.w.choose_rows([0,1]);self.app.processEvents()
        before=self.w.form.dumps();self.drag('A',QPoint(7,10))
        self.assertEqual((self.w.form.named('A').x,self.w.form.named('A').y),(2.85,2.5))
        self.assertEqual((self.w.form.named('B').x,self.w.form.named('B').y),(21.,3.7))
        self.assertEqual(self.w.selection_names(),{'A','B'});self.assertEqual(len(self.w.history),1)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_frame_drag_moves_descendants_once_and_keeps_local_coordinates(self):
        self.load(Form(height=30,gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=3,y=2,width=50,height=25,tabs=[Gadget(kind='frame',name='Page')]),
            Gadget(kind='frame',name='Group',parent='Page',x=4.25,y=3.25,width=20,height=10),Gadget(name='Child',parent='Group',x=2.25,y=2.25,width=8)]))
        self.w.drag_step_spin.setValue(.3);before=self.w.form.dumps();child=self.item('Child').pos();page=self.item('Page').pos()
        self.drag('Group',QPoint(4,8))
        self.assertEqual((self.w.form.named('Group').x,self.w.form.named('Group').y),(4.55,3.55))
        self.assertEqual((self.w.form.named('Child').x,self.w.form.named('Child').y),(2.25,2.25))
        self.assertAlmostEqual(self.item('Child').pos().x()-child.x(),3)
        self.assertAlmostEqual(self.item('Child').pos().y()-child.y(),7.8)
        self.assertEqual(self.item('Page').pos(),page)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_escape_and_substep_drag_preserve_state_and_redo(self):
        self.load(Form(gadgets=[Gadget(name='Run',x=2.25,y=2.25,width=8)]))
        self.preset(1.);before=self.w.form.dumps();redo=Form(title='Redo');self.w.future=[redo]
        self.drag('Run',QPoint(2,3))
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[]);self.assertEqual(self.w.future,[redo])
        self.drag('Run',QPoint(20,26),escape=True)
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[]);self.assertEqual(self.w.future,[redo])
        self.assertFalse(self.w.dirty)

    def test_path_lock_and_keyboard_use_selected_movement_step(self):
        self.load(Form(gadgets=[Gadget(name='Base',x=2,y=2,width=8),Gadget(name='Auto',layout_mode='AUTO',width=8)]))
        self.preset(2.);before=self.w.form.dumps();self.drag('Auto',QPoint(20,26))
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[])
        self.w.choose_row(0);self.w.view.setFocus()
        QTest.keyClick(self.w.view.viewport(),Qt.Key_Right);self.app.processEvents()
        self.assertEqual(self.w.form.named('Base').x,4)
        QTest.keyClick(self.w.view.viewport(),Qt.Key_Right,Qt.AltModifier);self.app.processEvents()
        self.assertEqual(self.w.form.named('Base').x,6)

    def test_default_and_custom_keyboard_steps_in_all_directions_at_different_zooms(self):
        for step,zoom in ((.1,100),(.3,200),(2.,50)):
            with self.subTest(step=step,zoom=zoom):
                self.load(Form(gadgets=[Gadget(name='Run',x=10,y=10,width=8)]))
                self.w.drag_step_spin.setValue(step);self.w.view.set_zoom(zoom)
                self.w.choose_row(0);self.w.view.setFocus();before=self.w.form.dumps()
                for key,modifier,dx,dy in ((Qt.Key_Right,Qt.NoModifier,step,0),
                    (Qt.Key_Down,Qt.AltModifier,step,step),(Qt.Key_Left,Qt.AltModifier,0,step),
                    (Qt.Key_Up,Qt.NoModifier,0,0)):
                    QTest.keyClick(self.w.view.viewport(),key,modifier);self.app.processEvents()
                    gadget=self.w.form.named('Run')
                    self.assertAlmostEqual(gadget.x,10+dx);self.assertAlmostEqual(gadget.y,10+dy)
                self.assertEqual(len(self.w.history),4)
                for _ in range(4):self.w.undo()
                self.assertEqual(self.w.form.dumps(),before)
