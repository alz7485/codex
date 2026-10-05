import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
from PySide6.QtWidgets import QApplication,QMessageBox
from e3d_designer.app import Window
from e3d_designer.settings import Settings,application_directory
from e3d_designer.model import Form,Gadget
from e3d_designer.clipboard import clone_subtree


class OutputSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.window=Window(settings_path=self.folder/'settings.json')
    def tearDown(self):
        self.app.clipboard().clear();self.window.dirty=False;self.window.close();self.app.processEvents();self.temp.cleanup()

    def test_macro_folder_persistence_and_file_dialog_start(self):
        w=self.window
        self.assertEqual(w.settings.macro_folder,application_directory())
        original=w.form.dumps();history=len(w.history)
        with patch('e3d_designer.app.QFileDialog.getExistingDirectory',return_value=str(self.folder)):
            w.choose_macro_folder()
        w.settings.save_output_folder(self.folder);w.settings.remember_design(self.folder/'design.json');w.settings.clear_recent()
        self.assertEqual(Settings(self.folder/'settings.json').macro_folder,self.folder)
        with patch('e3d_designer.app.QFileDialog.getOpenFileName',return_value=('','')) as dialog:
            w.choose_macro()
            self.assertEqual(dialog.call_args.args[2],str(self.folder))
        self.assertEqual(w.form.dumps(),original);self.assertEqual(len(w.history),history)
        w.macro_folder.setText(str(self.folder/'missing'));self.assertFalse(w.save_macro_folder())
        self.assertEqual(w.settings.macro_folder,self.folder)
        self.assertEqual(w.macro_folder.text(),str(self.folder))
        with patch('e3d_designer.settings.os.replace',side_effect=OSError('read only')):
            with self.assertRaises(OSError):w.settings.save_macro_folder(application_directory())
        self.assertEqual(w.settings.macro_folder,self.folder)

    def test_application_directory_default_and_executable_location(self):
        self.assertEqual(self.window.output_folder.text(),str(application_directory()))
        self.assertFalse((self.folder/'settings.json').exists())
        with patch('e3d_designer.settings.sys.frozen',True,create=True),patch('e3d_designer.settings.sys.executable',str(self.folder/'Designer.exe')):
            self.assertEqual(application_directory(),self.folder)

    def test_folder_persistence_restart_and_invalid_edit_preserves_json(self):
        w=self.window;w.output_folder.setText(str(self.folder));self.assertTrue(w.save_output_folder())
        data=(self.folder/'settings.json').read_bytes();self.assertEqual(json.loads(data)['output_folder'],str(self.folder))
        self.assertEqual(Settings(self.folder/'settings.json').output_folder,self.folder)
        other=Window(settings_path=self.folder/'settings.json')
        self.assertEqual(other.output_folder.text(),str(self.folder));other.close()
        w.output_folder.setText(str(self.folder/'missing'));self.assertFalse(w.save_output_folder())
        self.assertEqual((self.folder/'settings.json').read_bytes(),data)
        self.assertFalse(w.dirty)

    def test_mac_output_default_folder_extension_and_overwrite_guard(self):
        w=self.window;w.output_folder.setText(str(self.folder));w.save_output_folder()
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(self.folder/'sample'),'')) as dialog:w.export()
        self.assertEqual(Path(dialog.call_args.args[2]),self.folder/'USERFORM.mac')
        self.assertEqual(dialog.call_args.args[3],'マクロ (*.mac)')
        self.assertTrue((self.folder/'sample.mac').exists())
        (self.folder/'other.mac').write_bytes(b'original')
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(self.folder/'other.txt'),'')),patch('e3d_designer.app.QMessageBox.question',return_value=QMessageBox.No):w.export()
        self.assertEqual((self.folder/'other.mac').read_bytes(),b'original')
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=('', '')):w.export()
        self.assertFalse((self.folder/'other.txt').exists())

    def test_malformed_settings_falls_back_with_error(self):
        path=self.folder/'bad.json';path.write_text('not JSON')
        settings=Settings(path);self.assertEqual(settings.output_folder,application_directory());self.assertTrue(settings.error)

    def test_comments_edit_export_copy_and_undo(self):
        w=self.window;w.add('button');w.gadget_comment.setPlainText('用途: ポンプの起動\n-- 注意: test Mixed Case')
        self.assertEqual(w.form.gadgets[0].comment,'用途: ポンプの起動\n-- 注意: test Mixed Case')
        code=w.form.pml()
        self.assertIn('-- 用途: ポンプの起動\n  -- -- 注意: test Mixed Case\n  Button',code)
        self.assertEqual(Form.loads(w.form.dumps()).gadgets[0].comment,w.form.gadgets[0].comment)
        cloned,index=clone_subtree(w.form,w.form,0)
        self.assertEqual(cloned.gadgets[index].comment,w.form.gadgets[0].comment)
        w.undo();self.assertEqual(w.form.gadgets[0].comment,'')
        w.redo();w.choose_row(0);self.assertIn('ポンプ',w.gadget_comment.toPlainText())
        w.output_folder.setText(str(self.folder));w.save_output_folder()
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(self.folder/'comment.mac'),'')):w.export()
        self.assertIn('用途: ポンプの起動',(self.folder/'comment.mac').read_bytes().decode('cp932'))

    def test_nested_comments_are_not_executable_and_nul_rejected(self):
        form=Form(gadgets=[Gadget(kind='frame',name='frame',width=30,height=10,comment='Frame'),Gadget(name='run',parent='frame',comment='first\r\nSHOW !!other')])
        code=form.pml()
        self.assertIn('    -- SHOW !!other\n    Button .RUN',code)
        form.gadgets[1].comment='\x00'
        with self.assertRaises(ValueError):form.validate()
