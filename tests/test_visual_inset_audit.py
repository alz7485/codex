import copy
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.model import Form,Gadget


class VisualInsetAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json');self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.clipboard().clear();self.app.processEvents();self.temp.cleanup()
    def load(self,parts,height=15):
        self.w.form=Form(height=30,gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=2,y=2,width=35,height=height,
            tabs=[Gadget(kind='frame',name='Page')]),*parts])
        self.w.selected=None;self.w._multi_selection.clear();self.w.history=[];self.w.future=[];self.w.dirty=False
        self.w.refresh();self.app.processEvents()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def drag(self,name,delta,escape=False):
        item=self.item(name);point=item.boundingRect().center()
        self.assertTrue(item.shape().contains(point))
        start=self.w.view.mapFromScene(item.mapToScene(point));end=start+delta
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(self.w.view.viewport(),end,30)
        if escape:QTest.keyClick(self.w.view.viewport(),Qt.Key_Escape)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()

    def test_horizontal_drag_near_page_bottom_keeps_owner_and_local_coordinates(self):
        for escape in (False,True):
            with self.subTest(escape=escape):
                self.load([Gadget(name='Run',parent='Page',x=2,y=13.2,width=8)])
                before=self.w.form.dumps();origin=self.item('Run').pos()
                self.drag('Run',QPoint(10,0),escape)
                g=self.w.form.named('Run')
                self.assertEqual((g.parent,g.x,g.y),('Page',2 if escape else 3,13.2))
                self.assertEqual(self.item('Run').pos(),origin+(QPointF() if escape else QPointF(10,0)))
                self.assertEqual(len(self.w.history),0 if escape else 1)
                if not escape:self.w.undo()
                self.assertEqual(self.w.form.dumps(),before)

    def test_last_row_frame_keeps_page_and_child_coordinates(self):
        self.load([Gadget(kind='frame',name='Group',parent='Page',x=2,y=12,width=20,height=3),
            Gadget(name='Child',parent='Group',x=1,y=1,width=8)])
        before=self.w.form.dumps();child=self.item('Child').pos()
        self.drag('Group',QPoint(10,0))
        g=self.w.form.named('Group');self.assertEqual((g.parent,g.x,g.y),('Page',3,12))
        self.assertEqual((self.w.form.named('Child').x,self.w.form.named('Child').y),(1,1))
        self.assertEqual(self.item('Child').pos(),child+QPointF(10,0))
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_page_owner_can_still_change_to_deeper_frame_or_form(self):
        self.load([Gadget(kind='frame',name='Group',parent='Page',x=10,y=4,width=20,height=6),
            Gadget(name='Run',parent='Page',x=2,y=2,width=8)])
        before=self.w.form.dumps();group=self.item('Group')
        point=group.pos()+QPointF(SX,SY)
        self.w.move_committed(copy.deepcopy(self.w.form),'Run',point.x()/SX,point.y()/SY);self.app.processEvents()
        g=self.w.form.named('Run');self.assertEqual((g.parent,g.x,g.y),('Group',1,1))
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)
        point=self.item('Run').pos()+QPointF(40*SX,0)
        self.w.move_committed(copy.deepcopy(self.w.form),'Run',point.x()/SX,point.y()/SY);self.app.processEvents()
        self.assertEqual(self.w.form.named('Run').parent,'')
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_page_shorter_than_header_has_no_out_of_bounds_selection_or_paint(self):
        self.load([],height=1);page=self.item('Page')
        for selected in (False,True):
            with self.subTest(selected=selected):
                page.setSelected(selected)
                self.assertTrue(page.shape().isEmpty())
                image=QImage(320,60,QImage.Format_ARGB32);image.fill(Qt.transparent)
                painter=QPainter(image)
                try:page.paint(painter,None)
                finally:painter.end()
                self.assertFalse(any(image.pixelColor(x,y).alpha() for x in range(image.width()) for y in range(image.height())))
        tabs=self.item('Tabs')
        self.assertEqual(tabs.tab_page_at(QPointF(10,10)).name,'Page')

    def test_incomplete_tiny_button_can_preview_without_bypassing_export_validation(self):
        for height in (.05,.08,.1):
            with self.subTest(height=height):
                self.load([Gadget(name='Tiny',height=height)])
                before=self.w.form.dumps(allow_incomplete=True)
                self.w.toggle_runtime_preview(True);self.app.processEvents()
                preview=self.w.runtime_dialog
                self.assertTrue(preview.isVisible());self.assertIn('Tiny',preview.preview_warning)
                self.assertEqual(preview.controls['Tiny'].height(),1)
                self.assertIsNotNone(self.item('Tiny')._control_pixmap)
                self.assertEqual(self.w.form.dumps(allow_incomplete=True),before)
                self.assertEqual(self.w.history,[]);self.assertFalse(self.w.dirty)
                with self.assertRaises(ValueError):self.w.form.pml()
