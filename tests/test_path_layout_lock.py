import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QGraphicsItem,QMenu

from e3d_designer.app import Window,Item
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget


SOURCE="""Setup Form !!Demo Size 80 50 Dialog
Button .Base At X 4 Y 3 'Base' Width 10
Path Down
List .Rows 'Rows' Width 10 Height 5
Button .Partial At X 30 'Partial' Width 5
Exit
Show !!Demo"""


class PathLayoutLockTests(unittest.TestCase):
    def test_import_keeps_path_and_partial_axes_through_json_and_export(self):
        f=import_mac(SOURCE).form
        self.assertEqual(f.named('Base').layout_mode,'ABSOLUTE')
        for name,axes,pos in (('Rows','XY',(4,4)),('Partial','Y',(30,5))):
            g=f.named(name);self.assertEqual((g.layout_mode,g.path_axes),('AUTO',axes))
            self.assertTrue(g.path_row_step);self.assertEqual(f.geometry(g)[:2],pos)
        code=f.pml();self.assertIn('PATH DOWN',code.upper())
        self.assertIn("Button .Partial At X 30 'Partial'",code)
        self.assertNotIn("List .Rows At X",code)
        restored=import_mac(code).form
        self.assertEqual(Form.loads(f.dumps()).dumps(),f.dumps())
        self.assertEqual(restored.named('Rows').layout_mode,'AUTO')
        self.assertEqual(restored.geometry(restored.named('Partial'))[:2],(30,5))
        self.assertEqual(import_mac(SOURCE,partial=True).form.dumps(),f.dumps())

    def test_up_left_right_and_explicit_spacing_keep_live_dependencies(self):
        for path in ('DOWN','UP','RIGHT','LEFT'):
            for spacing in ('','Vdist 2\nHdist 3\n'):
                with self.subTest(path=path,spacing=spacing):
                    text=f"Setup Form !!Demo Size 80 50 Dialog\nList .Base At X 20 Y 20 'Base' Width 10 Height 4\nPath {path}\n{spacing}Button .Next 'Next' Width 5\nExit\nShow !!Demo"
                    f=import_mac(text).form;g=f.named('Next');before=f.geometry(g)[:2]
                    f.named('Base').x+=2;f.named('Base').y+=3
                    self.assertEqual(f.geometry(g)[:2],(before[0]+2,before[1]+3))
                    restored=import_mac(f.pml()).form
                    self.assertEqual(restored.geometry(restored.named('Next'))[:2],f.geometry(g)[:2])

    def test_first_implicit_object_is_locked_without_previous_reference(self):
        f=import_mac("Setup Form !!Demo\nPath Right\nButton .First 'First' Width 4\nButton .Next 'Next' Width 5\nExit\nShow !!Demo").form
        self.assertEqual(f.named('First').layout_mode,'AUTO')
        self.assertEqual(f.geometry(f.named('First'))[:2],(0,0))
        restored=import_mac(f.pml()).form
        self.assertEqual(restored.geometry(restored.named('Next'))[:2],(5,0))

    def test_switch_to_coordinates_captures_resolved_position_and_keeps_width_reference(self):
        f=import_mac(SOURCE).form;g=f.named('Rows');g.width_ref='Base';f.named('Base').x=8;f.named('Base').y=7
        original=f.dumps();f.change_layout(g,'ABSOLUTE')
        self.assertEqual((g.x,g.y,g.path_axes,g.width_ref),(8,8,'','Base'))
        f.named('Base').x=10;f.named('Base').y=10
        self.assertEqual(f.geometry(g)[:2],(8,8))
        self.assertEqual(Form.loads(original).named('Rows').layout_mode,'AUTO')

    def test_frame_switch_to_coordinates_outputs_at(self):
        f=import_mac("Setup Form !!Demo Size 80 50 Dialog\nButton .Base At X 4 Y 3 'Base' Width 5\nFrame .Group 'Group'\nButton .Child 'Child' Width 5\nExit\nExit\nShow !!Demo").form
        g=f.named('Group');position=f.geometry(g)[:2];f.change_layout(g,'ABSOLUTE')
        self.assertIn('Frame .Group',f.pml());self.assertTrue(g.frame_at)
        restored=import_mac(f.pml()).form
        self.assertEqual(restored.named('Group').layout_mode,'ABSOLUTE')
        self.assertEqual(restored.geometry(restored.named('Group'))[:2],position)

    def test_invalid_path_metadata_is_rejected(self):
        for kwargs in ({'path_axes':'YX'},{'path_axes':None},{'path_row_step':'true'},{'frame_at':1}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):Form(gadgets=[Gadget(**kwargs)]).validate()

    def test_copy_keeps_path_instead_of_silently_switching_to_coordinates(self):
        f=import_mac(SOURCE).form;original=f.dumps()
        cloned,index=clone_subtree(Form(width=80,height=50),f,1)
        self.assertEqual(cloned.gadgets[index].layout_mode,'AUTO')
        self.assertEqual(cloned.gadgets[index].path_axes,'XY')
        self.assertEqual(cloned.geometry(cloned.gadgets[index])[:2],(0,0))
        self.assertEqual(f.dumps(),original)


class PathLayoutLockGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.directory=Path(self.folder.name)
        self.w=Window(settings_path=self.directory/'settings.json');self.w.show();self.app.processEvents()
        self.w.form=import_mac(SOURCE).form;self.w.selected=1;self.w.history.clear();self.w.refresh();self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.folder.cleanup()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)

    def test_path_cannot_be_dragged_or_nudged(self):
        g=self.w.form.named('Rows');original=self.w.form.dumps();item=self.item('Rows');position=item.pos()
        self.assertFalse(item.flags() & QGraphicsItem.ItemIsMovable)
        point=self.w.view.mapFromScene(item.sceneBoundingRect().center())
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,pos=point)
        QTest.mouseMove(self.w.view.viewport(),point+type(point)(20,20))
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,pos=point+type(point)(20,20))
        self.app.processEvents();self.assertEqual(self.item('Rows').pos(),position)
        self.w.choose_row(1);self.w.move_selection(.5,0)
        self.assertEqual(self.w.form.dumps(),original);self.assertEqual(self.w.history,[])
        self.assertEqual(g.layout_mode,'AUTO')

    def test_quick_switch_preserves_position_and_undo_restores_lock(self):
        original=self.w.form.dumps();position=self.w.form.geometry(self.w.form.named('Rows'))[:2]
        self.assertEqual(self.w.quick_layout.currentData(),'AUTO')
        self.w.quick_layout.setCurrentIndex(self.w.quick_layout.findData('ABSOLUTE'))
        g=self.w.form.named('Rows');self.assertEqual(g.layout_mode,'ABSOLUTE')
        self.assertEqual((g.x,g.y),position);self.assertEqual(len(self.w.history),1)
        self.assertTrue(self.item('Rows').flags() & QGraphicsItem.ItemIsMovable)
        self.w.move_selection(.5,0);self.assertEqual(self.w.form.named('Rows').x,position[0]+.5)
        self.w.undo();self.w.undo();self.assertEqual(self.w.form.dumps(),original)
        self.assertFalse(self.item('Rows').flags() & QGraphicsItem.ItemIsMovable)
        self.w.redo();self.assertEqual(self.w.form.named('Rows').layout_mode,'ABSOLUTE')

    def test_existing_layout_field_uses_same_position_preserving_switch(self):
        self.w.form.named('Base').x=8;self.w.form.named('Base').y=7;self.w.refresh()
        self.w.fields['layout_mode'].setCurrentText('ABSOLUTE')
        self.assertEqual((self.w.form.named('Rows').x,self.w.form.named('Rows').y),(8,8))
        self.assertEqual(self.w.quick_layout.currentData(),'ABSOLUTE')

    def test_context_switch_targets_clicked_object_and_has_one_undo(self):
        self.w.choose_row(0);original=self.w.form.dumps();menu=QMenu()
        self.w.add_layout_actions(menu,'Rows');actions=menu.actions()
        self.assertTrue(actions[0].isEnabled());self.assertFalse(actions[1].isEnabled())
        actions[0].trigger();self.assertEqual(self.w.form.named('Rows').layout_mode,'ABSOLUTE')
        self.assertEqual(self.w.selected,1);self.assertEqual(len(self.w.history),1)
        self.w.undo();self.assertEqual(self.w.form.dumps(),original)

    def test_tree_and_direct_canvas_commit_cannot_remove_path(self):
        original=self.w.form.dumps()
        self.assertFalse(self.w.objects.item(1).flags() & Qt.ItemIsDragEnabled)
        self.assertIn('PATH',self.w.objects.item(1).text(0))
        self.w.move_tree_gadget(1,'',0);self.assertEqual(self.w.form.dumps(),original)
        self.w.move_committed(copy.deepcopy(self.w.form),'Rows',12,10);self.app.processEvents()
        self.assertEqual(self.w.form.dumps(),original);self.assertEqual(self.w.history,[])

    def test_multi_selection_movement_fails_atomically_when_path_selected(self):
        self.w.choose_rows([0,1]);original=self.w.form.dumps()
        self.w.move_selection(.5,.5)
        self.assertEqual(self.w.form.dumps(),original);self.assertEqual(self.w.history,[])

    def test_spacing_edit_changes_to_explicit_vdist_and_keeps_lock(self):
        self.assertTrue(self.w.form.named('Rows').path_row_step)
        self.w.fields['vgap'].setValue(2)
        g=self.w.form.named('Rows');self.assertFalse(g.path_row_step);self.assertEqual(g.layout_mode,'AUTO')
        self.assertIn('Vdist 2',self.w.form.pml())

    def test_import_edit_export_keeps_path_until_explicit_switch(self):
        path=self.directory/'source.mac';data=SOURCE.replace('\n','\r\n').encode('cp932');path.write_bytes(data)
        with patch('e3d_designer.app.QMessageBox.information'),patch('e3d_designer.app.QMessageBox.warning') as warning:
            self.assertTrue(self.w.open_design(path,confirmed=True));self.w.choose_row(1)
            self.w.fields['label'].setText('Edited');self.w.update_gadget()
            self.assertEqual(self.w.form.named('Rows').layout_mode,'AUTO')
            self.w.path=self.directory/'design.json';self.assertTrue(self.w.save());self.assertTrue(self.w.open_design(self.w.path,confirmed=True))
            output=self.directory/'output.mac'
            with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):self.w.export()
            restored=import_mac(output.read_bytes().decode('cp932')).form
            self.assertEqual(restored.named('Rows').layout_mode,'AUTO')
            self.assertEqual(restored.named('Rows').label,'Edited');warning.assert_not_called()
        self.assertEqual(path.read_bytes(),data)


if __name__=='__main__':unittest.main()
