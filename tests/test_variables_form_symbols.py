import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac,MacImportError
from e3d_designer.method_manager import update_helpers
from e3d_designer.model import Form,Gadget,Method
from e3d_designer.name_manager import NameManager,BulkRenameDialog
from e3d_designer.names import rename,rename_many,reference_locations
from e3d_designer.quick_editor import FormProperties
from e3d_designer.symbols import parse_variables


SYMBOLS=('!!Demo','!Demo','.Demo','_Demo','!!_Demo','._Demo','Demo','button','.!!Mixed')


def macro(symbol='!!Demo', declarations='', methods='', preamble=''):
    return (f"{preamble}\nKill {symbol}\nSetup Form {symbol} Dialog Size 70 22\n"
            f"{declarations}\nExit\nShow {symbol}\n{methods}")


class VariableAndSymbolTests(unittest.TestCase):
    def test_parser_supports_both_scopes_and_preserves_values(self):
        globals_,locals_=parse_variables("foo=A\n!!bar= B  C \n\n!foo=L\n!_value=x=y\n")
        self.assertEqual(globals_,{'foo':'A','bar':' B  C '})
        self.assertEqual(locals_,{'foo':'L','_value':'x=y'})

    def test_invalid_and_duplicate_variable_names_are_rejected_per_scope(self):
        for text in ('x=A\n!!X=B','!x=A\n!X=B','!this=x','!!!x=A','wrong name=A','x','.x=A'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_variables(text)
        self.assertEqual(parse_variables('x=A\n!x=B'),({'x':'A'},{'x':'B'}))

    def test_local_declarations_export_import_and_json_roundtrip(self):
        form=Form(variables={'shared':' G '},local_variables={'shared':' L ','_Value':"O'Brien"})
        output=form.pml()
        self.assertIn("Var !!shared ' G '\nVar !shared ' L '\nVar !_Value |O'Brien|",output)
        self.assertLess(output.index('Var !shared'),output.index('Setup Form'))
        restored=import_mac(output).form
        self.assertEqual(restored.variables,form.variables)
        self.assertEqual(restored.local_variables,form.local_variables)
        self.assertEqual(Form.loads(restored.dumps()).local_variables,form.local_variables)

    def test_nonliteral_local_initialization_stays_in_original_preamble(self):
        original="VAR !count 3\n!count = !count + 1"
        form=import_mac(macro(preamble=original)).form
        self.assertEqual(form.local_variables,{})
        self.assertIn(original,form.preamble_code)
        self.assertIn(original,form.pml())

    def test_duplicate_imported_local_declarations_are_rejected(self):
        with self.assertRaises(MacImportError):
            import_mac(macro(preamble="VAR !x 'A'\nVAR !X 'B'"))
        form=import_mac(macro(preamble="VAR !!x 'A'\nVAR !x 'B'")).form
        self.assertEqual((form.variables,form.local_variables),({'x':'A'},{'x':'B'}))

    def test_legacy_json_without_local_variables_or_prefix_keeps_default(self):
        import json
        data=json.loads(Form().dumps())
        del data['form']['local_variables'];del data['form']['form_prefix']
        restored=Form.loads(json.dumps(data))
        self.assertEqual(restored.symbol,'!!userform')
        self.assertEqual(restored.local_variables,{})

    def test_each_form_reference_is_preserved_in_strict_partial_and_export(self):
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                text=macro(symbol,"Button .Run 'Run'")
                strict=import_mac(text).form
                self.assertEqual(strict.symbol,symbol)
                self.assertEqual(strict.dumps(),import_mac(text,partial=True).form.dumps())
                output=Form.loads(strict.dumps()).pml()
                self.assertIn(f'Kill {symbol}',output)
                self.assertIn(f'Setup Form {symbol}',output)
                self.assertIn(f'Show {symbol}',output)
                self.assertEqual(import_mac(output).form.symbol,symbol)

    def test_show_without_form_exit_uses_original_reference(self):
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                text=f"Setup Form {symbol} Dialog\nButton .Run 'Run'\nShow {symbol}"
                result=import_mac(text)
                self.assertEqual(result.form.symbol,symbol)
                self.assertTrue(any('省略されたフォームのEXIT' in w for w in result.warnings))
                self.assertIn('Show '+symbol,result.form.pml())

    def test_constructor_name_with_leading_underscore_is_restored(self):
        text=macro('_Demo',"Option .Pick 'Pick'",
                   "Define Method ._Demo()\n"
                   "!choices=ARRAY()\n!choices[1]='A'\n!this.Pick.Dtext=!choices\nEndmethod")
        form=import_mac(text).form
        self.assertEqual(form.name,'_Demo')
        self.assertEqual(form.named('Pick').items,['A'])
        self.assertEqual(form.constructor_mode,'GENERATED')
        self.assertEqual(form.extra_methods,[])
        self.assertIn('Define Method ._Demo()',form.pml())

    def test_source_program_show_order_and_reference_are_preserved(self):
        text="Setup Form .Demo Dialog\nExit\n$P 'first'\nSHOW .Demo"
        form=import_mac(text).form
        self.assertEqual(form.program_mode,'SOURCE')
        self.assertEqual(form.after_show_code,"$P 'first'\nSHOW .Demo")
        self.assertEqual(form.pml().count('SHOW .Demo'),1)
        self.assertNotIn('!!Demo',form.pml())

    def test_mismatched_show_or_malformed_form_reference_is_rejected(self):
        for token in ('!DemoMore','!!Demo',".Other"):
            with self.subTest(token=token),self.assertRaises(MacImportError):
                import_mac(f"Setup Form !Demo Dialog\nShow {token}")
        for token in ("'Demo'",'!!','9Demo','!Demo()'):
            with self.subTest(token=token),self.assertRaises(MacImportError):
                import_mac(f"Setup Form {token} Dialog\nExit")

    def test_form_and_gadget_rename_follow_preserved_symbol_and_boundaries(self):
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                form=import_mac(macro(symbol,"Button .Run 'Run'")).form
                form.default_body=f'{symbol}.Run.val = 1\n{symbol}More.Run.val = 2\n!this.Run.val = 3\n!!external.Run.val = 4'
                renamed=rename(form,'gadget',0,'Changed')
                self.assertIn(f'{symbol}.Changed.val',renamed.default_body)
                self.assertIn(f'{symbol}More.Run.val',renamed.default_body)
                self.assertIn('!!external.Run.val',renamed.default_body)
                renamed=rename(renamed,'form',None,'Next')
                expected=form.form_prefix+'Next'
                self.assertEqual(renamed.symbol,expected)
                self.assertIn(f'{expected}.Changed.val',renamed.default_body)
                self.assertNotIn(f'{symbol}.Changed.val',renamed.default_body)

    def test_explicit_form_prefix_change_updates_references(self):
        form=Form(default_body='!!userform.Run.val = 1',gadgets=[Gadget(name='Run')])
        renamed=rename(form,'form',None,'.Other')
        self.assertEqual(renamed.symbol,'.Other')
        self.assertEqual(renamed.default_body,'.Other.Run.val = 1')

    def test_local_rename_updates_macro_scope_without_touching_method_locals(self):
        form=Form(variables={'value':'G'},local_variables={'value':'L','other':'O'},
                  preamble_code='!value = !!value\n!valueMore = !value',
                  after_show_code='$P !value',default_body='!value = 3',
                  extra_methods=[Method('Work','(!value Is String)','Return !value')],
                  gadgets=[Gadget(command='USE !value')])
        self.assertEqual(len(reference_locations(form,'local_variable','value')),2)
        renamed=rename(form,'local_variable','value','!next')
        self.assertEqual(renamed.local_variables,{'next':'L','other':'O'})
        self.assertEqual(renamed.preamble_code,'!next = !!value\n!valueMore = !next')
        self.assertEqual(renamed.after_show_code,'$P !next')
        self.assertEqual(renamed.default_body,'!value = 3')
        self.assertEqual(renamed.extra_methods,form.extra_methods)
        self.assertEqual(renamed.gadgets[0].command,'USE !value')
        self.assertEqual(renamed.variables,form.variables)

    def test_local_swaps_and_same_named_global_rename_are_independent(self):
        form=Form(variables={'one':'G'},local_variables={'one':'A','two':'B'},
                  preamble_code='!one = !two\n!!one = !one')
        renamed=rename_many(form,[('local_variable','one','two'),('local_variable','two','one'),('variable','one','shared')])
        self.assertEqual(renamed.local_variables,{'two':'A','one':'B'})
        self.assertEqual(renamed.preamble_code,'!two = !one\n!!shared = !two')

    def test_local_validation_and_actual_form_symbol_collisions(self):
        for values in ({'this':''},{'x':'A','X':'B'},{'wrong name':''},{'value':3},[]):
            with self.subTest(values=values),self.assertRaises(ValueError):
                Form(local_variables=values).pml()
        Form(name='Demo',form_prefix='.',variables={'Demo':'G'},local_variables={'Demo':'L'}).validate()
        with self.assertRaises(ValueError):Form(name='Demo',form_prefix='!',local_variables={'Demo':'L'}).validate()
        with self.assertRaises(ValueError):Form(name='Demo',variables={'Demo':'G'}).validate()

    def test_custom_form_method_order_helper_rename_and_copy(self):
        for symbol in ('.Demo','!Demo','_Demo'):
            with self.subTest(symbol=symbol):
                form=import_mac(macro(symbol,"Button .Run 'Run'",
                    f"Define Method .First()\n{symbol}.Second()\nEndmethod\n"
                    "Define Method .Second()\n$P 'second'\nEndmethod")).form
                form.named('Run').callback='RunHandler';form.named('Run').body=f'{symbol}.First()'
                output=form.pml()
                self.assertLess(output.index('Define Method .Second'),output.index('Define Method .First'))
                renamed=update_helpers(form,[('First',Method('First',body=f'{symbol}.Second()')),
                                            ('Second',Method('Renamed',body="$P 'second'"))])
                self.assertEqual(renamed.extra_methods[0].body,f'{symbol}.Renamed()')
                copied,index=clone_subtree(Form(name='Target'),renamed,0)
                self.assertIn('!!Target.First_copy',copied.gadgets[index].body)
                self.assertEqual(len(copied.extra_methods),2)
                self.assertIn('!!Target.Renamed_copy',copied.extra_methods[0].body)


class VariableEditingGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json')
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_enter_at_end_and_multiple_blank_lines_remain_with_cursor(self):
        self.w.variables.setPlainText('flag=A')
        self.w.variables.moveCursor(QTextCursor.End)
        for _ in range(3):QTest.keyClick(self.w.variables,Qt.Key_Return)
        self.assertEqual(self.w.variables.toPlainText(),'flag=A\n\n\n')
        self.assertEqual(self.w.variables.textCursor().position(),len('flag=A\n\n\n'))
        self.w.refresh()
        self.assertEqual(self.w.variables.toPlainText(),'flag=A\n\n\n')
        QTest.keyClicks(self.w.variables,'!local=B')
        self.assertEqual(self.w.variables.toPlainText(),'flag=A\n\n\n!local=B')
        self.assertEqual(self.w.form.local_variables,{'local':'B'})
        self.assertFalse(self.w.variable_error)

    def test_newline_in_middle_whitespace_and_explicit_global_prefix_survive(self):
        self.w.variables.setPlainText('  !!flag =A  B\n!local=C')
        cursor=self.w.variables.textCursor();cursor.setPosition(len('  !!flag =A  B'))
        self.w.variables.setTextCursor(cursor);QTest.keyClick(self.w.variables,Qt.Key_Return)
        self.assertEqual(self.w.variables.toPlainText(),'  !!flag =A  B\n\n!local=C')
        self.assertEqual(self.w.variables.textCursor().position(),len('  !!flag =A  B\n'))
        self.assertEqual(self.w.form.variables,{'flag':'A  B'})

    def test_local_edit_undo_redo_json_save_and_export(self):
        self.w.variables.setPlainText('global=A\n!local=B')
        self.assertEqual(self.w.form.local_variables,{'local':'B'})
        self.w.undo();self.assertEqual(self.w.form.local_variables,{})
        self.w.redo();self.assertEqual(self.w.form.local_variables,{'local':'B'})
        design=self.folder/'saved.json'
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(design),'')):
            self.assertTrue(self.w.save())
        restored=Form.loads(design.read_text(encoding='utf-8'))
        self.assertEqual(restored.local_variables,{'local':'B'})
        self.assertIn("Var !local 'B'",restored.pml())

    def test_invalid_partial_line_is_retained_and_recovers_after_completing(self):
        self.w.variables.setPlainText('!local=B\n!unfinished')
        self.assertTrue(self.w.variable_error)
        self.assertEqual(self.w.variables.toPlainText(),'!local=B\n!unfinished')
        self.w.variables.moveCursor(QTextCursor.End);QTest.keyClicks(self.w.variables,'=C')
        self.assertFalse(self.w.variable_error)
        self.assertEqual(self.w.form.local_variables,{'local':'B','unfinished':'C'})

    def test_local_name_manager_add_value_rename_apply_and_undo(self):
        self.w.form=Form(local_variables={'value':'A'},preamble_code='$P !value',
                         default_body='!value = 1');self.w.refresh()
        dialog=NameManager(self.w)
        try:
            dialog.tabs.setCurrentWidget(dialog.local_variables)
            editor=dialog.local_variables.cellWidget(0,1)
            editor.selectAll();QTest.keyClicks(editor,'B')
            self.assertTrue(dialog.rename_entry('local_variable','value','other'))
            self.assertTrue(dialog.apply_changes())
            self.assertEqual(self.w.form.local_variables,{'other':'B'})
            self.assertEqual(self.w.form.preamble_code,'$P !other')
            self.assertEqual(self.w.form.default_body,'!value = 1')
            self.w.undo();self.assertEqual(self.w.form.local_variables,{'value':'A'})
            dialog.add_local_variable();self.assertIn('local1',dialog.draft.local_variables)
            dialog.delete_variable();self.assertNotIn('local1',dialog.draft.local_variables)
        finally:dialog.close()

    def test_local_bulk_rename_and_used_variable_delete_guard(self):
        self.w.form=Form(local_variables={'one':'A','two':'B'},preamble_code='!one = !two')
        dialog=NameManager(self.w)
        try:
            dialog.tabs.setCurrentWidget(dialog.local_variables);dialog.select_visible()
            entries=dialog.selected_entries()
            self.assertEqual([entry[0] for entry in entries],['local_variable']*2)
            bulk=BulkRenameDialog(dialog,entries)
            bulk.prefix.setText('new_');bulk.generate()
            self.assertEqual(bulk.result_form.local_variables,{'new_one':'A','new_two':'B'})
            bulk.close()
            dialog.local_variables.setCurrentCell(0,0);dialog.delete_variable()
            self.assertIn('one',dialog.draft.local_variables)
            self.assertIn('使用中',dialog.status.text())
        finally:dialog.close()

    def test_imported_symbol_in_form_editor_tree_summary_and_save(self):
        for symbol in ('_Demo','.Demo','!Demo'):
            with self.subTest(symbol=symbol):
                path=self.folder/'input.mac';path.write_text(macro(symbol,"Button .Run 'Run'"),encoding='utf-8')
                with patch('e3d_designer.app.QMessageBox.information'):
                    self.assertTrue(self.w.open_design(path,confirmed=True))
                self.assertEqual(self.w.fname.text(),symbol)
                self.assertIn(symbol,self.w.objects.root.text(0))
                self.assertIn(symbol,self.w.output_summary.text())
                editor=FormProperties(self.w,self.w.form)
                self.assertEqual(editor.name.text(),symbol);editor.accept()
                self.assertEqual(editor.result_form.symbol,symbol);editor.close()
                self.assertIn('Setup Form '+symbol,self.w.code.toPlainText())


if __name__=='__main__':unittest.main()
