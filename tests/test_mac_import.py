import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from PySide6.QtGui import QImage
from e3d_designer.model import Form, Gadget
from e3d_designer.mac_import import import_mac, read_mac, decode_mac, MacImportError
from e3d_designer.names import rename
from e3d_designer.quick_editor import MiniProperties, ItemsDialog
from e3d_designer.import_editor import ImportCodeDialog
from e3d_designer.app import Window

ROOT=Path(__file__).resolve().parents[1]


def source(declarations, methods='', before='', after=''):
    return f"{before}\nSetup Form !!ImportForm Dialog Size 70 22\nTitle '取込フォーム'\n{declarations}\nExit\nShow !!ImportForm\n{after}\n{methods}"


class MacImportTests(unittest.TestCase):
    def test_all_form_examples_round_trip_editable_data(self):
        count=0
        for path in sorted((ROOT/'examples').glob('*.mac')):
            if path.name=='macro-code1.mac':continue
            with self.subTest(path=path.name):
                original=Form.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
                result=read_mac(path);restored=result.form
                self.assertEqual(restored.name,original.name)
                self.assertEqual(restored.title,original.title)
                self.assertEqual(restored.variables,original.variables)
                self.assertEqual(sorted((g.name,g.kind,g.parent) for g in restored.gadgets),
                                 sorted((g.name,g.kind,g.parent) for g in original.gadgets))
                for g in restored.gadgets:
                    old=original.named(g.name)
                    for key in ('items','item_values','headings','rows','pane_lines','macro_flag','macro_value','macro_path','callback','body'):
                        self.assertEqual(getattr(g,key),getattr(old,key),(path.name,g.name,key))
                restored.pml()
                self.assertEqual(Form.loads(restored.dumps()).pml(),restored.pml())
                self.assertEqual(restored.constructor_mode,'GENERATED')
                count+=1
        self.assertEqual(count,11)

    def test_manual_modern_option_preserves_case_values_and_command(self):
        code=source("Option .Material At X2 Y1 '材質' Width 18 Call 'HandlePick'",
            """Define Method .ImportForm()
!Labels = ARRAY()
!Labels[1] = 'steel'
!Labels[2] = 'Copper'
!this.Material.Dtext = !Labels
!Values = ARRAY()
!Values[1] = 'st'
!Values[2] = 'Cu'
!this.Material.Rtext = !Values
!this.DEFAULT()
Endmethod
Define Method .DEFAULT()
!this.Material.Val = 2
Endmethod""")
        f=import_mac(code).form;g=f.gadgets[0]
        self.assertEqual(g.option_style,'GADGET')
        self.assertEqual((g.items,g.item_values,g.initial),(['steel','Copper'],['st','Cu'],'2'))
        self.assertEqual(g.command,'HandlePick')
        pml=f.pml();self.assertIn("Option .Material At X 2 Y 1 '材質' Width 18 Call 'HandlePick'",pml)
        self.assertIn('!this.Material.rtext',pml)
        self.assertNotIn('Var List',pml)
        self.assertEqual(import_mac(pml).form.gadgets[0].item_values,g.item_values)

    def test_table_arbitrary_local_names_and_implicit_rows(self):
        f=import_mac(source("List .Table At X 2 Y 1 '表' Single Width 30 Height 6",
            """Define Method .ImportForm()
!this.FillTable()
Endmethod
Define Method .FillTable()
!Names = ARRAY()
!Names[1] = '番号'
!Names[2] = '表示名'
!this.Table.Setheadings(!Names)
!Data[1] = ARRAY()
!Data[1][1] = '001'
!Data[1][2] = 'test'
!this.Table.Setrows(!Data)
Endmethod""")).form
        self.assertEqual(f.gadgets[0].rows,[['001','test']])
        self.assertEqual(f.gadgets[0].headings,['番号','表示名'])
        self.assertEqual(f.gadgets[0].table_method,'FillTable')

    def test_unknown_constructor_is_preserved_without_duplicate_initialization(self):
        body="""!Choices = ARRAY()
!Choices[1] = 'First'
!this.Select.Dtext = !Choices
!this.Helper(7)
!this.DEFAULT()"""
        methods=f"""Define Method .ImportForm()
{body}
Endmethod
Define Method .Helper(!Input Is REAL)
$P process
Endmethod
Define Method .DEFAULT()
!this.Select.Val = 1
Endmethod"""
        result=import_mac(source("List .Select At X 2 Y 1 'Select' Single Width 20 Height 5",methods))
        f=result.form
        self.assertEqual(f.constructor_mode,'SOURCE');self.assertEqual(f.constructor_body,body)
        self.assertTrue(result.warnings)
        pml=f.pml();self.assertIn(body,pml)
        self.assertEqual(pml.count('.Select.Dtext ='),1)
        self.assertLess(pml.index('Define Method .Helper'),pml.index('Define Method .ImportForm'))
        self.assertEqual(Form.loads(f.dumps()).constructor_body,body)
        renamed=rename(f,'gadget',0,'Selected')
        self.assertIn('!this.Selected.Dtext',renamed.constructor_body)

    def test_extra_methods_preamble_and_after_show_preserve_source(self):
        code=source("Button .Run At X 2 Y 1 'Run' Width 10 Call '!this.Apply()'",
            """Define Method .Apply()
!this.Helper()
Endmethod
Define Method .Helper() Is STRING
Return 'MiXeD'
Endmethod""",
            before="VAR !!Flag 'start'\n!!Flag = 'changed'\nVAR !!Later 'second'",
            after="$P 'After Show'")
        f=import_mac(code).form;pml=f.pml()
        self.assertEqual(f.variables,{'Flag':'start'})
        self.assertIn("VAR !!Later 'second'",f.preamble_code)
        self.assertIn("$P 'After Show'",f.after_show_code)
        self.assertIn("Return 'MiXeD'",pml)
        self.assertLess(pml.index("!!Flag = 'changed'"),pml.index("VAR !!Later 'second'"))
        self.assertLess(pml.index('Define Method .Helper'),pml.index('Define Method .Apply'))

    def test_default_comments_are_not_broken_by_extraction(self):
        code=source("Text .Input At X 2 Y 1 '値' Width 15 Is String",
            """Define Method .DEFAULT()
$( comment begins
comment ends $)
!this.Input.Val = 'MiXeD' -- keep note
$P 'Tail'
Endmethod""")
        f=import_mac(code).form;pml=f.pml()
        self.assertEqual(f.default_mode,'SOURCE')
        self.assertEqual(f.gadgets[0].initial,'')
        self.assertEqual(pml.count("!this.Input.Val = 'MiXeD'"),1)
        self.assertIn('$( comment begins\ncomment ends $)',pml)
        self.assertIn('-- keep note',pml);self.assertIn("$P 'Tail'",pml)

    def test_invalid_forms_fail_with_line_without_running_source(self):
        with self.assertRaisesRegex(ValueError,'SETUP FORM'):import_mac("$M 'program.mac'")
        with self.assertRaises(MacImportError) as caught:
            import_mac(source("Mystery .Invalid"))
        self.assertEqual(caught.exception.line,4)
        with self.assertRaisesRegex(MacImportError,'ENDMETHOD'):
            import_mac(source('',"Define Method .Helper()\n$P test"))
        with self.assertRaisesRegex(ValueError,'SETUP FORM'):
            import_mac(source('')+'\nSetup Form !!Other\nExit')
        with self.assertRaisesRegex(ValueError,'未対応'):
            import_mac(source("Text .Invalid At X (2+3) Y 1 'x'"))

    def test_encodings_and_limits(self):
        text=source("Paragraph .Label At X 2 Y 1 Text '日本語' Width 12")
        for encoding in ('cp932','utf-8-sig','utf-16'):
            data=text.replace('\n','\r\n').encode(encoding)
            decoded,name=decode_mac(data)
            self.assertEqual(import_mac(decoded).form.gadgets[0].label,'日本語')
        with self.assertRaises(ValueError):decode_mac(b'a\x00b')
        with self.assertRaises(ValueError):decode_mac(b'a'*(4*1024*1024+1))

    def test_radio_initial_value_maps_to_group_choice(self):
        f=import_mac(source("""Frame .Group 'Group'
Rtoggle .One At X 1 Y 1 'One' States '' 'one'
Rtoggle .Two At X 1 Y 2 'Two' States '' 'two'
Exit""","""Define Method .DEFAULT()
!this.Group.Val = 0
!this.Group.Val = 2
Endmethod""")).form
        self.assertEqual([g.initial for g in f.gadgets[1:]],['FALSE','TRUE'])
        self.assertIn('!this.Group.val = 2',f.pml())

    def test_direct_indexed_dtext_and_rtext(self):
        f=import_mac(source("List .Choices At X 2 Y 1 'Choices' Multiple Width 20 Height 5",
            """Define Method .ImportForm()
!Labels[1] = '表示1'
!Labels[2] = '表示2'
!this.Choices.Dtext = !Labels
!Values[1] = 'real1'
!Values[2] = 'real2'
!this.Choices.Rtext = !Values
Endmethod""")).form
        self.assertEqual(f.constructor_mode,'GENERATED')
        self.assertEqual(f.gadgets[0].items,['表示1','表示2'])
        self.assertEqual(f.gadgets[0].item_values,['real1','real2'])

    def test_unrepresented_declarations_are_rejected_and_inline_comment_kept(self):
        with self.assertRaisesRegex(MacImportError,'MEMBER'):
            import_mac(source('Member .Unmapped Is STRING'))
        with self.assertRaisesRegex(MacImportError,'IMPORT'):
            import_mac(source("Import 'UnknownDll'"))
        f=import_mac(source("Button .Run At X 2 Y 1 'Run' Width 12 -- user note")).form
        self.assertEqual(f.gadgets[0].comment,'user note')
        self.assertIn('-- user note',f.pml())


class MacImportGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json')
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close()
        self.app.processEvents();self.temp.cleanup()
    def write_mac(self,text):
        path=self.folder/'original.mac';path.write_bytes(text.encode('cp932'));return path

    def shared_form(self):
        return import_mac(source("""Button .A At X 1 Y 1 'A' Width 10 Call '!this.Work()'
Button .B At X 1 Y 3 'B' Width 10 Call '!this.Work()'""",
            "Define Method .Work()\n$P 'old'\nEndmethod")).form

    def install_form(self,form,index):
        self.w.form=form;self.w.selected=None;self.w.refresh();self.w.choose_row(index)

    def test_shared_callback_edit_updates_all_users_and_undo(self):
        self.install_form(self.shared_form(),0)
        self.w.body.setPlainText("$P 'new'")
        self.assertEqual([g.body for g in self.w.form.gadgets],["$P 'new'"]*2)
        self.assertEqual(self.w.form.pml().count('Define Method .Work()'),1)
        self.w.undo()
        self.assertEqual([g.body for g in self.w.form.gadgets],["$P 'old'"]*2)
        self.w.redo()
        self.assertIn("$P 'new'",self.w.form.pml())
        self.w.choose_row(1);self.w.body.clear()
        self.assertEqual([g.body for g in self.w.form.gadgets],['',''])
        self.assertNotIn('Define Method .Work()',self.w.form.pml())

    def test_join_existing_callback_uses_its_body_in_both_editors(self):
        for mini in (False,True):
            with self.subTest(mini=mini):
                f=self.shared_form();f.gadgets[1].callback='Other';f.gadgets[1].body="$P 'different'"
                if mini:
                    d=MiniProperties(self.w,f,1);d.fields['action'].setText('work');d.accept()
                    self.assertEqual(d.result(),QDialog.Accepted);f=d.result_form;d.deleteLater()
                else:
                    self.install_form(f,1);self.w.fields['callback'].setText('work')
                    self.w.update_gadget();f=self.w.form
                self.assertEqual(f.gadgets[1].body,"$P 'old'")
                self.assertEqual(f.pml().lower().count('define method .work()'),1)

    def test_default_callback_body_has_one_editable_source(self):
        f=import_mac(source("List .Choices At X 1 Y 1 'Choices' Single Width 20 Height 5 Callback '!this.DEFAULT()'",
                            "Define Method .DEFAULT()\n$P 'original'\nEndmethod")).form
        self.install_form(f,0)
        self.assertEqual(self.w.body.toPlainText(),"$P 'original'")
        self.w.body.setPlainText("$P 'changed'")
        self.assertEqual(self.w.form.default_body,"$P 'changed'")
        self.assertEqual(self.w.form.gadgets[0].body,'')
        self.assertEqual(self.w.form.pml().count("$P 'changed'"),1)
        self.w.default_body.clear()
        self.assertEqual(self.w.body.toPlainText(),'')
        self.assertNotIn("$P 'changed'",self.w.form.pml())

    def test_source_default_initial_fields_and_mode_are_consistent(self):
        f=import_mac(source("Toggle .Check At X 1 Y 1 'Check'",
                            "Define Method .DEFAULT()\n!this.Check.Val = TRUE\n$P 'side effect'\nEndmethod")).form
        self.install_form(f,0)
        self.assertFalse(self.w.initial_choice.isEnabled())
        self.assertIn('取り込みコード',self.w.initial_choice.toolTip())
        d=MiniProperties(self.w,f,0);self.assertFalse(d.fields['initial'].isEnabled());d.deleteLater()
        items=ItemsDialog(self.w,Gadget('list','Rows'),initial_editable=False)
        self.assertFalse(items.initial.isEnabled());items.deleteLater()
        d=ImportCodeDialog(self.w,f)
        self.assertEqual(d.default_mode.currentData(),'SOURCE')
        self.assertFalse(d.auto_default.isEnabled())
        d.editors['default_body'].clear();d.default_mode.setCurrentIndex(d.default_mode.findData('GENERATED'))
        self.assertTrue(d.auto_default.isEnabled())
        d.accept();self.assertEqual(d.result(),QDialog.Accepted)
        self.install_form(d.result_form,0)
        self.assertTrue(self.w.initial_choice.isEnabled());d.deleteLater()

    def test_import_save_json_preserves_source_and_image_lookup(self):
        image=QImage(40,25,QImage.Format_ARGB32);image.fill(0xffcc8800)
        self.assertTrue(image.save(str(self.folder/'sample.png')))
        path=self.write_mac(source("Paragraph .Picture At X 4 Y 3 Pixmap 'sample.png' Width 40 Height 25"))
        original=path.read_bytes()
        with patch('e3d_designer.app.QMessageBox.information'):
            self.assertTrue(self.w.open_design(path,confirmed=True))
        self.assertIsNone(self.w.path);self.assertTrue(self.w.dirty)
        self.assertIn(self.folder,self.w.image_directories())
        g=self.w.form.gadgets[0];self.assertEqual((g.width,g.height),(40,25))
        json_path=path.with_suffix('.json')
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(json_path),'')) as dialog:
            self.assertTrue(self.w.save())
            self.assertEqual(dialog.call_args.args[2],str(json_path))
        self.assertEqual(path.read_bytes(),original);self.assertFalse(self.w.dirty)
        self.assertEqual(Form.loads(json_path.read_text()).source_mac_path,str(path))
        self.w.new();self.assertEqual(self.w.form.source_mac_path,'')

    def test_failed_or_cancelled_import_preserves_design_and_history(self):
        self.w.form=Form(gadgets=[Gadget(name='Existing')]);self.w.path=self.folder/'current.json'
        self.w.selected=0;self.w.checkpoint()
        before=copy.deepcopy(self.w.form);history=copy.deepcopy(self.w.history)
        bad=self.write_mac(source('Mystery .Invalid'))
        with patch('e3d_designer.app.QMessageBox.warning') as warning:
            self.assertFalse(self.w.open_design(bad,confirmed=True));warning.assert_called_once()
        self.assertEqual(self.w.form,before);self.assertEqual(self.w.history,history)
        self.assertEqual(self.w.selected,0);self.assertTrue(self.w.dirty)
        with patch.object(self.w,'confirm_discard',return_value=False):
            self.assertFalse(self.w.open_design(bad))
        self.assertEqual(self.w.path,self.folder/'current.json')

    def test_modern_option_property_edit_retains_values_and_width(self):
        f=import_mac(source("Option .Choice At X 2 Y 1 'Choice' Width 14 Call 'pick'")).form
        f.gadgets[0].items=['Steel'];f.gadgets[0].item_values=['st']
        self.w.form=f;self.w.selected=0;self.w.refresh()
        self.assertTrue(self.w.item_values.isEnabled())
        self.w.fields['label'].setText('Changed')
        self.assertEqual(self.w.form.gadgets[0].item_commands,[])
        self.assertEqual(self.w.form.gadgets[0].item_values,['st'])
        d=MiniProperties(self.w,self.w.form,0)
        self.assertIn('width',d.fields);self.assertIn('action',d.fields)
        d.fields['action'].setText('newCommand');d.fields['width'].setValue(19);d.accept()
        self.assertEqual(d.result_form.gadgets[0].command,'newCommand');d.deleteLater()
        items=ItemsDialog(self.w,d.result_form.gadgets[0])
        self.assertEqual(items.table.horizontalHeaderItem(1).text(),'実値')
        items.reject();items.deleteLater()

    def test_retained_code_editor_is_transactional_and_checks_method_conflicts(self):
        f=Form(gadgets=[Gadget(name='Existing')],constructor_mode='SOURCE',constructor_body='$P original')
        d=ImportCodeDialog(self.w,f);d.editors['constructor_body'].setPlainText('$P changed')
        d.editors['extra_methods'].setPlainText('Define Method .Helper()\n$P body\nEndmethod')
        d.accept();self.assertIsNotNone(d.result_form)
        self.assertEqual(f.constructor_body,'$P original')
        self.assertEqual(d.result_form.extra_methods[0].name,'Helper');d.deleteLater()
        d=ImportCodeDialog(self.w,f);d.editors['extra_methods'].setPlainText('Define Method .DEFAULT()\n$P bad\nEndmethod')
        d.accept();self.assertIsNone(d.result_form);self.assertTrue(d.error.text());d.reject();d.deleteLater()

    def test_adding_parts_avoids_imported_method_names(self):
        self.w.form=import_mac(source('',"""Define Method .button1()
$P reserved object name
Endmethod
Define Method .on_button2()
$P reserved event name
Endmethod""")).form
        self.w.refresh();self.w.add('button')
        g=self.w.form.gadgets[0]
        self.assertEqual(g.name,'button2')
        self.assertEqual(g.callback,'on_button2_2')
        self.w.form.pml()

    def test_source_default_editor_and_empty_definition_setting(self):
        f=Form(constructor_mode='SOURCE',constructor_body='!this.DEFAULT()',keep_default=True)
        d=ImportCodeDialog(self.w,f)
        self.assertFalse(d.auto_default.isEnabled())
        self.assertFalse(hasattr(d,'keep_default'))
        self.assertIn('default_body',d.editors)
        d.editors['default_body'].setPlainText("$P 'edited DEFAULT'")
        d.accept();self.assertIsNotNone(d.result_form)
        self.assertIn("$P 'edited DEFAULT'",d.result_form.pml())
        self.assertEqual(f.default_body,'');d.deleteLater()

    def test_invalid_attribute_import_preserves_current_design(self):
        self.w.form=Form(gadgets=[Gadget(name='Existing')]);self.w.selected=0;self.w.checkpoint()
        original=self.w.form.dumps();history=copy.deepcopy(self.w.history)
        path=self.write_mac(source("Line .Line At X 1 Y 1 '' Horiz Width 20 Height 1 Scroll 3"))
        with patch('e3d_designer.app.QMessageBox.warning') as warning:
            self.assertFalse(self.w.open_design(path,confirmed=True))
        self.assertIn('SCROLL',warning.call_args.args[2])
        self.assertEqual(self.w.form.dumps(),original);self.assertEqual(self.w.history,history)


if __name__=='__main__':unittest.main()
