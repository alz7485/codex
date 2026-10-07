import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget
from e3d_designer.quick_editor import MiniProperties,ItemsDialog


def arrays(target='!this.Pick',labels='DTEXT',values='RTEXT'):
    return (f"!{labels} = ARRAY()\n!{values} = ARRAY()\n"
            f"!{labels}.APPEND('表示1')\n!{values}.APPEND('ValueA')\n"
            f"!{labels}.APPEND('表示2')\n!{values}.APPEND('ValueB')\n"
            f"{target}.DTEXT = !{labels}\n{target}.RTEXT = !{values}")


def source(body,symbol='!!Demo',where='constructor',declarations=None):
    declarations=declarations or "OPTION .Pick AT X 2 Y 1 '材質' CALL '$P Selected' WIDTH 18"
    base=f"Setup Form {symbol} Size 70 22 Dialog\n{declarations}\nExit\n"
    name=symbol.lstrip('!.')
    if where=='before_show':return base+body+f"\nShow {symbol}\n"
    if where=='after_show':return base+f"Show {symbol}\n"+body+'\n'
    return base+f"Show {symbol}\nDefine Method .{name}()\n"+body+"\nEndmethod\n"


class OptionAppendImportTests(unittest.TestCase):
    def test_interleaved_arrays_restore_editable_display_and_real_values(self):
        code=source(arrays('!!Demo.Pick'));f=import_mac(code).form;g=f.named('Pick')
        self.assertEqual((g.items,g.item_values),(['表示1','表示2'],['ValueA','ValueB']))
        self.assertEqual((g.option_style,g.command,g.width,g.x,g.y),('GADGET','$P Selected',18,2,1))
        self.assertEqual(f.constructor_mode,'GENERATED')
        self.assertEqual(import_mac(code,partial=True).form.dumps(),f.dumps())
        self.assertEqual(Form.loads(f.dumps()).dumps(),f.dumps())
        generated=f.pml()
        self.assertNotIn('.APPEND(',generated.upper());self.assertIn('!choices[1]',generated)
        restored=import_mac(generated).form.named('Pick')
        self.assertEqual((restored.items,restored.item_values),(g.items,g.item_values))

    def test_arbitrary_array_names_case_spacing_and_form_prefixes(self):
        for symbol in ('!!Demo','!Demo','.Demo','_Demo','Demo','!!_Demo'):
            with self.subTest(symbol=symbol):
                body=arrays(symbol+'.pICK','_Labels2','actualValues')
                body=body.replace('ARRAY()',' object aRRay(   )').replace('.APPEND(','.append (  ')
                body=body.replace('!_Labels2\n','!_LABELS2\n')
                f=import_mac(source(body,symbol)).form
                self.assertEqual(f.named('Pick').items,['表示1','表示2'])
                self.assertEqual(f.named('Pick').item_values,['ValueA','ValueB'])

    def test_quoted_special_characters_empty_strings_and_comments(self):
        body="""-- User array comment
!Captions = ARRAY()
!Actual = ARRAY()
!Captions.APPEND(|First ' name  EXIT, )|)
!Actual.APPEND('MixedCase')
!Captions.APPEND('') -- Empty caption
!Actual.APPEND(|a ' b|)
!this.Pick.DTEXT = !Captions
!this.Pick.RTEXT = !Actual"""
        f=import_mac(source(body)).form
        self.assertEqual(f.named('Pick').items,["First ' name  EXIT, )",''])
        self.assertEqual(f.named('Pick').item_values,['MixedCase',"a ' b"])
        self.assertIn('-- User array comment',f.pml());self.assertIn('-- Empty caption',f.pml())
        self.assertEqual(import_mac(f.pml()).form.named('Pick').items,f.named('Pick').items)

    def test_mixed_indexed_and_appended_values(self):
        body="!Names = ARRAY()\n!Names[1] = 'A'\n!Names.Append('B')\n!this.Pick.DTEXT = !Names"
        f=import_mac(source(body)).form
        self.assertEqual(f.named('Pick').items,['A','B'])

    def test_shared_array_and_reinitialized_names(self):
        declarations="Option .Pick 'A' Width 10\nOption .Other At X 20 Y 1 'B' Width 10"
        body="""!Local = ARRAY()
!Local.Append('First')
!this.Pick.DTEXT = !Local
!this.Pick.RTEXT = !Local
!Local = ARRAY()
!Local.Append('Second')
!this.Other.DTEXT = !Local"""
        f=import_mac(source(body,declarations=declarations)).form
        self.assertEqual((f.named('Pick').items,f.named('Pick').item_values),(['First'],['First']))
        self.assertEqual(f.named('Other').items,['Second'])

    def test_list_and_combo_use_same_literal_array_import(self):
        for declaration in ("List .Pick 'リスト' Single Width 18 Height 4","Combo .Pick 'コンボ' Scroll 5 Width 18"):
            with self.subTest(declaration=declaration):
                f=import_mac(source(arrays(),declarations=declaration)).form
                self.assertEqual((f.named('Pick').items,f.named('Pick').item_values),(['表示1','表示2'],['ValueA','ValueB']))

    def test_standalone_arrays_before_or_after_show(self):
        for where in ('before_show','after_show'):
            with self.subTest(where=where):
                result=import_mac(source(arrays('!!Demo.Pick'),where=where));f=result.form
                self.assertEqual(f.named('Pick').items,['表示1','表示2'])
                self.assertEqual(f.named('Pick').item_values,['ValueA','ValueB'])
                self.assertEqual(f.program_mode,'GENERATED')
                self.assertEqual(f.pml().count('Show !!Demo'),1)
                self.assertTrue(any('コンストラクタへ復元' in warning for warning in result.warnings))
                self.assertEqual(import_mac(f.pml()).form.named('Pick').item_values,['ValueA','ValueB'])

    def test_arrays_directly_after_option_declaration(self):
        code=source('',declarations="Option .Pick At X 2 Y 1 '材質' Call '$P Selected' Width 18\n"+arrays('!!Demo.Pick'))
        f=import_mac(code).form
        self.assertEqual((f.named('Pick').items,f.named('Pick').item_values),(['表示1','表示2'],['ValueA','ValueB']))
        self.assertEqual(f.constructor_mode,'GENERATED')
        self.assertEqual(import_mac(code,partial=True).form.dumps(),f.dumps())
        self.assertEqual(import_mac(f.pml()).form.named('Pick').items,['表示1','表示2'])

    def test_declaration_arrays_and_complex_constructor_keep_initialization(self):
        code=source("$P 'Keep this'",declarations="Option .Pick 'Pick' Width 18\n"+arrays('!!Demo.Pick'))
        f=import_mac(code).form
        self.assertEqual(f.constructor_mode,'SOURCE')
        self.assertIn('!this.Pick.DTEXT = !DTEXT',f.constructor_body)
        self.assertIn("$P 'Keep this'",f.constructor_body)
        self.assertEqual(f.named('Pick').items,['表示1','表示2'])
        self.assertNotIn('!choices[1]',f.pml())
        self.assertEqual(f.pml().count('!DTEXT.APPEND('),2)

    def test_uncertain_values_are_preserved_without_partial_conversion(self):
        variations=(
            arrays().replace("'ValueB'","!runtime"),
            arrays().replace("'ValueB'","'a' & 'b'"),
            arrays().replace("'ValueB'","'$SERVER/file.mac'"),
            arrays().replace("'ValueB'",'12'),
            arrays().replace('!this.Pick.RTEXT','!!Other.Pick.RTEXT'),
            arrays().replace("!RTEXT.APPEND('ValueB')\n",''),
            arrays().replace("!DTEXT = ARRAY()","!this = ARRAY()"),
            arrays().replace('!RTEXT = ARRAY()',''),
        )
        for body in variations:
            with self.subTest(body=body):
                f=import_mac(source(body)).form
                self.assertEqual(f.constructor_mode,'SOURCE');self.assertEqual(f.constructor_body,body)
                self.assertEqual((f.named('Pick').items,f.named('Pick').item_values),([],[]))
                self.assertIn(body,f.pml())

    def test_later_local_references_and_mutation_keep_source(self):
        for ending in ("$P !DTEXT","!DTEXT.Append('Later')","!DTEXT[1] = 'Changed'"):
            body=arrays()+'\n'+ending
            with self.subTest(ending=ending):
                f=import_mac(source(body)).form
                self.assertEqual(f.constructor_mode,'SOURCE');self.assertEqual(f.constructor_body,body)
                self.assertEqual(f.named('Pick').items,[])

    def test_standalone_arrays_with_other_commands_are_not_relocated(self):
        for body in (arrays('!!Demo.Pick')+"\n$P 'after'",arrays('!!Other.Pick')):
            f=import_mac(source(body,where='after_show')).form
            self.assertEqual(f.named('Pick').items,[]);self.assertIn(body,f.after_show_code)
            self.assertIn(body,f.pml())

    def test_selected_initial_value_and_command_callback_survive(self):
        body=arrays()+'\n!this.DEFAULT()'
        code=source(body)+"Define Method .DEFAULT()\n!this.Pick.Val = 2\nEndmethod\n"
        f=import_mac(code).form
        self.assertEqual(f.named('Pick').initial,'2');self.assertTrue(f.auto_default)
        self.assertEqual(import_mac(f.pml()).form.named('Pick').initial,'2')

    def test_new_option_generation_keeps_current_formats(self):
        pair=Form(gadgets=[Gadget(kind='option',name='Pick',items=['A'],item_commands=['$P A'])]).pml()
        self.assertIn('Var List _Pick Pairs',pair);self.assertNotIn('.Append(',pair)
        modern=Form(gadgets=[Gadget(kind='option',option_style='GADGET',name='Pick',items=['A'],item_values=['a'])]).pml()
        self.assertIn('!choices[1]',modern);self.assertIn('!values[1]',modern);self.assertNotIn('.Append(',modern)
        legacy=Form(gadgets=[Gadget(kind='option',name='Pick',items=['A'],item_values=['a'])]).pml()
        restored=import_mac(legacy).form
        self.assertEqual(restored.constructor_mode,'GENERATED')
        self.assertEqual((restored.named('Pick').items,restored.named('Pick').item_values),(['A'],['a']))


class OptionAppendImportGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_cp932_import_table_edit_json_and_mac_export(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);w=Window(settings_path=directory/'settings.json')
            w.show();self.app.processEvents()
            try:
                path=directory/'original.mac';data=source(arrays('!!Demo.Pick')).replace('\n','\r\n').encode('cp932');path.write_bytes(data)
                with patch('e3d_designer.app.QMessageBox.information'),patch('e3d_designer.app.QMessageBox.warning') as warning:
                    self.assertTrue(w.open_design(path,confirmed=True))
                    def edit_items(dialog):
                        self.assertEqual(dialog.table.rowCount(),2);self.assertEqual(dialog.table.columnCount(),2)
                        dialog.table.item(0,0).setText('変更後');dialog.table.item(0,1).setText('KeptCase')
                        dialog.accept();return dialog.result()
                    def edit_gadget(dialog):
                        with patch.object(ItemsDialog,'exec',edit_items):dialog.edit_items()
                        dialog.accept();return dialog.result()
                    with patch.object(MiniProperties,'exec',edit_gadget):w.edit_object_properties('Pick')
                    self.assertEqual(w.form.named('Pick').items,['変更後','表示2'])
                    self.assertEqual(w.form.named('Pick').item_values,['KeptCase','ValueB'])
                    w.path=directory/'design.json';self.assertTrue(w.save())
                    self.assertTrue(w.open_design(w.path,confirmed=True))
                    output=directory/'output.mac'
                    with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):w.export()
                    restored=import_mac(output.read_bytes().decode('cp932')).form
                    self.assertEqual(restored.named('Pick').items,['変更後','表示2'])
                    self.assertEqual(restored.named('Pick').item_values,['KeptCase','ValueB'])
                    warning.assert_not_called()
                self.assertEqual(path.read_bytes(),data)
            finally:
                w.dirty=False;w.close();self.app.processEvents()


if __name__=='__main__':unittest.main()
