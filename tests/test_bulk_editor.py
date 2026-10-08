import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit, QPlainTextEdit

from e3d_designer.app import Window
from e3d_designer.bulk_editor import BulkPropertiesDialog, apply_values, editable_reason
from e3d_designer.model import Form, Gadget, Method


class BulkEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app = QApplication.instance() or QApplication([])

    def form(self):
        return Form(gadgets=[Gadget(name='First', label='First'), Gadget(name='Second', label='Second', y=3),
            Gadget(kind='paragraph', name='Label', label='Label', y=5), Gadget(kind='text', name='Entry', y=7)])

    def dialog(self, form=None, selection=()):
        d = BulkPropertiesDialog(None, form or self.form(), selection)
        self.addCleanup(d.deleteLater);self.addCleanup(d.close)
        return d

    def select(self, d, rows):
        d.table.clearSelection()
        for row in rows:d.table.selectionModel().select(d.table.model().index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def test_batch_skips_unsupported_and_preserves_input_case_and_original(self):
        f = self.form();before = copy.deepcopy(f)
        new, count, skipped = apply_values(f, [0, 1, 2, 3], 'command', '$M /Server/MixedCase.mac')
        self.assertEqual((count, skipped), (3, 1));self.assertEqual(f, before)
        self.assertEqual(new.gadgets[2].command, '')
        self.assertIn('$M /Server/MixedCase.mac', new.pml())

    def test_shared_method_assignment_adopts_body_and_update_reaches_unselected_caller(self):
        f = self.form();f.gadgets[0].callback = 'OnClick';f.gadgets[0].body = '!Value = 3'
        f, _, _ = apply_values(f, [1], 'callback', 'OnClick')
        self.assertEqual(f.gadgets[1].body, '!Value = 3')
        updated, _, _ = apply_values(f, [1], 'body', '!Value = 7\n!Name = |Mixed Case|')
        self.assertEqual(updated.gadgets[0].body, updated.gadgets[1].body)
        self.assertEqual(f.gadgets[0].body, '!Value = 3')
        self.assertEqual(updated.pml().lower().count('define method .onclick'), 1)

    def test_body_allocates_individual_unique_names(self):
        f = self.form();f.extra_methods = [Method('on_First', body='!A = 1')]
        new, _, _ = apply_values(f, [0, 1], 'body', '!A = 2\n!B = 3')
        self.assertEqual(new.gadgets[0].callback, 'on_First_2')
        self.assertEqual(new.gadgets[1].callback, 'on_Second')
        self.assertIn('!A = 2\n!B = 3', new.gadgets[0].body)
        new.validate();self.assertTrue(new.pml())

    def test_command_and_method_switch_is_explicit_and_clears_old_call_expression(self):
        f = self.form();g = f.gadgets[0];g.callback = 'Old';g.body = '!A = 1';g.callback_expression = '!THIS.Old()'
        new, _, _ = apply_values(f, [0], 'command', 'MyCommand')
        self.assertEqual((new.gadgets[0].callback, new.gadgets[0].callback_expression), ('', ''))
        self.assertEqual(new.gadgets[0].body, '!A = 1')
        self.assertTrue(editable_reason(new, new.gadgets[0], 'body'))
        new, _, _ = apply_values(new, [0], 'callback', 'New')
        self.assertEqual(new.gadgets[0].command, '');self.assertIn('Define Method .New()', new.pml())

    def test_incompatible_shared_callback_rejects_entire_batch(self):
        f = Form(gadgets=[Gadget(name='Run'), Gadget(kind='combo', name='Choice', y=3)])
        before = copy.deepcopy(f)
        with self.assertRaisesRegex(ValueError, 'COMBO'):apply_values(f, [0, 1], 'callback', 'Same')
        self.assertEqual(f, before)

    def test_retained_body_can_be_reactivated_with_automatic_method_name(self):
        f = self.form();f.gadgets[0].body = '!Keep = 1'
        updated, _, _ = apply_values(f, [0], 'body', '!Keep = 1')
        self.assertEqual(updated.gadgets[0].callback, 'on_First')
        self.assertIn('!Keep = 1', updated.pml());self.assertEqual(f.gadgets[0].callback, '')

    def test_source_constructor_and_default_values_are_disabled(self):
        f = Form(constructor_mode='SOURCE', default_mode='SOURCE', constructor_body='!Keep = 1',
            gadgets=[Gadget(kind='combo', name='Choice'), Gadget(kind='text', name='Text', y=3)])
        self.assertTrue(editable_reason(f, f.gadgets[0], 'callback'))
        self.assertTrue(editable_reason(f, f.gadgets[0], 'body'))
        self.assertTrue(editable_reason(f, f.gadgets[1], 'initial'))
        updated, _, _ = apply_values(f, [1], 'command', '!Do = 1')
        self.assertEqual(updated.constructor_body, '!Keep = 1')

    def test_default_body_routes_to_common_default(self):
        f = self.form();f.gadgets[0].callback = 'DEFAULT';f.gadgets[1].callback = 'default'
        new, _, _ = apply_values(f, [0], 'body', '!MyDefault = 1')
        self.assertEqual(new.default_body, '!MyDefault = 1')
        self.assertEqual(new.gadgets[0].body, '');self.assertEqual(new.gadgets[1].body, '')
        self.assertIn('!MyDefault = 1', new.pml())

    def test_fixed_dimensions_and_auto_width_disabled_then_explicit_enabled(self):
        f = Form(gadgets=[Gadget(name='Run', width_explicit=False), Gadget(kind='text', name='Entry', y=3)])
        self.assertTrue(editable_reason(f, f.gadgets[0], 'width'))
        self.assertTrue(editable_reason(f, f.gadgets[1], 'height'))
        f, _, _ = apply_values(f, [0], 'width_explicit', 'TRUE')
        f, _, _ = apply_values(f, [0], 'width', '12.345')
        self.assertEqual(f.gadgets[0].width, 12.345);self.assertIn('Width 12.345', f.pml())

    def test_frame_size_updates_emitted_axes_and_tab_page_is_readonly(self):
        f = Form(gadgets=[Gadget(kind='frame', name='Group', width=20, height=8)])
        f, _, _ = apply_values(f, [0], 'width', '25')
        f, _, _ = apply_values(f, [0], 'height', '10')
        self.assertIn("Frame .Group 'Run' Width 25 Height 10", f.pml())
        tabs = Form(gadgets=[Gadget(kind='frame', name='Tabs', frame_style='TABSET', tabs=[Gadget(kind='frame', name='Page')])])
        self.assertTrue(editable_reason(tabs, tabs.named('Page'), 'width'))

    def test_boolean_initial_rejects_invalid_for_whole_batch(self):
        f = Form(gadgets=[Gadget(kind='toggle', name='Check'), Gadget(kind='text', name='Text', y=3)])
        with self.assertRaises(ValueError):apply_values(f, [0, 1], 'initial', 'no')
        self.assertEqual(f.gadgets[1].initial, '')
        new, _, _ = apply_values(f, [0, 1], 'initial', '')
        self.assertEqual(new.gadgets[0].initial, '')

    def test_filtered_hidden_selected_rows_never_receive_bulk_change(self):
        d = self.dialog(selection={'First', 'Second', 'Label', 'Entry'})
        d.type_filter.setCurrentIndex(d.type_filter.findData('button'))
        self.assertEqual(d.selected_rows(), [0, 1])
        d.batch_text.setPlainText('DoButtons');d.apply_batch()
        self.assertEqual(d.draft.gadgets[0].command, 'DoButtons')
        self.assertEqual(d.draft.gadgets[3].command, '')
        d.search.setText('Second');self.assertEqual(d.selected_rows(), [1])
        d.batch_text.setPlainText('Other');d.apply_batch()
        self.assertEqual(d.draft.gadgets[0].command, 'DoButtons');self.assertEqual(d.draft.gadgets[1].command, 'Other')

    def test_select_visible_and_frame_subtype_filters(self):
        f = Form(gadgets=[Gadget(kind='frame', name='Group'), Gadget(kind='frame', name='Tabs', frame_style='TABSET', x=20,
            tabs=[Gadget(kind='frame', name='Page')]), Gadget(name='Run', y=5)])
        d = self.dialog(f)
        for key, names in [('frame', {'Group', 'Tabs', 'Page'}), ('FRAME', {'Group'}), ('TABSET', {'Tabs'}), ('PAGE', {'Page'})]:
            d.type_filter.setCurrentIndex(d.type_filter.findData(key));d.select_visible()
            self.assertEqual({d.draft.gadgets[r].name for r in d.selected_rows()}, names)

    def test_switch_header_keeps_draft_values_and_selection(self):
        d = self.dialog(selection={'First', 'Second'})
        d.table.item(0, 2).setText('MixedCommand')
        d.set_column(2, 'label');d.table.item(0, 2).setText('New Label')
        d.set_column(2, 'command')
        self.assertEqual(d.table.item(0, 2).text(), 'MixedCommand');self.assertEqual(d.selected_rows(), [0, 1])
        self.assertEqual(d.draft.gadgets[0].label, 'New Label')

    def test_unsupported_cells_gray_and_noneditable_and_empty_selection_disabled(self):
        d = self.dialog()
        item = d.table.item(2, 2)
        self.assertFalse(item.flags() & Qt.ItemIsEditable);self.assertTrue(item.toolTip())
        self.assertFalse(d.apply_button.isEnabled())
        self.select(d, [2]);self.assertFalse(d.apply_button.isEnabled())
        d.batch_field.setCurrentIndex(d.batch_field.findData('background'));self.assertTrue(d.apply_button.isEnabled())

    def test_invalid_cell_survives_column_switch_and_blocks_accept_until_fixed(self):
        d = self.dialog()
        d.set_column(2, 'background');d.table.item(0, 2).setText('bad')
        self.assertTrue(d.invalid_cells);self.assertEqual(d.table.item(0, 2).text(), 'bad')
        d.set_column(2, 'comment');d.accept();self.assertIsNone(d.result_form)
        d.set_column(2, 'background');self.assertEqual(d.table.item(0, 2).text(), 'bad')
        d.table.item(0, 2).setText('48');d.accept()
        self.assertEqual(d.result_form.gadgets[0].background, '48')

    def test_invalid_bulk_is_atomic_and_does_not_erase_batch_text(self):
        d = self.dialog(selection={'First', 'Second'});before = copy.deepcopy(d.draft)
        d.batch_field.setCurrentIndex(d.batch_field.findData('background'))
        d.batch_text.setPlainText('bad');d.apply_batch()
        self.assertEqual(d.draft, before);self.assertEqual(d.batch_text.toPlainText(), 'bad');self.assertTrue(d.error.text())

    def test_cancel_does_not_change_original(self):
        f = self.form();before = copy.deepcopy(f);d = self.dialog(f, {'First'})
        d.table.item(0, 2).setText('Changed');d.reject()
        self.assertEqual(f, before);self.assertIsNone(d.result_form)

    def test_json_and_sjis_mac_roundtrip_keeps_bulk_fields(self):
        from e3d_designer.mac_import import import_mac
        f = self.form()
        f, _, _ = apply_values(f, [0, 1], 'background', '48')
        f, _, _ = apply_values(f, [0, 1], 'callback', 'SharedMethod')
        f, _, _ = apply_values(f, [1], 'body', "!Value = 'Mixed Case'\n!this.Entry.Val = '距離'")
        f, _, _ = apply_values(f, [3], 'initial', 'Initial')
        restored = Form.loads(f.dumps())
        self.assertEqual(restored, f)
        mac = f.pml().replace('\n', '\r\n').encode('cp932')
        imported = import_mac(mac.decode('cp932')).form
        for name in ('First', 'Second'):
            self.assertEqual(imported.named(name).callback, 'SharedMethod')
            self.assertEqual(imported.named(name).background, '48')
            self.assertIn('Mixed Case', imported.named(name).body)
        self.assertEqual(imported.named('Entry').initial, 'Initial')

    def test_bulk_color_picker_applies_only_after_explicit_setting(self):
        from e3d_designer.color_picker import ColorPicker
        d = self.dialog(selection={'First', 'Second'})
        d.batch_field.setCurrentIndex(d.batch_field.findData('background'))
        def select_color(dialog):dialog.choose('168');return QDialog.Accepted
        with patch.object(ColorPicker, 'exec', select_color):d.choose_color()
        self.assertEqual(d.draft.gadgets[0].background, '')
        self.assertEqual(d.batch_text.toPlainText(), '168')
        d.apply_batch();self.assertEqual(d.draft.gadgets[1].background, '168')

    def test_common_method_manager_stays_inside_outer_transaction(self):
        from e3d_designer.method_manager import MethodManagerDialog
        f = self.form();before = copy.deepcopy(f);d = self.dialog(f)
        def add_method(dialog):
            dialog.add();dialog.name.setText('MyHelper');dialog.body.setPlainText('!A = 1')
            dialog.accept();return QDialog.Accepted
        with patch.object(MethodManagerDialog, 'exec', add_method):d.manage_helpers()
        self.assertEqual(d.draft.extra_methods[0].name, 'MyHelper')
        d.reject();self.assertEqual(f, before)

    def test_ok_invalid_active_cell_keeps_dialog_open_and_typed_value(self):
        d = self.dialog();d.set_column(2, 'background');d.show();self.app.processEvents()
        d.table.setCurrentCell(0, 2);d.table.editItem(d.table.item(0, 2));self.app.processEvents()
        editor = d.table.findChild(QLineEdit);QTest.keyClicks(editor, 'invalid')
        QTest.mouseClick(d.buttons.button(QDialogButtonBox.Ok), Qt.LeftButton);self.app.processEvents()
        self.assertIsNone(d.result_form);self.assertTrue(d.isVisible());self.assertTrue(d.invalid_cells)
        self.assertEqual(d.table.item(0, 2).text(), 'invalid')

    def test_boolean_and_form_processing_choices(self):
        f = Form(gadgets=[Gadget(kind='toggle', name='Check')]);d = self.dialog(f, {'Check'})
        d.batch_field.setCurrentIndex(d.batch_field.findData('initial'))
        self.assertEqual(d.batch_stack.currentIndex(), 1)
        self.assertEqual([d.batch_choices.itemText(i) for i in range(d.batch_choices.count())], ['', 'TRUE', 'FALSE'])
        d.batch_choices.setCurrentText('TRUE');d.apply_batch();self.assertEqual(d.draft.gadgets[0].initial, 'TRUE')

    def test_active_cell_commits_when_ok_clicked(self):
        d = self.dialog();d.show();self.app.processEvents()
        d.table.setCurrentCell(0, 2);d.table.editItem(d.table.item(0, 2));self.app.processEvents()
        editor = d.table.findChild(QLineEdit);self.assertIsNotNone(editor)
        QTest.keyClicks(editor, 'LastTypedCommand')
        QTest.mouseClick(d.buttons.button(QDialogButtonBox.Ok), Qt.LeftButton);self.app.processEvents()
        self.assertEqual(d.result_form.gadgets[0].command, 'LastTypedCommand')

    def test_multiline_method_commit_and_outer_ok(self):
        d = self.dialog();d.show();self.app.processEvents()
        d.table.setCurrentCell(0, 4);d.table.editItem(d.table.item(0, 4));self.app.processEvents()
        editor = d.table.findChild(QPlainTextEdit);self.assertIsNotNone(editor)
        QTest.keyClicks(editor, '!A = 1');QTest.keyClick(editor, Qt.Key_Return);QTest.keyClicks(editor, '!B = 2')
        QTest.keyClick(editor, Qt.Key_Return, Qt.ControlModifier);self.app.processEvents()
        d.accept();self.assertEqual(d.result_form.gadgets[0].body, '!A = 1\n!B = 2')

    def test_window_integration_is_one_undo_and_noop_keeps_redo_and_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Window(settings_path=Path(tmp)/'settings.json');w.form = self.form();w.refresh()
            before = copy.deepcopy(w.form);future = Form(title='Future');w.future = [future];w.dirty = False
            try:
                def changed(dialog):
                    dialog.apply_change([0, 1], 'command', 'BatchCommand');dialog.accept();return QDialog.Accepted
                with patch.object(BulkPropertiesDialog, 'exec', changed):w.edit_bulk_properties()
                self.assertEqual(len(w.history), 1);self.assertTrue(w.dirty);self.assertEqual(w.future, [])
                w.undo();self.assertEqual(w.form, before)
                w.dirty = False;previous_future = copy.deepcopy(w.future)
                with patch.object(BulkPropertiesDialog, 'exec', lambda d:(d.accept(), QDialog.Accepted)[1]):w.edit_bulk_properties()
                self.assertFalse(w.dirty);self.assertEqual(w.future, previous_future)
                w.redo();self.assertEqual(w.form.gadgets[1].command, 'BatchCommand')
            finally:w.dirty = False;w.close();self.app.processEvents()

