import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.model import Form,Gadget
from e3d_designer.name_manager import NameManager
from e3d_designer.names import rename_many
from e3d_designer.recovery import RecoveryStore


class SelectionHandleAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json');self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def load(self,form,selected=None):
        self.w.form=form;self.w.selected=selected;self.w._multi_selection.clear();self.w.active_pages.clear()
        self.w.history=[];self.w.future=[];self.w.dirty=False;self.w.refresh();self.app.processEvents()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def click(self,name,modifiers):
        item=self.item(name);point=self.w.view.mapFromScene(item.mapToScene(item.boundingRect().center()))
        QTest.mouseClick(self.w.view.viewport(),Qt.LeftButton,modifiers,point);self.app.processEvents()
    def select(self,*names):self.w.choose_rows([i for i,g in enumerate(self.w.form.gadgets) if g.name in names]);self.app.processEvents()
    def tree_names(self):return {i.data(0,Qt.UserRole+1) for i in self.w.objects.selectedItems()}
    def resize(self,item,handle,delta=QPoint(20,26),escape=False):
        point=self.w.view.mapFromScene(item.mapToScene(item.handles()[handle].center()))
        self.assertIs(self.w.view.itemAt(point),item)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,point);self.app.processEvents()
        end=point+delta;QTest.mouseMove(self.w.view.viewport(),end,30)
        if escape:QTest.keyClick(self.w.view.viewport(),Qt.Key_Escape)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
    def form_with_hidden_selection(self):
        return Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=2,y=2,width=30,height=15,
            tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')]),
            Gadget(name='Hidden',parent='PageB',x=2,y=2,width=8),
            Gadget(name='Visible',x=42,y=2,width=8),Gadget(name='Extra',x=42,y=5,width=8)])

    def test_ctrl_and_shift_toggle_preserve_hidden_selected_members(self):
        w=self.w
        for modifier in (Qt.ControlModifier,Qt.ShiftModifier):
            with self.subTest(modifier=modifier):
                self.load(self.form_with_hidden_selection());original=w.form.dumps()
                self.select('Hidden','Visible');self.assertFalse(self.item('Hidden').isVisible())
                self.click('Extra',modifier)
                self.assertEqual(w.selection_names(),{'Hidden','Visible','Extra'});self.assertEqual(self.tree_names(),w.selection_names())
                self.assertFalse(w.inspector_tabs.isEnabled());self.assertFalse(self.item('Hidden').isVisible())
                self.click('Extra',modifier)
                self.assertEqual(w.selection_names(),{'Hidden','Visible'});self.assertEqual(self.tree_names(),w.selection_names())
                self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[]);self.assertFalse(w.dirty)

    def test_deselecting_visible_member_reveals_hidden_single_selection(self):
        w=self.w;self.load(self.form_with_hidden_selection());original=w.form.dumps()
        self.select('Hidden','Visible');self.click('Visible',Qt.ControlModifier)
        self.assertEqual(w.selection_names(),{'Hidden'});self.assertEqual(self.tree_names(),{'Hidden'})
        self.assertEqual(w.active_pages['tabs'],'pageb');self.assertTrue(self.item('Hidden').isSelected())
        self.assertTrue(w.inspector_tabs.isEnabled());self.assertEqual(w.fields['name'].text(),'Hidden')
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])

    def test_tabset_all_resize_handles_are_reachable_through_page_frame(self):
        w=self.w
        for handle in ('width','height','both'):
            with self.subTest(handle=handle):
                self.load(Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=2,y=2,width=30,height=15,
                    tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')])]),0)
                original=w.form.dumps();self.resize(self.item('Tabs'),handle)
                expected=(32 if handle in ('width','both') else 30,16 if handle in ('height','both') else 15)
                self.assertEqual((w.form.named('Tabs').width,w.form.named('Tabs').height),expected)
                for name in ('PageA','PageB'):
                    self.assertEqual(w.form.geometry(w.form.named(name)),(0,0,*expected))
                    self.assertEqual(self.item(name).pos(),self.item('Tabs').pos())
                    self.assertEqual((self.item(name)._width,self.item(name)._height),expected)
                self.assertEqual(len(w.history),1);self.assertEqual(w.validation_error,'')
                resized=w.form.dumps();w.undo();self.assertEqual(w.form.dumps(),original)
                w.redo();self.assertEqual(w.form.dumps(),resized)

    def test_tabset_resize_escape_restores_pages_and_history(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=2,y=2,width=30,height=15,
            tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')]),
            Gadget(name='Child',parent='PageA',x=2,y=2,width=8)]),0)
        original=w.form.dumps();self.resize(self.item('Tabs'),'both',escape=True)
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[]);self.assertFalse(w.dirty)
        for name in ('Tabs','PageA','PageB'):self.assertEqual((self.item(name)._width,self.item(name)._height),(30,15))
        self.assertEqual(self.item('Child').pos(),QPoint(4*SX,4*SY))

    def test_form_all_resize_handles_are_reachable_under_full_size_frame(self):
        w=self.w
        for handle in ('width','height','both'):
            with self.subTest(handle=handle):
                self.load(Form(width=40,height=18,gadgets=[Gadget(kind='frame',name='Full',x=0,y=0,width=40,height=18)]))
                original=w.form.dumps();self.resize(w.form_item,handle)
                self.assertEqual((w.form.width,w.form.height),(42 if handle in ('width','both') else 40,19 if handle in ('height','both') else 18))
                self.assertEqual((w.form.named('Full').width,w.form.named('Full').height),(40,18))
                self.assertEqual(self.item('Full').pos(),QPoint(0,0));self.assertEqual(len(w.history),1)
                w.undo();self.assertEqual(w.form.dumps(),original)

    def test_normal_frame_handle_is_reachable_under_overlapping_child(self):
        w=self.w;self.load(Form(gadgets=[Gadget(kind='frame',name='Group',x=2,y=2,width=20,height=10),
            Gadget(name='Child',parent='Group',x=12,y=4.5,width=8)]),0)
        original=w.form.dumps();self.resize(self.item('Group'),'width')
        self.assertEqual(w.form.named('Group').width,22)
        self.assertEqual((w.form.named('Child').x,w.form.named('Child').y),(12,4.5))
        self.assertEqual(len(w.history),1);w.undo();self.assertEqual(w.form.dumps(),original)

    def test_hidden_multi_selection_does_not_enable_tabset_resize_handles(self):
        w=self.w;self.load(self.form_with_hidden_selection());self.select('Tabs','Hidden')
        self.assertFalse(self.item('Hidden').isVisible());self.assertEqual(self.item('Tabs').handles(),{})
        self.assertFalse(w.inspector_tabs.isEnabled());self.assertEqual(w.history,[])

    def test_name_manager_bulk_rename_preserves_multi_selection_and_active_page(self):
        w=self.w;self.load(self.form_with_hidden_selection())
        w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name=='PageB'))
        self.select('Hidden','Visible');original=w.form.dumps();manager=NameManager(w)
        try:
            targets={'Tabs':'RenamedTabs','PageB':'RenamedPage','Hidden':'RenamedHidden','Visible':'RenamedVisible'}
            changes=[('gadget',i,targets[g.name]) for i,g in enumerate(manager.draft.gadgets) if g.name in targets]
            manager.draft=rename_many(manager.draft,changes)
            self.assertTrue(manager.apply_changes());self.app.processEvents()
            self.assertEqual(w.selection_names(),{'RenamedHidden','RenamedVisible'})
            self.assertEqual(self.tree_names(),w.selection_names());self.assertFalse(w.inspector_tabs.isEnabled())
            self.assertEqual(w.active_pages['renamedtabs'],'renamedpage');self.assertTrue(self.item('RenamedHidden').isVisible())
            self.assertEqual(len(w.history),1);w.undo();self.assertEqual(w.form.dumps(),original)
        finally:manager.deleteLater();self.app.processEvents()

    def test_name_manager_renaming_selected_tabset_keeps_active_page(self):
        w=self.w;self.load(self.form_with_hidden_selection())
        w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name=='PageB'));w.choose_row(0)
        manager=NameManager(w)
        try:
            self.assertTrue(manager.rename_entry('gadget',0,'NewTabs'));self.assertTrue(manager.apply_changes())
            self.assertEqual(w.active_pages['newtabs'],'pageb');self.assertTrue(self.item('Hidden').isVisible())
            self.assertEqual(w.form.gadgets[w.selected].name,'NewTabs');self.assertTrue(w.inspector_tabs.isEnabled())
        finally:manager.deleteLater();self.app.processEvents()

    def test_recovery_clears_previous_project_selection_and_active_page(self):
        w=self.w;self.load(self.form_with_hidden_selection())
        abandoned=RecoveryStore(w.recovery.directory);abandoned.write(w.form);abandoned.lock.unlock()
        w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name=='PageB'));self.select('Hidden','Visible')
        self.assertTrue(w.restore_work(abandoned.path))
        self.assertEqual(w.selection_names(),set());self.assertTrue(w.form_item.isSelected())
        self.assertTrue(w.inspector_tabs.isEnabled());self.assertEqual(w.active_pages['tabs'],'pagea')
        self.assertEqual(w.history,[]);self.assertEqual(w.future,[]);self.assertTrue(w.dirty)

    def test_open_and_new_reset_previous_tab_context(self):
        w=self.w;self.load(self.form_with_hidden_selection())
        path=Path(self.temp.name)/'next.json';path.write_text(w.form.dumps(),encoding='utf-8')
        w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name=='PageB'));self.select('Hidden','Visible')
        self.assertTrue(w.open_design(path,confirmed=True))
        self.assertEqual(w.selection_names(),set());self.assertEqual(w.active_pages['tabs'],'pagea')
        self.assertTrue(w.inspector_tabs.isEnabled());self.assertTrue(w.form_item.isSelected())
        w.new();self.assertEqual(w.selection_names(),set());self.assertEqual(w.active_pages,{})
        self.assertEqual(w.form.gadgets,[]);self.assertFalse(w.dirty)
