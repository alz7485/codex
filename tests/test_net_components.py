import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import QTimer
from e3d_designer.app import Window
from e3d_designer.model import Form, Gadget
from e3d_designer.net_components import NetComponentSpec
from e3d_designer.net_component_dialog import NetComponentWizard
from e3d_designer.names import rename
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac, MacImportError


class NetRecipeTests(unittest.TestCase):
    def test_grid_round_trip_and_connection_order(self):
        g = NetComponentSpec(rows=[['Pump A', 'EQUI'], ['Pipe A', 'PIPE']], single=True).gadget()
        form = Form(gadgets=[g])
        restored = Form.loads(form.dumps())
        self.assertEqual(restored.gadgets[0], g)
        code = restored.pml(normalize=False)
        self.assertIn("!netRows[2][1] = 'Pipe A'", code)
        self.assertIn('SingleRowSelection(TRUE)', code)
        self.assertIn('EditableGrid(FALSE)', code)
        self.assertLess(code.index('!this.netGrid1.Control ='), code.index('BindToDataSource('))
        ctor = code.split('define method .userform()')[1]
        self.assertLess(ctor.index('using namespace'), ctor.index('object NetGridControl()'))

    def test_grid_rename_duplicate_and_cross_project_copy(self):
        original = Form(gadgets=[NetComponentSpec().gadget()])
        changed = rename(original, 'gadget', 0, 'results')
        self.assertIn('!this.resultsControl.', changed.gadgets[0].net_setup)
        self.assertNotIn('!this.netGrid1Control.', changed.pml())
        for target in (original, Form(name='destination')):
            copied, selected = clone_subtree(target, original, 0)
            g = copied.gadgets[selected]
            self.assertIn(f'!this.{g.name}Control.BindToDataSource', g.net_setup)
            copied.pml()

    def test_grid_mac_import_retains_initialization(self):
        source = Form(gadgets=[NetComponentSpec().gadget()]).pml()
        imported = import_mac(source).form
        self.assertEqual(imported.constructor_mode, 'SOURCE')
        self.assertIn('BindToDataSource', imported.constructor_body)
        self.assertIn('EditableGrid(FALSE)', imported.pml())
        imported_again = import_mac(imported.pml()).form
        self.assertIn('BindToDataSource', imported_again.constructor_body)

    def test_current_element_members_build_rows_without_database_writes(self):
        g=NetComponentSpec(data_source='MEMBERS', headings=[], rows=[['ignored']]).gadget()
        code=Form(gadgets=[g]).pml()
        self.assertIn('do !netElement values !!CE.members',code)
        self.assertIn('!netRow[1] = !netElement.name',code)
        self.assertIn('!netRows.append(!netRow)',code)
        self.assertIn('BADREF(!!CE)',code)
        self.assertNotIn('ignored',code)

    def test_multiple_assemblies_and_repeated_assembly_import(self):
        gadgets = []
        for name, assembly in (('first', 'A'), ('second', 'B'), ('third', 'A')):
            gadgets.append(NetComponentSpec(recipe='custom', name=name, assembly=assembly,
                namespace='Vendor.Controls', control_type='ExampleControl').gadget())
        imported = import_mac(Form(gadgets=gadgets).pml()).form
        self.assertEqual([g.assembly for g in imported.gadgets], ['A', 'B', 'A'])

    def test_file_open_save_and_cancel(self):
        for mode, exists in (('OPEN', 'TRUE'), ('SAVE', 'FALSE')):
            g = NetComponentSpec(recipe='file', name='choose', mode=mode,
                directory='C:/Reports', seed='data.csv', file_filter='CSV|*.csv').gadget()
            code = Form(gadgets=[g]).pml()
            self.assertIn(f"object PMLFileBrowser('{mode}')", code)
            self.assertIn(f"{exists}, 'CSV|*.csv', 1", code)
            self.assertLess(code.index("if (!selectedFile eq '')"), code.index('$p Selected file:'))
            clone, selected = clone_subtree(Form(), Form(gadgets=[g]), 0)
            self.assertNotEqual(clone.gadgets[selected].callback, g.callback)
            clone.pml()

    def test_mydata_adds_only_current_element(self):
        g = NetComponentSpec(recipe='mydata', name='register').gadget()
        code = Form(gadgets=[g]).pml()
        self.assertIn("import 'MyDataAddin'", code)
        self.assertIn('BADREF(!!CE)', code)
        self.assertIn('!myData.AddElement(!elementName)', code)
        self.assertNotIn('Remove', code)

    def test_external_recipes_require_real_connection(self):
        for recipe in ('flexible', 'dimension', 'custom'):
            with self.subTest(recipe=recipe):
                g = NetComponentSpec(recipe=recipe, assembly='Vendor',
                    namespace='Vendor.Controls', control_type='PmlControl',
                    setup_code='!this.netGrid1Control.Initialize()').gadget()
                self.assertIn('Initialize()', Form(gadgets=[g]).pml())
        with self.assertRaisesRegex(ValueError, 'DLL名'):
            NetComponentSpec(recipe='flexible', assembly='', namespace='', control_type='').gadget()

    def test_invalid_input_and_source_initialization(self):
        cases = [dict(rows=[['one']]), dict(headings=['A', 'a']), dict(headings=[]),
                 dict(headings=['bad$']), dict(control_type='Other'), dict(assembly='bad\nDLL'),
                 dict(recipe='file', mode='BAD'), dict(recipe='file', file_filter='invalid'),
                 dict(recipe='custom', namespace='Bad;command')]
        for settings in cases:
            with self.subTest(settings=settings), self.assertRaises(ValueError): NetComponentSpec(**settings).gadget()
        g = NetComponentSpec().gadget()
        with self.assertRaisesRegex(ValueError, 'コンストラクタ'):
            Form(gadgets=[g], constructor_mode='SOURCE').pml()

    def test_nonempty_import_handler_is_not_silently_discarded(self):
        code = Form(gadgets=[NetComponentSpec().gadget()]).pml(normalize=False)
        code = code.replace('-- Assembly already loaded', '$p Unexpected handler')
        with self.assertRaises(MacImportError): import_mac(code)


class NetWizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.w = Window(settings_path=Path(self.temp.name)/'settings.json')
    def tearDown(self):
        self.app.clipboard().clear(); self.w.dirty = False; self.w.close(); self.temp.cleanup()

    def test_palette_and_menu_open_wizard_without_changing_palette_size(self):
        w = self.w
        self.assertEqual(len(w.palette_buttons), 18)
        self.assertEqual(len(w.palette_actions), 23)
        with patch('e3d_designer.net_component_dialog.NetComponentWizard') as wizard:
            wizard.return_value.exec.return_value=QDialog.Rejected
            next(a for a in w.palette_buttons['container'].menu().actions() if a.data()=='net_components').trigger()
            w.net_component_action.trigger()
            self.assertEqual(wizard.call_count, 2)
        self.assertEqual(w.form.gadgets, [])
        self.assertEqual(w.history, [])

    def test_wizard_preview_validation_and_recipe_switch(self):
        d = NetComponentWizard(self.w, self.w.form)
        self.assertEqual(d.error.text(), '')
        self.assertIn('BindToDataSource', d.preview.toPlainText())
        d.rows.setPlainText('Wrong column count')
        self.assertIn('列数', d.error.text()); self.assertEqual(d.preview.toPlainText(), '')
        d.accept(); self.assertIsNone(d.result_gadget)
        d.recipe.setCurrentIndex(d.recipe.findData('file'))
        self.assertEqual(d.error.text(), '')
        d.mode.setCurrentIndex(d.mode.findData('SAVE'))
        d.accept(); self.assertIn("PMLFileBrowser('SAVE')", d.result_gadget.body)
        d.recipe.setCurrentIndex(d.recipe.findData('flexible'))
        self.assertIn('DLL名', d.error.text())
        d.assembly.setText('Company.Tree'); d.namespace.setText('Company.Controls'); d.control_type.setText('PmlTree')
        self.assertEqual(d.error.text(), ''); d.close()

    def test_wizard_current_element_source_replaces_manual_rows(self):
        d=NetComponentWizard(self.w,self.w.form)
        d.data_source.setCurrentIndex(d.data_source.findData('MEMBERS'))
        self.assertEqual(d.error.text(),'')
        self.assertIn('!!CE.members',d.preview.toPlainText())
        self.assertTrue(d.rows.isHidden());self.assertTrue(d.headings.isHidden())
        d.data_source.setCurrentIndex(d.data_source.findData('ROWS'))
        self.assertIn('Sample-1',d.preview.toPlainText())
        d.close()

    def test_standard_container_requires_only_basic_inputs_and_retains_advanced_edits(self):
        d=NetComponentWizard(self.w,self.w.form);d.show()
        self.assertTrue(d.assembly.isHidden());self.assertTrue(d.namespace.isHidden())
        self.assertTrue(d.control_type.isHidden());self.assertTrue(d.setup_code.isHidden())
        self.assertFalse(d.advanced.isHidden());self.assertEqual(d.error.text(),'')
        d.label.setText('結果一覧');d.headings.setPlainText('名前\n種類')
        d.rows.setPlainText('PUMP-1\tEQUI\nPIPE-1\tPIPE');d.single.setChecked(True)
        d.advanced.setChecked(True);self.assertFalse(d.assembly.isHidden())
        d.setup_code.setPlainText('!this.netGrid1Control.RefreshTable()')
        d.advanced.setChecked(False);self.assertTrue(d.setup_code.isHidden())
        d.accept();g=d.result_gadget
        self.assertEqual(g.label,'結果一覧');self.assertEqual(g.assembly,'GridControl')
        self.assertIn('SingleRowSelection(TRUE)',g.net_setup)
        self.assertIn('RefreshTable()',g.net_setup)
        self.assertTrue(self.w.insert_net_component(g));d.close()

    def test_external_container_always_exposes_required_connection_fields(self):
        d=NetComponentWizard(self.w,self.w.form);d.show()
        for recipe in ('flexible','dimension','custom'):
            d.recipe.setCurrentIndex(d.recipe.findData(recipe))
            self.assertTrue(d.advanced.isHidden());self.assertFalse(d.assembly.isHidden())
            self.assertFalse(d.namespace.isHidden());self.assertFalse(d.control_type.isHidden())
            if recipe!='dimension':
                d.accept();self.assertIsNone(d.result_gadget);self.assertIn('DLL名',d.error.text())
            d.assembly.setText('Vendor');d.namespace.setText('Vendor.Controls');d.control_type.setText('PmlControl')
            self.assertEqual(d.error.text(),'')
        d.close()

    def test_real_menu_dialog_and_initialization_editor(self):
        w=self.w
        def create():
            dialog=w.findChildren(NetComponentWizard)[-1]
            dialog.accept()
        QTimer.singleShot(0,create);w.net_component_action.trigger()
        self.assertEqual(len(w.form.gadgets),1)
        self.assertFalse(w.net_setup_button.isHidden())
        before=w.form.gadgets[0].net_setup
        def edit():
            from PySide6.QtWidgets import QPlainTextEdit, QDialogButtonBox
            dialog=self.app.activeModalWidget()
            dialog.findChild(QPlainTextEdit).appendPlainText('!this.netGrid1Control.RefreshTable()')
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        QTimer.singleShot(0,edit);w.edit_net_setup()
        self.assertIn('RefreshTable()',w.form.gadgets[0].net_setup)
        w.undo();self.assertEqual(w.form.gadgets[0].net_setup,before)

    def test_insert_save_undo_redo_and_unique_names(self):
        d = NetComponentWizard(self.w, self.w.form); d.accept()
        self.assertTrue(self.w.insert_net_component(d.result_gadget))
        self.assertEqual(len(self.w.history), 1)
        self.assertEqual(self.w.validation_error, '')
        saved = Form.loads(self.w.form.dumps()).pml()
        self.assertIn('BindToDataSource', saved)
        next_dialog = NetComponentWizard(self.w, self.w.form)
        self.assertEqual(next_dialog.name.text(), 'netGrid2')
        self.w.undo(); self.assertEqual(self.w.form.gadgets, [])
        self.w.redo(); self.assertEqual(self.w.form.pml(), saved)
        next_dialog.close(); d.close()

    def test_insert_into_frame_and_active_tab(self):
        for style in ('FRAME', 'TABSET'):
            frame = Gadget(kind='frame', name='frame', frame_style=style, width=50, height=15, x=0, y=0)
            gadgets = [frame]
            parent = frame
            if style == 'TABSET':
                parent = Gadget(kind='frame', name='page', parent='frame', width=50, height=15, x=0, y=0)
                gadgets.append(parent)
            self.w.form = Form(gadgets=gadgets); self.w.selected = 0; self.w.refresh()
            self.assertTrue(self.w.insert_net_component(NetComponentSpec().gadget()))
            self.assertEqual(self.w.form.gadgets[-1].parent, parent.name)

    def test_failed_insert_preserves_history_redo_and_design(self):
        w = self.w
        for form in (Form(width=10, height=5), Form(constructor_mode='SOURCE'),
                     Form(program_mode='SOURCE'), Form(form_type='MAIN'),
                     Form(gadgets=[Gadget(name='netGrid1Control')])):
            w.form = form; w.selected = None; w.refresh()
            before = w.form.dumps(); history = list(w.history); future = list(w.future); dirty = w.dirty
            self.assertFalse(w.insert_net_component(NetComponentSpec().gadget()))
            self.assertEqual(w.form.dumps(), before); self.assertEqual(w.history, history)
            self.assertEqual(w.future, future); self.assertEqual(w.dirty, dirty)


if __name__ == '__main__': unittest.main()
