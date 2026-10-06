import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from e3d_designer.model import Form
from e3d_designer.mac_import import import_mac,MacImportError
from e3d_designer.app import Window


def source(declarations,show='Show !!Demo',suffix=''):
    return (f"Setup Form !!Demo Dialog Size 70 22\n{declarations}\n{show}\n{suffix}\n"
            "Define Method .Demo()\nEndmethod")


class MacShowBoundaryTests(unittest.TestCase):
    def test_show_without_final_form_exit_is_a_boundary(self):
        result=import_mac(source("Button .Run At X 1 Y 1 '実行' Width 10",
                                 show='sHoW !!dEmO',suffix="$P 'after show'"))
        self.assertEqual(result.form.gadgets[0].label,'実行')
        self.assertTrue(any('省略されたフォームのEXIT' in w for w in result.warnings))
        code=result.form.pml()
        self.assertEqual(code.count('Show !!Demo'),1)
        self.assertLess(code.index('Exit'),code.index('Show !!Demo'))
        self.assertIn("$P 'after show'",code)
        self.assertEqual(import_mac(code).form.gadgets[0].name,'Run')
        self.assertEqual(Form.loads(result.form.dumps()).pml(),code)

    def test_menu_exit_is_not_required_to_be_followed_by_form_exit(self):
        declarations="""Bar
Add 'ツール' .Tools
Menu .Tools
Add '実行' 'MiXeD command'
Exit"""
        for ending in ('','\nExit'):
            with self.subTest(ending=ending):
                result=import_mac(source(declarations+ending))
                self.assertEqual(result.form.menus[0].label,'ツール')
                self.assertEqual(result.form.menus[0].items[0].command,'MiXeD command')
                self.assertIn("Add 'ツール' .Tools",result.form.pml())
                self.assertEqual(any('省略されたフォームのEXIT' in w for w in result.warnings),not bool(ending))

    def test_last_frame_exit_then_show_keeps_parent(self):
        declarations="""Frame .Group 'グループ'
Button .Run At X 2 Y 2 '実行'
Exit"""
        result=import_mac(source(declarations))
        self.assertEqual(result.form.named('Run').parent,'Group')
        self.assertEqual(import_mac(result.form.pml()).form.named('Run').parent,'Group')

    def test_show_closes_remaining_nested_tab_frames_with_warning(self):
        declarations="""Frame .Pages Tabset At X 2 Y 2 'Pages' Width 30
Frame .First 'タブ1'
Frame .Inner 'グループ'
Button .Run At X 1 Y 1 '実行'"""
        result=import_mac(source(declarations))
        self.assertEqual(result.form.named('Run').parent,'Inner')
        self.assertEqual(result.form.named('Inner').parent,'First')
        self.assertEqual(result.form.named('First').parent,'Pages')
        self.assertTrue(any('Pages, First, Inner' in w for w in result.warnings))
        restored=import_mac(result.form.pml()).form
        self.assertEqual(restored.named('Run').parent,'Inner')
        self.assertEqual(len(restored.named('Pages').tabs),1)

    def test_view_and_option_block_exit_then_show(self):
        declarations=("View .Display At X 1 Y 1 Area Width 20 Height 10\nExit",
                      "Option _Choice At X 1 Y 1 'Choice' Call '$$_Choice'\n"
                      "Var List _Choice Pairs\n'A' 'Q CE'\nExit")
        for declaration in declarations:
            with self.subTest(declaration=declaration):
                form=import_mac(source(declaration)).form
                self.assertEqual(len(form.gadgets),1)
                self.assertEqual(len(import_mac(form.pml()).form.gadgets),1)

    def test_show_comments_and_method_content_are_preserved(self):
        code=source("Button .Run 'Run'",
                    show="Show !!Demo $( show note\ncontinued $)",
                    suffix="$P 'SHOW !!Demo'\nDefine Method .Work()\nSHOW !!Other\nEndmethod")
        form=import_mac(code).form
        self.assertIn('$( show note\ncontinued $)',form.pml())
        self.assertIn("$P 'SHOW !!Demo'",form.pml())
        self.assertIn('SHOW !!Other',form.extra_methods[0].body)
        self.assertEqual(form.pml().count('Show !!Demo'),1)

    def test_comments_and_strings_do_not_close_the_form(self):
        declarations="""$( SHOW !!Demo
$)
Paragraph .Note At X 1 Y 1 Text 'SHOW !!Demo' Width 20
Button .Run At X 1 Y 3 'Run'
Exit"""
        result=import_mac(source(declarations))
        self.assertEqual(len(result.form.gadgets),2)
        self.assertFalse(any('省略されたフォームのEXIT' in w for w in result.warnings))

    def test_invalid_show_and_unknown_declarations_are_still_rejected(self):
        for show in ('SHOW !!Other','SHOW !!Demo extra',"SHOW '!!Demo'"):
            with self.subTest(show=show),self.assertRaises(MacImportError) as error:
                import_mac(source("Button .Run 'Run'",show=show))
            self.assertEqual(error.exception.line,3)
        with self.assertRaises(MacImportError) as error:
            import_mac(source("Mystery .Unknown 'Unknown'"))
        self.assertEqual(error.exception.line,2)


class MacShowBoundaryGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json')
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close()
        self.app.processEvents();self.temp.cleanup()

    def test_mac_menu_open_save_and_export_with_show_boundary(self):
        path=self.folder/'original.MAC'
        text=source("Bar\nAdd 'ツール' .Tools\nMenu .Tools\nAdd '実行' 'Q CE'\nExit")
        original=text.replace('\n','\r\n').encode('cp932');path.write_bytes(original)
        with patch('e3d_designer.app.QFileDialog.getOpenFileName',return_value=(str(path),'')), \
             patch('e3d_designer.app.QMessageBox.information') as info, \
             patch('e3d_designer.app.QMessageBox.warning') as warning:
            self.w.open_mac()
            warning.assert_not_called();info.assert_called_once()
        self.assertTrue(self.w.dirty);self.assertIsNone(self.w.path)
        self.assertEqual(self.w.preview_menu_bar.actions()[0].text(),'ツール')
        design=self.folder/'saved.json'
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(design),'')):
            self.assertTrue(self.w.save())
        restored=Form.loads(design.read_text(encoding='utf-8'))
        output=self.folder/'exported.mac'
        output.write_bytes(restored.pml().replace('\n','\r\n').encode('cp932'))
        with patch('e3d_designer.app.QMessageBox.information'):
            self.assertTrue(self.w.open_design(output,confirmed=True))
        self.assertEqual(self.w.form.menus[0].label,'ツール')
        self.assertEqual(path.read_bytes(),original)

    def test_invalid_show_does_not_replace_current_design_or_history(self):
        self.w.add('button');before=self.w.form.dumps()
        history=list(self.w.history)
        path=self.folder/'invalid.mac';path.write_text(source('',show='Show !!Other'))
        with patch('e3d_designer.app.QMessageBox.warning') as warning:
            self.assertFalse(self.w.open_design(path,confirmed=True))
            self.assertIn('!!Demo',warning.call_args.args[2])
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,history)
