import json
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window
from e3d_designer.mac_import import import_mac, MacImportError
from e3d_designer.model import Form, Gadget
from e3d_designer.quick_editor import MiniProperties


class ButtonCallSuffixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_literal_command_suffix_and_width_roundtrip(self):
        for suffix in ('OKCALL','CANCELCALL'):
            source=f"""Setup Form !!Demo Dialog Size 70 22
Button .Run At X 1 Y 1 '実行' Call |$M //Server/Share/MixedCase.mac| {suffix.lower()} Width 8
Exit
Show !!Demo
"""
            form=import_mac(source).form;g=form.gadgets[0]
            self.assertEqual(g.button_call,suffix);self.assertEqual(g.button_role,'NORMAL')
            self.assertEqual(g.command,'$M //Server/Share/MixedCase.mac')
            code=form.pml();self.assertIn(f"Call '$M //Server/Share/MixedCase.mac' {suffix.capitalize()} Width 8",code)
            self.assertEqual(import_mac(code).form.gadgets[0].button_call,suffix)
            self.assertEqual(import_mac(source,partial=True).form.dumps(),form.dumps())
            self.assertEqual(Form.loads(form.dumps()).dumps(),form.dumps())

    def test_callback_method_suffix_and_width_omission(self):
        form=Form(gadgets=[Gadget(name='Run',callback='Measure',body="!answer = 'MixedCase'",button_call='OKCALL',width_explicit=False)])
        code=form.pml()
        self.assertIn("Call '!this.Measure()' Okcall",code);self.assertNotIn('Width',code)
        g=import_mac(code).form.gadgets[0]
        self.assertEqual(g.button_call,'OKCALL');self.assertEqual(g.callback,'Measure')
        self.assertIn("'MixedCase'",g.body)

    def test_macro_button_suffix_and_existing_roles_are_separate(self):
        form=Form(gadgets=[Gadget(name='Run',action_mode='MACRO',macro_path='//Server/Share/Run.mac',button_call='CANCELCALL',button_role='APPLY')])
        code=form.pml();self.assertIn("Apply Call '!this.macro_Run()' Cancelcall Width",code)
        g=import_mac(code).form.gadgets[0]
        self.assertEqual((g.button_role,g.button_call,g.action_mode),('APPLY','CANCELCALL','MACRO'))

    def test_suffix_words_inside_command_are_literal_data(self):
        form=Form(gadgets=[Gadget(name='Run',command='PRINT OKCALL CANCELCALL')])
        g=import_mac(form.pml()).form.gadgets[0]
        self.assertEqual(g.command,'PRINT OKCALL CANCELCALL');self.assertEqual(g.button_call,'')

    def test_wrong_kind_duplicate_suffix_and_invalid_json_are_rejected(self):
        for declaration in ("Toggle .Bad 'Bad' OKCALL", "Button .Bad 'Bad' OKCALL CANCELCALL", "Button .Bad 'Bad' OKCALL OKCALL"):
            source=f"Setup Form !!Demo Dialog Size 70 22\n{declaration}\nExit\nShow !!Demo\n"
            with self.subTest(declaration=declaration),self.assertRaises(MacImportError):import_mac(source)
        for g in (Gadget(kind='text',button_call='OKCALL'),Gadget(button_call='INVALID'),Gadget(button_call=None)):
            with self.subTest(g=g),self.assertRaises(ValueError):Form(gadgets=[g]).validate()
        data=json.loads(Form(gadgets=[Gadget(name='Run')]).dumps());data['form']['gadgets'][0].pop('button_call')
        self.assertEqual(Form.loads(json.dumps(data)).gadgets[0].button_call,'')

    def test_inspector_and_mini_editor_keep_command_with_suffix(self):
        with tempfile.TemporaryDirectory() as folder:
            w=Window(settings_path=Path(folder)/'settings.json')
            try:
                w.form=Form(gadgets=[Gadget(name='Run',command='SAVEWORK')]);w.selected=0;w.refresh()
                w.fields['button_call'].setCurrentText('OKCALL');self.app.processEvents()
                self.assertEqual(w.form.gadgets[0].command,'SAVEWORK')
                self.assertIn("Call 'SAVEWORK' Okcall Width",w.form.pml())
                w.undo();self.app.processEvents();self.assertEqual(w.form.gadgets[0].button_call,'')
                dialog=MiniProperties(w,w.form,0)
                try:
                    dialog.fields['button_call'].setCurrentText('CANCELCALL');dialog.accept()
                    self.assertEqual(dialog.result_form.gadgets[0].command,'SAVEWORK')
                    self.assertIn("Call 'SAVEWORK' Cancelcall Width",dialog.result_form.pml())
                finally:dialog.deleteLater()
            finally:w.dirty=False;w.close();self.app.processEvents()
