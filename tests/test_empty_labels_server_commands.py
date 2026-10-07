import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget,Menu,MenuItem,literal,image_path_literal


SERVER_PATH=r'\\Server\Share$\My Macros\Run.mac'
SERVER_COMMAND='$M "'+SERVER_PATH+'"'


class EmptyLabelsServerTests(unittest.TestCase):
    def test_empty_string_and_word_nul_are_valid_and_nul_byte_is_distinct(self):
        self.assertEqual(literal(''),"''")
        self.assertEqual(literal('NUL'),"'NUL'")
        with self.assertRaises(ValueError) as caught:literal('\x00')
        self.assertIn('NUL文字（0x00）',str(caught.exception))
        self.assertIn("空文字列（''）は使用できます",str(caught.exception))
        self.assertNotIn('$',str(caught.exception))
        self.assertNotIn('改行',str(caught.exception))

    def test_error_names_only_actual_forbidden_characters(self):
        for value,expected,absent in (('value$','$（文字列展開）',('NUL','改行')),
                                     ('line\nbreak','改行',('NUL','$')),
                                     ('line\rbreak','改行',('NUL','$'))):
            with self.subTest(value=repr(value)),self.assertRaises(ValueError) as caught:
                literal(value)
            message=str(caught.exception)
            self.assertIn(expected,message)
            for word in absent:self.assertNotIn(word,message)
        self.assertEqual(literal(SERVER_COMMAND,allow_expansion=True),"'"+SERVER_COMMAND+"'")
        self.assertEqual(image_path_literal(SERVER_PATH),"'"+SERVER_PATH+"'")

    def test_empty_labels_round_trip_all_gadgets_form_and_menus(self):
        for kind in ('button','paragraph','text','toggle','option','list','line','frame',
                     'slider','combo','view','commandline','container','textpane','selector'):
            with self.subTest(kind=kind):
                form=Form(title='',gadgets=[Gadget(kind=kind,name='Part',label='')],
                          menus=[Menu(name='Tools',label='',items=[MenuItem('',SERVER_COMMAND)])])
                restored=import_mac(form.pml()).form
                self.assertEqual(restored.title,'')
                self.assertEqual(restored.named('Part').label,'')
                self.assertEqual(restored.menus[0].display_label,'')
                self.assertEqual(restored.menus[0].items[0].label,'')
                self.assertEqual(restored.menus[0].items[0].command,SERVER_COMMAND)
        form=Form(gadgets=[Gadget(kind='frame',name='Group',label='',width=40,height=10),
                           Gadget(kind='rtoggle',name='Choice',label='',parent='Group')])
        self.assertEqual(import_mac(form.pml()).form.named('Choice').label,'')

    def test_server_commands_with_empty_labels_keep_dollars_and_case(self):
        for kind in ('button','toggle','text','option'):
            with self.subTest(kind=kind):
                form=Form(gadgets=[Gadget(kind=kind,name='Run',label='',command=SERVER_COMMAND,option_style='GADGET')])
                text=form.pml();strict=import_mac(text).form;partial=import_mac(text,partial=True).form
                self.assertEqual(strict.named('Run').command,SERVER_COMMAND)
                self.assertEqual(strict.named('Run').label,'')
                self.assertEqual(strict.dumps(),partial.dumps())
                self.assertIn(SERVER_COMMAND,text)
        form=Form(gadgets=[Gadget(kind='option',name='Pick',label='',items=[''],item_commands=[SERVER_COMMAND])])
        self.assertEqual(import_mac(form.pml()).form.named('Pick').item_commands,[SERVER_COMMAND])

    def test_static_macro_on_unc_admin_share_can_be_generated_and_imported(self):
        for path in (SERVER_PATH,SERVER_PATH.replace('\\','/'),r'\\Server\C$\Tools\Run.mac'):
            with self.subTest(path=path):
                form=Form(gadgets=[Gadget(name='Run',label='',action_mode='MACRO',macro_path=path)])
                text=form.pml();restored=import_mac(text).form
                self.assertEqual(restored.named('Run').action_mode,'MACRO')
                self.assertEqual(restored.named('Run').macro_path,path.replace('\\','/'))
                self.assertEqual(Form.loads(form.dumps()).gadgets[0].macro_path,path)
                self.assertIn('$M "'+path.replace('\\','/')+'"',text)
                self.assertEqual(import_mac(text,partial=True).form.dumps(),restored.dumps())

    def test_dynamic_macro_path_keeps_source_callback_instead_of_invalid_static_path(self):
        for body in ('$M "$!Server/Share/Run.mac"',"!!Flag = '"+SERVER_PATH+"'\n$M \"C:/Run.mac\""):
            source=("VAR !!Flag ''\nSetup Form !!Demo Dialog\nButton .Run '' Call '!this.macro_Run()'\nExit\n"
                    "Show !!Demo\nDefine Method .macro_Run()\n"+body+"\nEndmethod")
            for partial in (False,True):
                with self.subTest(body=body,partial=partial):
                    form=import_mac(source,partial=partial).form;g=form.named('Run')
                    self.assertEqual(g.action_mode,'CODE')
                    self.assertEqual(g.callback,'macro_Run')
                    self.assertEqual(g.body,body)
                    self.assertIn(body,form.pml())

    def test_server_path_variables_stay_in_source_with_user_command(self):
        for symbol in ('!!Path','!Path'):
            with self.subTest(symbol=symbol):
                declaration="VAR "+symbol+" '"+SERVER_PATH+"'"
                command='$M $'+symbol
                source=(declaration+"\nSetup Form !!Demo Dialog\nButton .Run '' Call '"+command+"'\n"
                        "Exit\nShow !!Demo")
                form=import_mac(source).form
                self.assertIn(declaration,form.preamble_code)
                self.assertEqual(form.named('Run').command,command)
                self.assertIn(declaration,form.pml())
                self.assertEqual(import_mac(source,partial=True).form.dumps(),form.dumps())

    def test_server_path_initial_value_keeps_entire_default_and_call_order(self):
        body="!this.Input.Val = '"+SERVER_PATH+"'"
        source=("Setup Form !!Demo Dialog\nText .Input '' Width 10 Is String\nExit\nShow !!Demo\n"
                "Define Method .Demo()\n!this.DEFAULT()\nEndmethod\n"
                "Define Method .DEFAULT()\n"+body+"\nEndmethod")
        form=import_mac(source).form
        self.assertEqual(form.default_mode,'SOURCE')
        self.assertEqual(form.named('Input').initial,'')
        code=form.pml()
        self.assertIn(body,code);self.assertIn('!this.DEFAULT()',code)
        self.assertLess(code.index('Define Method .DEFAULT'),code.index('Define Method .Demo'))
        self.assertEqual(import_mac(source,partial=True).form.dumps(),form.dumps())
        self.assertEqual(Form.loads(form.dumps()).pml(),code)

    def test_server_path_in_choices_or_values_keeps_source_constructor(self):
        for property_name in ('Dtext','Rtext'):
            with self.subTest(property_name=property_name):
                body="!values = ARRAY()\n!values[1] = '"+SERVER_PATH+"'\n!this.Pick."+property_name+" = !values"
                source=("Setup Form !!Demo Dialog\nOption .Pick '' Width 10\nExit\nShow !!Demo\n"
                        "Define Method .Demo()\n"+body+"\nEndmethod")
                form=import_mac(source).form
                self.assertEqual(form.constructor_mode,'SOURCE')
                self.assertIn(body,form.pml())
                self.assertEqual(form.named('Pick').items,[])
                self.assertEqual(form.named('Pick').item_values,[])
                self.assertEqual(import_mac(source,partial=True).form.dumps(),form.dumps())

    def test_server_path_in_table_cell_or_textpane_keeps_source_method(self):
        table_body=("!head = ARRAY()\n!head[1] = 'Name'\n!this.Rows.Setheadings(!head)\n"
                    "!rows = ARRAY()\n!rows[1] = ARRAY()\n!rows[1][1] = '"+SERVER_PATH+"'\n"
                    "!this.Rows.Setrows(!rows)")
        table_source=("Setup Form !!Demo Dialog\nList .Rows '' Single Width 30 Height 5\nExit\nShow !!Demo\n"
                      "Define Method .Demo()\n!this.FillRows()\nEndmethod\n"
                      "Define Method .FillRows()\n"+table_body+"\nEndmethod")
        form=import_mac(table_source).form
        self.assertIn(table_body,form.pml())
        self.assertEqual(form.named('Rows').list_mode,'SIMPLE')
        self.assertEqual(import_mac(table_source,partial=True).form.dumps(),form.dumps())
        pane_body="!lines = ARRAY()\n!lines[1] = '"+SERVER_PATH+"'\n!this.Pane.Val = !lines"
        pane_source=("Setup Form !!Demo Dialog\nTextpane .Pane '' Width 30 Height 5\nExit\nShow !!Demo\n"
                     "Define Method .DEFAULT()\n"+pane_body+"\nEndmethod")
        pane=import_mac(pane_source).form
        self.assertEqual(pane.default_mode,'SOURCE')
        self.assertIn(pane_body,pane.pml())
        self.assertEqual(import_mac(pane_source,partial=True).form.dumps(),pane.dumps())

    def test_error_identifies_label_value_variable_menu_or_table_cell(self):
        forms=[
            (Form(gadgets=[Gadget(name='Run',label='$bad')]),'Run: 表示名'),
            (Form(gadgets=[Gadget(kind='text',name='Input',initial='$bad')]),'Input: 初期値'),
            (Form(variables={'Server':'$bad'}),'!!Server: 変数の初期値'),
            (Form(local_variables={'Server':'$bad'}),'!Server: 変数の初期値'),
            (Form(menus=[Menu(name='Tools',label='$bad')]),'Tools: メニューのタイトル表示名'),
            (Form(menus=[Menu(name='Tools',items=[MenuItem('$bad','Q CE')])]),'Tools: メニュー項目の表示名'),
            (Form(gadgets=[Gadget(kind='list',name='Rows',list_mode='TABLE',headings=['Col'],rows=[['$bad']])]),
             'Rows: リスト1行1列'),
            (Form(gadgets=[Gadget(kind='list',name='Rows',items=['A'],item_values=['$bad'])]),'Rows: 選択肢1の実値'),
        ]
        for form,field in forms:
            with self.subTest(field=field),self.assertRaises(ValueError) as caught:form.pml()
            self.assertIn(field,str(caught.exception));self.assertNotIn('NUL',str(caught.exception))


class EmptyLabelsServerGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_gui_import_and_export_empty_label_server_call_and_macro(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);window=Window(settings_path=directory/'settings.json')
            original=Form(gadgets=[Gadget(name='Run',label='',command=SERVER_COMMAND)])
            source=directory/'source.mac';source.write_bytes(original.pml().replace('\n','\r\n').encode('cp932'))
            data=source.read_bytes()
            try:
                with patch('e3d_designer.app.QMessageBox.warning') as warning,patch(
                        'e3d_designer.app.QMessageBox.information'):
                    for partial in (False,True):
                        self.assertTrue(window.open_design(source,confirmed=True,partial=partial))
                        self.assertEqual(window.validation_error,'')
                        g=window.form.named('Run');self.assertEqual(g.label,'')
                        self.assertEqual(g.command,SERVER_COMMAND)
                        output=directory/'output.mac'
                        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):
                            window.export()
                        self.assertIn(SERVER_COMMAND,output.read_bytes().decode('cp932'))
                    g.command='';g.action_mode='MACRO';g.macro_path=SERVER_PATH
                    window.refresh();self.assertEqual(window.validation_error,'')
                    with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):
                        window.export()
                    self.assertIn(SERVER_PATH.replace('\\','/'),output.read_bytes().decode('cp932'))
                    warning.assert_not_called()
                g.label='$bad';window.refresh()
                self.assertIn('Run: 表示名',window.validation_error)
                self.assertNotIn('NUL',window.validation_error)
                self.assertEqual(source.read_bytes(),data)
            finally:
                window.dirty=False;window.close();self.app.processEvents()


if __name__=='__main__':unittest.main()
