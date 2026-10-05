import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication
from e3d_designer.model import Form
from e3d_designer.app import Window


class DockingTests(unittest.TestCase):
    def test_directions_round_trip_and_legacy(self):
        for side in ('LEFT','RIGHT','TOP','BOTTOM'):
            form=Form(dock_side=side)
            self.assertIn('DIALOG DOCK '+side,form.pml())
            self.assertEqual(Form.loads(form.dumps()).docking_side(),side)
        self.assertEqual(Form.loads('{"version":1,"form":{"dock_right":false,"gadgets":[]}}').docking_side(),'NONE')
        self.assertEqual(Form().docking_side(),'RIGHT')
        self.assertIn('size 70 22 DIALOG',Form(dock_side='NONE').pml())
        self.assertIn('setup form !!userform MAIN',Form(form_type='MAIN',dock_side='LEFT').pml())
        with self.assertRaises(ValueError):Form(dock_side='FILL').pml()

    def test_gui_directions_save_load_and_undo(self):
        app=QApplication.instance() or QApplication([]);window=Window()
        try:
            for index,side in ((3,'LEFT'),(4,'TOP'),(5,'BOTTOM'),(0,'RIGHT')):
                window.docking.setCurrentIndex(index)
                self.assertEqual(window.form.docking_side(),side)
                self.assertIn('DIALOG DOCK '+side,window.code.toPlainText())
            window.undo();self.assertEqual(window.form.docking_side(),'BOTTOM')
            self.assertEqual(window.docking.currentIndex(),5)
            window.form=Form.loads(window.form.dumps());window.refresh()
            self.assertEqual(window.docking.currentIndex(),5)
        finally:
            app.clipboard().clear();window.dirty=False;window.close();app.processEvents()
