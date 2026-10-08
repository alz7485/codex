import json
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Item, Window
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form, Gadget, uses_auto_width
from e3d_designer.quick_editor import MiniProperties


class AutomaticWidthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_omitted_width_is_preserved_through_mac_and_json(self):
        source="""Setup Form !!Demo Dialog Size 70 22
Button .Short At X 1 Y 1 'Go'
Button .Long At X 1 Y 3 'A longer button name'
Paragraph .Caption At X 1 Y 5 Text '日本語ラベル'
Text .Input At X 1 Y 7 '値' Is String
Combo .Choice '種類' At X 1 Y 9
Exit
Show !!Demo
"""
        for partial in (False,True):
            form=import_mac(source,partial=partial).form
            self.assertTrue(all(uses_auto_width(g) for g in form.gadgets))
            self.assertLess(form.geometry(form.named('Short'))[2],form.geometry(form.named('Long'))[2])
            code=form.pml()
            self.assertNotIn('Width',code)
            restored=import_mac(code).form
            self.assertTrue(all(uses_auto_width(g) for g in restored.gadgets))
            self.assertEqual(Form.loads(form.dumps()).dumps(),form.dumps())

    def test_explicit_hidden_and_reference_widths_remain_explicit(self):
        source="""Setup Form !!Demo Dialog Size 70 22
Button .Wide At X 1 Y 1 'Go' Width 18
Button .Same At X 1 Y 3 'OK' Width.Wide
Text .Invisible At X 1 Y 5 '' Width 0 Is String
Exit
Show !!Demo
"""
        form=import_mac(source).form
        self.assertTrue(all(g.width_explicit for g in form.gadgets))
        self.assertEqual(form.geometry(form.named('Wide'))[2],18)
        self.assertEqual(form.geometry(form.named('Same'))[2],18)
        self.assertEqual(form.geometry(form.named('Invisible'))[2],0)
        self.assertIn('Width 18',form.pml());self.assertIn('Width.Wide',form.pml())
        self.assertIn('Width 0',form.pml())

    def test_legacy_json_and_invalid_width_mode(self):
        data=json.loads(Form(gadgets=[Gadget(name='Go',width=18)]).dumps())
        data['form']['gadgets'][0].pop('width_explicit')
        form=Form.loads(json.dumps(data));self.assertTrue(form.gadgets[0].width_explicit)
        self.assertIn('Width 18',form.pml())
        data['form']['gadgets'][0]['width_explicit']='false'
        with self.assertRaises(ValueError):Form.loads(json.dumps(data))

    def test_path_right_uses_content_width_and_keeps_path_after_reimport(self):
        source="""Setup Form !!Demo Dialog Size 70 22
Button .Start At X 0 Y 0 'Go'
Path Right
Button .Next 'Next'
Exit
Show !!Demo
"""
        form=import_mac(source).form
        first=form.named('Start');second=form.named('Next')
        x,y,width,_=form.geometry(first)
        self.assertLess(width,14);self.assertAlmostEqual(form.geometry(second)[0],x+width+1)
        self.assertEqual(second.layout_mode,'AUTO')
        restored=import_mac(form.pml()).form
        self.assertEqual(restored.named('Next').layout_mode,'AUTO')
        self.assertEqual(restored.geometry(restored.named('Next')),form.geometry(second))

    def test_widthless_children_fit_a_small_inferred_frame(self):
        source="""Setup Form !!Demo Dialog
Frame .Group 'Group'
Button .Start At X 0 Y 0 'Go'
Path Right
Button .Next 'Next'
Exit
Exit
Show !!Demo
"""
        form=import_mac(source).form;form.validate()
        child=form.named('Next');x,_,width,_=form.geometry(child)
        self.assertLess(x+width,14)
        self.assertLess(form.width,35)

    def test_native_content_width_and_font_changes_do_not_insert_width(self):
        with tempfile.TemporaryDirectory() as folder:
            w=Window(settings_path=Path(folder)/'settings.json')
            try:
                w.form=Form(gadgets=[Gadget(name='Short',label='Go',x=1,y=1,width_explicit=False),
                    Gadget(name='Long',label='A longer button name',x=1,y=3,width_explicit=False),
                    Gadget(kind='paragraph',name='Label',label='日本語',x=1,y=5,width_explicit=False),
                    Gadget(kind='text',name='Input',label='値',initial='12.3',x=1,y=7,width_explicit=False),
                    Gadget(kind='option',option_style='GADGET',name='Option',label='種類',items=['短い','少し長い選択肢'],x=1,y=9,width_explicit=False),
                    Gadget(kind='combo',name='Combo',label='Type',items=['A','Longer choice'],x=1,y=11,width_explicit=False)])
                code=w.form.pml();before=w.form.dumps();widths=[]
                for point_size in (10,16):
                    font=QFont(w.appearance.preview_font);font.setPointSize(point_size);w.appearance.preview_font=font
                    w.refresh();w.runtime_action.setChecked(True);self.app.processEvents()
                    for g in w.form.gadgets:
                        item=next(i for i in w.scene.items() if isinstance(i,Item) and i.gadget.name==g.name)
                        self.assertEqual(item.boundingRect().size().toSize(),w.runtime_dialog.controls[g.name].size())
                    short=w.runtime_dialog.controls['Short'];long=w.runtime_dialog.controls['Long']
                    self.assertLess(short.width(),long.width());self.assertLess(short.width(),80)
                    self.assertGreaterEqual(short.width(),short.fontMetrics().horizontalAdvance(short.text()))
                    label=w.runtime_dialog.controls['Label']
                    self.assertEqual(label.width(),label.sizeHint().width())
                    widths.append(short.width());w.runtime_action.setChecked(False)
                self.assertGreater(widths[1],widths[0])
                self.assertEqual(w.form.pml(),code);self.assertEqual(w.form.dumps(),before)
            finally:w.dirty=False;w.close();self.app.processEvents()

    def test_option_width_checkbox_overrides_omitted_width(self):
        g=Gadget(kind='option',name='Choices',items=['A','B'],width_explicit=False)
        form=Form(gadgets=[g]);self.assertNotIn('Width',form.pml())
        g.option_width_explicit=True;g.width=9
        self.assertFalse(uses_auto_width(g));self.assertIn('Width 9',form.pml())

    def test_mini_editor_switches_auto_and_manual_without_touching_source_form(self):
        form=Form(gadgets=[Gadget(name='Run',label='Go',width_explicit=False)])
        dialog=MiniProperties(None,form,0)
        try:
            self.assertTrue(dialog.auto_width.isChecked());self.assertFalse(dialog.fields['width'].isEnabled())
            dialog.fields['label'].setText('Longer title');dialog.accept()
            self.assertNotIn('Width',dialog.result_form.pml());self.assertEqual(form.gadgets[0].label,'Go')
        finally:dialog.deleteLater()
        dialog=MiniProperties(None,form,0)
        try:
            dialog.auto_width.setChecked(False);self.assertTrue(dialog.fields['width'].isEnabled())
            dialog.fields['width'].setValue(8);dialog.accept()
            self.assertIn('Width 8',dialog.result_form.pml());self.assertFalse(form.gadgets[0].width_explicit)
        finally:dialog.deleteLater()

    def test_inspector_mode_label_edit_and_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            w=Window(settings_path=Path(folder)/'settings.json')
            try:
                w.form=Form(gadgets=[Gadget(name='Run',label='Go',width_explicit=False)])
                w.selected=0;w.refresh();self.app.processEvents()
                self.assertTrue(w.auto_width_check.isChecked());self.assertFalse(w.fields['width'].isEnabled())
                w.auto_width_check.setChecked(False);self.app.processEvents()
                self.assertTrue(w.form.gadgets[0].width_explicit);self.assertTrue(w.fields['width'].isEnabled())
                w.undo();self.app.processEvents();self.assertFalse(w.form.gadgets[0].width_explicit)
                w.choose_row(0);self.app.processEvents()
                w.fields['label'].setText('計測');w.update_gadget();self.app.processEvents()
                self.assertNotIn('Width',w.form.pml());self.assertEqual(w.form.gadgets[0].label,'計測')
            finally:w.dirty=False;w.close();self.app.processEvents()

    def test_expanded_variable_editor_preserves_multiline_input(self):
        with tempfile.TemporaryDirectory() as folder:
            w=Window(settings_path=Path(folder)/'settings.json')
            try:
                w.show();self.app.processEvents();self.assertGreaterEqual(w.variables.height(),180)
                w.variables.setFocus();w.variables.setPlainText('project=MixedCase')
                cursor=w.variables.textCursor();cursor.movePosition(QTextCursor.End);w.variables.setTextCursor(cursor)
                QTest.keyClick(w.variables,Qt.Key_Return);QTest.keyClicks(w.variables,'!local=Value')
                self.app.processEvents()
                self.assertEqual(w.form.variables,{'project':'MixedCase'})
                self.assertEqual(w.form.local_variables,{'local':'Value'})
                self.assertEqual(w.variables.toPlainText(),'project=MixedCase\n!local=Value')
            finally:w.dirty=False;w.close();self.app.processEvents()
