import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget


def source(body):
    return f'Setup Form !!Demo Size 80 60 Dialog\n{body}\nExit\nShow !!Demo'


FRAME="Frame .Group At X 7 Y 5 'Group' Width 20 Height 8\nButton .Child At X 2 Y 3 'Child' Width 5\nPath Down\nExit\nButton .After 'After' Width 5"
PARTIAL="Button .Base At X 4 Y 3 'Base' Width 10\nPath Down\nButton .Partial At X 30 'Partial' Width 5"


def mixed_form():
    original=import_mac(source("Button .Base At X 4 Y 3 'Base' Width 10\nPath Down\nButton .Row 'Row' Width 5")).form
    target=Form(width=80,height=60,gadgets=[Gadget(name='Base',x=4,y=3,width=10),
        Gadget(kind='list',name='Edge',width=10,height=5,layout_mode='AUTO',vgap=2)])
    result,index=clone_subtree(target,original,1);result.gadgets[index].name='Row'
    return result


class PathLayoutAuditTests(unittest.TestCase):
    def test_explicit_frame_dimensions_and_following_path_survive_roundtrip(self):
        f=import_mac(source(FRAME)).form
        self.assertEqual(f.named('Group').frame_size_axes,'WH')
        self.assertEqual(Form.loads(f.dumps()).dumps(),f.dumps())
        self.assertEqual(import_mac(source(FRAME),partial=True).form.dumps(),f.dumps())
        restored=import_mac(f.pml()).form
        for g in f.gadgets:self.assertEqual(restored.geometry(restored.named(g.name)),f.geometry(g))
        self.assertEqual(restored.geometry(restored.named('After'))[:2],(7,14))

    def test_only_explicit_frame_dimensions_are_emitted(self):
        for declaration,axes in (('', ''),('Width 20','W'),('Height 8','H'),('Width 20 Height 8','WH')):
            with self.subTest(declaration=declaration):
                f=import_mac(source(f"Frame .Group At X 7 Y 5 'Group' {declaration}\nButton .Child At X 2 Y 3 'Child' Width 5\nExit")).form
                self.assertEqual(f.named('Group').frame_size_axes,axes)
                line=next(line for line in f.pml().splitlines() if 'Frame .Group' in line)
                self.assertEqual('Width' in line,'W' in axes);self.assertEqual('Height' in line,'H' in axes)
                r=import_mac(f.pml()).form
                self.assertEqual(r.geometry(r.named('Group')),f.geometry(f.named('Group')))

    def test_nested_tabset_dimensions_survive(self):
        f=import_mac(source("Frame .Tabs Tabset At X 3 Y 2 'Tabs' Width 40 Height 20\nFrame .Page 'Page' Width 40 Height 20\nFrame .Inner At X 2 Y 3 'Inner' Width 20 Height 8\nButton .Child At X 1 Y 1 'Child' Width 5\nExit\nExit\nExit")).form
        restored=import_mac(f.pml()).form
        for g in f.gadgets:self.assertEqual(restored.geometry(restored.named(g.name)),f.geometry(g))

    def test_width_zero_frame_is_still_automatic(self):
        f=import_mac(source("Frame .Group 'Group' Width 0\nButton .Child At X 2 Y 3 'Child' Width 5\nExit")).form
        self.assertEqual(f.named('Group').frame_size_axes,'W')
        self.assertNotIn('Width 0',f.pml())
        r=import_mac(f.pml()).form
        self.assertEqual(r.geometry(r.named('Group')),f.geometry(f.named('Group')))

    def test_edited_explicit_height_and_copy_are_preserved(self):
        f=import_mac(source(FRAME)).form;f.named('Group').height=10
        r=import_mac(f.pml()).form
        self.assertEqual(r.geometry(r.named('After'))[:2],(7,16))
        copied,index=clone_subtree(Form(width=80,height=60),f,0)
        self.assertEqual(copied.gadgets[index].frame_size_axes,'WH')
        self.assertEqual(import_mac(copied.pml()).form.named(copied.gadgets[index].name).height,10)

    def test_invalid_frame_dimension_metadata_is_rejected(self):
        for value in ('HW','X',None,True,1,[]):
            with self.subTest(value=value),self.assertRaises(ValueError):Form(gadgets=[Gadget(frame_size_axes=value)]).validate()

    def test_mixed_spacing_cannot_silently_export_different_positions(self):
        f=mixed_form();before=f.dumps();f.validate()
        self.assertEqual(Form.loads(before).dumps(),before)
        with self.assertRaisesRegex(ValueError,'Row.*VDIST'):f.pml()
        self.assertEqual(f.dumps(),before)

    def test_explicit_spacing_can_resolve_mixed_path_without_unlocking(self):
        f=mixed_form();g=f.named('Row');g.path_row_step=False;g.vgap=1
        restored=import_mac(f.pml()).form
        self.assertEqual(restored.geometry(restored.named('Row')),f.geometry(g))
        self.assertEqual(restored.named('Row').layout_mode,'AUTO')

    def test_explicit_spacing_in_other_container_does_not_block_rows(self):
        f=import_mac(source("Frame .Group At X 4 Y 3 'Group' Width 20 Height 8\nButton .Child At X 1 Y 1 'Child' Width 5\nVdist 2\nButton .Edge 'Edge' Width 5\nExit\nPath Down\nButton .Row 'Row' Width 5")).form
        restored=import_mac(f.pml()).form
        self.assertTrue(restored.named('Row').path_row_step)
        self.assertEqual(restored.geometry(restored.named('Row')),f.geometry(f.named('Row')))


class PathLayoutAuditGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.directory=Path(self.folder.name)
        self.w=Window(settings_path=self.directory/'settings.json');self.w.show();self.app.processEvents()
        self.w.form=import_mac(source(PARTIAL)).form;self.w.selected=1;self.w.history.clear();self.w.refresh()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.folder.cleanup()

    def test_inspector_displays_effective_path_coordinates_without_changing_model(self):
        self.w.form.named('Base').x=8;self.w.form.named('Base').y=7
        before=self.w.form.dumps();self.w.refresh()
        self.assertEqual((self.w.fields['x'].value(),self.w.fields['y'].value()),(30,8))
        self.assertEqual(self.w.form.dumps(),before)
        self.w.form.named('Base').y=10;self.w.sync_selection()
        self.assertEqual(self.w.fields['y'].value(),11)
        g=self.w.form.named('Partial');raw=(g.x,g.y,g.path_axes)
        self.w.fields['label'].setText('Edited');self.w.update_gadget()
        g=self.w.form.named('Partial');self.assertEqual((g.x,g.y,g.path_axes),raw)
        self.assertEqual(self.w.fields['y'].value(),11)

    def test_relative_inspector_and_resize_preview_show_effective_position(self):
        g=self.w.form.named('Partial');g.layout_mode='RELATIVE';g.xref=g.yref='Base';g.yoffset=2
        self.w.refresh();before=self.w.form.dumps();xy=self.w.form.geometry(g)[:2]
        self.assertEqual((self.w.fields['x'].value(),self.w.fields['y'].value()),xy)
        self.assertEqual(self.w.form.dumps(),before)
        self.w.form.named('Base').height=3;self.w.resize_preview()
        xy=self.w.form.geometry(g)[:2]
        self.assertEqual((self.w.fields['x'].value(),self.w.fields['y'].value()),xy)

    def test_row_mode_toggle_is_undoable_and_keeps_path_locked(self):
        before=self.w.form.dumps();self.assertTrue(self.w.path_rows.isChecked())
        self.w.path_rows.setChecked(False)
        self.assertFalse(self.w.form.named('Partial').path_row_step)
        self.assertEqual(self.w.form.named('Partial').layout_mode,'AUTO')
        self.assertIn('Vdist 1',self.w.form.pml());self.assertEqual(len(self.w.history),1)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before);self.w.choose_row(1);self.assertTrue(self.w.path_rows.isChecked())
        self.w.redo();self.w.choose_row(1);self.assertFalse(self.w.path_rows.isChecked())

    def test_spacing_edit_updates_mode_checkbox(self):
        self.w.fields['vgap'].setValue(2)
        self.assertFalse(self.w.path_rows.isChecked());self.assertFalse(self.w.form.named('Partial').path_row_step)

    def test_row_mode_toggle_fails_atomically_when_geometry_does_not_fit(self):
        g=self.w.form.named('Partial');g.path_row_step=False;g.vgap=0
        base=self.w.form.named('Base');base.kind='frame';base.height=5;base.y=54
        self.w.form.height=60;self.w.form.validate()
        self.w.refresh();before=self.w.form.dumps();self.w.history.clear()
        self.w.path_rows.setChecked(True)
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[])
        self.assertFalse(self.w.path_rows.isChecked())

    def test_export_error_leaves_existing_mac_and_source_untouched(self):
        self.w.form=mixed_form();self.w.selected=2;self.w.refresh()
        before=self.w.form.dumps();path=self.directory/'output.mac';path.write_bytes(b'existing macro')
        with patch('e3d_designer.app.QMessageBox.warning') as warning,patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(path),'')) as dialog:
            self.w.export();warning.assert_called_once();dialog.assert_not_called()
            self.assertIn('Row',warning.call_args.args[-1])
        self.assertEqual(path.read_bytes(),b'existing macro');self.assertEqual(self.w.form.dumps(),before)
        self.w.path_rows.setChecked(False)
        self.assertEqual(self.w.form.named('Row').layout_mode,'AUTO')
        import_mac(self.w.form.pml())
