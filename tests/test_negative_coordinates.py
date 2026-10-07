import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QGraphicsScene,QStyleOptionGraphicsItem

from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget


SOURCE="""Setup Form !!Demo Size 80 60 Dialog
Button .Root At X -2 Y -0.5 'Root' Width 6
Frame .Group At X -1 Y -1 'Group' Width 20 Height 10
List .Child At X -2 Y -1 'Child' Single Width 6 Height 3
Exit
Exit
Show !!Demo"""


class NegativeCoordinateModelTests(unittest.TestCase):
    def test_mac_json_and_export_preserve_negative_at_and_parent(self):
        f=import_mac(SOURCE).form
        self.assertEqual(import_mac(SOURCE,partial=True).form.dumps(),f.dumps())
        self.assertEqual(Form.loads(f.dumps()).dumps(),f.dumps())
        restored=import_mac(f.pml()).form
        for g in f.gadgets:
            self.assertEqual(restored.geometry(restored.named(g.name)),f.geometry(g))
            self.assertEqual(restored.named(g.name).parent,g.parent)

    def test_copy_preserves_negative_coordinates(self):
        f=import_mac(SOURCE).form;before=f.dumps()
        copied,index=clone_subtree(Form(width=80,height=60),f,1)
        root=copied.gadgets[index];child=copied.children(root.name)[0]
        self.assertEqual((root.x,root.y),(-1,-1));self.assertEqual((child.x,child.y),(-2,-1))
        self.assertEqual(f.dumps(),before)

    def test_entirely_clipped_objects_are_still_valid(self):
        f=Form(gadgets=[Gadget(x=-100,y=-50,width=6)])
        f.validate();self.assertEqual(Form.loads(f.dumps()).gadgets[0].x,-100)
        self.assertEqual(import_mac(f.pml()).form.gadgets[0].x,-100)

    def test_negative_resolved_relative_and_path_positions_are_valid(self):
        f=Form(gadgets=[Gadget(name='Base',x=0,y=0,width=6),
            Gadget(name='Relative',layout_mode='RELATIVE',xref='Base',yref='Base',xoffset=-2,yoffset=-2,width=6),
            Gadget(name='Next',layout_mode='AUTO',path='LEFT',width=6)])
        f.validate();r=import_mac(f.pml()).form
        for g in f.gadgets:self.assertEqual(r.geometry(r.named(g.name)),f.geometry(g))

    def test_invalid_sizes_nonfinite_coordinates_and_right_bottom_overflow_still_fail(self):
        for kwargs in ({'x':float('nan')},{'y':float('-inf')},{'width':-1},{'height':-1},{'x':79},{'y':60}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):Form(width=80,height=60,gadgets=[Gadget(**kwargs)]).validate()


class NegativeCoordinatePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def draw(self,item,selected=False):
        item.setSelected(selected)
        image=QImage(160,140,QImage.Format_ARGB32);image.fill(Qt.transparent)
        painter=QPainter(image);painter.translate(20,20)
        try:item.paint(painter,QStyleOptionGraphicsItem())
        finally:painter.end()
        return image

    def load(self,nested=False,table=False):
        gadgets=[Gadget(kind='frame',name='Group',x=4,y=3,width=20,height=10)] if nested else []
        child=Gadget(kind='list',name='Child',label='',x=-2,y=-1,width=6,height=3,parent='Group' if nested else '')
        if table:child.list_mode='TABLE';child.headings=['Col'];child.rows=[['One'],['Two']]
        f=Form(gadgets=[*gadgets,child]);f.validate()
        scene=QGraphicsScene();items=[Item(g,f) for g in f.gadgets]
        for item in items:scene.addItem(item)
        return scene,items[-1]

    def test_content_is_clipped_at_form_and_frame_but_selected_outline_remains(self):
        for nested in (False,True):
            with self.subTest(nested=nested):
                scene,item=self.load(nested);image=self.draw(item)
                self.assertEqual(image.pixelColor(30,30).alpha(),0)
                self.assertGreater(image.pixelColor(55,60).alpha(),0)
                self.assertFalse(item.shape().contains(QPointF(5,5)))
                self.assertTrue(item.shape().contains(QPointF(35,40)))
                selected=self.draw(item,True)
                self.assertEqual(selected.pixelColor(30,30).alpha(),0)
                self.assertEqual(selected.pixelColor(21,21).name(),'#2277cc')
                self.assertTrue(item.shape().contains(QPointF(5,5)))

    def test_table_inner_clip_does_not_override_parent_clip(self):
        scene,item=self.load(True,True);image=self.draw(item)
        self.assertEqual(image.pixelColor(30,30).alpha(),0)
        self.assertGreater(image.pixelColor(55,60).alpha(),0)

    def test_pixmap_is_clipped_without_resizing_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'image.png';img=QImage(60,52,QImage.Format_ARGB32);img.fill(Qt.green);img.save(str(path))
            g=Gadget(kind='paragraph',name='Image',x=-2,y=-.5,display_mode='PIXMAP',pixmap_path=str(path),width=60,height=52)
            f=Form(gadgets=[g]);scene=QGraphicsScene();item=Item(g,f);scene.addItem(item)
            image=self.draw(item)
            self.assertEqual(image.pixelColor(30,30).alpha(),0)
            self.assertEqual(image.pixelColor(55,50),QColor(Qt.green))
            self.assertEqual((g.width,g.height),(60,52))

    def test_all_ancestor_boundaries_and_live_parent_positions_are_used(self):
        f=Form(gadgets=[Gadget(kind='frame',name='Outer',x=-3,y=-2,width=30,height=20),
            Gadget(kind='frame',name='Inner',parent='Outer',x=1,y=1,width=20,height=10),
            Gadget(kind='list',name='Child',label='',parent='Inner',x=1,y=0,width=6,height=3)])
        scene=QGraphicsScene();items=[Item(g,f) for g in f.gadgets]
        for item in items:scene.addItem(item)
        child=items[-1];image=self.draw(child)
        self.assertEqual(image.pixelColor(25,25).alpha(),0)
        self.assertGreater(image.pixelColor(55,60).alpha(),0)
        scene2,item=self.load(True);parent=next(i for i in scene2.items() if isinstance(i,Item) and i.gadget.name=='Group')
        before=item.content_clip_rect().left();parent.setPos(parent.pos()+QPointF(10,0))
        self.assertEqual(item.content_clip_rect().left(),before+10)

    def test_fully_clipped_object_can_be_selected_from_tree(self):
        g=Gadget(kind='list',name='Gone',label='',x=-10,y=-10,width=6,height=3)
        f=Form(gadgets=[g]);scene=QGraphicsScene();item=Item(g,f);scene.addItem(item)
        image=self.draw(item);self.assertTrue(item.shape().isEmpty())
        self.assertFalse(any(image.pixelColor(x,y).alpha() for x in range(20,80) for y in range(20,98)))
        selected=self.draw(item,True);self.assertEqual(selected.pixelColor(21,21).name(),'#2277cc')

    def test_tab_child_does_not_paint_into_header(self):
        f=Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=3,y=2,width=30,height=10,
            tabs=[Gadget(kind='frame',name='Page',width=30,height=10)]),
            Gadget(kind='list',name='Child',label='',parent='Page',x=-2,y=-1,width=6,height=3)])
        scene=QGraphicsScene();items=[Item(g,f) for g in f.gadgets]
        for item in items:scene.addItem(item)
        item=next(i for i in items if i.gadget.name=='Child');image=self.draw(item)
        self.assertEqual(image.pixelColor(55,60).alpha(),0)
        self.assertGreater(image.pixelColor(55,80).alpha(),0)


class NegativeCoordinateGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.directory=Path(self.folder.name)
        self.w=Window(settings_path=self.directory/'settings.json');self.w.show()
        self.w.form=import_mac(SOURCE).form;self.w.selected=2;self.w.refresh();self.app.processEvents();self.w.history.clear()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.folder.cleanup()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)

    def test_application_title_and_executable_build_name(self):
        self.assertTrue(self.w.windowTitle().startswith('FormDesigner'))
        root=Path(__file__).resolve().parents[1]
        for name in ('build_onedir.ps1','EXE_BUILD_ONEDIR.txt'):
            text=(root/name).read_text();self.assertIn('--name FormDesigner',text);self.assertNotIn('E3DFormDesigner',text)

    def test_negative_coordinate_fields_and_keyboard_move_with_undo(self):
        before=self.w.form.dumps()
        self.assertEqual(self.w.fields['x'].value(),-2)
        self.w.fields['x'].setValue(-3);self.w.fields['y'].setValue(-2)
        self.assertEqual((self.w.form.named('Child').x,self.w.form.named('Child').y),(-3,-2))
        self.w.view.setFocus();QTest.keyClick(self.w.view,Qt.Key_Left)
        QTest.keyClick(self.w.view,Qt.Key_Up,Qt.AltModifier)
        g=self.w.form.named('Child');self.assertEqual((g.x,g.y,g.parent),(-3.5,-2.1,'Group'))
        for _ in range(4):self.w.undo()
        self.assertEqual(self.w.form.dumps(),before)

    def test_drag_negative_child_keeps_parent_and_relative_position(self):
        before=self.w.form.dumps();g=self.w.form.named('Child');ox,oy=self.w.form.offset(g)
        item=self.item('Child');item.setPos((ox-3)*SX,(oy-2)*SY)
        self.assertEqual(item.pos(),QPointF((ox-3)*SX,(oy-2)*SY))
        self.w.move_committed(copy.deepcopy(self.w.form),'Child',(ox-3)*SX/SX,(oy-2)*SY/SY)
        self.app.processEvents();g=self.w.form.named('Child')
        self.assertEqual((g.x,g.y,g.parent),(-3,-2,'Group'))
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_negative_objects_do_not_prevent_form_resize(self):
        item=self.w.form_item;before=self.w.form.dumps()
        self.assertTrue(item.resize_to(70,50));self.w.form.validate()
        self.w.resize_committed(Form.loads(before));self.app.processEvents();self.w.undo()
        self.assertEqual(self.w.form.dumps(),before)

    def test_frame_handle_resize_accepts_negative_children_and_undo(self):
        before=self.w.form.dumps();self.w.choose_row(1);item=self.item('Group')
        start=self.w.view.mapFromScene(item.mapToScene(item.handles()['width'].center()))
        end=start+type(start)(SX,0)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,pos=start)
        QTest.mouseMove(self.w.view.viewport(),end)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,pos=end)
        self.app.processEvents()
        self.assertEqual(self.w.form.named('Group').width,21)
        self.assertEqual((self.w.form.named('Child').x,self.w.form.named('Child').y),(-2,-1))
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_actual_mouse_drag_keeps_negative_root_position(self):
        before=self.w.form.dumps();self.w.choose_row(0);self.app.processEvents();item=self.item('Root')
        start=self.w.view.mapFromScene(item.mapToScene(QPointF(51,18)))
        end=start+type(start)(-SX,0)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,pos=start)
        QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,pos=end)
        self.app.processEvents()
        self.assertEqual(self.w.form.named('Root').x,-3)
        self.assertEqual(self.w.form.named('Root').parent,'')
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_large_negative_coordinates_and_selection_outline_scene_bounds(self):
        g=self.w.form.named('Child');g.x=-400;g.y=-400;self.w.refresh()
        self.assertEqual((self.w.fields['x'].value(),self.w.fields['y'].value()),(-400,-400))
        self.assertTrue(self.w.scene.sceneRect().contains(self.item('Child').sceneBoundingRect()))
        self.w.choose_rows([0,2]);self.assertTrue(self.w.scene.sceneRect().contains(self.item('Child').sceneBoundingRect()))

    def test_multiple_selection_can_cross_zero_atomically_and_undo(self):
        before=self.w.form.dumps();self.w.choose_rows([0,2]);self.w.move_selection(-.5,-.5)
        self.assertEqual((self.w.form.named('Root').x,self.w.form.named('Child').x),(-2.5,-2.5))
        self.assertEqual(self.w.form.named('Child').parent,'Group');self.assertEqual(len(self.w.history),1)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_cp932_export_and_reimport_keep_negative_coordinates(self):
        path=self.directory/'output.mac'
        with patch('e3d_designer.app.QMessageBox.warning') as warning,patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(path),'')):
            self.w.export();warning.assert_not_called()
        restored=import_mac(path.read_bytes().decode('cp932')).form
        self.assertEqual((restored.named('Child').x,restored.named('Child').y,restored.named('Child').parent),(-2,-1,'Group'))
