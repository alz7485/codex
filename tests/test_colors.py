import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtGui import QColor,QImage,QPainter
from e3d_designer.colors import PREVIEW_COLORS,preview_color,foreground_color
from e3d_designer.color_picker import ColorPicker
from e3d_designer.app import Window,Item
from e3d_designer.model import Form,Gadget


class ColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_complete_palette_and_unmapped_numbers(self):
        self.assertEqual(set(PREVIEW_COLORS),set(range(1,321)))
        self.assertTrue(all(QColor(color).isValid() for color in PREVIEW_COLORS.values()))
        self.assertIsNone(preview_color(''));self.assertIsNone(preview_color('999'))
        self.assertEqual(foreground_color('#000000'),'#ffffff')
        self.assertEqual(foreground_color('#ffffff'),'#17202b')
        self.assertEqual(preview_color('320'),PREVIEW_COLORS[320])

    def test_picker_selection_clear_cancel(self):
        dialog=ColorPicker(None,'320')
        self.assertEqual(len(dialog.buttons),320)
        dialog.buttons[320].click();self.assertEqual(dialog.value,'320');self.assertEqual(dialog.result(),QDialog.Accepted)
        dialog.choose('');self.assertEqual(dialog.value,'')
        dialog.close()
        dialog=ColorPicker(None,'2');dialog.reject();self.assertEqual(dialog.value,'2');dialog.close()

    def test_button_background_is_rendered_and_number_exported(self):
        gadget=Gadget(background='2');form=Form(gadgets=[gadget]);item=Item(gadget,form)
        image=QImage(140,26,QImage.Format_ARGB32);image.fill(QColor('#ffffff'))
        painter=QPainter(image);item.paint(painter,None,None);painter.end()
        self.assertEqual(image.pixelColor(5,5).name(),PREVIEW_COLORS[2])
        self.assertIn('Background 2',form.pml());self.assertNotIn(PREVIEW_COLORS[2],form.pml())

    def test_gui_pick_apply_undo_and_cancel(self):
        window=Window()
        try:
            window.add('paragraph')
            def accept(dialog):dialog.value='320';return QDialog.Accepted
            with patch('e3d_designer.color_picker.ColorPicker.exec',accept):window.pick_background()
            self.assertEqual(window.form.gadgets[0].background,'320')
            self.assertIn('Background 320',window.code.toPlainText())
            window.undo();self.assertEqual(window.form.gadgets[0].background,'')
            window.choose_row(0)
            with patch('e3d_designer.color_picker.ColorPicker.exec',return_value=QDialog.Rejected):window.pick_background()
            self.assertEqual(window.form.gadgets[0].background,'')
        finally:self.app.clipboard().clear();window.dirty=False;window.close();self.app.processEvents()
