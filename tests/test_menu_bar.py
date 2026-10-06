import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.model import Form,Menu,MenuItem,Gadget
from e3d_designer.mac_import import import_mac,MacImportError
from e3d_designer.names import rename
from e3d_designer.app import Window


def source(declarations):
    return f"Setup Form !!Demo Dialog Size 70 22\n{declarations}\nExit\nShow !!Demo"


class MenuBarTests(unittest.TestCase):
    def test_bar_titles_are_separate_from_menu_items_and_names(self):
        form=Form(menus=[Menu('tools',[MenuItem('実行','MiXeD Command')],label='ツール'),
                         Menu('file',[MenuItem('保存','SAVEWORK')],label='ファイル')])
        code=form.pml()
        self.assertIn("  Bar\n    Add 'ツール' .tools\n    Add 'ファイル' .file\n  Menu .tools",code)
        self.assertIn("Add '実行' 'MiXeD Command'",code)
        self.assertEqual(code.count('  Bar\n'),1)
        restored=Form.loads(form.dumps())
        self.assertEqual(restored.pml(),code)
        renamed=rename(restored,'menu',0,'Actions')
        self.assertIn("Add 'ツール' .Actions",renamed.pml())
        self.assertIn('Menu .Actions',renamed.pml())
        self.assertEqual(renamed.menus[0].label,'ツール')

    def test_legacy_json_uses_object_name_as_default_title(self):
        raw=json.loads(Form(menus=[Menu('Tools')]).dumps())
        del raw['form']['menus'][0]['label'];del raw['form']['menus'][0]['on_bar']
        form=Form.loads(json.dumps(raw))
        self.assertEqual(form.menus[0].display_label,'Tools')
        self.assertIn("Bar\n    Add 'Tools' .Tools",form.pml())

    def test_popup_and_unregistered_menu_do_not_appear_on_bar(self):
        form=Form(menus=[Menu('tools',label='ツール'),
                         Menu('hidden',label='未登録',on_bar=False),
                         Menu('context',[MenuItem('選択','Q CE')],popup=True)])
        code=form.pml()
        self.assertIn("Add 'ツール' .tools",code)
        self.assertNotIn("Add '未登録' .hidden",code)
        self.assertNotIn(".context\n",code.split('Menu .tools')[0])
        self.assertIn('Menu .hidden',code)
        self.assertIn('Menu .context POPUP',code)
        self.assertIn("!this.context.Add('CALLBACK', '選択', 'Q CE')",code)
        self.assertNotIn('  Bar\n',Form(menus=[Menu('context',popup=True)]).pml())
        self.assertNotIn('  Bar\n',Form().pml())

    def test_import_bar_forward_references_title_order_and_unregistered_menu(self):
        declarations="""Bar
Add 'ファイル' .File
Add 'MiXeD Tools' .Tools
Menu .tools
Add '実行' 'SaVeWoRk'
Exit
Menu .unused
Add '未登録の項目' 'Q CE'
Exit
Menu .file
Add '開く' 'open'
Exit"""
        form=import_mac(source(declarations)).form
        self.assertEqual([m.name for m in form.menus],['file','tools','unused'])
        self.assertEqual([m.display_label for m in form.menus[:2]],['ファイル','MiXeD Tools'])
        self.assertFalse(form.menus[2].on_bar)
        self.assertEqual(form.menus[1].items[0].command,'SaVeWoRk')
        restored=import_mac(Form.loads(form.dumps()).pml()).form
        self.assertEqual(restored.menus,form.menus)
        renamed=rename(restored,'menu',1,'Actions')
        self.assertIn("Add 'MiXeD Tools' .Actions",renamed.pml())

    def test_invalid_bar_bindings_fail_with_source_row(self):
        cases=[("Bar\nAdd 'Missing' .missing",3),
               ("Bar\nAdd 'A' .tools\nAdd 'B' .TOOLS\nMenu .tools\nExit",4),
               ("Bar\nAdd 'A' 'tools'",3),
               ("Bar\nAdd 'A' .tools\nMenu .tools POPUP\nExit",3),
               ("Bar\nAdd 'A' .tools\nMenu .tools\nExit\nBar\nAdd 'B' .tools",6)]
        for declarations,row in cases:
            with self.subTest(declarations=declarations),self.assertRaises(MacImportError) as error:
                import_mac(source(declarations))
            self.assertEqual(error.exception.line,row)

    def test_legacy_mac_without_bar_is_migrated_explicitly(self):
        result=import_mac(source("Menu .Tools\nAdd 'Run' 'Q CE'\nExit"))
        self.assertIn("Add 'Tools' .Tools",result.form.pml())
        self.assertTrue(any('旧形式' in message for message in result.warnings))

    def test_title_type_and_implicit_bar_name_conflicts_are_rejected(self):
        for menu in (Menu(label=123),Menu(label='bad\nlabel'),Menu(on_bar='yes'),Menu(name=123)):
            with self.subTest(menu=menu),self.assertRaises(ValueError):Form(menus=[menu]).validate()
        for form in (Form(menus=[Menu('bar')]),
                     Form(menus=[Menu('tools')],gadgets=[Gadget(name='BAR')])):
            with self.subTest(form=form),self.assertRaises(ValueError):form.validate()


class MenuBarGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close()
        self.app.processEvents();self.temp.cleanup()

    def test_title_edit_preview_save_rename_and_undo(self):
        w=self.w;w.add_menu();w.show();w.menu_dialog.show();self.app.processEvents()
        w.menu_label.setFocus();w.menu_label.selectAll();QTest.keyClicks(w.menu_label,'My Tools')
        self.assertEqual(w.form.menus[0].label,'My Tools')
        self.assertEqual(w.preview_menu_bar.actions()[0].text(),'My Tools')
        self.assertEqual(w.form.menus[0].name,'menu1')
        w.path=Path(self.temp.name)/'design.json'
        QTest.keyClick(w.menu_label,Qt.Key_S,Qt.ControlModifier);self.app.processEvents()
        self.assertEqual(Form.loads(w.path.read_text()).menus[0].label,'My Tools')
        w.update_menu_name('Actions')
        self.assertIn("Add 'My Tools' .Actions",w.form.pml())
        self.assertEqual(w.preview_menu_bar.actions()[0].text(),'My Tools')
        w.undo();self.assertEqual(w.form.menus[0].name,'menu1')
        w.redo();self.assertEqual(w.form.menus[0].name,'Actions')

    def test_bar_toggle_and_popup_keep_title_but_hide_preview(self):
        w=self.w;w.add_menu();w.update_menu_label('Visible')
        w.menu_on_bar.setChecked(False)
        self.assertEqual(w.preview_menu_bar.actions(),[])
        self.assertNotIn('  Bar\n',w.form.pml())
        w.undo();self.assertEqual(w.preview_menu_bar.actions()[0].text(),'Visible')
        w.menu_popup.setChecked(True)
        self.assertFalse(w.menu_label.isEnabled());self.assertFalse(w.menu_on_bar.isEnabled())
        self.assertFalse(w.menu_on_bar.isChecked())
        self.assertEqual(w.preview_menu_bar.actions(),[])
        w.menu_popup.setChecked(False)
        self.assertEqual(w.preview_menu_bar.actions()[0].text(),'Visible')
