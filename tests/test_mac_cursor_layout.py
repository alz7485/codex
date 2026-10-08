import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window
from e3d_designer.mac_import import import_mac,MacImportError
from e3d_designer.model import Form


def source(declarations,header='Setup Form !!Demo Dialog'):
    return header+'\n'+declarations+'\nExit\nShow !!Demo'


class MacCursorLayoutTests(unittest.TestCase):
    def read(self,declarations,header='Setup Form !!Demo Dialog'):
        text=source(declarations,header)
        strict=import_mac(text).form
        partial=import_mac(text,partial=True).form
        self.assertEqual(strict.dumps(),partial.dumps())
        self.assertEqual(Form.loads(strict.dumps()).dumps(),strict.dumps())
        return strict

    def pos(self,form,name):
        return form.geometry(form.named(name))[:2]

    def test_menu_next_line_add_and_implicit_exit_before_menu_and_frame(self):
        form=self.read("Bar\nAdd 'Tools' .Tools\nAdd 'File' .File\n"
            "Menu .Tools\n\n$* comment\nAdd |MiXeD item| |Q CE -- EXIT|\n"
            "Menu .File\nAdd 'Open' 'MiXeD Command'\n"
            "Frame .Group 'Group'\nButton .Run 'Run' Width 10\nExit")
        self.assertEqual([m.name for m in form.menus],['Tools','File'])
        self.assertEqual(form.menus[0].items[0].command,'Q CE -- EXIT')
        self.assertEqual(form.menus[1].items[0].command,'MiXeD Command')
        self.assertEqual(form.named('Run').parent,'Group')
        self.assertEqual(self.pos(form,'Run'),(0,0))
        self.assertEqual(import_mac(form.pml()).form.menus,form.menus)

    def test_menu_implicit_exit_at_show_preserves_program(self):
        text="Setup Form !!Demo Dialog\nMenu .Tools\nAdd 'Run' 'Q CE'\nShow !!Demo\n$P 'after'"
        for partial in (False,True):
            with self.subTest(partial=partial):
                form=import_mac(text,partial=partial).form
                self.assertEqual(form.menus[0].items[0].command,'Q CE')
                self.assertIn("$P 'after'",form.after_show_code)
                self.assertEqual(form.pml().count('Show !!Demo'),1)

    def test_invalid_menu_does_not_swallow_following_path_in_partial_import(self):
        text=source("Menu .Bad\nAdd 'Missing command'\nPath Right\n"
                    "Button .A At X 2 Y 3 'A' Width 4\nButton .B 'B' Width 5")
        with self.assertRaises(MacImportError):import_mac(text)
        form=import_mac(text,partial=True).form
        self.assertEqual(form.menus,[])
        self.assertEqual(self.pos(form,'B'),(7,3))
        self.assertEqual(len(form.partial_import_notes),1)

    def test_omitted_at_starts_at_zero_and_moves_down_one_row(self):
        form=self.read("Path Down\nList .A 'A' Width 20 Height 5\n"
                       "Button .B 'B' Width 5\nButton .C 'C' Width 5")
        self.assertEqual([self.pos(form,n) for n in ('A','B','C')],[(0,0),(0,1),(0,2)])
        self.assertEqual(form.named('A').height,5)
        self.assertTrue(all(g.layout_mode=='AUTO' for g in form.gadgets))
        restored=import_mac(form.pml()).form
        self.assertEqual([self.pos(restored,n) for n in ('A','B','C')],[(0,0),(0,1),(0,2)])

    def test_x_only_y_only_compact_and_reversed_axes_use_current_coordinate(self):
        form=self.read("Button .A At X 4 'A' Width 5\n"
                       "Button .B At Y 3 'B' Width 5\n"
                       "Button .C At X9 'C' Width 5\n"
                       "Button .D At Y7 X2 'D' Width 5\n"
                       "Button .E At Y 10 'E' Width 5")
        self.assertEqual([self.pos(form,n) for n in ('A','B','C','D','E')],
                         [(4,0),(4,3),(9,4),(2,7),(2,10)])
        first_y=self.read("Button .A At Y 3 'A' Width 5")
        self.assertEqual(self.pos(first_y,'A'),(0,3))

    def test_right_left_and_partial_y_use_edges_with_one_unit_gap(self):
        form=self.read("Button .A At X 2 Y 3 'A' Width 4\nPath Right\n"
                       "Button .B 'B' Width 8\nButton .C At Y 5 'C' Width 3\n"
                       "Path Left\nButton .D 'D' Width 5\nPath Down\nButton .E 'E' Width 5")
        self.assertEqual([self.pos(form,n) for n in ('A','B','C','D','E')],
                         [(2,3),(7,3),(16,5),(10,5),(10,6)])
        self.assertEqual(form.named('D').path,'LEFT')
        self.assertEqual(self.pos(form,'C')[0]-(self.pos(form,'D')[0]+5),1)

    def test_up_moves_one_row_and_full_at_resets_current_position(self):
        form=self.read("Button .A At X 3 Y 5 'A' Width 5\nPath Up\n"
                       "Button .B 'B' Width 5\nButton .C At X 10 Y 8 'C' Width 5\nButton .D 'D' Width 5")
        self.assertEqual([self.pos(form,n) for n in ('A','B','C','D')],[(3,5),(3,4),(10,8),(10,7)])

    def test_nested_frames_reset_coordinates_and_keep_last_path(self):
        form=self.read("Path Down\nButton .Before At X 2 Y 3 'Before' Width 5\n"
                       "Frame .Outer 'Outer'\nButton .A 'A' Width 8\nPath Right\n"
                       "Frame .Inner 'Inner'\nButton .Long 'Long' Width 25\nExit\n"
                       "Button .B 'B' Width 4\nExit\nButton .After 'After' Width 5")
        for name,pos in {'Before':(2,3),'Outer':(2,4),'A':(0,0),'Inner':(9,0),
                         'Long':(0,0),'B':(36,0),'After':(44,4)}.items():
            self.assertEqual(self.pos(form,name),pos,name)
        self.assertEqual(form.named('Inner').width,26)
        self.assertEqual(form.named('Outer').width,41)
        self.assertEqual(form.named('Outer').height,6)
        self.assertEqual(form.offset(form.named('Long')),(11,4))

    def test_horizontal_placement_uses_inferred_frame_edge(self):
        form=self.read("Path Right\nFrame .Group 'Group'\nButton .Child 'Child' Width 30\n"
                       "Exit\nButton .After 'After' Width 8")
        self.assertEqual(self.pos(form,'Child'),(0,0))
        self.assertEqual(form.named('Group').width,31)
        self.assertEqual(self.pos(form,'After'),(32,0))

    def test_frame_without_size_and_following_control_fit_explicit_form(self):
        form=self.read("Frame .Group 'Group'\n"
                       "List .Rows At X 0 Y 0 'Rows' Width 20 Height 20\n"
                       "Exit\nButton .After 'After' Width 8",
                       header='Setup Form !!Demo Dialog Size 70 24')
        self.assertEqual((form.named('Group').width,form.named('Group').height),(21,21))
        self.assertEqual(self.pos(form,'After'),(0,22))
        self.assertEqual((form.width,form.height),(70,24))

    def test_tab_pages_fit_nested_frames_and_share_tabset_size(self):
        form=self.read("Frame .Tabs Tabset 'Tabs'\n"
                       "Frame .PageA 'Page A'\nFrame .Group 'Group'\n"
                       "Button .Long At X 20 Y 7 'Long' Width 18\nExit\nExit\n"
                       "Frame .PageB 'Page B'\nButton .Short 'Short' Width 5\nExit\nExit")
        self.assertEqual(form.named('Group').width,39)
        self.assertEqual(form.named('Group').height,9)
        self.assertEqual(form.named('Tabs').width,40)
        self.assertEqual(form.named('Tabs').height,10)
        for page in ('PageA','PageB'):
            self.assertEqual(form.geometry(form.named(page)),(0,0,40,10))
        self.assertEqual(self.pos(form,'Short'),(0,0))

    def test_partial_frame_size_and_form_size_are_inferred_from_children(self):
        form=self.read("Frame .Group At X 5 Y 3 'Group' Width 50\n"
                       "List .Rows At X 2 Y 12 'Rows' Width 20 Height 10\nExit")
        self.assertEqual((form.named('Group').width,form.named('Group').height),(50,23))
        self.assertEqual((form.width,form.height),(56,27))

    def test_explicit_gaps_alignment_and_width_reference_are_respected(self):
        form=self.read("List .A At X 5 Y 2 'A' Width 20 Height 4\n"
                       "Path Down\nVdist 2\nHalign Right\nButton .B 'B' Width 10\n"
                       "Path Right\nHdist 3\nButton .C At Y 10 'C' Width.B")
        self.assertEqual(self.pos(form,'B'),(15,8))
        self.assertEqual(self.pos(form,'C'),(28,10))
        self.assertEqual(form.geometry(form.named('C'))[2],10)

    def test_relative_at_remains_relative_and_supplies_next_cursor(self):
        form=self.read("Button .A At X 2 Y 3 'A' Width 10\n"
                       "Button .B At XMAX.A+1 YMIN.A 'B' Width 5\n"
                       "Button .C At Y 8 'C' Width 5")
        self.assertEqual(form.named('B').layout_mode,'RELATIVE')
        self.assertEqual(self.pos(form,'B'),(13,3))
        self.assertEqual(self.pos(form,'C'),(13,8))

    def test_toolbar_preserves_toolbar_layout(self):
        form=self.read("Frame .Tools Toolbar 'Tools'\nButton .A 'A' Width 10\n"
                       "Button .B 'B' Width 20\nExit",header='Setup Form !!Demo Main')
        self.assertEqual(self.pos(form,'A'),(1,1))
        self.assertEqual(self.pos(form,'B'),(12,1))
        self.assertEqual(form.named('Tools').width,33)

    def test_invalid_at_and_layout_values_are_not_silently_accepted(self):
        for declaration in ("Button .A At X (2+3) 'A'","Button .A At X 2 X 3 'A'",
                            "Button .A At X 2 At Y 3 'A'","Path Sideways","Hdist -1",
                            "Vdist -1","Halign Invalid","Valign Invalid"):
            with self.subTest(declaration=declaration),self.assertRaises(MacImportError):
                import_mac(source(declaration))

    def test_explicit_small_container_is_not_silently_resized(self):
        with self.assertRaisesRegex(ValueError,'親コンテナ'):
            import_mac(source("Frame .Group 'Group' Width 10 Height 5\n"
                              "Button .Wide At X 0 Y 0 'Wide' Width 20\nExit"))


class MacCursorGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_import_save_json_reopen_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);window=Window(settings_path=folder/'settings.json')
            text=source("Bar\nAdd 'Tools' .Tools\nMenu .Tools\nAdd 'Run' 'Q CE'\n"
                        "Frame .Group 'Group'\nButton .A At X 3 'A' Width 25\n"
                        "Path Right\nButton .B At Y 2 'B' Width 5\nExit")
            path=folder/'source.mac';path.write_bytes(text.replace('\n','\r\n').encode('cp932'))
            original=path.read_bytes()
            try:
                for partial in (False,True):
                    with self.subTest(partial=partial),patch('e3d_designer.app.QMessageBox.warning') as warning,patch(
                            'e3d_designer.app.QMessageBox.information'):
                        self.assertTrue(window.open_design(path,confirmed=True,partial=partial))
                        self.assertEqual(window.validation_error,'')
                        self.assertEqual(window.form.geometry(window.form.named('B'))[:2],(29,2))
                        before=window.form.dumps()
                        design=folder/'saved.json'
                        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(design),'')):
                            self.assertTrue(window.save())
                        self.assertTrue(window.open_design(design,confirmed=True))
                        self.assertEqual(window.form.dumps(),before)
                        output=folder/'saved.mac'
                        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):
                            window.export()
                        self.assertEqual(read_text(output),window.form.pml())
                        warning.assert_not_called()
                self.assertEqual(path.read_bytes(),original)
            finally:
                window.dirty=False;window.close();self.app.processEvents()


def read_text(path):
    return path.read_bytes().decode('cp932').replace('\r\n','\n')


if __name__=='__main__':unittest.main()
