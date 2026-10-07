import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window,Item,SY
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form


def source(declarations,size='Size 80 60'):
    return f"Setup Form !!Demo Dialog {size}\n{declarations}\nExit\nShow !!Demo"


class FramePathImportTests(unittest.TestCase):
    def read(self,declarations,size='Size 80 60'):
        code=source(declarations,size);f=import_mac(code).form
        self.assertEqual(import_mac(code,partial=True).form.dumps(),f.dumps())
        self.assertEqual(Form.loads(f.dumps()).dumps(),f.dumps())
        return f
    def pos(self,form,name):return form.geometry(form.named(name))[:2]

    def test_down_after_frame_uses_lower_edge_and_one_row_gap(self):
        f=self.read("Frame .Group At X 7 Y 5 'Group' Width 20 Height 8\n"
                    "Button .Child At X 2 Y 3 'Child' Width 5\nExit\nPath Down\n"
                    "Button .After 'After' Width 5\nButton .Next 'Next' Width 5")
        self.assertEqual(self.pos(f,'After'),(7,14));self.assertEqual(self.pos(f,'Next'),(7,15))
        self.assertEqual(self.pos(f,'Child'),(2,3));self.assertEqual(f.named('Child').parent,'Group')

    def test_down_inside_or_outside_frame_has_identical_result(self):
        for initial_path in ('RIGHT','UP','LEFT','DOWN'):
            forms=[]
            for inside in (False,True):
                declarations=f"Path {initial_path}\nFrame .Group At X 7 Y 5 'Group' Width 20 Height 8\nButton .Child At X 2 Y 3 'Child' Width 5\n"
                if inside:declarations+='Path Down\n'
                declarations+='Exit\n'
                if not inside:declarations+='Path Down\n'
                f=self.read(declarations+"Button .After 'After' Width 5")
                self.assertEqual(self.pos(f,'After'),(7,14))
                self.assertEqual(f.named('After').path,'DOWN');forms.append(f)
            self.assertEqual(self.pos(forms[0],'After'),self.pos(forms[1],'After'))

    def test_path_is_inherited_on_frame_entry(self):
        f=self.read("Path Right\nFrame .Group 'Group' Width 30 Height 8\n"
                    "Button .A 'A' Width 4\nButton .B 'B' Width 5\nExit\nButton .After 'After' Width 5")
        self.assertEqual(self.pos(f,'A'),(0,0));self.assertEqual(self.pos(f,'B'),(5,0))
        self.assertEqual(f.named('B').path,'RIGHT');self.assertEqual(self.pos(f,'After'),(31,0))

    def test_last_direction_survives_multiple_exits(self):
        f=self.read("Path Right\nFrame .Outer At X 4 Y 3 'Outer' Width 40 Height 20\n"
                    "Frame .Inner At X 2 Y 4 'Inner' Width 18 Height 6\n"
                    "Button .Last At X 1 Y 3 'Last' Width 5\nPath Down\nExit\n"
                    "Button .InsideAfter 'Inside after' Width 3\nExit\nButton .After 'After' Width 5")
        self.assertEqual(self.pos(f,'InsideAfter'),(2,11))
        self.assertEqual(self.pos(f,'After'),(4,24))
        self.assertEqual(f.named('InsideAfter').parent,'Outer');self.assertEqual(f.named('After').parent,'')
        self.assertEqual(f.offset(f.named('Last')),(6,7))

    def test_inferred_frame_edge_and_form_height_include_following_object(self):
        f=self.read("Frame .Group 'Group'\nList .Rows At X 0 Y 0 'Rows' Width 20 Height 20\n"
                    "Path Down\nExit\nButton .After 'After' Width 8",size='')
        self.assertEqual(f.named('Group').height,21);self.assertEqual(self.pos(f,'After'),(0,22))
        self.assertEqual(f.height,24)

    def test_explicit_at_and_partial_axes_override_current_coordinate(self):
        f=self.read("Frame .Group At X 7 Y 5 'Group' Width 20 Height 8\nButton .Child 'Child' Width 5\n"
                    "Path Down\nExit\nButton .XOnly At X 30 'X only' Width 5\n"
                    "Button .Full At X 2 Y 3 'Full' Width 5\nButton .Next 'Next' Width 5")
        self.assertEqual(self.pos(f,'XOnly'),(30,14));self.assertEqual(self.pos(f,'Full'),(2,3))
        self.assertEqual(self.pos(f,'Next'),(2,4))
        f=self.read("Frame .Group At X 7 Y 5 'Group' Width 20 Height 8\nButton .Child 'Child' Width 5\n"
                    "Exit\nPath Down\nButton .YOnly At Y 20 'Y only' Width 5")
        self.assertEqual(self.pos(f,'YOnly'),(7,20))

    def test_explicit_spacing_and_alignment_remain_respected(self):
        f=self.read("Vdist 2\nHalign Right\nFrame .Group At X 7 Y 5 'Group' Width 20 Height 8\n"
                    "Button .Child 'Child' Width 5\nPath Down\nExit\nButton .After 'After' Width 5")
        self.assertEqual(self.pos(f,'After'),(22,15))

    def test_insufficient_explicit_form_is_rejected_instead_of_overlapping(self):
        with self.assertRaisesRegex(ValueError,'親コンテナ'):
            import_mac(source("Frame .Group 'Group'\nList .Rows 'Rows' Width 20 Height 20\n"
                              "Exit\nButton .After 'After' Width 8",size='Size 70 22'))

    def test_tabset_exit_uses_tabset_edge_and_last_direction(self):
        f=self.read("Path Right\nFrame .Tabs Tabset At X 3 Y 4 'Tabs' Width 25 Height 9\n"
                    "Frame .Page 'Page'\nButton .Child At X 2 Y 3 'Child' Width 5\n"
                    "Path Down\nExit\nExit\nButton .After 'After' Width 5")
        self.assertEqual(self.pos(f,'After'),(3,14));self.assertEqual(f.named('After').path,'DOWN')
        self.assertEqual(f.named('Child').parent,'Page')


class FramePathImportGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_preview_json_and_export_keep_corrected_positions(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);w=Window(settings_path=folder/'settings.json')
            w.show();self.app.processEvents()
            text=source("Frame .Group 'Group'\nList .Rows 'Rows' Width 20 Height 8\n"
                        "Path Down\nExit\nButton .After 'After' Width 8")
            path=folder/'source.mac';data=text.replace('\n','\r\n').encode('cp932');path.write_bytes(data)
            try:
                with patch('e3d_designer.app.QMessageBox.information'),patch('e3d_designer.app.QMessageBox.warning') as warning:
                    self.assertTrue(w.open_design(path,confirmed=True))
                    self.assertEqual(w.form.named('Group').height,9)
                    after=next(i for i in w.scene.items() if isinstance(i,Item) and i.gadget.name=='After')
                    self.assertAlmostEqual(after.pos().y(),10*SY);self.assertEqual(w.validation_error,'')
                    w.path=folder/'design.json';self.assertTrue(w.save())
                    self.assertTrue(w.open_design(w.path,confirmed=True))
                    self.assertEqual(w.form.geometry(w.form.named('After'))[:2],(0,10))
                    output=folder/'saved.mac'
                    with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):w.export()
                    restored=import_mac(output.read_bytes().decode('cp932')).form
                    self.assertEqual(restored.geometry(restored.named('After'))[:2],(0,10))
                    self.assertEqual(restored.named('Rows').parent,'Group');warning.assert_not_called()
                self.assertEqual(path.read_bytes(),data)
            finally:
                w.dirty=False;w.close();self.app.processEvents()


if __name__=='__main__':unittest.main()
