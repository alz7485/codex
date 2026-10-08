import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window,Item
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget,Method


def sample():
    return Form(width=120,height=70,gadgets=[
        Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=10,y=5,width=90,height=55,frame_size_axes='WH',
            tabs=[Gadget(kind='frame',name='PageA',label='設備'),Gadget(kind='frame',name='PageB',label='情報')]),
        Gadget(kind='frame',name='Group',parent='PageA',label='Group',x=3,y=4,width=30,height=20,frame_at=True,frame_size_axes='WH'),
        Gadget(kind='text',name='Input',parent='Group',x=1,y=2,width=10,initial='MiXeD'),
        Gadget(name='Run',parent='Group',x=1,y=3,width=8,layout_mode='AUTO',path='DOWN',path_axes='XY',path_row_step=True,
               callback='Changed',body='!this.Input.val = 1\n!this.Shared()'),
        Gadget(name='Relative',parent='Group',width=6,layout_mode='RELATIVE',xref='Input',yref='Input',xedge='XMAX',yedge='YMIN',xoffset=1),
        Gadget(kind='list',name='Rows',parent='PageA',x=40,y=6,width=30,height=6,list_mode='TABLE',headings=['A','B'],rows=[['1','2']],table_method='Populate'),
        Gadget(name='External',parent='PageB',x=1,y=1,width=8),
    ],extra_methods=[Method('Shared',body='!this.Input.val = 2')])


class DuplicateTabPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json');self.w.form=sample();self.w.selected=0
        self.w.refresh();self.w.show();self.app.processEvents()
    def tearDown(self):self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def duplicate(self):
        QTest.mouseClick(self.w.duplicate_page_button,Qt.LeftButton);self.app.processEvents()
        return self.w.form.gadgets[self.w.selected]

    def test_current_page_and_nested_controls_copy_at_same_coordinates_and_activate(self):
        before=self.w.form.dumps();originals={g.name:copy.deepcopy(g) for g in self.w.form.gadgets}
        page=self.duplicate()
        self.assertTrue(self.w.form.is_tab_page(page));self.assertEqual(page.parent,'Tabs')
        self.assertEqual(page.label,'設備 (コピー)')
        self.assertEqual(len(self.w.form.children('Tabs')),3)
        self.assertEqual(self.w.form.geometry(page),(0,0,90,55))
        self.assertEqual(self.w.active_pages['tabs'],page.name.lower())
        self.assertEqual(self.w.page_tabs.tabData(self.w.page_tabs.currentIndex()),page.name)
        group=next(g for g in self.w.form.children(page.name) if g.kind=='frame')
        self.assertEqual((group.x,group.y,group.width,group.height),(3,4,30,20))
        self.assertEqual(len(self.w.form.descendants(page.name)),5)
        visible={i.gadget.name for i in self.w.scene.items() if isinstance(i,Item) and i.isVisible()}
        self.assertIn(group.name,visible);self.assertNotIn('Group',visible)
        for name,g in originals.items():
            actual=copy.deepcopy(self.w.form.named(name))
            if name=='Tabs':actual.tabs=g.tabs
            self.assertEqual(actual,g)
        self.assertEqual(len(self.w.history),1);self.assertTrue(self.w.dirty)
        after=self.w.form.dumps();self.w.undo();self.assertEqual(self.w.form.dumps(),before)
        self.w.redo();self.assertEqual(self.w.form.dumps(),after)

    def test_names_callbacks_paths_relative_refs_and_helper_bodies_are_independent(self):
        page=self.duplicate();group=next(g for g in self.w.form.children(page.name) if g.kind=='frame')
        controls=self.w.form.children(group.name)
        value=next(g for g in controls if g.kind=='text')
        run=next(g for g in controls if g.layout_mode=='AUTO')
        relative=next(g for g in controls if g.layout_mode=='RELATIVE')
        self.assertEqual(value.initial,'MiXeD')
        self.assertEqual(run.path_axes,'XY');self.assertTrue(run.path_row_step)
        self.assertEqual(relative.xref,value.name);self.assertEqual(relative.yref,value.name)
        self.assertNotEqual(run.callback,'Changed');self.assertIn(f'!this.{value.name}.val',run.body)
        helper=next(m for m in self.w.form.extra_methods if m.name!='Shared')
        self.assertIn(f'!this.{helper.name}()',run.body);self.assertIn(f'!this.{value.name}.val',helper.body)
        rows=next(g for g in self.w.form.children(page.name) if g.kind=='list')
        self.assertNotEqual(rows.table_method,'Populate')
        self.assertEqual(rows.headings,['A','B']);self.assertEqual(rows.rows,[['1','2']])
        value.initial='Changed';rows.rows[0][0]='Changed'
        self.assertEqual(self.w.form.named('Input').initial,'MiXeD')
        self.assertEqual(self.w.form.named('Rows').rows,[['1','2']])
        self.w.form.validate()

    def test_selected_child_does_not_limit_copy_and_selected_tab_controls_source(self):
        self.w.choose_row(next(i for i,g in enumerate(self.w.form.gadgets) if g.name=='Input'))
        page=self.duplicate();self.assertEqual(len(self.w.form.descendants(page.name)),5)
        self.w.choose_row(next(i for i,g in enumerate(self.w.form.gadgets) if g.name=='PageB'))
        page=self.duplicate();self.assertEqual(page.label,'情報 (コピー)')
        self.assertEqual(len(self.w.form.children(page.name)),1)

    def test_repeated_copy_has_unique_page_captions_and_new_object_names(self):
        first=self.duplicate()
        self.w.choose_row(next(i for i,g in enumerate(self.w.form.gadgets) if g.name=='PageA'))
        second=self.duplicate()
        self.assertEqual(second.label,'設備 (コピー) 2')
        self.assertNotEqual(first.name,second.name)
        names=[g.name.lower() for g in self.w.form.gadgets]
        self.assertEqual(len(names),len(set(names)));self.w.form.validate()

    def test_json_and_mac_roundtrip_preserve_copied_page_and_internal_positions(self):
        page=self.duplicate();f=Form.loads(self.w.form.dumps());self.assertEqual(f.dumps(),self.w.form.dumps())
        code=f.pml();restored=import_mac(code).form
        self.assertEqual(restored.named(page.name).parent,'Tabs')
        for name in f.descendants(page.name):
            self.assertEqual(restored.named(name).parent,f.named(name).parent)
            self.assertEqual(restored.geometry(restored.named(name)),f.geometry(f.named(name)))
        path=self.folder/'copy.mac'
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(path),'')):self.w.export()
        self.assertEqual(path.read_bytes(),code.replace('\n','\r\n').encode('cp932'))

    def test_empty_tabset_has_add_button_but_no_page_to_duplicate(self):
        self.w.form=Form(gadgets=[Gadget(kind='frame',name='Empty',frame_style='TABSET',width=40,height=12)])
        self.w.selected=0;self.w.refresh()
        self.assertTrue(self.w.add_page_button.isEnabled());self.assertFalse(self.w.duplicate_page_button.isEnabled())
        before=self.w.form.dumps();self.w.duplicate_page();self.assertEqual(self.w.form.dumps(),before)
        self.w.add_page_button.click();self.assertTrue(self.w.duplicate_page_button.isEnabled())

    def test_nested_tabsets_copy_all_pages_and_their_contents(self):
        nested=Gadget(kind='frame',name='NestedTabs',parent='PageA',frame_style='TABSET',x=45,y=22,width=35,height=20,
            frame_size_axes='WH',tabs=[Gadget(kind='frame',name='InnerA',label='A'),Gadget(kind='frame',name='InnerB',label='B')])
        self.w.form=Form(width=120,height=70,gadgets=[*self.w.form.gadgets,nested,
            Gadget(name='InnerControl',parent='InnerB',x=2,y=2,width=8)])
        self.w.selected=0;self.w.refresh();self.app.processEvents()
        page=self.duplicate()
        owner=next(g for g in self.w.form.children(page.name) if g.frame_style=='TABSET')
        pages=self.w.form.children(owner.name)
        self.assertEqual([g.label for g in pages],['A','B'])
        child=self.w.form.children(pages[1].name)[0]
        self.assertEqual((child.x,child.y,child.width),(2,2,8))
        self.assertNotEqual(child.name,'InnerControl')
        self.assertEqual(Form.loads(self.w.form.dumps()).dumps(),self.w.form.dumps())
        restored=import_mac(self.w.form.pml()).form
        self.assertEqual(restored.named(child.name).parent,pages[1].name)

    def test_copy_failure_keeps_form_selection_and_undo_history(self):
        before=self.w.form.dumps();selection=self.w.selected;dirty=self.w.dirty
        with patch('e3d_designer.clipboard.clone_subtree',side_effect=ValueError('部品数は500個まで')):self.w.duplicate_page()
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.selected,selection)
        self.assertEqual(self.w.history,[]);self.assertEqual(self.w.dirty,dirty)
        self.assertIn('タブを複製できません',self.w.statusBar().currentMessage())
