from e3d_designer.formatting import canonical_pml
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication,QDoubleSpinBox
from e3d_designer.model import Form
from e3d_designer.app import Window


class DockingTests(unittest.TestCase):
    def test_directions_round_trip_and_legacy(self):
        for side in ('LEFT','RIGHT','TOP','BOTTOM'):
            form=Form(dock_side=side)
            self.assertIn('DIALOG DOCK '+side,form.pml(normalize=False))
            self.assertEqual(Form.loads(form.dumps()).docking_side(),side)
        self.assertEqual(Form.loads('{"version":1,"form":{"dock_right":false,"gadgets":[]}}').docking_side(),'NONE')
        self.assertEqual(Form().docking_side(),'NONE')
        self.assertEqual(Form.loads('{"version":1,"form":{"gadgets":[]}}').docking_side(),'RIGHT')
        self.assertIn('size 70 22 DIALOG',Form(dock_side='NONE').pml(normalize=False))
        self.assertIn('setup form !!userform MAIN',Form(form_type='MAIN',dock_side='LEFT').pml(normalize=False))
        with self.assertRaises(ValueError):Form(dock_side='FILL').pml(normalize=False)

    def test_gui_directions_save_load_and_undo(self):
        app=QApplication.instance() or QApplication([]);window=Window()
        try:
            self.assertEqual([window.docking.itemData(i) for i in range(6)],['NONE','RIGHT','LEFT','TOP','BOTTOM','MAIN'])
            self.assertEqual(window.docking.currentIndex(),0)
            for index,side in ((2,'LEFT'),(3,'TOP'),(4,'BOTTOM'),(1,'RIGHT')):
                window.docking.setCurrentIndex(index)
                self.assertEqual(window.form.docking_side(),side)
                self.assertIn(canonical_pml('DIALOG DOCK '+side),window.code.toPlainText())
            window.undo();self.assertEqual(window.form.docking_side(),'BOTTOM')
            self.assertEqual(window.docking.currentIndex(),4)
            window.form=Form.loads(window.form.dumps());window.refresh()
            self.assertEqual(window.docking.currentIndex(),4)
        finally:
            app.clipboard().clear();window.dirty=False;window.close();app.processEvents()

    def test_spin_fields_use_tenth_steps_and_one_decimal_including_images(self):
        app=QApplication.instance() or QApplication([]);window=Window()
        try:
            for kind,direction in (('button',None),('paragraph','PIXMAP'),('slider',None)):
                window.add(kind,direction)
                for spin in window.findChildren(QDoubleSpinBox):
                    self.assertEqual(spin.decimals(),1)
                    self.assertEqual(spin.singleStep(),.1)
            field=window.fields['x'];before=field.value();field.stepUp()
            self.assertAlmostEqual(field.value(),before+.1)
        finally:
            app.clipboard().clear();window.dirty=False;window.close();app.processEvents()
