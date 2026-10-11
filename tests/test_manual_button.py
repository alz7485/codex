import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QToolBar
from e3d_designer.app import Window


class ManualButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.w=Window(settings_path=root/'settings.json')
        self.w.settings.app_directory=root/'日本語の 配布フォルダー'
        self.folder=self.w.settings.app_directory/'docs'/'manual';self.folder.mkdir(parents=True)
        self.html=self.folder/'index.html';self.html.write_text('<html lang="ja">マニュアル</html>',encoding='utf-8')
        self.w.show();self.app.processEvents()

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_click_and_f1_open_bundled_html_without_changing_design(self):
        w=self.w;before=w.form.dumps();history=list(w.history)
        with patch('e3d_designer.app.QDesktopServices.openUrl',return_value=True) as opener:
            QTest.mouseClick(w.manual_button,Qt.LeftButton);self.app.processEvents()
            w.activateWindow();w.manual_button.setFocus();self.app.processEvents()
            QTest.keyClick(w.manual_button,Qt.Key_F1);self.app.processEvents()
        self.assertEqual(opener.call_count,2)
        for call in opener.call_args_list:
            url=call.args[0];self.assertTrue(url.isLocalFile())
            self.assertEqual(Path(url.toLocalFile()),self.html.resolve())
        self.assertEqual(w.form.dumps(),before);self.assertEqual(w.history,history);self.assertFalse(w.dirty)

    def test_manual_button_stays_at_the_right_edge_when_resized(self):
        w=self.w;toolbar=w.findChild(QToolBar)
        self.assertFalse(toolbar.isMovable());self.assertFalse(w.manual_button.icon().isNull())
        gaps=[]
        for width in (1480,1680,w.minimumSizeHint().width()):
            w.resize(width,880);self.app.processEvents()
            self.assertTrue(w.manual_button.isVisible())
            right=w.manual_button.mapTo(w,QPoint(w.manual_button.width(),0)).x()
            gaps.append(w.width()-right)
            self.assertGreaterEqual(gaps[-1],0);self.assertLessEqual(gaps[-1],16)
        self.assertLessEqual(max(gaps)-min(gaps),1)

    def test_missing_html_uses_pdf_and_missing_both_reports_the_folder(self):
        self.html.unlink();pdf=self.folder/'FormDesigner-Manual.pdf';pdf.write_bytes(b'%PDF-1.4')
        with patch('e3d_designer.app.QDesktopServices.openUrl',return_value=True) as opener:
            QTest.mouseClick(self.w.manual_button,Qt.LeftButton)
        self.assertEqual(Path(opener.call_args.args[0].toLocalFile()),pdf.resolve())
        pdf.unlink()
        with patch('e3d_designer.app.QDesktopServices.openUrl') as opener,patch('e3d_designer.app.QMessageBox.warning') as warning:
            QTest.mouseClick(self.w.manual_button,Qt.LeftButton)
        opener.assert_not_called();warning.assert_called_once()
        self.assertIn('docs/manual',warning.call_args.args[2])

    def test_unavailable_browser_reports_the_manual_path(self):
        with patch('e3d_designer.app.QDesktopServices.openUrl',return_value=False) as opener,patch('e3d_designer.app.QMessageBox.warning') as warning:
            QTest.mouseClick(self.w.manual_button,Qt.LeftButton)
        opener.assert_called_once();warning.assert_called_once()
        self.assertIn(str(self.html),warning.call_args.args[2])
