import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.model import Form,Gadget


class TabsetDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def load(self,form):
        self.w.form=form;self.w.selected=None;self.w._multi_selection.clear();self.w.active_pages.clear()
        self.w.history=[];self.w.future=[];self.w.dirty=False;self.w.refresh();self.app.processEvents()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def positions(self):return {g.name:self.item(g.name).pos() for g in self.w.form.gadgets}
    def assert_model_positions(self):
        for g in self.w.form.gadgets:
            x,y,_,_=self.w.form.geometry(g);ox,oy=self.w.form.offset(g)
            self.assertAlmostEqual(self.item(g.name).pos().x(),(x+ox)*SX,msg=g.name)
            self.assertAlmostEqual(self.item(g.name).pos().y(),(y+oy)*SY,msg=g.name)
    def start_drag(self,name,page=0,delta=QPoint(30,52),wait=True,modifiers=Qt.NoModifier):
        item=self.item(name);pages=self.w.form.children(name)
        point=QPointF((page+.5)*item.boundingRect().width()/len(pages),12)
        start=self.w.view.mapFromScene(item.mapToScene(point));end=start+delta
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,modifiers,start)
        if wait:self.app.processEvents()
        QTest.mouseMove(self.w.view.viewport(),end,30)
        return end
    def finish_drag(self,end,modifiers=Qt.NoModifier):
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,modifiers,end);self.app.processEvents()
    def nested_form(self):
        return Form(height=30,gadgets=[Gadget(kind='frame',name='Outer',x=3,y=2,width=55,height=25),
            Gadget(kind='frame',name='Tabs',parent='Outer',frame_style='TABSET',x=10,y=3,width=40,height=20,
                tabs=[Gadget(kind='frame',name='PageA',label='A'),Gadget(kind='frame',name='PageB',label='B')]),
            Gadget(kind='frame',name='Group',parent='PageA',x=2,y=2,width=20,height=10),
            Gadget(name='Child',parent='Group',x=1,y=2,width=8),
            Gadget(name='HiddenChild',parent='PageB',x=2,y=3,width=8)])

    def test_added_tabset_header_drag_follows_both_pages_and_commits_once(self):
        w=self.w;w.palette_actions['tabset'].trigger();self.app.processEvents()
        tabs=w.form.gadgets[w.selected];pages=w.form.children(tabs.name)
        before=w.form.dumps();history=len(w.history);positions=self.positions()
        end=self.start_drag(tabs.name)
        for name,position in positions.items():self.assertEqual(self.item(name).pos(),position+QPoint(30,52),name)
        self.finish_drag(end)
        self.assertEqual((w.form.named(tabs.name).x,w.form.named(tabs.name).y),(tabs.x+3,tabs.y+2))
        for page in pages:self.assertEqual((w.form.named(page.name).x,w.form.named(page.name).y),(0,0))
        self.assertEqual(len(w.history),history+1);self.assertTrue(w.dirty);self.assertEqual(w.selected,0)
        self.assert_model_positions();self.assertEqual(w.validation_error,'')
        moved=w.form.dumps()
        for page in reversed(pages):
            w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name==page.name))
            self.assert_model_positions();self.assertEqual(w.form.dumps(),moved)
        w.undo();self.assertEqual(w.form.dumps(),before);self.assert_model_positions()
        w.redo();self.assertEqual(w.form.dumps(),moved);self.assert_model_positions()
        w.form=Form.loads(moved);w.refresh();self.assert_model_positions()

    def test_header_drag_without_event_loop_between_press_and_move(self):
        w=self.w;w.palette_actions['tabset'].trigger();self.app.processEvents()
        tabs=w.form.gadgets[w.selected];history=len(w.history)
        end=self.start_drag(tabs.name,wait=False);self.finish_drag(end)
        self.assertEqual((w.form.named(tabs.name).x,w.form.named(tabs.name).y),(3,2))
        self.assertEqual(len(w.history),history+1);self.assert_model_positions()

    def test_nested_tabset_drag_preserves_ancestor_and_local_child_coordinates(self):
        w=self.w;self.load(self.nested_form());original=w.form.dumps();positions=self.positions()
        end=self.start_drag('Tabs',page=1,delta=QPoint(30,13))
        self.assertEqual(self.item('Outer').pos(),positions['Outer'])
        for name in ('Tabs','PageA','PageB','Group','Child','HiddenChild'):
            self.assertEqual(self.item(name).pos(),positions[name]+QPoint(30,13),name)
        self.finish_drag(end)
        self.assertEqual((w.form.named('Tabs').parent,w.form.named('Tabs').x,w.form.named('Tabs').y),('Outer',13,3.5))
        self.assertEqual((w.form.named('Outer').x,w.form.named('Outer').y),(3,2))
        self.assertEqual((w.form.named('Child').x,w.form.named('Child').y),(1,2))
        self.assertEqual((w.form.named('HiddenChild').x,w.form.named('HiddenChild').y),(2,3))
        self.assertEqual(w.active_pages['tabs'],'pagea');self.assertEqual(len(w.history),1)
        self.assert_model_positions();w.undo();self.assertEqual(w.form.dumps(),original)

    def test_header_click_with_small_jitter_switches_page_without_moving(self):
        w=self.w;self.load(self.nested_form());original=w.form.dumps();positions=self.positions()
        end=self.start_drag('Tabs',page=1,delta=QPoint(2,2));self.finish_drag(end)
        self.assertEqual(w.active_pages['tabs'],'pageb');self.assertEqual(w.form.gadgets[w.selected].name,'PageB')
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[]);self.assertFalse(w.dirty)
        self.assertEqual(self.positions(),positions);self.assert_model_positions()

    def test_header_drag_escape_restores_all_pages_without_switch_or_commit(self):
        w=self.w;self.load(self.nested_form());original=w.form.dumps();positions=self.positions()
        end=self.start_drag('Tabs',page=1)
        QTest.keyClick(w.view.viewport(),Qt.Key_Escape);self.app.processEvents()
        self.assertEqual(self.positions(),positions)
        QTest.mouseMove(w.view.viewport(),end+QPoint(20,26),30);self.finish_drag(end+QPoint(20,26))
        self.assertEqual(self.positions(),positions);self.assertEqual(w.form.dumps(),original)
        self.assertEqual(w.history,[]);self.assertFalse(w.dirty);self.assertEqual(w.active_pages['tabs'],'pagea')

    def test_parent_and_tabset_group_drag_moves_ancestor_only_once(self):
        w=self.w;self.load(self.nested_form());original=w.form.dumps();positions=self.positions()
        w.choose_rows([0,1]);end=self.start_drag('Tabs',delta=QPoint(30,13))
        for name,position in positions.items():self.assertEqual(self.item(name).pos(),position+QPoint(30,13),name)
        self.finish_drag(end)
        self.assertEqual((w.form.named('Outer').x,w.form.named('Outer').y),(6,2.5))
        self.assertEqual((w.form.named('Tabs').x,w.form.named('Tabs').y),(10,3))
        self.assertEqual(w.selection_names(),{'Outer','Tabs'});self.assertEqual(len(w.history),1)
        self.assert_model_positions();w.undo();self.assertEqual(w.form.dumps(),original)

    def test_relative_tabset_header_drag_does_not_move_only_its_outline(self):
        w=self.w;self.load(Form(gadgets=[Gadget(name='Base',x=2,y=2,width=8),
            Gadget(kind='frame',name='Tabs',frame_style='TABSET',layout_mode='RELATIVE',xref='Base',yref='Base',
                xedge='XMAX',yedge='YMIN',xoffset=2,yoffset=0,width=30,height=15,
                tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')])]))
        original=w.form.dumps();positions=self.positions();end=self.start_drag('Tabs',page=1)
        self.assertEqual(self.positions(),positions);self.finish_drag(end)
        self.assertEqual(self.positions(),positions);self.assertEqual(w.form.dumps(),original)
        self.assertEqual(w.history,[]);self.assertFalse(w.dirty);self.assert_model_positions()

    def test_ctrl_header_selection_gesture_does_not_start_native_drag(self):
        w=self.w;self.load(self.nested_form());w.choose_row(1)
        original=w.form.dumps();positions=self.positions()
        end=self.start_drag('Tabs',modifiers=Qt.ControlModifier)
        self.assertEqual(self.positions(),positions);self.finish_drag(end,Qt.ControlModifier)
        self.assertEqual(self.positions(),positions);self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
