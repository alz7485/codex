import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QPlainTextEdit
from e3d_designer.app import Window
from e3d_designer.import_editor import ImportCodeDialog
from e3d_designer.mac_import import import_mac,read_mac,MacImportError
from e3d_designer.model import Form


def source(declarations,methods=''):
    return f"Setup Form !!Demo Dialog Size 70 22\n{declarations}\nExit\nShow !!Demo\n{methods}"


GOOD="Button .Good At X 1 Y 1 'Good'"


class PartialMacTests(unittest.TestCase):
    def test_supported_file_matches_strict_import(self):
        text=source(GOOD)
        self.assertEqual(import_mac(text,partial=True).form.dumps(),import_mac(text).form.dumps())

    def test_unknown_declaration_preserved_as_reference_not_executable(self):
        text=source("Mystery .Unknown 'x'\n"+GOOD)
        with self.assertRaises(MacImportError):import_mac(text)
        result=import_mac(text,partial=True);form=result.form
        self.assertEqual([g.name for g in form.gadgets],['Good'])
        self.assertEqual(form.partial_import_source,text)
        self.assertIn('2〜2行',form.partial_import_notes[0])
        self.assertNotIn('Mystery',form.pml())
        restored=Form.loads(form.dumps())
        self.assertEqual(restored.partial_import_source,text)
        self.assertEqual(restored.partial_import_notes,form.partial_import_notes)

    def test_invalid_gadget_does_not_discard_supported_siblings(self):
        form=import_mac(source("Text .Bad At X (2+3) Y 1 'Bad' Width 10 Is String\n"+GOOD),partial=True).form
        self.assertEqual([g.name for g in form.gadgets],['Good'])

    def test_bad_child_keeps_nested_tab_parent_and_other_children(self):
        declarations="""Frame .Pages Tabset At X 1 Y 1 'Pages' Width 40
Frame .First 'First'
Frame .Group 'Group'
Mystery .Bad 'x'
Button .Inside At X 1 Y 1 'Inside'
Exit
Exit
Exit
Button .Good At X 1 Y 15 'Good'"""
        form=import_mac(source(declarations),partial=True).form
        self.assertEqual(form.named('Inside').parent,'Group')
        self.assertEqual(form.named('Group').parent,'First')
        self.assertEqual(form.named('First').parent,'Pages')
        self.assertEqual(form.named('Good').parent,'')
        form.pml()

    def test_bad_frame_header_discards_entire_subtree(self):
        declarations="""Frame .Bad 'Bad' Unsupported
Frame .Nested 'Nested'
Button .Inside 'Inside'
Exit
Exit
"""+GOOD
        form=import_mac(source(declarations),partial=True).form
        self.assertEqual([g.name for g in form.gadgets],['Good'])
        self.assertIn('2〜6行',form.partial_import_notes[0])

    def test_unknown_block_does_not_consume_following_gadget(self):
        declarations="Grid .Opaque 'Grid'\nStuff 'Unknown'\nExit\n"+GOOD
        form=import_mac(source(declarations),partial=True).form
        self.assertEqual([g.name for g in form.gadgets],['Good'])
        self.assertNotIn('Stuff',form.after_show_code)
        self.assertNotIn('Grid',form.pml())

    def test_unknown_block_with_implicit_form_exit_keeps_sibling_in_form(self):
        text=source("Grid .Opaque 'Grid'\nStuff 'Unknown'\nExit\n"+GOOD)
        text=text.replace("\nExit\nShow !!Demo","\nShow !!Demo")
        form=import_mac(text,partial=True).form
        self.assertEqual([g.name for g in form.gadgets],['Good'])
        self.assertEqual(form.named('Good').parent,'')
        self.assertNotIn('Button',form.after_show_code)

    def test_invalid_menu_block_keeps_following_gadget(self):
        form=import_mac(source("Menu .Broken\nAdd 'Only label'\nExit\n"+GOOD),partial=True).form
        self.assertEqual(form.menus,[])
        self.assertEqual([g.name for g in form.gadgets],['Good'])

    def test_optional_menu_exit_preserves_menu_and_following_gadget(self):
        form=import_mac(source("Menu .Broken\nAdd 'Item' 'Q CE'\n"+GOOD),partial=True).form
        self.assertEqual(form.menus[0].items[0].command,'Q CE')
        self.assertEqual([g.name for g in form.gadgets],['Good'])

    def test_invalid_view_block_and_missing_exit_do_not_swallow_sibling(self):
        for ending in ('Exit\n',''):
            with self.subTest(ending=ending):
                declarations="View .Broken Area Width Wrong\n"+ending+GOOD
                form=import_mac(source(declarations),partial=True).form
                self.assertEqual([g.name for g in form.gadgets],['Good'])

    def test_missing_relative_target_discards_dependent_only(self):
        declarations=("Mystery .Missing 'x'\n"
                      "Button .Dependent At Xmax.Missing Ymin.Missing 'Dependent'\n"+GOOD)
        form=import_mac(source(declarations),partial=True).form
        self.assertEqual([g.name for g in form.gadgets],['Good'])
        self.assertEqual(len(form.partial_import_notes),2)

    def test_unlinked_methods_and_default_values_are_retained(self):
        methods="""Define Method .DEFAULT()
!this.Input.Val = 'Ready'
Endmethod
Define Method .Standalone(!value Is Real) Is Real
!result = !value * 2
Return !result
Endmethod"""
        text=source("Mystery .Bad 'x'\nText .Input 'Input' Width 10 Is String",methods)
        form=import_mac(text,partial=True).form
        self.assertEqual(form.named('Input').initial,'Ready')
        self.assertEqual(form.extra_methods[0].name,'Standalone')
        self.assertIn('Return !result',form.extra_methods[0].body)
        self.assertIn('Standalone',form.pml())

    def test_malformed_method_is_skipped_and_next_unlinked_method_remains(self):
        methods="""Define Method .Broken()
$P 'broken'
Define Method .Standalone(!value Is Real)
$P !value
Endmethod"""
        form=import_mac(source(GOOD,methods),partial=True).form
        self.assertEqual([m.name for m in form.extra_methods],['Standalone'])
        self.assertNotIn("$P 'broken'",form.pml())
        self.assertIn('ENDMETHODなし',form.partial_import_notes[0])

    def test_comment_commands_never_become_executable_after_skipping(self):
        text=source("Mystery .Bad 'x' $( note\n$M 'never.mac'\n$)\n"+GOOD)
        form=import_mac(text,partial=True).form
        from e3d_designer.pml_syntax import mask_non_code
        self.assertNotIn('$M',mask_non_code(form.pml()))
        self.assertIn("$M 'never.mac'",form.partial_import_source)

    def test_bad_header_boundary_or_limits_are_not_silently_repaired(self):
        texts=(source(GOOD).replace('Dialog Size','Document Size'),
               source(GOOD).replace('Show !!Demo','Show !!Other').replace('\nExit\n','\n'),
               source(GOOD)+'\nSetup Form !!Other Dialog\nExit',
               source('\n'.join("Mystery .Bad 'x'" for _ in range(102))),
               source('\n'.join(f"Button .B{i} 'B'" for i in range(501))))
        for text in texts:
            with self.subTest(prefix=text[:70]),self.assertRaises(ValueError):import_mac(text,partial=True)
        for text in ('no form',source(GOOD)+'\x00'):
            with self.assertRaises(ValueError):import_mac(text,partial=True)

    def test_cp932_crlf_source_path_and_reference_are_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sample.mac'
            text=source("Mystery .Bad '未対応'\n"+GOOD)
            path.write_bytes(text.replace('\n','\r\n').encode('cp932'))
            result=read_mac(path,partial=True)
            self.assertEqual(result.form.partial_import_source,text)
            self.assertEqual(result.form.source_mac_path,str(path.resolve()))
            self.assertEqual(result.encoding,'SJIS（CP932）')


class PartialMacGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json')
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_partial_menu_open_save_and_readonly_original(self):
        path=self.folder/'original.mac';text=source("Mystery .Bad 'x'\n"+GOOD)
        path.write_text(text);original=path.read_bytes()
        with patch('e3d_designer.app.QFileDialog.getOpenFileName',return_value=(str(path),'')), \
             patch('e3d_designer.app.QMessageBox.information') as info:
            self.w.open_partial_mac()
            self.assertIn('部分取り込み',info.call_args.args[2])
        self.assertEqual([g.name for g in self.w.form.gadgets],['Good'])
        self.assertIsNone(self.w.path);self.assertTrue(self.w.dirty)
        self.assertFalse(self.w.partial_notice.isHidden())
        design=self.folder/'saved.json'
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(design),'')):
            self.assertTrue(self.w.save())
        restored=Form.loads(design.read_text())
        self.assertEqual(restored.partial_import_source,text)
        dialog=ImportCodeDialog(self.w,restored)
        readonly=[editor for editor in dialog.findChildren(QPlainTextEdit) if editor.isReadOnly()]
        self.assertTrue(any(editor.toPlainText()==text for editor in readonly))
        dialog.reject();dialog.close()
        self.assertEqual(path.read_bytes(),original)

    def test_failed_partial_import_keeps_current_design_and_history(self):
        self.w.add('button');before=self.w.form.dumps();history=list(self.w.history)
        path=self.folder/'invalid.mac';path.write_text('no form')
        with patch('e3d_designer.app.QMessageBox.warning'):
            self.assertFalse(self.w.open_design(path,confirmed=True,partial=True))
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,history)
