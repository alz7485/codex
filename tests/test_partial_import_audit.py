import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Method
from e3d_designer.method_manager import update_helpers,callers
from e3d_designer.pml_syntax import mask_non_code


def source(declarations,ending='Exit\nShow !!Demo',methods=''):
    return f'Setup Form !!Demo Dialog Size 70 22\n{declarations}\n{ending}\n{methods}'


OPAQUE="Grid .Opaque 'Grid'\nStuff 'Unknown'\nExit"


class PartialBoundaryAuditTests(unittest.TestCase):
    def test_nested_opaque_block_with_implicit_exit_keeps_parent(self):
        text=source("Frame .Outer 'Outer'\n"+OPAQUE+"\nButton .Inside 'Inside'\nExit",ending='Show !!Demo')
        form=import_mac(text,partial=True).form
        self.assertEqual(form.named('Inside').parent,'Outer')
        self.assertEqual(len(form.partial_import_notes),1)
        self.assertIn('3〜5行',form.partial_import_notes[0])
        again=import_mac(Form.loads(form.dumps()).pml()).form
        self.assertEqual(again.named('Inside').parent,'Outer')
        self.assertEqual(form.partial_import_source,text)

    def test_unrelated_single_line_does_not_borrow_later_block_exit(self):
        declarations="Mystery .Bad 'Bad'\nButton .Keep 'Keep'\n"+OPAQUE+"\nButton .Good 'Good'"
        form=import_mac(source(declarations),partial=True).form
        self.assertEqual([g.name for g in form.gadgets],['Keep','Good'])
        self.assertEqual(len(form.partial_import_notes),2)
        self.assertIn('2〜2行',form.partial_import_notes[0])
        self.assertIn('4〜6行',form.partial_import_notes[1])

    def test_later_opaque_block_cannot_change_earlier_frame_scope(self):
        declarations=("Frame .Outer 'Outer'\nMystery .Bad 'Bad'\nButton .Inside 'Inside'\nExit\n"
                      +OPAQUE+"\nButton .Outside 'Outside'")
        form=import_mac(source(declarations),partial=True).form
        self.assertEqual(form.named('Inside').parent,'Outer')
        self.assertEqual(form.named('Outside').parent,'')
        self.assertEqual(form.named('Outer').parent,'')

    def test_unknown_single_line_does_not_swallow_form_directives(self):
        for directive in ("Title 'Kept title'","Hdist 2","Bar\nAdd 'Tools' .Tools\nMenu .Tools\nAdd 'Run' 'Q CE'\nExit"):
            with self.subTest(directive=directive):
                form=import_mac(source("Mystery .Bad 'Bad'\n"+directive+"\nButton .Good 'Good'"),partial=True).form
                self.assertEqual([g.name for g in form.gadgets],['Good'])
                self.assertIn('2〜2行',form.partial_import_notes[0])
                if directive.startswith('Title'):self.assertEqual(form.title,'Kept title')
                if directive.startswith('Bar'):self.assertEqual(form.menus[0].display_label,'Tools')

    def test_tabset_nested_frame_opaque_block_keeps_all_known_parents(self):
        declarations=("Frame .Pages Tabset At X 1 Y 1 'Pages' Width 40\nFrame .First 'First'\n"
                      "Frame .Outer 'Outer'\n"+OPAQUE+"\nButton .Inside 'Inside'\nExit\nExit\nExit")
        form=import_mac(source(declarations,ending='Show !!Demo'),partial=True).form
        self.assertEqual(form.named('Inside').parent,'Outer')
        self.assertEqual(form.named('Outer').parent,'First')
        self.assertEqual(form.named('First').parent,'Pages')
        self.assertEqual(import_mac(form.pml()).form.named('Inside').parent,'Outer')

    def test_unknown_block_with_nested_known_frame_is_skipped_as_one_unit(self):
        declarations=("Grid .Opaque 'Grid'\nStuff 'Unknown'\nFrame .Hidden 'Hidden'\n"
                      "Button .HiddenChild 'Hidden'\nExit\nExit\nButton .Good 'Good'")
        form=import_mac(source(declarations),partial=True).form
        self.assertEqual([g.name for g in form.gadgets],['Good'])
        self.assertEqual(len(form.partial_import_notes),1)
        self.assertIn('2〜7行',form.partial_import_notes[0])

    def test_stranded_declaration_in_program_is_rejected(self):
        for declaration in ("Button .Stranded 'Stranded'","Bar\nAdd 'Tools' .Tools"):
            with self.subTest(declaration=declaration):
                text=source("Mystery .Bad 'Bad'\nButton .Good 'Good'",ending="Exit\n"+declaration+"\nShow !!Demo")
                with self.assertRaisesRegex(ValueError,'フォーム終了後'):import_mac(text,partial=True)

    def test_program_literals_and_method_body_are_not_stranded_declarations(self):
        text=source("Mystery .Bad 'Bad'\nButton .Good 'Good'",
                    ending="Exit\nShow !!Demo\n$P 'Button .Printed'\n$(\nButton .Commented\n$)",
                    methods="Define Method .Body()\n$P 'Button .Text'\nEndmethod")
        form=import_mac(text,partial=True).form
        self.assertEqual([g.name for g in form.gadgets],['Good'])
        self.assertIn("$P 'Button .Printed'",form.pml())
        self.assertEqual(form.extra_methods[0].name,'Body')

    def test_comment_crossing_skipped_opaque_block_remains_non_executable(self):
        declarations="Grid .Opaque 'Grid' $( note\n$M 'never.mac'\n$)\nStuff 'Unknown'\nExit\nButton .Good 'Good'"
        form=import_mac(source(declarations),partial=True).form
        self.assertNotIn('$M',mask_non_code(form.pml()))
        self.assertEqual([g.name for g in form.gadgets],['Good'])


class MethodLiteralAuditTests(unittest.TestCase):
    def make_form(self,body,program=''):
        return Form(name='Demo',extra_methods=[Method('Helper',body=body)],after_show_code=program)

    def renamed(self,form):
        return update_helpers(form,[('Helper',Method('Shared',form.extra_methods[0].signature,form.extra_methods[0].body))])

    def test_data_literals_in_all_three_quote_styles_are_preserved(self):
        for quote in ("'",'"','|'):
            with self.subTest(quote=quote):
                value=f'!value = {quote}!!Demo.Helper(){quote}'
                form=self.make_form("$P 'done'",value)
                updated=self.renamed(form)
                self.assertEqual(updated.after_show_code,value)
                self.assertEqual(callers(form,'Helper'),[])

    def test_comments_preserved_while_real_calls_change(self):
        program="-- !this.Helper()\n$* !!Demo.Helper()\n$( !this.Helper() $) !!Demo.Helper()"
        form=self.make_form("$P 'done'",program)
        updated=self.renamed(form)
        self.assertEqual(updated.after_show_code,program.rsplit('!!Demo.Helper()',1)[0]+'!!Demo.Shared()')
        self.assertIn('表示後のプログラム',callers(form,'Helper'))

    def test_assignment_to_default_local_value_is_not_a_callback(self):
        form=self.make_form("$P 'done'")
        form.default_body="!value = '!!Demo.Helper()'"
        updated=self.renamed(form)
        self.assertEqual(updated.default_body,form.default_body)
        self.assertEqual(callers(form,'Helper'),[])

    def test_quoted_callback_and_form_event_assignments_are_updated(self):
        for attribute in ('Hook.Callback','Initcall','Autocall','Okcall','Cancelcall'):
            for quote in ("'",'"','|'):
                with self.subTest(attribute=attribute,quote=quote):
                    program=f"!this.{attribute} = {quote}!!Demo.Helper({quote}"
                    form=self.make_form("$P 'done'",program)
                    updated=self.renamed(form)
                    self.assertIn('!!Demo.Shared(',updated.after_show_code)
                    self.assertIn('表示後のプログラム',callers(form,'Helper'))

    def test_inner_data_literal_in_callback_is_not_changed(self):
        program='!this.Hook.Callback = "!this.Helper(\'!this.Helper()\')"'
        updated=self.renamed(self.make_form("$P 'done'",program))
        self.assertEqual(updated.after_show_code,'!this.Hook.Callback = "!this.Shared(\'!this.Helper()\')"')

    def test_data_literals_do_not_block_deletion_of_helper(self):
        form=self.make_form("$P 'done'","!label = '!this.Helper()'\n-- !this.Helper()")
        updated=update_helpers(form,[])
        self.assertEqual(updated.extra_methods,[])
        self.assertEqual(updated.after_show_code,form.after_show_code)

    def test_quoted_callback_does_block_deletion_of_helper(self):
        form=self.make_form("$P 'done'","!this.Hook.Callback = '!this.Helper('")
        with self.assertRaisesRegex(ValueError,'呼び出し'):update_helpers(form,[])

    def test_real_command_keeps_its_argument_literals_and_external_calls(self):
        from e3d_designer.model import Gadget
        form=self.make_form("$P 'done'")
        command="!this.Helper('!this.Helper()'); !!Other.Helper()"
        form.gadgets=[Gadget(kind='button',name='Run',command=command)]
        updated=self.renamed(form)
        self.assertEqual(updated.gadgets[0].command,"!this.Shared('!this.Helper()'); !!Other.Helper()")

    def test_inline_comments_between_method_name_and_arguments_are_preserved(self):
        program="!this.Helper $( call note $) ()\n!this.Hook.Callback = '!this.Helper $( callback note $) ('"
        updated=self.renamed(self.make_form("$P 'done'",program))
        self.assertEqual(updated.after_show_code,program.replace('!this.Helper','!this.Shared'))


class ClipboardReferenceAuditTests(unittest.TestCase):
    def make_source(self,body,helpers=None):
        from e3d_designer.model import Gadget
        return Form(name='Source',variables={'Flag':'Ready'},
                    gadgets=[Gadget(kind='button',name='Run',callback='Apply',body=body)],
                    extra_methods=helpers or [Method('Helper',body="$P 'helper'")])

    def copied(self,form):
        from e3d_designer.clipboard import clone_subtree
        return clone_subtree(Form(name='Target'),form,0)[0]

    def test_data_literals_do_not_copy_helpers_or_globals_or_change_values(self):
        body="!label = '!this.Helper()'\n!value = '!!Flag'\n!member = '!!Source.Run.Val'\n-- !this.Helper()"
        source=self.make_source(body);before=source.dumps()
        target=self.copied(source)
        self.assertEqual(target.gadgets[0].body,body)
        self.assertEqual(target.extra_methods,[]);self.assertEqual(target.variables,{})
        self.assertEqual(source.dumps(),before)

    def test_real_helper_call_is_copied_without_rewriting_argument_data(self):
        body="!this.Helper('!this.Helper()')\n!!Source.Run.Val = !!Flag\n-- !this.Helper()"
        target=self.copied(self.make_source(body))
        gadget=target.gadgets[0]
        self.assertIn("!this.Helper_copy1('!this.Helper()')",gadget.body)
        self.assertIn('!!Target.'+gadget.name+'.Val = !!Flag',gadget.body)
        self.assertIn('-- !this.Helper()',gadget.body)
        self.assertEqual(target.variables,{'Flag':'Ready'})
        self.assertEqual([m.name for m in target.extra_methods],['Helper_copy1'])

    def test_callback_assignment_copies_and_updates_helper_and_gadget_member(self):
        body="!this.Run.Callback = '!this.Helper('\n!label = '!this.Helper()'"
        target=self.copied(self.make_source(body))
        self.assertIn("!this."+target.gadgets[0].name+".Callback = '!this.Helper_copy1('",target.gadgets[0].body)
        self.assertIn("!label = '!this.Helper()'",target.gadgets[0].body)
        self.assertEqual(len(target.extra_methods),1)

    def test_transitive_helper_literals_do_not_copy_extra_dependencies(self):
        helpers=[Method('Helper',body="!label = '!this.Unused()'\n$P 'helper'"),
                 Method('Unused',body="$P 'unused'")]
        target=self.copied(self.make_source('!this.Helper()',helpers))
        self.assertEqual([m.name for m in target.extra_methods],['Helper_copy1'])
        self.assertIn("'!this.Unused()'",target.extra_methods[0].body)

    def test_cut_restore_reuses_helper_when_only_literal_named_dependency_changed(self):
        import copy
        from e3d_designer.clipboard import clone_subtree
        source=self.make_source('!this.Helper()',[Method('Helper',body="!label = '!this.Unused()'"),
                                                 Method('Unused',body="$P 'old'")])
        target=copy.deepcopy(source);target.gadgets=[];target.extra_methods[1].body="$P 'changed'"
        restored,_=clone_subtree(target,source,0,restore_names=True)
        self.assertEqual(restored.extra_methods,target.extra_methods)
        self.assertEqual(restored.gadgets[0].body,'!this.Helper()')


class PartialAuditGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json')
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_gui_partial_import_save_reopen_keeps_nested_parent_and_source(self):
        text=source("Frame .Outer 'Outer'\n"+OPAQUE+"\nButton .Inside 'Inside'\nExit",ending='Show !!Demo')
        path=self.folder/'source.mac';path.write_text(text);original=path.read_bytes()
        with patch('e3d_designer.app.QMessageBox.information'):
            self.assertTrue(self.w.open_design(path,confirmed=True,partial=True))
        self.assertEqual(self.w.form.named('Inside').parent,'Outer')
        design=self.folder/'saved.json'
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(design),'')):
            self.assertTrue(self.w.save())
        self.assertTrue(self.w.open_design(design,confirmed=True))
        self.assertEqual(self.w.form.named('Inside').parent,'Outer')
        self.assertEqual(self.w.form.partial_import_source,text)
        self.assertFalse(self.w.partial_notice.isHidden())
        self.assertEqual(path.read_bytes(),original)

    def test_gui_rejects_stranded_declaration_without_changing_current_design(self):
        self.w.add('button');before=self.w.form.dumps();history=list(self.w.history)
        path=self.folder/'ambiguous.mac'
        path.write_text(source("Mystery .Bad 'Bad'",ending="Exit\nButton .Stranded 'x'\nShow !!Demo"))
        with patch('e3d_designer.app.QMessageBox.warning') as warning, \
             patch('e3d_designer.app.QMessageBox.information'):
            self.assertFalse(self.w.open_design(path,confirmed=True,partial=True))
            self.assertIn('フォーム終了後',warning.call_args.args[2])
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,history)
