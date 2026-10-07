import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.model import Form,Gadget,Menu,MenuItem


class MultiSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.load(Form(gadgets=[Gadget(name='A',x=2,y=2,width=8),Gadget(name='B',x=20,y=2,width=8)]))
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def load(self,form):
        self.w.form=form;self.w.selected=None;self.w._multi_selection.clear();self.w.history=[];self.w.future=[];self.w.dirty=False
        self.w.refresh();self.app.processEvents()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def click(self,name,modifiers=Qt.NoModifier):
        item=self.item(name);pos=self.w.view.mapFromScene(item.mapToScene(item.boundingRect().center()))
        QTest.mouseClick(self.w.view.viewport(),Qt.LeftButton,modifiers,pos);self.app.processEvents()
    def selected_tree(self):return {i.data(0,Qt.UserRole) for i in self.w.objects.selectedItems()}
    def key(self,key,modifiers=Qt.NoModifier):
        self.w.view.setFocus();QTest.keyClick(self.w.view.viewport(),key,modifiers);self.app.processEvents()
    def context_menu(self,widget,point):
        event=QContextMenuEvent(QContextMenuEvent.Mouse,point,widget.mapToGlobal(point))
        self.app.sendEvent(widget,event);self.app.processEvents()
        popup=self.app.activePopupWidget();self.assertIsNotNone(popup)
        self.assertIn('子を含めてすべて選択',[a.text() for a in popup.actions()])
        return popup
    def activate_context_selection(self,popup):
        action=next(a for a in popup.actions() if a.text()=='子を含めてすべて選択')
        QTest.mouseClick(popup,Qt.LeftButton,Qt.NoModifier,popup.actionGeometry(action).center())
        self.app.processEvents()
    def test_button_order_in_two_rows(self):
        expected=['button','option','frame','toggle','line','menubar','container','text','paragraph','list','slider','commandline','selector','toolbar']
        self.assertEqual(list(self.w.palette_buttons),expected)
        self.assertEqual(self.w.palette_panel._columns,7)
    def test_canvas_ctrl_selection_tree_sync_and_disabled_inspector(self):
        w=self.w;original=w.form.dumps();self.click('A');self.click('B',Qt.ControlModifier)
        self.assertEqual(w.selection_names(),{'A','B'});self.assertEqual(self.selected_tree(),{0,1})
        self.assertFalse(w.inspector_tabs.isEnabled());self.assertEqual(w.selection_stack.currentIndex(),2)
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
        self.click('B',Qt.ControlModifier)
        self.assertEqual(w.selection_names(),{'A'});self.assertTrue(w.inspector_tabs.isEnabled())
        self.assertEqual(w.fields['name'].text(),'A');self.assertEqual(self.selected_tree(),{0})
    def test_tree_ctrl_selection_selects_canvas_objects(self):
        tree=self.w.objects
        for index,mod in [(0,Qt.NoModifier),(1,Qt.ControlModifier)]:
            point=tree.visualItemRect(tree.item(index)).center()
            QTest.mouseClick(tree.viewport(),Qt.LeftButton,mod,point);self.app.processEvents()
        self.assertEqual(self.w.selection_names(),{'A','B'})
        self.assertEqual({i.gadget.name for i in self.w.scene.selectedItems() if isinstance(i,Item)},{'A','B'})
        self.assertFalse(self.w.inspector_tabs.isEnabled())
    def test_arrow_and_alt_arrow_move_exact_steps_and_undo(self):
        self.click('A');original=self.w.form.dumps()
        self.key(Qt.Key_Right);self.assertEqual(self.w.form.named('A').x,2.1)
        self.key(Qt.Key_Down,Qt.AltModifier);self.assertEqual(self.w.form.named('A').y,2.1)
        self.key(Qt.Key_Left,Qt.AltModifier);self.assertEqual(self.w.form.named('A').x,2)
        self.assertAlmostEqual(self.item('A').pos().x()/SX,2)
        self.assertEqual(len(self.w.history),3)
        for _ in range(3):self.w.undo()
        self.assertEqual(self.w.form.dumps(),original)
    def test_group_key_move_keeps_selection_and_is_one_history_entry(self):
        w=self.w;self.click('A');self.click('B',Qt.ControlModifier);original=w.form.dumps()
        w.drag_step_spin.setValue(.3)
        self.key(Qt.Key_Right,Qt.AltModifier)
        self.assertEqual((w.form.named('A').x,w.form.named('B').x),(2.3,20.3))
        self.assertEqual(w.selection_names(),{'A','B'});self.assertEqual(self.selected_tree(),{0,1})
        self.assertFalse(w.inspector_tabs.isEnabled());self.assertEqual(len(w.history),1)
        w.undo();self.assertEqual(w.form.dumps(),original);self.assertTrue(w.inspector_tabs.isEnabled())
    def test_parent_and_child_selected_move_only_parent_local_coordinate(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Group',x=10,y=3,width=30,height=12),
            Gadget(name='Child',parent='Group',x=2,y=2,width=8)]))
        w.drag_step_spin.setValue(.5)
        w.choose_rows([0,1]);self.app.processEvents();origin=self.item('Child').pos()
        self.key(Qt.Key_Right)
        self.assertEqual(w.form.named('Group').x,10.5);self.assertEqual(w.form.named('Child').x,2)
        self.assertEqual(self.item('Child').pos().x()-origin.x(),.5*SX)
        self.assertEqual(w.selection_names(),{'Group','Child'})
    def test_group_boundary_rejection_is_atomic_and_does_not_create_history(self):
        w=self.w;w.form.named('A').x=w.form.width-w.form.named('A').width;w.refresh();w.choose_rows([0,1])
        original=w.form.dumps();self.key(Qt.Key_Right)
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[]);self.assertFalse(w.dirty)
        self.assertEqual(w.selection_names(),{'A','B'})
    def test_group_drag_and_escape_restore_all_members(self):
        w=self.w;self.click('A');self.click('B',Qt.ControlModifier);original=w.form.dumps()
        item=self.item('A');start=w.view.mapFromScene(item.mapToScene(item.boundingRect().center()));end=start+QPoint(30,52)
        QTest.mousePress(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(w.view.viewport(),end,30);QTest.keyClick(w.view.viewport(),Qt.Key_Escape)
        QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
        self.assertEqual(self.item('A').pos(),QPoint(2*SX,2*SY));self.assertEqual(self.item('B').pos(),QPoint(20*SX,2*SY))
        self.assertEqual(w.selection_names(),{'A','B'})
    def test_group_drag_commits_both_positions_once_and_undo(self):
        w=self.w;self.click('A');self.click('B',Qt.ControlModifier);original=w.form.dumps()
        item=self.item('A');start=w.view.mapFromScene(item.mapToScene(item.boundingRect().center()));end=start+QPoint(30,52)
        QTest.mousePress(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(w.view.viewport(),end,30)
        self.assertEqual(self.item('B').pos(),QPoint(23*SX,4*SY))
        QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        self.assertEqual((w.form.named('A').x,w.form.named('A').y),(5,4))
        self.assertEqual((w.form.named('B').x,w.form.named('B').y),(23,4))
        self.assertEqual(w.selection_names(),{'A','B'});self.assertEqual(len(w.history),1)
        w.undo();self.assertEqual(w.form.dumps(),original)
    def test_alt_key_inside_tab_keeps_parent_position_and_local_coordinates(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=10,y=3,width=30,height=15,
            tabs=[Gadget(kind='frame',name='Page')]),Gadget(name='Child',parent='Page',x=2,y=2,width=8)]))
        self.click('Child');self.key(Qt.Key_Up,Qt.AltModifier)
        self.assertEqual((w.form.named('Child').parent,w.form.named('Child').x,w.form.named('Child').y),('Page',2,1.9))
        self.assertEqual((w.form.named('Tabs').x,w.form.named('Tabs').y),(10,3))
        self.assertAlmostEqual(self.item('Child').pos().y()/SY,4.9)
    def test_relative_layout_key_move_rejected_without_history(self):
        w=self.w;self.load(Form(gadgets=[Gadget(name='A',x=2,y=2,width=8),
            Gadget(name='Follower',layout_mode='RELATIVE',xref='A',yref='A',xedge='XMAX',yedge='YMIN',xoffset=2,width=8)]))
        self.click('Follower');original=w.form.dumps();self.key(Qt.Key_Right)
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
        self.assertIn('座標で移動できません',w.statusBar().currentMessage())
    def test_multi_delete_and_single_undo(self):
        self.click('A');self.click('B',Qt.ControlModifier);original=self.w.form.dumps()
        self.w.delete();self.assertEqual(self.w.form.gadgets,[]);self.assertEqual(len(self.w.history),1)
        self.assertTrue(self.w.inspector_tabs.isEnabled());self.w.undo();self.assertEqual(self.w.form.dumps(),original)
    def test_menu_preview_double_click_opens_editor_without_changing_form(self):
        w=self.w;w.form.menus=[Menu(name='Tools',items=[MenuItem(label='Run')])];w.refresh();self.app.processEvents()
        original=w.form.dumps();point=w.preview_menu_bar.rect().center()
        QTest.mouseDClick(w.preview_menu_bar,Qt.LeftButton,Qt.NoModifier,point);self.app.processEvents()
        self.assertTrue(w.menu_dialog.isVisible());self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
    def test_canvas_frame_context_selects_descendants_and_moves_once(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Group',x=10,y=3,width=35,height=15),
            Gadget(kind='frame',name='Nested',parent='Group',x=2,y=2,width=20,height=8),
            Gadget(name='Child',parent='Nested',x=2,y=2,width=8),
            Gadget(name='Sibling',parent='Group',x=24,y=2,width=8),Gadget(name='Outside',x=50,y=2,width=8)]))
        original=w.form.dumps();item=self.item('Group')
        point=w.view.mapFromScene(item.mapToScene(QPoint(10,35)))
        popup=self.context_menu(w.view.viewport(),point);self.activate_context_selection(popup)
        names={'Group','Nested','Child','Sibling'}
        self.assertEqual(w.selection_names(),names);self.assertEqual(self.selected_tree(),{0,1,2,3})
        self.assertEqual({i.gadget.name for i in w.scene.selectedItems() if isinstance(i,Item)},names)
        self.assertFalse(w.inspector_tabs.isEnabled());self.assertEqual(w.form.dumps(),original)
        self.assertEqual(w.history,[]);self.assertFalse(w.dirty)
        w.drag_step_spin.setValue(.5)
        self.key(Qt.Key_Right)
        self.assertEqual(w.form.named('Group').x,10.5)
        self.assertEqual(w.form.named('Nested').x,2);self.assertEqual(w.form.named('Child').x,2)
        self.assertEqual(w.form.named('Sibling').x,24);self.assertEqual(w.form.named('Outside').x,50)
        self.assertEqual(len(w.history),1);w.undo();self.assertEqual(w.form.dumps(),original)
    def test_tree_frame_context_in_hidden_tab_reveals_and_selects_descendants(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=10,y=3,width=35,height=15,
            tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')]),
            Gadget(name='First',parent='PageA',x=2,y=2,width=8),
            Gadget(kind='frame',name='Group',parent='PageB',x=2,y=2,width=25,height=10),
            Gadget(name='Child',parent='Group',x=2,y=2,width=8)]))
        original=w.form.dumps();self.assertFalse(self.item('Group').isVisible())
        index=next(i for i,g in enumerate(w.form.gadgets) if g.name=='Group')
        point=w.objects.visualItemRect(w.objects.item(index)).center()
        popup=self.context_menu(w.objects.viewport(),point);self.activate_context_selection(popup)
        self.assertEqual(w.selection_names(),{'Group','Child'});self.assertEqual(w.active_pages['tabs'],'pageb')
        self.assertTrue(self.item('Group').isVisible());self.assertTrue(self.item('Child').isSelected())
        self.assertFalse(self.item('First').isVisible());self.assertFalse(w.inspector_tabs.isEnabled())
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
    def test_tabset_context_includes_all_pages_and_hidden_descendants(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=10,y=3,width=35,height=15,
            tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')]),
            Gadget(name='First',parent='PageA',x=2,y=2,width=8),Gadget(name='Second',parent='PageB',x=2,y=2,width=8),
            Gadget(name='Outside',x=50,y=2,width=8)]))
        original=w.form.dumps();w.objects.item(0).setExpanded(False)
        point=w.objects.visualItemRect(w.objects.item(0)).center()
        popup=self.context_menu(w.objects.viewport(),point);self.activate_context_selection(popup)
        self.assertEqual(w.selection_names(),{'Tabs','PageA','PageB','First','Second'})
        self.assertEqual(len(self.selected_tree()),5);self.assertTrue(w.objects.item(0).isExpanded())
        self.assertFalse(w.inspector_tabs.isEnabled());self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
        self.key(Qt.Key_Right,Qt.AltModifier)
        self.assertEqual(w.form.named('Tabs').x,10.1);self.assertEqual(w.form.named('First').x,2)
        self.assertEqual(w.form.named('Second').x,2);self.assertEqual(len(w.selection_names()),5)
        self.assertEqual(len(self.selected_tree()),5)
        w.delete();self.assertEqual([g.name for g in w.form.gadgets],['Outside'])
        w.undo();w.undo();self.assertEqual(w.form.dumps(),original)
    def test_page_frame_context_selects_only_its_page_and_children(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=10,y=3,width=35,height=15,
            tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')]),
            Gadget(name='First',parent='PageA',x=2,y=2,width=8),Gadget(name='Second',parent='PageB',x=2,y=2,width=8)]))
        page=w.form.named('PageA');index=w.form.gadgets.index(page)
        popup=self.context_menu(w.objects.viewport(),w.objects.visualItemRect(w.objects.item(index)).center())
        self.activate_context_selection(popup)
        self.assertEqual(w.selection_names(),{'PageA','First'})
        self.assertFalse(w.inspector_tabs.isEnabled());self.assertEqual(w.history,[])
    def test_empty_frame_context_stays_single_selection_and_enables_inspector(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Empty',x=2,y=2,width=20,height=10)]))
        popup=self.context_menu(w.objects.viewport(),w.objects.visualItemRect(w.objects.item(0)).center())
        self.activate_context_selection(popup)
        self.assertEqual(w.selection_names(),{'Empty'});self.assertTrue(w.inspector_tabs.isEnabled())
        self.assertEqual(w.selected,0);self.assertEqual(w.history,[]);self.assertFalse(w.dirty)
    def test_drag_selection_including_hidden_page_keeps_and_moves_both_members(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=10,y=3,width=35,height=15,
            tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')]),
            Gadget(name='Hidden',parent='PageB',x=2,y=2,width=8),Gadget(name='Outside',x=50,y=2,width=8)]))
        indices=[i for i,g in enumerate(w.form.gadgets) if g.name in ('Hidden','Outside')]
        original=w.form.dumps();w.choose_rows(indices);self.app.processEvents()
        self.assertFalse(self.item('Hidden').isVisible());self.assertEqual(self.item('Outside').handles(),{})
        item=self.item('Outside');start=w.view.mapFromScene(item.mapToScene(item.boundingRect().center()));end=start+QPoint(10,26)
        QTest.mousePress(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(w.view.viewport(),end,30)
        QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        self.assertEqual((w.form.named('Outside').x,w.form.named('Outside').y),(51,3))
        self.assertEqual((w.form.named('Hidden').x,w.form.named('Hidden').y),(3,3))
        self.assertEqual(w.selection_names(),{'Hidden','Outside'});self.assertEqual(self.selected_tree(),set(indices))
        self.assertFalse(w.inspector_tabs.isEnabled());self.assertEqual(len(w.history),1)
        w.undo();self.assertEqual(w.form.dumps(),original)
    def test_menu_title_double_click_closes_preview_popup_and_opens_editor(self):
        w=self.w;w.form.menus=[Menu(name='Tools',items=[MenuItem(label='Run')])];w.refresh();self.app.processEvents()
        point=w.preview_menu_bar.actionGeometry(w.preview_menu_bar.actions()[0]).center()
        QTest.mouseClick(w.preview_menu_bar,Qt.LeftButton,Qt.NoModifier,point);self.app.processEvents()
        self.assertTrue(w.preview_menus[0].isVisible())
        QTest.mouseDClick(w.preview_menu_bar,Qt.LeftButton,Qt.NoModifier,point);self.app.processEvents()
        self.assertTrue(w.menu_dialog.isVisible());self.assertFalse(w.preview_menus[0].isVisible())
        self.assertEqual(w.history,[])
