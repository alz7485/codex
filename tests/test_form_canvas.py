import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window,SX,SY,Item
from e3d_designer.form_item import FormItem
from e3d_designer.quick_editor import FormProperties
from e3d_designer.model import Form,Gadget

class FormCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.form=Form(width=35,height=12,gadgets=[Gadget(name='Run',x=2,y=2,width=8)])
        self.w.selected=None;self.w.refresh();self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def drag(self,handle,delta):
        w=self.w;self.app.processEvents();item=w.form_item
        start=w.view.mapFromScene(item.mapToScene(item.handles()[handle].center()));end=start+delta
        QTest.mousePress(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(w.view.viewport(),end,30);QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end)
        self.app.processEvents()
    def test_form_and_part_share_properties_without_form_tab(self):
        w=self.w;original=w.form.dumps()
        self.assertEqual([w.inspector_tabs.tabText(i) for i in range(w.inspector_tabs.count())],['プロパティ','処理'])
        self.assertEqual(w.selection_stack.currentIndex(),0);self.assertTrue(w.form_item.isSelected())
        w.choose_row(0);self.assertEqual(w.selection_stack.currentIndex(),1);self.assertFalse(w.form_item.isSelected())
        point=w.view.mapFromScene(100,-12)
        QTest.mouseClick(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,point);self.app.processEvents()
        self.assertIsNone(w.selected);self.assertEqual(w.selection_stack.currentIndex(),0)
        self.assertTrue(w.form_item.isSelected());self.assertEqual(w.objects.currentRow(),-1)
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[])
        w.delete();w.duplicate();self.assertEqual(w.form.dumps(),original)
    def test_all_handles_resize_form_only_and_undo(self):
        w=self.w;parts=copy.deepcopy(w.form.gadgets);original=w.form.dumps()
        self.drag('width',QPoint(20,0));self.assertEqual((w.form.width,w.form.height),(37,12))
        self.drag('height',QPoint(0,26));self.assertEqual((w.form.width,w.form.height),(37,13))
        self.drag('both',QPoint(10,26));self.assertEqual((w.form.width,w.form.height),(38,14))
        self.assertEqual(w.form.gadgets,parts);self.assertEqual(len(w.history),3)
        self.assertEqual((w.fw.value(),w.fh.value()),(38,14))
        self.assertIn('Size 38 14 Dialog',w.code.toPlainText())
        w.undo();w.undo();w.undo();self.assertEqual(w.form.dumps(),original)
        w.redo();self.assertEqual(w.form.width,37)
    def test_shrink_constraints_and_unconfigured_macro_do_not_block_growth(self):
        w=self.w;original=w.form.dumps();history=len(w.history)
        self.assertFalse(w.form_item.resize_to(5,3));self.assertEqual(w.form.dumps(),original)
        self.assertEqual(len(w.history),history)
        w.form.gadgets[0].action_mode='MACRO';w.form_item.resize_to(36,13)
        self.assertEqual((w.form.width,w.form.height),(36,13))
    def test_double_click_form_edits_and_renames_references_atomically(self):
        w=self.w;w.form.default_body='!this.Run.val = !!userform.Run.val';w.refresh()
        original=w.form.dumps()
        def edit(dialog):
            dialog.name.setText('MyForm');dialog.title.setText('My Title');dialog.width.setValue(40);dialog.accept();return 1
        point=w.view.mapFromScene(100,-12)
        with patch('e3d_designer.quick_editor.FormProperties.exec',autospec=True,side_effect=edit):
            QTest.mouseDClick(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,point);self.app.processEvents()
        self.assertEqual(w.form.name,'MyForm');self.assertEqual(w.form.width,40)
        self.assertIn('!!MyForm.Run.val',w.form.default_body);self.assertEqual(len(w.history),1)
        w.undo();self.assertEqual(w.form.dumps(),original)
        d=FormProperties(w,w.form);d.width.setValue(1);d.accept();self.assertIsNone(d.result_form);self.assertTrue(d.error.text());d.reject();d.deleteLater()
        self.assertEqual(w.form.dumps(),original)
