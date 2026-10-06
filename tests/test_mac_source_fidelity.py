import copy
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window
from e3d_designer.clipboard import clone_subtree
from e3d_designer.import_editor import ImportCodeDialog
from e3d_designer.mac_import import import_mac, MacImportError
from e3d_designer.model import Form, Method
from e3d_designer.names import rename
from e3d_designer.pml_syntax import mask_non_code


def source(program="Show !!Demo", methods="", ending="Exit"):
    return ("Setup Form !!Demo Dialog Size 70 22\n"
            "Button .Run At X 1 Y 1 'Run' Call '!this.Apply()'\n"
            f"{ending}\n{program}\n{methods}")


HELPERS = """Define Method .Apply()
!this.Helper()
Endmethod
Define Method .Helper()
!!Demo.Leaf('value')
Endmethod
Define Method .Leaf(!arg Is String)
!this.Run.Val = !!Flag
Endmethod"""


class MacSourceFidelityTests(unittest.TestCase):
    def test_comment_on_final_exit_remains_non_executable(self):
        form = import_mac(source("Show !!Demo", ending=
            "Exit $( documentation begins\n$M 'do_not_run.mac'\nends $)")).form
        output = form.pml()
        self.assertIn("$( documentation begins\n$M 'do_not_run.mac'\nends $)", output)
        self.assertNotIn('do_not_run.mac', mask_non_code(output))
        self.assertEqual(import_mac(output).form.pml(), output)

    def test_comment_starting_before_exit_preserves_complete_span(self):
        text = source().replace("Exit\nShow", "$( documentation\n$) Exit $( continued\n$M 'never.mac'\n$)\nShow")
        output = import_mac(text).form.pml()
        self.assertNotIn('never.mac', mask_non_code(output))
        self.assertIn("$( continued\n$M 'never.mac'\n$)", output)

    def test_implicit_boundary_keeps_comment_that_closes_on_show_line(self):
        text = source(ending="$( boundary\n$M 'never.mac'\n$) Show !!Demo", program="")
        output = import_mac(text).form.pml()
        self.assertNotIn('never.mac', mask_non_code(output))
        self.assertEqual(mask_non_code(output).lower().count('show !!demo'), 1)

    def test_exit_line_comment_survives(self):
        for comment in ("-- boundary note", "$* boundary note"):
            with self.subTest(comment=comment):
                output = import_mac(source(ending='Exit '+comment)).form.pml()
                self.assertIn(comment, output)

    def test_method_error_line_stays_correct_after_boundary_comment(self):
        text = source(ending="Exit $( note\n$)", methods="Define Method .Broken()\n$P 'x'")
        with self.assertRaises(MacImportError) as error:
            import_mac(text)
        self.assertEqual(error.exception.line, 6)

    def test_repeated_show_and_hide_keep_order(self):
        form = import_mac(source("Show !!Demo\nHide !!Demo\nShow !!Demo")).form
        output = mask_non_code(form.pml()).lower()
        self.assertEqual(output.count('show !!demo'), 2)
        self.assertLess(output.index('show !!demo'), output.index('hide !!demo'))
        self.assertLess(output.index('hide !!demo'), output.rindex('show !!demo'))
        self.assertEqual(Form.loads(form.dumps()).pml(), form.pml())

    def test_conditional_show_is_not_moved_outside_condition(self):
        program = "If !!Ready Then\nShow !!Demo\nEndif"
        form = import_mac(source(program)).form
        self.assertEqual(form.program_mode, 'SOURCE')
        self.assertIn(program, form.pml())
        self.assertEqual(mask_non_code(form.pml()).lower().count('show !!demo'), 1)

    def test_before_show_initialization_round_trip_and_rename(self):
        program = "!!Flag = 'Ready'\nShow !!Demo\nHide !!Demo\nShow !!Demo"
        form = import_mac(source(program)).form
        self.assertEqual(form.program_mode, 'SOURCE')
        self.assertIn(program, form.pml())
        renamed = rename(Form.loads(form.dumps()), 'form', None, 'Target')
        self.assertIn(program.replace('!!Demo', '!!Target'), renamed.pml())
        again = import_mac(renamed.pml()).form
        self.assertEqual(again.program_mode, 'SOURCE')
        self.assertEqual(again.after_show_code, renamed.after_show_code)

    def test_no_show_source_does_not_introduce_show(self):
        form = import_mac(source("$P 'Ready'")).form
        self.assertEqual(form.program_mode, 'SOURCE')
        self.assertNotIn('Show !!Demo', form.pml())
        fresh = Form()
        self.assertIn('Show !!'+fresh.name, fresh.pml())

    def test_transitive_helpers_copy_once_with_signature_and_references(self):
        original = import_mac("Var !!Flag 'Ready'\n"+source(methods=HELPERS)).form
        before = original.dumps()
        target = Form(name='Target', extra_methods=[Method('Helper_copy1', body="$P 'existing'")])
        target_before = target.dumps()
        cloned, index = clone_subtree(target, original, 0)
        self.assertEqual(original.dumps(), before)
        self.assertEqual(target.dumps(), target_before)
        self.assertEqual(cloned.variables['Flag'], 'Ready')
        helpers = {m.name: m for m in cloned.extra_methods}
        self.assertIn('Helper_copy2', helpers)
        self.assertEqual(helpers['Leaf_copy1'].signature, '(!arg Is String)')
        self.assertIn("!!Target.Leaf_copy1('value')", helpers['Helper_copy2'].body)
        self.assertIn('!this.'+cloned.gadgets[index].name+'.Val', helpers['Leaf_copy1'].body)
        self.assertIn('!this.Helper_copy2()', cloned.gadgets[index].body)
        self.assertEqual(Form.loads(cloned.dumps()).pml(), cloned.pml())

    def test_helper_dependency_in_comment_is_not_copied(self):
        original = import_mac(source(methods=HELPERS)).form
        original.gadgets[0].body = "-- !this.Helper()\n$P 'done'"
        cloned, _ = clone_subtree(Form(name='Target'), original, 0)
        self.assertEqual(cloned.extra_methods, [])

    def test_cut_restore_reuses_identical_dependency_graph_and_globals(self):
        original = import_mac("Var !!Flag 'Ready'\n"+source(methods=HELPERS)).form
        target = copy.deepcopy(original); target.gadgets=[]; target.variables={}
        cloned, _ = clone_subtree(target, original, 0, restore_names=True)
        self.assertEqual(cloned.extra_methods, original.extra_methods)
        self.assertEqual(cloned.variables, original.variables)
        self.assertEqual(cloned.gadgets[0].body, original.gadgets[0].body)
        cloned.pml()

    def test_cut_restore_clones_changed_dependency_without_mutating_target(self):
        original = import_mac(source(methods=HELPERS)).form
        target = copy.deepcopy(original); target.gadgets=[]
        target.extra_methods[-1].body = "$P 'changed'"
        before = target.dumps()
        cloned, _ = clone_subtree(target, original, 0, restore_names=True)
        self.assertEqual(target.dumps(), before)
        self.assertEqual(cloned.extra_methods[:2], target.extra_methods)
        self.assertIn('!this.Helper_copy1()', cloned.gadgets[0].body)
        self.assertIn("!!Demo.Leaf_copy1('value')", cloned.extra_methods[2].body)
        cloned.pml()

    def test_existing_target_global_binding_is_retained(self):
        original = import_mac("Var !!Flag 'Ready'\n"+source(methods=HELPERS)).form
        cloned, _ = clone_subtree(Form(name='Target', variables={'flag':'Existing'}), original, 0)
        self.assertEqual(cloned.variables, {'flag':'Existing'})


class MacSourceFidelityGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.w = Window(settings_path=Path(self.temp.name)/'settings.json')

    def tearDown(self):
        self.app.clipboard().clear(); self.w.dirty=False; self.w.close()
        self.app.processEvents(); self.temp.cleanup()

    def test_source_program_editor_keeps_mode_and_order(self):
        form = import_mac(source("!!Ready = true\nShow !!Demo")).form
        self.w.form=form; self.w.refresh()
        self.assertIn('SHOWを含む', self.w.program_label.text())
        dialog = ImportCodeDialog(self.w, form)
        dialog.editors['after_show_code'].setPlainText("!!Ready = false\nShow !!Demo")
        dialog.accept()
        self.assertIsNotNone(dialog.result_form)
        self.assertEqual(dialog.result_form.program_mode, 'SOURCE')
        self.assertIn("!!Ready = false\nShow !!Demo", dialog.result_form.pml())
        dialog.close()

    def test_gui_cross_design_paste_undo_redo_and_save_retains_helpers(self):
        original = import_mac(source(methods=HELPERS)).form
        self.w.form=original; self.w.refresh(); self.w.choose_row(0); self.w.copy_gadget()
        self.w.form=Form(name='Target'); self.w.refresh()
        self.w.paste_gadget()
        self.assertEqual(len(self.w.form.extra_methods), 2)
        saved = self.w.form.dumps()
        self.w.undo(); self.assertEqual(self.w.form.gadgets, [])
        self.w.redo(); self.assertEqual(self.w.form.dumps(), saved)
        self.assertEqual(Form.loads(saved).pml(), self.w.form.pml())
