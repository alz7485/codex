import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from e3d_designer.app import Window, GADGET_MIME
from e3d_designer.model import Form, Gadget


class DesignFileDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json');self.w.show();self.app.processEvents()
        self.form=Form(name='Demo',gadgets=[Gadget(name='Run',label='実行',command='SAVEWORK',button_call='OKCALL')])
        self.mac=self.folder/'日本語 demo.MAC';self.mac.write_bytes(self.form.pml().replace('\n','\r\n').encode('cp932'))
        self.json=self.folder/'設計.json';self.json.write_text(self.form.dumps(),encoding='utf-8')

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def drop(self,target,urls,actions=Qt.CopyAction):
        mime=QMimeData();mime.setUrls(urls)
        enter=QDragEnterEvent(QPoint(10,10),actions,mime,Qt.LeftButton,Qt.NoModifier)
        QApplication.sendEvent(target,enter)
        if not enter.isAccepted():return False
        event=QDropEvent(QPointF(10,10),actions,mime,Qt.LeftButton,Qt.NoModifier)
        QApplication.sendEvent(target,event);self.app.processEvents()
        return event.isAccepted()

    def test_mac_drop_on_canvas_tree_and_text_editor_matches_open(self):
        with patch.object(QMessageBox,'information'),patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):
            self.assertTrue(self.w.open_design(self.mac));expected=self.w.form.dumps()
            for target in (self.w,self.w.view.viewport(),self.w.objects.viewport(),self.w.variables.viewport()):
                with self.subTest(target=type(target).__name__):
                    self.w.new();self.assertTrue(self.drop(target,[QUrl.fromLocalFile(str(self.mac))]))
                    self.assertEqual(self.w.form.dumps(),expected)
                    self.assertEqual(self.w.form.gadgets[0].button_call,'OKCALL')
                    self.assertEqual(self.w.variables.toPlainText(),'')
                    self.assertEqual(self.w.form.source_mac_path,str(self.mac.resolve()))
                    self.assertIsNone(self.w.path);self.assertTrue(self.w.dirty)
                    self.assertEqual(self.w.history,[])
        self.assertEqual(self.mac.read_bytes(),self.form.pml().replace('\n','\r\n').encode('cp932'))

    def test_json_drop_uses_same_saved_design_path(self):
        self.assertTrue(self.drop(self.w.view.viewport(),[QUrl.fromLocalFile(str(self.json))]))
        self.assertEqual(self.w.form.dumps(),self.form.dumps())
        self.assertEqual(self.w.path,self.json);self.assertFalse(self.w.dirty)

    def test_cancel_unsaved_changes_preserves_design_and_draft_text(self):
        self.w.form=Form(title='Keep',gadgets=[Gadget(name='Keep')]);self.w.refresh()
        self.w.variables.setPlainText('incomplete');before=self.w.form.dumps(allow_incomplete=True)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel) as question:
            self.assertTrue(self.drop(self.w.variables.viewport(),[QUrl.fromLocalFile(str(self.mac))]))
        self.assertEqual(question.call_count,1)
        self.assertEqual(self.w.form.dumps(allow_incomplete=True),before)
        self.assertEqual(self.w.variables.toPlainText(),'incomplete');self.assertTrue(self.w.dirty)

    def test_invalid_mac_or_missing_file_preserves_current_design(self):
        bad=self.folder/'invalid.mac';bad.write_bytes(b'Setup broken form')
        before=self.w.form.dumps()
        for path in (bad,self.folder/'missing.mac'):
            with patch.object(QMessageBox,'warning') as warning:
                self.assertTrue(self.drop(self.w.view.viewport(),[QUrl.fromLocalFile(str(path))]))
                self.assertEqual(warning.call_count,1)
            self.assertEqual(self.w.form.dumps(),before);self.assertFalse(self.w.dirty)

    def test_remote_multiple_unsupported_and_move_only_drops_are_ignored(self):
        before=self.w.form.dumps()
        cases=[([QUrl('https://example.com/design.mac')],Qt.CopyAction),
            ([QUrl.fromLocalFile(str(self.mac)),QUrl.fromLocalFile(str(self.json))],Qt.CopyAction),
            ([QUrl.fromLocalFile(str(self.folder/'file.txt'))],Qt.CopyAction),
            ([QUrl.fromLocalFile(str(self.mac))],Qt.MoveAction)]
        for urls,actions in cases:
            with self.subTest(urls=urls):self.assertFalse(self.drop(self.w.variables.viewport(),urls,actions))
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.variables.toPlainText(),'')
        mime=QMimeData();mime.setData(GADGET_MIME,b'[]')
        self.assertIsNone(self.w.dropped_design_path(mime))
