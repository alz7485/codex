import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QGraphicsItem
from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.model import Form,Gadget


class TabFramePlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.form=Form(height=30,gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=10,y=3,width=40,height=20,
            tabs=[Gadget(kind='frame',name='PageA',label='A'),Gadget(kind='frame',name='PageB',label='B')])])
        self.w.selected=0;self.w.refresh();self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def test_normal_frame_choice_adds_to_active_page_and_is_movable(self):
        w=self.w;original=w.form.dumps();w.palette_actions['frame'].trigger();self.app.processEvents()
        g=w.form.gadgets[w.selected]
        self.assertEqual(g.parent,'PageA');self.assertFalse(w.form.is_tab_page(g))
        self.assertEqual(len(w.form.children('Tabs')),2)
        self.assertTrue(self.item(g.name).flags() & QGraphicsItem.ItemIsMovable)
        self.assertTrue(w.props.isVisible());w.form.validate()
        name=g.name
        w.undo();self.assertEqual(w.form.dumps(),original);w.redo()
        self.assertEqual(w.form.named(name).parent,'PageA')
    def test_active_second_page_is_used_and_local_drag_preserves_tabs(self):
        w=self.w;w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name=='PageB'));w.choose_row(0)
        self.assertIn('PageB',w.placement_hint.text());w.palette_actions['frame'].trigger();self.app.processEvents()
        g=w.form.gadgets[w.selected];self.assertEqual(g.parent,'PageB')
        name=g.name;original=w.form.dumps();item=self.item(name)
        start=w.view.mapFromScene(item.mapToScene(item.boundingRect().center()));end=start+QPoint(3*SX,2*SY)
        x,y=g.x,g.y
        QTest.mousePress(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(w.view.viewport(),end,30);QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end)
        self.app.processEvents();moved=w.form.named(name)
        self.assertEqual((moved.parent,moved.x,moved.y),('PageB',x+3,y+2))
        self.assertEqual((w.form.named('Tabs').x,w.form.named('Tabs').y),(10,3))
        self.assertEqual(w.form.geometry(w.form.named('PageB'))[:2],(0,0))
        self.assertEqual(Form.loads(w.form.dumps()).named(name).parent,'PageB')
        w.undo();self.assertEqual(w.form.dumps(),original)
    def test_explicit_add_page_still_adds_page_when_inner_frame_is_selected(self):
        w=self.w;w.palette_actions['frame'].trigger();self.app.processEvents();original=w.form.dumps()
        w.add_page_button.click();self.app.processEvents();g=w.form.gadgets[w.selected]
        self.assertEqual(g.parent,'Tabs');self.assertTrue(w.form.is_tab_page(g))
        self.assertEqual(len(w.form.children('Tabs')),3)
        self.assertEqual(w.form.geometry(g),(0,0,40,20))
        w.undo();self.assertEqual(w.form.dumps(),original)
    def test_empty_tabset_requires_explicit_page_before_normal_frame(self):
        w=self.w;w.form=Form(gadgets=[Gadget(kind='frame',name='Empty',frame_style='TABSET',width=40,height=12)])
        w.selected=0;w.history=[];w.refresh();self.app.processEvents();original=w.form.dumps()
        w.palette_actions['frame'].trigger();self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
        self.assertIn('＋ タブ',w.statusBar().currentMessage())
        w.add_page_button.click();self.assertEqual(len(w.form.children('Empty')),1);w.form.validate()
    def test_repeated_frame_button_does_not_create_new_pages(self):
        w=self.w;w.palette_actions['frame'].trigger();self.app.processEvents()
        first=w.form.gadgets[w.selected]
        w.choose_row(0);w.palette_buttons['frame'].click();self.app.processEvents()
        second=w.form.gadgets[w.selected]
        self.assertEqual((first.parent,second.parent),('PageA','PageA'))
        self.assertEqual(len(w.form.children('Tabs')),2);w.form.validate()
    def test_tree_drop_into_tabset_keeps_normal_frame_and_child(self):
        w=self.w;w.form.gadgets.extend([Gadget(kind='frame',name='Group',x=2,y=2,width=18,height=5),
            Gadget(name='Child',parent='Group',x=1,y=1,width=8)])
        w.refresh();self.app.processEvents();original=w.form.dumps()
        index=next(i for i,g in enumerate(w.form.gadgets) if g.name=='Group')
        w.move_tree_gadget(index,'Tabs');self.app.processEvents()
        g=w.form.named('Group');self.assertEqual(g.parent,'PageA');self.assertFalse(w.form.is_tab_page(g))
        self.assertEqual(len(w.form.children('Tabs')),2)
        self.assertEqual((w.form.named('Child').parent,w.form.named('Child').x,w.form.named('Child').y),('Group',1,1))
        self.assertEqual(w.form.geometry(g)[2:],(18,5));w.form.validate()
        w.undo();self.assertEqual(w.form.dumps(),original)
    def test_parent_properties_offer_pages_instead_of_tabset_for_normal_frame(self):
        w=self.w;w.palette_actions['frame'].trigger();self.app.processEvents()
        combo=w.fields['parent'];self.assertEqual(combo.findData('Tabs'),-1)
        self.assertGreaterEqual(combo.findData('PageA'),0);self.assertGreaterEqual(combo.findData('PageB'),0)
    def test_empty_tabset_tree_drop_does_not_create_page(self):
        w=self.w;w.form=Form(gadgets=[Gadget(kind='frame',name='Empty',frame_style='TABSET',width=40,height=12),
            Gadget(kind='frame',name='Group',x=45,y=2,width=18,height=5)])
        w.selected=None;w.history=[];w.refresh();self.app.processEvents();original=w.form.dumps()
        w.move_tree_gadget(1,'Empty');self.app.processEvents()
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
        self.assertIn('＋ タブ',w.statusBar().currentMessage())
