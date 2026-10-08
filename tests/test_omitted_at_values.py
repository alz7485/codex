import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window
from e3d_designer.mac_import import import_mac, MacImportError
from e3d_designer.model import Form


def macro(declarations, symbol='.Demo'):
    return f'Kill {symbol}\nSetup Form {symbol} Dialog Size 80 50\n{declarations}\nExit\nShow {symbol}'


class OmittedAtValuesTests(unittest.TestCase):
    def read(self, declarations, symbol='.Demo'):
        text=macro(declarations,symbol)
        result=import_mac(text)
        self.assertEqual(result.form.dumps(),import_mac(text,partial=True).form.dumps())
        form=result.form
        self.assertEqual(form.symbol,symbol)
        self.assertEqual(Form.loads(form.dumps()).dumps(),form.dumps())
        restored=import_mac(form.pml()).form
        self.assertEqual(restored.symbol,symbol)
        for g in form.gadgets:
            self.assertEqual(restored.geometry(restored.named(g.name)),form.geometry(g))
            self.assertEqual(restored.named(g.name).parent,g.parent)
        return form

    def test_bare_at_and_empty_axes_use_path_without_consuming_label(self):
        for at in ('At','At X','At Y','At X Y','At Y X'):
            for path,expected in (('Down',(20,11)),('Up',(20,9)),('Right',(26,10)),('Left',(15,10))):
                with self.subTest(at=at,path=path):
                    f=self.read(f"Button .Base At X 20 Y 10 'Base' Width 5\nPath {path}\n"
                                f"Button .Next {at} |  Mixed Case  | Call |$M //Server/Share$/A.mac| Width 4")
                    g=f.named('Next')
                    self.assertEqual(f.geometry(g)[:2],expected)
                    self.assertEqual(g.layout_mode,'AUTO');self.assertEqual(g.path_axes,'XY')
                    self.assertEqual(g.label,'  Mixed Case  ')
                    self.assertEqual(g.command,'$M //Server/Share$/A.mac')

    def test_one_axis_empty_keeps_the_other_coordinate(self):
        for at,expected,axes in (('At X Y 4',(8,4),'X'),('At Y 4 X',(8,4),'X'),
                                 ('At X 2 Y',(2,6),'Y'),('At Y X2',(2,6),'Y')):
            with self.subTest(at=at):
                f=self.read(f"Button .Base At X 8 Y 5 'Base' Width 5\nButton .Next {at} 'Next' Width 4")
                self.assertEqual(f.geometry(f.named('Next'))[:2],expected)
                self.assertEqual(f.named('Next').path_axes,axes)

    def test_empty_at_before_attributes_or_end_does_not_swallow_them(self):
        for tail in ('At','At X','At Y X',"At Width 4 Call ''",'At X Width 4',"At X Text '' Width 4"):
            with self.subTest(tail=tail):
                f=self.read(f"Text .Base At X 3 Y 2 '' Width 6 Is String\nText .Next {tail}")
                self.assertEqual(f.geometry(f.named('Next'))[:2],(3,3))
                self.assertEqual(f.named('Next').label,'')

    def test_frames_reset_current_point_and_exit_uses_frame_edge(self):
        f=self.read("Frame .Group At X 7 Y 5 'Group' Width 20 Height 8\n"
                    "Button .First At X Y 'First' Width 5\n"
                    "Path Right\nButton .Next At 'Next' Width 5\n"
                    "Path Down\nExit\nButton .After At Y 'After' Width 5")
        self.assertEqual(f.geometry(f.named('First'))[:2],(0,0))
        self.assertEqual(f.geometry(f.named('Next'))[:2],(6,0))
        self.assertEqual(f.geometry(f.named('After'))[:2],(7,14))
        self.assertEqual(f.named('Next').parent,'Group')

    def test_symbol_prefixes_are_preserved_with_omitted_at(self):
        for symbol in ('.Demo','!Demo','!!Demo','_Demo','!!_Demo','._Demo','.!!Demo','...Demo'):
            with self.subTest(symbol=symbol):
                self.read("Button .Run At X Y 'Run' Width 5",symbol)

    def test_duplicates_unknown_attributes_and_expressions_still_fail(self):
        for at in ('At X X 3','At X Y X','At At','At X !unknown','At X (2+3)',
                   'At X nonsense','At X Y 2 Y 3'):
            with self.subTest(at=at),self.assertRaises(MacImportError):
                import_mac(macro(f"Button .Run {at} 'Run' Width 5"))


class OmittedAtGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_cp932_file_open_json_and_export_keep_symbol_and_path(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);w=Window(settings_path=folder/'settings.json')
            path=folder/'source.mac'
            raw=macro("Button .Base At X 3 Y 2 '計測' Width 5\nPath Right\n"
                      "Text .Value At X Y '距離' Width 6 Is Real",'._Demo').replace('\n','\r\n').encode('cp932')
            path.write_bytes(raw)
            try:
                with patch('e3d_designer.app.QMessageBox.information'),patch('e3d_designer.app.QMessageBox.warning') as warning:
                    self.assertTrue(w.open_design(path,confirmed=True))
                    self.assertEqual(w.form.symbol,'._Demo')
                    self.assertEqual(w.form.geometry(w.form.named('Value'))[:2],(9,2))
                    self.assertEqual(w.form.named('Value').layout_mode,'AUTO')
                    self.assertEqual(w.validation_error,'')
                    w.path=folder/'saved.json';self.assertTrue(w.save())
                    self.assertTrue(w.open_design(w.path,confirmed=True))
                    output=folder/'saved.mac'
                    with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):w.export()
                    restored=import_mac(output.read_bytes().decode('cp932')).form
                    self.assertEqual(restored.symbol,'._Demo')
                    self.assertEqual(restored.geometry(restored.named('Value'))[:2],(9,2))
                    warning.assert_not_called()
                self.assertEqual(path.read_bytes(),raw)
            finally:
                w.dirty=False;w.close();self.app.processEvents()
