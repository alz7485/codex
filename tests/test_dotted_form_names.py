import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window
from e3d_designer.clipboard import clone_subtree
from e3d_designer.draft_validation import validate_draft
from e3d_designer.mac_import import import_mac, MacImportError
from e3d_designer.method_manager import update_helpers
from e3d_designer.method_output import OmittedMethodReferenceError
from e3d_designer.model import Form, Gadget, Method
from e3d_designer.name_manager import NameManager
from e3d_designer.names import rename
from e3d_designer.quick_editor import FormProperties
from e3d_designer.symbols import split_form_reference, parse_variables


def macro(symbol='_CDR.HD',declarations='',methods=''):
    return f'Kill {symbol}\nSetup Form {symbol}\n{declarations}\nExit\nShow {symbol}\n{methods}'


class DottedFormNameTests(unittest.TestCase):
    def read(self,text):
        form=import_mac(text).form
        self.assertEqual(import_mac(text,partial=True).form.dumps(),form.dumps())
        self.assertEqual(Form.loads(form.dumps()).dumps(),form.dumps())
        validate_draft(form)
        return form

    def test_reported_setup_without_attributes_keeps_complete_name(self):
        f=self.read('setup form _CDR.HD\nexit\nshow _CDR.HD\n')
        self.assertEqual((f.name,f.form_prefix,f.symbol),('_CDR.HD','','_CDR.HD'))
        self.assertIn('Setup Form _CDR.HD Dialog',f.pml())
        self.assertIn('Kill _CDR.HD',f.pml());self.assertIn('Show _CDR.HD',f.pml())
        self.assertNotIn('!!_CDR.HD',f.pml())
        self.assertNotIn('Define Method',f.pml())
        self.assertEqual(import_mac(f.pml()).form.symbol,'_CDR.HD')

    def test_dotted_name_prefixes_and_case_survive_both_directions(self):
        for symbol in ('_CDR.HD','!!CDR.HD','.CDR.HD','!CDR.HD','._CDR.HD',
                       '!!_Cdr.Hd','CDR.HD.More','button.option'):
            with self.subTest(symbol=symbol):
                f=self.read(macro(symbol,"Button .Run At X Y 'Run' Width 5"))
                self.assertEqual(f.symbol,symbol)
                self.assertEqual(import_mac(f.pml()).form.symbol,symbol)

    def test_generated_constructor_and_default_keep_whole_name(self):
        f=Form(name='_CDR.HD',form_prefix='',gadgets=[Gadget(kind='text',name='Input',initial='Mixed Case')])
        code=f.pml()
        self.assertIn('Define Method ._CDR.HD()',code)
        self.assertLess(code.index('Define Method .DEFAULT'),code.index('Define Method ._CDR.HD'))
        restored=self.read(code)
        self.assertEqual(restored.symbol,'_CDR.HD')
        self.assertEqual(restored.named('Input').initial,'Mixed Case')
        self.assertEqual(restored.pml(),code)

    def test_constructor_definition_is_not_truncated_and_helpers_precede_it(self):
        text=macro(methods="Define Method ._CDR.HD()\n!this.Work()\nEndmethod\n"
                           "Define Method .Work()\n$P 'MiXeD'\nEndmethod")
        f=self.read(text)
        self.assertEqual(f.constructor_body,'!this.Work()')
        self.assertEqual([m.name for m in f.extra_methods],['Work'])
        code=f.pml()
        self.assertLess(code.index('Define Method .Work'),code.index('Define Method ._CDR.HD'))
        restored=self.read(code)
        self.assertEqual(restored.constructor_body,f.constructor_body)

    def test_constructor_and_helper_with_same_first_segment_do_not_collide(self):
        f=Form(name='CDR.HD',form_prefix='',constructor_body='!this.CDR()',
               extra_methods=[Method('CDR',body="$P 'helper'")])
        code=f.pml()
        self.assertIn('Define Method .CDR ()',code)
        self.assertIn('Define Method .CDR.HD()',code)
        self.assertLess(code.index('Define Method .CDR ()'),code.index('Define Method .CDR.HD()'))
        restored=self.read(code)
        self.assertEqual([m.name for m in restored.extra_methods],['CDR'])
        self.assertEqual(restored.constructor_body,'!this.CDR()')

    def test_array_assignments_using_complete_form_reference_are_restored(self):
        f=self.read(macro(declarations="Option .Pick At 'Pick' Call '' Width 10\n"
                                     "!Labels = ARRAY()\n!Values = ARRAY()\n"
                                     "!Labels.APPEND('Steel')\n!Values.APPEND('St')\n"
                                     "_CDR.HD.Pick.DTEXT = !Labels\n_CDR.HD.Pick.RTEXT = !Values"))
        self.assertEqual(f.named('Pick').items,['Steel'])
        self.assertEqual(f.named('Pick').item_values,['St'])
        self.assertEqual(self.read(f.pml()).named('Pick').items,['Steel'])

    def test_form_and_gadget_rename_update_exact_references_and_constructor_calls(self):
        f=self.read(macro(declarations="Button .Run 'Run' Width 5"))
        f.constructor_body="$P 'Ready'"
        f.after_show_code=("_CDR.HD.Run.val = 1\n_CDR.HDMore.Run.val = 2\n"
                           "!this._CDR.HD()\n_CDR.HD._CDR.HD()\n"
                           "$P '_CDR.HD.Run.val'\n-- _CDR.HD.Run.val")
        f.named('Run').command='!this._CDR.HD()'
        renamed=rename(rename(f,'gadget',0,'Changed'),'form',None,'._Next.Form')
        self.assertEqual(renamed.symbol,'._Next.Form')
        self.assertIn('._Next.Form.Changed.val = 1',renamed.after_show_code)
        self.assertIn('_CDR.HDMore.Run.val = 2',renamed.after_show_code)
        self.assertIn('!this._Next.Form()',renamed.after_show_code)
        self.assertIn('._Next.Form._Next.Form()',renamed.after_show_code)
        self.assertIn("$P '_CDR.HD.Run.val'",renamed.after_show_code)
        self.assertIn('-- _CDR.HD.Run.val',renamed.after_show_code)
        self.assertEqual(renamed.named('Changed').command,'!this._Next.Form()')
        self.assertIn('Define Method ._Next.Form()',renamed.pml())

    def test_empty_constructor_calls_and_cycles_are_checked_with_complete_name(self):
        f=Form(name='_CDR.HD',form_prefix='',after_show_code='_CDR.HD._CDR.HD()')
        with self.assertRaises(OmittedMethodReferenceError):f.pml()
        f.constructor_body="$P 'Ready'"
        self.assertIn('_CDR.HD._CDR.HD()',f.pml())
        f.constructor_body='!this.Work()';f.extra_methods=[Method('Work',body='!this._CDR.HD()')]
        with self.assertRaisesRegex(ValueError,'循環'):f.pml()

    def test_helper_rename_and_copy_bind_to_complete_form_symbol(self):
        f=Form(name='_CDR.HD',form_prefix='',extra_methods=[Method('Work',body="$P 'Ready'")],
               gadgets=[Gadget(name='Run',command='_CDR.HD.Work()')])
        changed=update_helpers(f,[('Work',Method('Next',body="$P 'Ready'"))])
        self.assertEqual(changed.named('Run').command,'_CDR.HD.Next()')
        target=Form(name='_Target.Form',form_prefix='')
        copied,index=clone_subtree(target,changed,0)
        self.assertIn('_Target.Form.',copied.gadgets[index].command)
        self.assertNotIn('_CDR.HD.',copied.gadgets[index].command)
        self.assertIn('Define Method .Next_copy',copied.pml())

    def test_empty_names_show_mismatch_and_other_identifiers_remain_rejected(self):
        for symbol in ('','  ','Bad\nName','Bad\x00Name'):
            with self.subTest(symbol=symbol),self.assertRaises(ValueError):split_form_reference(symbol)
        with self.assertRaises(MacImportError):import_mac('Setup Form _CDR.HD\nShow _CDR.OTHER')
        with self.assertRaises(ValueError):parse_variables('!CDR.HD=value')
        with self.assertRaises(ValueError):Form(gadgets=[Gadget(name='CDR.HD')]).validate()
        with self.assertRaises(ValueError):Form(extra_methods=[Method('CDR.HD',body="$P 'other'")]).validate()


class DottedFormNameGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json')
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_cp932_import_property_json_and_export_preserve_name(self):
        text=macro(declarations="Text .Value At '距離' Width 6 Is String",
                   methods="Define Method .DEFAULT()\n!this.Value.val='初期値'\nEndmethod\n"
                           "Define Method ._CDR.HD()\n!this.DEFAULT()\nEndmethod")
        path=self.folder/'input.mac';raw=text.replace('\n','\r\n').encode('cp932');path.write_bytes(raw)
        with patch('e3d_designer.app.QMessageBox.information'),patch('e3d_designer.app.QMessageBox.warning') as warning:
            self.assertTrue(self.w.open_design(path,confirmed=True))
            self.assertEqual(self.w.fname.text(),'_CDR.HD')
            self.assertIn('_CDR.HD',self.w.objects.root.text(0))
            editor=FormProperties(self.w,self.w.form)
            self.assertEqual(editor.name.text(),'_CDR.HD');editor.accept()
            self.assertEqual(editor.result_form.symbol,'_CDR.HD');editor.close()
            self.w.path=self.folder/'saved.json';self.assertTrue(self.w.save())
            self.assertTrue(self.w.open_design(self.w.path,confirmed=True))
            output=self.folder/'saved.mac'
            with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):self.w.export()
            restored=self.read_output(output)
            self.assertEqual(restored.symbol,'_CDR.HD');self.assertEqual(restored.named('Value').initial,'初期値')
            warning.assert_not_called()
        self.assertEqual(path.read_bytes(),raw)

    @staticmethod
    def read_output(path):return import_mac(path.read_bytes().decode('cp932')).form

    def test_name_manager_can_rename_to_dotted_name_and_undo(self):
        self.w.form=Form(name='_CDR.HD',form_prefix='',constructor_body="$P 'Ready'",
                         after_show_code='_CDR.HD._CDR.HD()');self.w.refresh()
        dialog=NameManager(self.w)
        try:
            self.assertTrue(dialog.rename_entry('form',None,'_Next.Form'))
            self.assertTrue(dialog.apply_changes())
            self.assertEqual(self.w.form.symbol,'_Next.Form')
            self.assertEqual(self.w.form.after_show_code,'_Next.Form._Next.Form()')
            self.w.undo();self.assertEqual(self.w.form.symbol,'_CDR.HD')
            self.assertEqual(self.w.form.after_show_code,'_CDR.HD._CDR.HD()')
        finally:dialog.close()
