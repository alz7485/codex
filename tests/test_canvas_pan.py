import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Item, Window
from e3d_designer.model import Form, Gadget


class CanvasPanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.form=Form(width=40,height=15,gadgets=[
            Gadget(kind='frame',name='Group',label='Group',x=2,y=2,width=25,height=9,frame_at=True),
            Gadget(name='Run',parent='Group',x=2,y=2,width=6)])
        self.w.refresh();self.w.show();self.app.processEvents()
        self.w.choose_row(1);self.app.processEvents()
        self.before=self.w.form.dumps();self.code=self.w.form.pml()
        self.selection=self.w.selection_names();self.w.future=[Form(title='Redo')]

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def item(self):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name=='Run')

    def unchanged(self):
        self.assertEqual(self.w.form.dumps(),self.before);self.assertEqual(self.w.form.pml(),self.code)
        self.assertEqual(self.w.selection_names(),self.selection)
        self.assertEqual(self.w.history,[]);self.assertEqual(self.w.future[0].title,'Redo')
        self.assertFalse(self.w.dirty)

    def pan(self,delta,space=False):
        view=self.w.view;viewport=view.viewport();view.setFocus();self.app.processEvents()
        start=view.mapFromScene(self.item().sceneBoundingRect().center())
        if not viewport.rect().contains(start):start=viewport.rect().center()
        button=Qt.LeftButton if space else Qt.MiddleButton
        before=view.mapFromScene(self.item().scenePos())
        if space:QTest.keyPress(view,Qt.Key_Space)
        QTest.mousePress(viewport,button,Qt.NoModifier,start)
        self.assertTrue(view.panning)
        QTest.mouseMove(viewport,start+delta)
        QTest.mouseRelease(viewport,button,Qt.NoModifier,start+delta)
        if space:QTest.keyRelease(view,Qt.Key_Space)
        self.app.processEvents()
        after=view.mapFromScene(self.item().scenePos())
        self.assertLessEqual((after-before-delta).manhattanLength(),2)
        self.assertFalse(view.panning)

    def test_middle_and_space_pan_over_selected_object_preserve_design(self):
        for zoom,space in ((50,False),(100,True),(200,False),(800,True),(10,False)):
            with self.subTest(zoom=zoom,space=space):
                self.w.view.set_zoom(zoom);self.pan(QPoint(60,40),space);self.unchanged()

    def test_center_button_and_refresh_keep_source_and_view_position(self):
        self.w.pan_center_button.click();self.app.processEvents()
        view=self.w.view;center=view.mapFromScene(self.w.form_item.frame_rect().center())
        self.assertLessEqual((center-view.viewport().rect().center()).manhattanLength(),2)
        self.pan(QPoint(-100,60));before=view.mapToScene(view.viewport().rect().center())
        self.w.refresh();self.app.processEvents()
        after=view.mapToScene(view.viewport().rect().center())
        self.assertLessEqual((after-before).manhattanLength(),2)
        self.unchanged()

    def test_escape_cancels_pan_and_arrows_do_not_move_objects_during_pan(self):
        view=self.w.view;view.setFocus();self.w.pan_center_button.click();self.app.processEvents()
        viewport=view.viewport();start=viewport.rect().center()
        before=view.mapToScene(start)
        QTest.mousePress(viewport,Qt.MiddleButton,Qt.NoModifier,start)
        QTest.mouseMove(viewport,start+QPoint(80,50))
        QTest.keyClick(view,Qt.Key_Right)
        QTest.keyClick(view,Qt.Key_Escape)
        QTest.mouseRelease(viewport,Qt.MiddleButton,Qt.NoModifier,start+QPoint(80,50))
        self.assertFalse(view.panning)
        self.assertLessEqual((view.mapToScene(start)-before).manhattanLength(),2)
        self.unchanged()

    def test_left_drag_after_pan_at_zoom_keeps_child_local_coordinates(self):
        view=self.w.view;view.set_zoom(200);self.w.pan_center_button.click()
        self.pan(QPoint(30,30),True)
        item=self.item();start=view.mapFromScene(item.sceneBoundingRect().center())
        QTest.mousePress(view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(view.viewport(),start+QPoint(20,0))
        QTest.mouseRelease(view.viewport(),Qt.LeftButton,Qt.NoModifier,start+QPoint(20,0))
        self.app.processEvents()
        child=self.w.form.named('Run');parent=self.w.form.named('Group')
        self.assertEqual((child.parent,child.x,child.y),('Group',3,2))
        self.assertEqual((parent.x,parent.y),(2,2))
        self.assertEqual(len(self.w.history),1)
        self.w.undo();self.app.processEvents();self.assertEqual(self.w.form.dumps(),self.before)

    def test_space_focus_loss_clears_pan_mode(self):
        view=self.w.view;view.setFocus();self.app.processEvents()
        QTest.keyPress(view,Qt.Key_Space)
        self.w.zoom_text.setFocus();self.app.processEvents()
        self.assertFalse(view._space_pressed);self.assertFalse(view.panning)
        self.assertNotEqual(view.viewport().cursor().shape(),Qt.OpenHandCursor)

    def test_pan_preserves_multiple_selection_and_path_layout(self):
        self.w.form.gadgets[1].layout_mode='AUTO'
        self.w.form.gadgets.insert(1,Gadget(kind='paragraph',name='Anchor',parent='Group',x=1,y=1,width=5))
        self.w.refresh();self.w.choose_rows([0,2]);self.app.processEvents()
        self.before=self.w.form.dumps();self.code=self.w.form.pml();self.selection=self.w.selection_names()
        self.pan(QPoint(80,-35),True);self.unchanged()
        self.assertEqual(len(self.selection),2)

    def test_resizing_canvas_after_pan_keeps_view_origin(self):
        self.pan(QPoint(70,30))
        view=self.w.view;before=view.mapToScene(QPoint(0,0))
        self.w.resize(self.w.width()+100,self.w.height()+50);self.app.processEvents()
        self.assertLessEqual((view.mapToScene(QPoint(0,0))-before).manhattanLength(),2)
        self.unchanged()

    def test_space_pan_escape_does_not_leave_left_drag_active(self):
        view=self.w.view;view.setFocus();self.app.processEvents()
        viewport=view.viewport();start=viewport.rect().center()
        QTest.keyPress(view,Qt.Key_Space)
        QTest.mousePress(viewport,Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(viewport,start+QPoint(60,30))
        QTest.keyClick(view,Qt.Key_Escape)
        QTest.mouseRelease(viewport,Qt.LeftButton,Qt.NoModifier,start+QPoint(60,30))
        QTest.keyRelease(view,Qt.Key_Space);self.app.processEvents()
        self.assertIsNone(self.w.scene.mouseGrabberItem());self.unchanged()

