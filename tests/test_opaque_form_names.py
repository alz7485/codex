import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window
from e3d_designer.draft_validation import validate_draft
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget,Method
from e3d_designer.names import rename
from e3d_designer.symbols import split_form_reference,form_file_stem


class OpaqueFormNameTests(unittest.TestCase):
    def test_import_does_not_enforce_identifier_spelling(self):
        for symbol in ('123-name','_CDR..HD','_CDR.','_CDR.9HD','測定-フォーム',
                       '!!9button','@Form[1]','/Form:HD','_A$B','!!','!Demo()',"'Demo'"):
            with self.subTest(symbol=symbol):
                code=f'Setup Form {symbol}\nButton .Run At Width 5\nExit\nShow {symbol}'
                f=import_mac(code).form
                self.assertEqual(f.symbol,symbol)
                self.assertEqual(import_mac(code,partial=True).form.dumps(),f.dumps())
                self.assertEqual(Form.loads(f.dumps()).symbol,symbol)
                validate_draft(f)
                self.assertEqual(import_mac(f.pml()).form.symbol,symbol)

    def test_generated_constructor_keeps_case_numbers_symbols_and_unicode(self):
        for symbol in ('9button','測定-フォーム','/Form:HD','@Form[1]','_A$B','_CDR..HD'):
            with self.subTest(symbol=symbol):
                prefix,name=split_form_reference(symbol)
                f=Form(name=name,form_prefix=prefix,gadgets=[Gadget(kind='text',name='Value',initial='MiXeD')])
                code=f.pml()
                self.assertIn(f'Define Method .{name}()',code)
                restored=import_mac(code).form
                self.assertEqual(restored.symbol,symbol)
                self.assertEqual(restored.named('Value').initial,'MiXeD')

    def test_source_constructor_helper_order_and_rename_follow_opaque_name(self):
        text=('Setup Form !!測定-フォーム\nExit\nShow !!測定-フォーム\n'
              'Define Method .測定-フォーム()\n!this.Work()\nEndmethod\n'
              "Define Method .Work()\n$P 'Ready'\nEndmethod")
        f=import_mac(text).form
        f.after_show_code='!!測定-フォーム.測定-フォーム()\n!!測定-フォーム別.Value.val = 1'
        renamed=rename(f,'form',None,'!!123-next')
        self.assertIn('!!123-next.123-next()',renamed.after_show_code)
        self.assertIn('!!測定-フォーム別.Value.val',renamed.after_show_code)
        code=renamed.pml()
        self.assertLess(code.index('Define Method .Work'),code.index('Define Method .123-next'))
        self.assertEqual(import_mac(code).form.symbol,'!!123-next')

    def test_default_named_form_can_be_imported_and_has_one_initializer(self):
        self.assertEqual(import_mac('Setup Form !!DEFAULT\nExit\nShow !!DEFAULT').form.symbol,'!!DEFAULT')
        f=Form(name='DEFAULT',gadgets=[Gadget(kind='text',name='Value',initial='A')],after_show_code='!!DEFAULT.DEFAULT()')
        code=f.pml()
        self.assertEqual(code.count('Define Method .DEFAULT'),1)
        self.assertNotIn('!this.DEFAULT()',code)
        restored=import_mac(code).form
        self.assertEqual(restored.symbol,'!!DEFAULT')
        self.assertIn("!this.Value.val = 'A'",restored.pml())

    def test_file_suggestion_is_separate_from_form_spelling(self):
        for name in ('../Outside',r'..\Outside','/absolute/form','CON','NUL.txt',r'a:b*?','測定-1'):
            with self.subTest(name=name):
                stem=form_file_stem(name)
                self.assertNotIn('/',stem);self.assertNotIn('\\',stem)
                self.assertNotIn(':',stem);self.assertNotIn('?',stem)
                self.assertNotIn('*',stem)
                self.assertNotIn(stem.split('.')[0].upper(),('CON','NUL'))
        self.assertEqual(form_file_stem('_CDR.HD'),'_CDR.HD')
        self.assertEqual(form_file_stem('測定-1'),'測定-1')

    def test_empty_line_break_and_nul_still_do_not_form_a_declaration(self):
        for value in ('',' ','Bad\nName','Bad\rName','Bad\x00Name'):
            with self.subTest(value=value),self.assertRaises(ValueError):split_form_reference(value)


class OpaqueFormNameGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_import_rename_undo_and_default_filenames_keep_symbol(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);w=Window(settings_path=folder/'settings.json')
            source=folder/'source.mac';source.write_text('Setup Form 測定-フォーム\nExit\nShow 測定-フォーム',encoding='utf-8')
            try:
                with patch('e3d_designer.app.QMessageBox.information'),patch('e3d_designer.app.QMessageBox.warning') as warning:
                    self.assertTrue(w.open_design(source,confirmed=True))
                    self.assertEqual(w.fname.text(),'測定-フォーム')
                    candidate=rename(w.form,'form',None,'../Other:Form')
                    w.checkpoint();w.form=candidate;w.refresh()
                    self.assertEqual(w.form.symbol,'../Other:Form')
                    w.form.source_mac_path=''
                    with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=('','')) as choose:
                        w.save_as()
                        self.assertEqual(Path(choose.call_args.args[2]).parent,w.settings.app_directory)
                    with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=('','')) as choose:
                        w.export()
                        self.assertEqual(Path(choose.call_args.args[2]).parent,w.settings.output_folder)
                    self.assertEqual(w.form.symbol,'../Other:Form')
                    warning.assert_not_called()
                    w.undo();self.assertEqual(w.form.symbol,'測定-フォーム')
            finally:w.dirty=False;w.close();self.app.processEvents()
