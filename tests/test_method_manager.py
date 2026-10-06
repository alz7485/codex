import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog
from e3d_designer.app import Window
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Method,Form,Gadget
from e3d_designer.method_manager import MethodManagerDialog,update_helpers,callers


TEXT="""Setup Form !!Demo Dialog Size 70 22
Button .Run 'Run' Call '!this.Apply()'
Text .Input 'Input' Width 10 Is String
Exit
Show !!Demo
Define Method .Apply()
!this.Helper('value')
Endmethod
Define Method .DEFAULT()
!this.Input.Val = 'Ready'
Endmethod
Define Method .Helper(!value Is String)
$P !value
Endmethod
Define Method .Unused()
-- not statically called
Endmethod"""


class HelperManagerTests(unittest.TestCase):
    def setUp(self):self.form=import_mac(TEXT).form

    def test_only_independent_methods_are_managed(self):
        self.assertEqual([m.name for m in self.form.extra_methods],['Helper','Unused'])
        self.assertEqual(self.form.named('Run').callback,'Apply')
        self.assertEqual(self.form.named('Input').initial,'Ready')
        self.assertIn('Run: body',callers(self.form,'Helper'))

    def test_edit_helper_keeps_commands_and_initial_values(self):
        before=self.form.dumps()
        entries=[(m.name,Method(m.name,m.signature,m.body+"\n$P 'edited'")) for m in self.form.extra_methods]
        updated=update_helpers(self.form,entries)
        self.assertEqual(self.form.dumps(),before)
        self.assertEqual(updated.named('Run'),self.form.named('Run'))
        self.assertEqual(updated.named('Input'),self.form.named('Input'))
        self.assertIn("$P 'edited'",updated.extra_methods[0].body)
        self.assertEqual(Form.loads(updated.dumps()).pml(),updated.pml())

    def test_rename_updates_known_callers_and_preserves_original_reference(self):
        self.form.partial_import_source=TEXT
        entries=[('Helper',Method('Shared','(!value Is String)',"$P !value")),
                 ('Unused',self.form.extra_methods[1])]
        updated=update_helpers(self.form,entries)
        self.assertIn("!this.Shared('value')",updated.named('Run').body)
        self.assertEqual(updated.partial_import_source,TEXT)
        self.assertEqual(updated.named('Run').callback,'Apply')

    def test_simultaneous_swaps_do_not_cascade(self):
        form=Form(extra_methods=[Method('First',body='!this.Second()'),Method('Second',body="$P 'done'")])
        updated=update_helpers(form,[('First',Method('Second',body='!this.Second()')),
                                     ('Second',Method('First',body="$P 'done'"))])
        self.assertEqual(updated.extra_methods[0].body,'!this.First()')
        updated.pml()

    def test_method_rename_does_not_rename_gadget_property_with_same_name(self):
        form=Form(gadgets=[Gadget(kind='text',name='Helper',value_type='STRING')],
                  extra_methods=[Method('Helper',body="!this.Helper.Val = 'value'")],
                  after_show_code='!this.Helper()')
        updated=update_helpers(form,[('Helper',Method('Shared',body="!this.Helper.Val = 'value'"))])
        self.assertEqual(updated.after_show_code,'!this.Shared()')
        self.assertEqual(updated.extra_methods[0].body,"!this.Helper.Val = 'value'")
        self.assertEqual(updated.gadgets[0].name,'Helper')

    def test_delete_used_helper_is_rejected_but_unused_can_be_deleted(self):
        with self.assertRaisesRegex(ValueError,'呼び出し'):update_helpers(self.form,[('Unused',self.form.extra_methods[1])])
        updated=update_helpers(self.form,[('Helper',self.form.extra_methods[0])])
        self.assertEqual(len(updated.extra_methods),1)

    def test_collisions_bad_signatures_and_embedded_definitions_are_rejected(self):
        bad=(Method('Apply'),Method('DEFAULT'),Method('Not valid'),
             Method('Helper','no signature'),Method('Helper',body="Endmethod\n$P 'outside'"))
        for method in bad:
            with self.subTest(method=method),self.assertRaises(ValueError):update_helpers(self.form,[('Helper',method)])

    def test_reference_report_ignores_comments_and_labels_unknown_dynamic_calls(self):
        self.form.default_body="-- !this.Unused()\n$( !this.Unused() $)"
        self.assertEqual(callers(self.form,'Unused'),[])
        self.form.after_show_code="!!Demo.Helper('call')"
        self.assertIn('表示後のプログラム',callers(self.form,'Helper'))


class HelperManagerGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.form=import_mac(TEXT).form;self.w.refresh()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_manager_lists_helpers_and_edits_name_arguments_and_body(self):
        dialog=MethodManagerDialog(self.w,self.w.form)
        self.assertEqual(dialog.list.count(),2)
        self.assertIn('Run: body',dialog.references.text())
        dialog.name.setText('Shared')
        dialog.signature.setText('(!value Is String) Is String')
        dialog.body.setPlainText('Return !value')
        dialog.accept()
        self.assertEqual(dialog.result_form.extra_methods[0].name,'Shared')
        self.assertIn('!this.Shared(',dialog.result_form.named('Run').body)
        self.assertEqual(dialog.result_form.named('Input').initial,'Ready')
        dialog.close()

    def test_manager_add_remove_and_cancel_does_not_mutate_original(self):
        before=self.w.form.dumps();dialog=MethodManagerDialog(self.w,self.w.form)
        dialog.add();self.assertEqual(dialog.list.count(),3)
        self.assertEqual(dialog.name.text(),'helper1')
        dialog.remove();self.assertEqual(dialog.list.count(),2)
        dialog.reject();dialog.close();self.assertEqual(self.w.form.dumps(),before)

    def test_generated_table_initializer_is_avoided_when_adding_helper(self):
        form=Form(gadgets=[Gadget(kind='list',name='Rows',list_mode='TABLE',
                                table_method='helper1',headings=['Name'],rows=[['A']])])
        dialog=MethodManagerDialog(self.w,form);dialog.add()
        self.assertEqual(dialog.name.text(),'helper2')
        dialog.accept();self.assertIsNotNone(dialog.result_form)
        dialog.close()

    def test_manager_window_commit_is_one_undo_and_redo(self):
        before=self.w.form.dumps()
        def accept_edit(dialog):
            dialog.body.setPlainText("$P 'changed'")
            dialog.accept();return QDialog.Accepted
        with patch.object(MethodManagerDialog,'exec',accept_edit):self.w.manage_methods()
        after=self.w.form.dumps();self.assertNotEqual(before,after)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)
        self.w.redo();self.assertEqual(self.w.form.dumps(),after)
