import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QRadioButton

from e3d_designer.app import Item, Window
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form, Gadget
from e3d_designer.quick_editor import MiniProperties


class RadioTagwidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def form(self,value=''):
        return Form(gadgets=[Gadget(kind='frame',name='Group',label='Group',width=30,height=8),
            Gadget(kind='rtoggle',name='Choice',label='選択名',parent='Group',x=1,y=1,combo_tagwid=value)])

    def test_export_import_and_json_preserve_tagwid_and_user_text(self):
        for value in ('','0','6.50'):
            with self.subTest(value=value):
                form=self.form(value);form.gadgets[1].on_value='MixedCase'
                code=form.pml()
                if value:self.assertIn(f"Rtoggle .Choice Tagwid {value} '選択名'",code)
                else:self.assertNotIn('Tagwid',code)
                restored=import_mac(code).form
                self.assertEqual(restored.gadgets[1].combo_tagwid,value)
                self.assertEqual(restored.gadgets[1].on_value,'MixedCase')
                self.assertEqual(import_mac(code,partial=True).form.dumps(),restored.dumps())
                self.assertEqual(Form.loads(form.dumps()).gadgets[1].combo_tagwid,value)
                if value:
                    self.assertEqual(import_mac(code.replace('Tagwid','Tagwidth')).form.gadgets[1].combo_tagwid,value)

    def test_negative_nonfinite_and_injected_tagwid_are_rejected(self):
        for value in ('-1','nan','inf','1 Exit','1\nExit','9'*400):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError,'RTOGGLE.*TAGWID'):self.form(value).pml()

    def test_mini_editor_accepts_tagwid_transactionally(self):
        form=self.form();dialog=MiniProperties(None,form,1)
        try:
            dialog.fields['combo_tagwid'].setText('4.5');dialog.accept()
            self.assertEqual(dialog.result_form.gadgets[1].combo_tagwid,'4.5')
            self.assertEqual(form.gadgets[1].combo_tagwid,'')
        finally:dialog.deleteLater()
        dialog=MiniProperties(None,form,1)
        try:
            dialog.fields['combo_tagwid'].setText('-1');dialog.accept()
            self.assertIsNone(dialog.result_form);self.assertTrue(dialog.error.text())
        finally:dialog.reject();dialog.deleteLater()

    def test_inspector_and_shared_native_display_support_radio_tagwid(self):
        with tempfile.TemporaryDirectory() as folder:
            window=Window(settings_path=Path(folder)/'settings.json')
            try:
                widths={}
                for value in ('0','2','8'):
                    window.form=self.form(value);window.selected=1;window.refresh()
                    self.app.processEvents()
                    self.assertTrue(window.fields['combo_tagwid'].isEnabled())
                    self.assertEqual(window.fields['combo_tagwid'].text(),value)
                    before=window.form.dumps();code=window.form.pml()
                    window.runtime_action.setChecked(True);self.app.processEvents()
                    control=window.runtime_dialog.controls['Choice']
                    widths[value]=control.width()
                    item=next(i for i in window.scene.items() if isinstance(i,Item) and i.gadget.name=='Choice')
                    self.assertIsInstance(control,QRadioButton)
                    self.assertEqual(item.boundingRect().size().toSize(),control.size())
                    if value=='0':self.assertEqual(control.text(),'')
                    self.assertEqual(window.form.dumps(),before);self.assertEqual(window.form.pml(),code)
                    window.runtime_action.setChecked(False)
                self.assertEqual(widths['8']-widths['2'],60)
            finally:
                window.dirty=False;window.close();self.app.processEvents()
