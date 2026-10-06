import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt,QPointF
from PySide6.QtWidgets import QApplication,QAbstractItemView
from PySide6.QtTest import QTest
from e3d_designer.app import Window
from e3d_designer.model import Form,Gadget

class ExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def load(self,form):self.w.form=form;self.w.selected=None;self.w.refresh();self.app.processEvents()
    def node(self,name):return self.w.objects.item(next(i for i,g in enumerate(self.w.form.gadgets) if g.name==name))
    def test_nested_folder_tab_hierarchy_and_page_selection(self):
        self.load(Form(gadgets=[Gadget(kind='frame',name='Group',x=1,y=1,width=30,height=15),
            Gadget(kind='frame',name='Inner',parent='Group',x=1,y=1,width=20,height=8),
            Gadget(name='NestedButton',parent='Inner',x=1,y=1,width=8),
            Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=40,y=1,width=25,height=12,tabs=[Gadget(kind='frame',name='PageA',label='A'),Gadget(kind='frame',name='PageB',label='B')]),
            Gadget(name='AButton',parent='PageA',x=1,y=1,width=8),Gadget(name='BButton',parent='PageB',x=1,y=1,width=8)]))
        for name,parent in [('Inner','Group'),('NestedButton','Inner'),('PageA','Tabs'),('PageB','Tabs'),('AButton','PageA'),('BButton','PageB')]:
            self.assertIs(self.node(name).parent(),self.node(parent))
        self.assertIs(self.node('Group').parent(),self.w.objects.root)
        original=self.w.form.dumps();self.w.objects.setCurrentItem(self.node('BButton'));self.app.processEvents()
        self.assertEqual(self.w.active_pages['tabs'],'pageb');self.assertEqual(self.w.form.gadgets[self.w.selected].name,'BButton')
        self.assertEqual(self.w.form.dumps(),original);self.assertEqual(self.w.history,[])
        index=self.w.form.gadgets.index(self.w.form.named('PageA'))
        self.w.objects.move_item(index,'Group');self.app.processEvents();self.assertEqual(self.w.form.dumps(),original)
        self.w.objects.setCurrentItem(self.w.objects.root);self.app.processEvents();self.w.add('button')
        self.assertEqual(self.w.form.gadgets[self.w.selected].parent,'')
    def test_palette_above_explorer_and_folder_state_preserved(self):
        self.load(Form(gadgets=[Gadget(kind='frame',name='Group',width=30,height=10),Gadget(name='Run',parent='Group')]))
        self.assertFalse(self.w.library_panel.isAncestorOf(self.w.palette_panel))
        self.assertLessEqual(self.w.palette_panel.height(),60)
        self.assertTrue(all(b.isVisible() and b.height()<=25 for b in self.w.palette_buttons.values()))
        self.node('Group').setExpanded(False);self.w.refresh();self.assertFalse(self.node('Group').isExpanded())
        self.w.objects.setCurrentItem(self.w.objects.root);self.app.processEvents();self.assertIsNone(self.w.selected)
        self.assertEqual(self.w.selection_stack.currentIndex(),0)
    def test_drop_into_frame_changes_parent_and_preserves_children_with_undo(self):
        self.load(Form(gadgets=[Gadget(kind='frame',name='Destination',x=20,y=2,width=30,height=15),
            Gadget(kind='frame',name='Moving',x=2,y=2,width=15,height=8),Gadget(name='Child',parent='Moving',x=2,y=1,width=8)]))
        original=self.w.form.dumps();tree=self.w.objects;tree._drag_index=1
        event=Mock();event.source.return_value=tree;event.position.return_value=QPointF(tree.visualItemRect(self.node('Destination')).center())
        with patch.object(tree,'dropIndicatorPosition',return_value=QAbstractItemView.OnItem):tree.dropEvent(event)
        self.app.processEvents();event.accept.assert_called_once()
        self.assertEqual(self.w.form.named('Moving').parent,'Destination')
        self.assertEqual((self.w.form.named('Child').parent,self.w.form.named('Child').x,self.w.form.named('Child').y),('Moving',2,1))
        self.assertIs(self.node('Moving').parent(),self.node('Destination'));self.w.form.validate()
        self.assertEqual(len(self.w.history),1);self.w.undo();self.assertEqual(self.w.form.dumps(),original)
        self.w.redo();self.assertEqual(self.w.form.named('Moving').parent,'Destination')
    def test_cyclic_and_small_target_and_tab_page_moves_are_rejected(self):
        self.load(Form(gadgets=[Gadget(kind='frame',name='Group',width=30,height=12),Gadget(kind='frame',name='Inner',parent='Group',x=1,y=1,width=20,height=8),
            Gadget(name='Run',parent='Inner',x=1,y=1,width=8),Gadget(kind='frame',name='Small',x=40,y=1,width=4,height=2)]))
        original=self.w.form.dumps()
        for source,parent in [(0,'Inner'),(1,'Small'),(2,'Run')]:self.w.objects.move_item(source,parent);self.app.processEvents();self.assertEqual(self.w.form.dumps(),original)
        self.assertEqual(self.w.history,[])
    def test_drag_uses_model_transaction_without_native_row_removal(self):
        self.load(Form(gadgets=[Gadget(name='First'),Gadget(name='Second',y=4)]))
        tree=self.w.objects;tree.setCurrentItem(self.node('First'));self.app.processEvents()
        def commit(*args):
            self.assertEqual(tree._drag_index,0);tree.move_item(0,'');self.app.processEvents();return Qt.MoveAction
        with patch('e3d_designer.explorer.QDrag') as drag:
            drag.return_value.exec.side_effect=commit;tree.startDrag(Qt.MoveAction)
            drag.return_value.setMimeData.assert_called_once()
        self.assertEqual(tree._drag_index,-1)
        self.assertEqual([g.name for g in self.w.form.gadgets],['Second','First'])
        self.assertEqual(tree.count(),2);self.assertIsNotNone(self.node('First'));self.w.form.validate()

    def test_tree_double_click_edits_gadget_and_root(self):
        self.load(Form(gadgets=[Gadget(name='Run')]))
        def edit_gadget(d):d.fields['label'].setText('Updated');d.accept();return 1
        tree=self.w.objects;point=tree.visualItemRect(self.node('Run')).center()
        with patch('e3d_designer.quick_editor.MiniProperties.exec',autospec=True,side_effect=edit_gadget):
            QTest.mouseClick(tree.viewport(),Qt.LeftButton,Qt.NoModifier,point)
            QTest.mouseDClick(tree.viewport(),Qt.LeftButton,Qt.NoModifier,point);self.app.processEvents()
        self.assertEqual(self.w.form.named('Run').label,'Updated')
        def edit_form(d):d.title.setText('New Form');d.accept();return 1
        point=tree.visualItemRect(tree.root).center()
        with patch('e3d_designer.quick_editor.FormProperties.exec',autospec=True,side_effect=edit_form):
            QTest.mouseClick(tree.viewport(),Qt.LeftButton,Qt.NoModifier,point)
            QTest.mouseDClick(tree.viewport(),Qt.LeftButton,Qt.NoModifier,point);self.app.processEvents()
        self.assertEqual(self.w.form.title,'New Form')
