import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication
from e3d_designer.model import Form,Gadget,Menu
from e3d_designer.names import rename_many
from e3d_designer.name_manager import NameManager,BulkRenameDialog
from e3d_designer.app import Window


class BulkRenameTests(unittest.TestCase):
    def test_simultaneous_swaps_and_structural_references(self):
        form=Form(variables={'one':'A','two':'B'},gadgets=[Gadget(kind='frame',name='first',width=30,height=10),Gadget(kind='frame',name='second',width=30,height=10),Gadget(name='child',parent='first')],default_body='!!one = !!two\n!THIS.first.visible = !!userform.second.visible\n!this.first()')
        result=rename_many(form,[('variable','one','two'),('variable','two','one'),('gadget',0,'second'),('gadget',1,'first')])
        self.assertEqual(result.variables,{'two':'A','one':'B'})
        self.assertEqual(result.gadgets[2].parent,'second')
        self.assertEqual(result.default_body,'!!two = !!one\n!THIS.second.visible = !!userform.first.visible\n!this.first()')
        self.assertEqual(form.gadgets[2].parent,'first')

    def test_form_and_variable_swap_with_members_and_popup(self):
        form=Form(variables={'other':'A'},gadgets=[Gadget(name='first',popup_menu='tools')],menus=[Menu(name='tools',popup=True)],default_body='!!USERFORM.first.val = !!other\n!this.tools.add()\n!!external.first.val = !!otherMore')
        changes=[('form',None,'other'),('variable','other','userform'),('gadget',0,'second'),('menu',0,'actions')]
        result=rename_many(form,changes)
        self.assertEqual(result.default_body,'!!other.second.val = !!userform\n!this.actions.add()\n!!external.first.val = !!otherMore')
        self.assertEqual(result.gadgets[0].popup_menu,'actions')
        retained=rename_many(form,changes,False)
        self.assertEqual(retained.default_body,form.default_body)
        self.assertEqual(retained.gadgets[0].popup_menu,'actions')

    def test_generated_members_and_helpers(self):
        form=Form(gadgets=[Gadget(kind='container',name='host'),Gadget(kind='list',name='rows',list_mode='TABLE',headings=['Value'])],default_body='!this.hostControl.handle()\n!!userform.populate_rows()')
        result=rename_many(form,[('gadget',0,'panel'),('gadget',1,'items')])
        self.assertEqual(result.default_body,'!this.panelControl.handle()\n!!userform.populate_items()')

    def test_failure_is_atomic(self):
        form=Form(variables={'one':'A','two':'B'})
        original=form.dumps()
        for changes in ([('variable','one','two')],[('variable','one','valid'),('variable','two','bad name')],[('variable','one','a'),('variable','one','b')]):
            with self.assertRaises(ValueError):rename_many(form,changes)
            self.assertEqual(form.dumps(),original)


class BulkManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.owner=Window();self.owner.form=Form(variables={'one':'A','two':'B','other':'C'},default_body='!!one = !!two')
        self.owner.refresh();self.manager=NameManager(self.owner)
    def tearDown(self):
        self.manager.close();self.owner.dirty=False;self.owner.close();self.app.clipboard().clear();self.app.processEvents()

    def test_filtered_selection_generation_validation_apply_undo(self):
        self.manager.select_visible();self.manager.search.setText('one')
        self.assertEqual(self.manager.selected_entries(),[('variable','one','one')])
        self.manager.search.clear();self.manager.select_visible()
        dialog=BulkRenameDialog(self.manager,self.manager.selected_entries())
        self.assertFalse(dialog.confirm.isEnabled())
        dialog.numbered.setChecked(True);dialog.base.setText('value');dialog.prefix.setText('p_');dialog.generate()
        self.assertEqual(list(dialog.result_form.variables),['p_value01','p_value02','p_value03'])
        dialog.table.item(1,2).setText('p_value01');self.assertFalse(dialog.confirm.isEnabled())
        dialog.generate();dialog.accept();self.manager.draft=dialog.result_form
        self.assertEqual(list(self.owner.form.variables),['one','two','other'])
        self.manager.apply_changes();self.assertEqual(self.owner.form.default_body,'!!p_value01 = !!p_value02')
        self.owner.undo();self.assertEqual(list(self.owner.form.variables),['one','two','other'])
        dialog.close()

    def test_preview_manual_swap_and_replace(self):
        dialog=BulkRenameDialog(self.manager,[('variable','one','one'),('variable','two','two')])
        dialog.table.item(0,2).setText('two');self.assertFalse(dialog.confirm.isEnabled())
        dialog.table.item(1,2).setText('one');self.assertTrue(dialog.confirm.isEnabled())
        self.assertEqual(dialog.result_form.default_body,'!!two = !!one')
        dialog.find.setText('o');dialog.replacement.setText('x');dialog.suffix.setText('_new');dialog.generate()
        self.assertEqual(list(dialog.result_form.variables),['xne_new','twx_new','other'])
        dialog.reject();self.assertEqual(list(self.manager.draft.variables),['one','two','other'])
        dialog.close()
