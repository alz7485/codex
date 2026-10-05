import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from e3d_designer.model import Form,Gadget,Menu,MenuItem
from e3d_designer.names import rename,reference_locations
from e3d_designer.name_manager import NameManager
from e3d_designer.app import Window


class RenameTests(unittest.TestCase):
    def test_variable_rename_boundaries_and_code_locations(self):
        form=Form(variables={'value':'literal !!value'},default_body='!!VALUE = !!valueMore',
                  after_show_code='$p !!value',gadgets=[Gadget(command='USE !!value')],
                  menus=[Menu(items=[MenuItem('Run','USE !!value')])])
        updated=rename(form,'variable','value','target')
        self.assertEqual(updated.default_body,'!!target = !!valueMore')
        self.assertEqual(updated.variables,{'target':'literal !!value'})
        self.assertEqual(updated.gadgets[0].command,'USE !!target')
        self.assertEqual(updated.menus[0].items[0].command,'USE !!target')
        self.assertEqual(form.default_body,'!!VALUE = !!valueMore')
        self.assertEqual(len(reference_locations(form,'variable','value')),4)

    def test_object_rename_structured_and_known_code_references(self):
        parent=Gadget(kind='frame',name='group',width=30,height=10)
        child=Gadget(name='child',parent='group')
        sibling=Gadget(name='follow',xref='group',yref='group',width_ref='group',y=14)
        form=Form(gadgets=[parent,child,sibling],default_body='!THIS.group.visible = true\n!!userform.group.val = 1\n!this.groupMore.val = 2\n!this.group()')
        updated=rename(form,'gadget',0,'section')
        self.assertEqual(updated.gadgets[1].parent,'section')
        self.assertEqual(updated.gadgets[2].width_ref,'section')
        self.assertIn('!THIS.section.visible',updated.default_body)
        self.assertIn('!!userform.section.val',updated.default_body)
        self.assertIn('!this.groupMore.val',updated.default_body)
        self.assertIn('!this.group()',updated.default_body)
        retained=rename(form,'gadget',0,'section',False)
        self.assertEqual(retained.default_body,form.default_body)
        self.assertEqual(retained.gadgets[1].parent,'section')

    def test_form_menu_option_and_generated_members(self):
        form=Form(gadgets=[Gadget(kind='option',name='choice',items=['A']),Gadget(kind='container',name='host',y=4)],
                  menus=[Menu(name='tools')],default_body='!!userform._choice.val = 1\n!this.tools.add()\n!this.hostControl.handle()')
        form=rename(form,'form',None,'newform')
        self.assertIn('!!newform._choice',form.default_body)
        form=rename(form,'gadget',0,'mode')
        self.assertIn('!!newform._mode',form.default_body)
        form=rename(form,'menu',0,'actions')
        self.assertIn('!this.actions.add()',form.default_body)
        form=rename(form,'gadget',1,'control')
        self.assertIn('!this.controlControl.handle()',form.default_body)

    def test_bad_or_duplicate_names_do_not_modify_original(self):
        form=Form(variables={'one':'A','two':'B'},gadgets=[Gadget()],menus=[Menu()])
        original=form.dumps()
        for kind,key,name in [('variable','one','TWO'),('gadget',0,'menu1'),('form',None,'one'),('menu',0,'bad name')]:
            with self.subTest(name=name),self.assertRaises(ValueError):rename(form,kind,key,name)
        self.assertEqual(form.dumps(),original)


class ManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.owner=Window();self.owner.form=Form(variables={'value':'A'},gadgets=[Gadget()],default_body='USE !!value')
        self.owner.refresh();self.dialog=NameManager(self.owner);self.dialog.show();self.app.processEvents()
    def tearDown(self):
        self.dialog.close();self.owner.dirty=False;self.owner.close();self.app.processEvents()

    def test_draft_values_rename_apply_and_undo(self):
        editor=self.dialog.variables.cellWidget(0,1);editor.setFocus();editor.selectAll();QTest.keyClicks(editor,'B')
        self.assertEqual(self.owner.form.variables['value'],'A')
        self.assertTrue(self.dialog.rename_entry('variable','value','target'))
        self.assertTrue(self.dialog.apply_changes())
        self.assertEqual(self.owner.form.variables,{'target':'B'})
        self.assertEqual(self.owner.form.default_body,'USE !!target')
        self.owner.undo();self.assertEqual(self.owner.form.variables,{'value':'A'})
        self.owner.redo();self.assertEqual(self.owner.form.variables,{'target':'B'})
        self.assertEqual(Form.loads(self.owner.form.dumps()).variables,{'target':'B'})

    def test_search_add_delete_and_invalid_apply(self):
        self.dialog.search.setText('missing');self.assertTrue(self.dialog.variables.isRowHidden(0))
        self.dialog.add_variable();self.assertEqual(len(self.dialog.draft.variables),2)
        self.dialog.delete_variable();self.assertEqual(len(self.dialog.draft.variables),1)
        self.dialog.variables.setCurrentCell(0,0);self.dialog.delete_variable()
        self.assertEqual(len(self.dialog.draft.variables),1)
        self.assertIn('使用中',self.dialog.status.text())
        self.dialog.draft.variables['bad name']='A'
        self.assertFalse(self.dialog.apply_changes());self.assertEqual(len(self.owner.form.variables),1)

    def test_object_rename_and_cancel_leaves_owner_untouched(self):
        self.assertTrue(self.dialog.rename_entry('gadget',0,'renamed'))
        self.dialog.reject();self.assertEqual(self.owner.form.gadgets[0].name,'button1')
        self.assertFalse(self.owner.dirty)

if __name__=='__main__':unittest.main()
