from e3d_designer.formatting import canonical_pml
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from e3d_designer.model import Form,Gadget
from e3d_designer.names import rename_many,reference_locations
from e3d_designer.clipboard import clone_subtree
from e3d_designer.macro_actions import branch_template
from e3d_designer.app import Window


def sample():
    return Form(variables={'buttonFlag':''},gadgets=[Gadget(name=name,label='Button '+name,action_mode='MACRO',macro_path='C:/My Macros/code1.txt',macro_flag='buttonFlag',macro_value=name,y=y) for name,y in (('a',1),('b',3))])


class MacroTests(unittest.TestCase):
    def test_shared_file_distinct_flags_and_round_trip(self):
        form=sample();pml=form.pml(normalize=False)
        self.assertIn("CALL '!this.macro_a()'",pml)
        self.assertIn("!!buttonFlag = 'a'",pml);self.assertIn("!!buttonFlag = 'b'",pml)
        self.assertEqual(pml.count('$M "C:/My Macros/code1.txt"'),2)
        self.assertEqual(pml.count('VAR !!buttonFlag'),1)
        self.assertEqual(Form.loads(form.dumps()).pml(normalize=False),pml)
        template=branch_template(form,'C:/My Macros/code1.txt',normalize=False)
        self.assertIn("IF (!!buttonFlag EQ 'a') THEN",template)
        self.assertIn("ELSEIF (!!buttonFlag EQ 'b') THEN",template)
        self.assertEqual(template.count('ENDIF'),1)

    def test_rename_flags_and_methods_and_cross_project_copy(self):
        form=sample();form.default_body='!this.macro_a()'
        updated=rename_many(form,[('variable','buttonFlag','source'),('gadget',0,'apply')],False)
        self.assertEqual(updated.gadgets[0].macro_flag,'source')
        self.assertIn("!!source = 'a'",updated.pml(normalize=False))
        self.assertEqual(len(reference_locations(form,'variable','buttonFlag')),2)
        updated=rename_many(form,[('gadget',0,'apply')])
        self.assertEqual(updated.default_body,'!this.macro_apply()')
        copied,index=clone_subtree(Form(),form,0)
        self.assertEqual(copied.variables,{'buttonFlag':''})
        self.assertIn('define method .macro_'+copied.gadgets[index].name+'()',copied.pml(normalize=False))
        copied,index=clone_subtree(form,form,0)
        self.assertEqual(len(copied.gadgets),3);self.assertIn("!!buttonFlag = 'a'",copied.pml(normalize=False))

    def test_invalid_path_flag_mode_and_method_collision(self):
        for attribute,value in (('macro_path',''),('macro_path','x\n$P bad'),('macro_path','x"bad'),('macro_path','x$bad'),('macro_flag','missing'),('callback','run'),('button_role','OK'),('kind','text'),('action_mode','BAD')):
            form=sample();setattr(form.gadgets[0],attribute,value)
            with self.subTest(attribute=attribute),self.assertRaises(ValueError):form.validate()
        form=sample();form.gadgets.append(Gadget(name='extra',callback='macro_a'))
        with self.assertRaises(ValueError):form.validate()
        form=sample();form.gadgets[0].macro_flag='';self.assertNotIn("!!buttonFlag = 'a'",form.pml(normalize=False))


class MacroGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.window=Window()
    def tearDown(self):
        self.app.clipboard().clear();self.window.dirty=False;self.window.close();self.app.processEvents()
    def test_simple_inputs_auto_register_variable_generate_and_undo(self):
        w=self.window;w.add('button');w.fields['action_mode'].setCurrentIndex(1)
        self.assertEqual(w.form.variables,{'buttonFlag':''})
        self.assertEqual(w.form.gadgets[0].macro_value,w.form.gadgets[0].name)
        w.fields['macro_path'].setText('C:/code1.txt');w.fields['macro_value'].setText('A');w.update_gadget()
        self.assertIn(canonical_pml("!!buttonFlag = 'A'"),w.code.toPlainText())
        self.assertFalse(w.fields['callback'].isEnabled())
        self.assertEqual(w.fields['action_mode'].currentData(),'MACRO')
        self.assertTrue(w.form.gadgets[0].macro_path)
        w.undo();self.assertEqual(w.form.gadgets[0].macro_path,'')
        w.redo();self.assertEqual(w.form.gadgets[0].macro_path,'C:/code1.txt')
        w.choose_row(0);w.fields['action_mode'].setCurrentIndex(0);self.assertEqual(w.form.gadgets[0].action_mode,'CODE')
        self.assertTrue(w.fields['callback'].isEnabled())
    def test_file_selection_and_template_save(self):
        w=self.window;w.form=sample();w.selected=0;w.refresh()
        with patch('e3d_designer.app.QFileDialog.getOpenFileName',return_value=('C:/shared.txt','')):w.choose_macro()
        self.assertEqual(w.form.gadgets[0].macro_path,'C:/shared.txt')
        w.form.gadgets[1].macro_path='C:/shared.txt';w.refresh()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'code1.mac'
            with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(path),'')):w.save_macro_template()
            self.assertIn("Elseif (!!buttonFlag Eq 'b') Then",path.read_text())
