import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication,QDialog
from e3d_designer.app import Window
from e3d_designer.import_editor import ImportCodeDialog
from e3d_designer.method_manager import update_helpers
from e3d_designer.model import Form,Method


SOURCE=("Setup Form !!Demo Dialog\nButton .Run 'Run' Call '!this.Empty(1)'\nExit\n"
        "Show !!Demo\nDefine Method .Empty(!value Is Real)\n-- no code\nEndmethod")


class EmptyReferenceGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json')
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_strict_and_partial_gui_import_save_and_repair(self):
        source=self.folder/'source.mac';source.write_bytes(SOURCE.encode('cp932'))
        original=source.read_bytes()
        for partial in (False,True):
            with self.subTest(partial=partial):
                with patch('e3d_designer.app.QMessageBox.warning') as warning,patch(
                        'e3d_designer.app.QMessageBox.information'):
                    self.assertTrue(self.w.open_design(source,confirmed=True,partial=partial))
                warning.assert_not_called()
                self.assertEqual(self.w.form.named('Run').command,'!this.Empty(1)')
                self.assertIn('.Empty',self.w.validation_error)
                self.assertIn('MAC出力には修正が必要',self.w.statusBar().currentMessage())
                design=self.folder/'saved.json'
                with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(design),'')):
                    self.assertTrue(self.w.save())
                self.assertTrue(self.w.open_design(design,confirmed=True))
                self.assertIn('.Empty',self.w.validation_error)
                self.w.form=update_helpers(self.w.form,[('Empty',Method('Empty','(!value Is Real)','$P !value'))])
                self.w.refresh()
                self.assertEqual(self.w.validation_error,'')
                self.assertIn("Call '!this.Empty(1)'",self.w.code.toPlainText())
        self.assertEqual(source.read_bytes(),original)

    def test_import_code_editor_keeps_incomplete_work_editable(self):
        form=Form(extra_methods=[Method('Empty','(!value Is Real)')],after_show_code='!this.Empty(1)')
        dialog=ImportCodeDialog(self.w,form)
        dialog.editors['preamble_code'].setPlainText("-- work in progress")
        dialog.accept()
        self.assertEqual(dialog.result(),QDialog.Accepted)
        candidate=dialog.result_form
        self.assertEqual(candidate.preamble_code,"-- work in progress")
        self.assertEqual(candidate.after_show_code,'!this.Empty(1)')
        self.assertEqual(Form.loads(candidate.dumps()).after_show_code,'!this.Empty(1)')
        with self.assertRaisesRegex(ValueError,'.Empty'):candidate.pml()
        dialog.close()

    def test_helper_manager_can_rename_incomplete_helpers_before_filling_them(self):
        form=Form(extra_methods=[Method('Empty','(!value Is Real)')],after_show_code='!this.Empty(1)')
        candidate=update_helpers(form,[('Empty',Method('Pending','(!value Is Real)'))])
        self.assertEqual(candidate.after_show_code,'!this.Pending(1)')
        self.assertEqual(form.after_show_code,'!this.Empty(1)')
        with self.assertRaisesRegex(ValueError,'.Pending'):candidate.pml()
