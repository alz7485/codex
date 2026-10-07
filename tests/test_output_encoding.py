import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window
from e3d_designer.model import Form,Gadget,Method


class OutputEncodingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.window=Window()
    def tearDown(self):
        self.app.clipboard().clear();self.window.dirty=False;self.window.close();self.app.processEvents()

    def test_pml_fixed_cp932_crlf_without_selector(self):
        self.assertFalse(hasattr(self.window,'encoding'))
        self.window.form=Form(title='設備設定')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'form.mac'
            with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(path),'')):self.window.export()
            data=path.read_bytes();self.assertIn('設備設定',data.decode('cp932'))
            self.assertIn(b'\r\n',data);self.assertNotIn(b'\n',data.replace(b'\r\n',b''))
            self.window.form.title='😀'
            with patch('e3d_designer.app.QMessageBox.warning'),patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(path),'')):
                self.window.export()
            self.assertEqual(path.read_bytes(),data)

    def test_macro_template_cp932_and_encoding_failure_preserves_file(self):
        self.window.form=Form(variables={'flag':''},gadgets=[Gadget(label='実行',action_mode='MACRO',macro_path='C:/code1.txt',macro_flag='flag',macro_value='開始')]);self.window.selected=0;self.window.refresh()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'code1.mac'
            with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(path),'')):self.window.save_macro_template()
            data=path.read_bytes();self.assertIn('開始',data.decode('cp932'));self.assertIn('実行',data.decode('cp932'))
            self.assertIn(b'\r\n',data)
            self.window.form.gadgets[0].label='😀'
            with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(path),'')):self.window.save_macro_template()
            self.assertEqual(path.read_bytes(),data)

    def test_dangling_empty_method_reference_prevents_overwriting_existing_mac(self):
        self.window.form=Form(extra_methods=[Method('Empty','(!value Is Real)')],
                              after_show_code='!this.Empty(1)')
        self.window.refresh()
        self.assertIn('.Empty',self.window.validation_error)
        self.assertIn('出力できません',self.window.code.toPlainText())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'form.mac'
            path.write_bytes(b'previous file\r\n')
            with patch('e3d_designer.app.QMessageBox.warning') as warning,patch(
                    'e3d_designer.app.QFileDialog.getSaveFileName',
                    return_value=(str(path),'')) as picker:
                self.window.export()
            warning.assert_called_once()
            picker.assert_not_called()
            self.assertEqual(path.read_bytes(),b'previous file\r\n')
