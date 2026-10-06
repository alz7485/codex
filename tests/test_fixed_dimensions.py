import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window, Item
from e3d_designer.images import sync_image_size
from e3d_designer.model import Form, Gadget
from e3d_designer.quick_editor import MiniProperties


class FixedDimensionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.directory = Path(self.folder.name)
        self.w = Window();self.w.show();self.app.processEvents()

    def tearDown(self):
        self.app.clipboard().clear()
        self.w.dirty = False;self.w.close();self.app.processEvents()
        self.folder.cleanup()

    def image(self, name, width, height):
        path = self.directory / name
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(QColor('red'));self.assertTrue(image.save(str(path)))
        return str(path)

    def load(self, gadget):
        self.w.form = Form(gadgets=[gadget]);self.w.selected = 0
        self.w.refresh();self.app.processEvents()

    def item(self):
        return next(item for item in self.w.scene.items() if isinstance(item, Item))

    def test_image_picker_uses_intrinsic_pixels_for_all_single_image_gadgets(self):
        filename = self.image('source.png', 137, 63)
        for kind in ('paragraph', 'button', 'toggle'):
            with self.subTest(kind=kind):
                self.load(Gadget(kind=kind, display_mode='PIXMAP', width=100, height=50))
                self.w.history.clear()
                with patch('e3d_designer.app.QFileDialog.getOpenFileName', return_value=(filename, '')):
                    self.w.choose_image()
                gadget = self.w.form.gadgets[0]
                self.assertEqual((gadget.width, gadget.height), (137, 63))
                self.assertAlmostEqual(self.item().boundingRect().width(),137)
                self.assertAlmostEqual(self.item().boundingRect().height(),63)
                self.assertEqual(self.item().handles(), {})
                self.assertFalse(self.w.fields['width'].isEnabled())
                self.assertFalse(self.w.fields['height'].isEnabled())
                self.assertFalse(self.w.fields['width_ref'].isEnabled())
                self.assertEqual(len(self.w.history), 1)
                self.w.undo();self.assertEqual(self.w.form.gadgets[0].pixmap_path, '')
                self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(100,50))

    def test_option_uses_maximum_dimensions_without_scaling_source(self):
        paths = [self.image('wide.png', 137, 30), self.image('tall.png', 20, 79)]
        self.load(Gadget(kind='option', display_mode='PIXMAP', width=100, height=50))
        with patch('e3d_designer.app.QFileDialog.getOpenFileNames', return_value=(paths, '')):
            self.w.choose_image()
        gadget = self.w.form.gadgets[0]
        self.assertEqual((gadget.width, gadget.height), (137, 79))
        self.assertEqual((self.item().pixmap.width(),self.item().pixmap.height()),(137,30))
        self.assertEqual(self.item().handles(), {})
        self.w.undo();self.assertEqual(self.w.form.gadgets[0].items, [])

    def test_manual_path_entry_reads_size_and_preserves_path(self):
        filename = self.image('Image$.png', 99, 47)
        self.load(Gadget(kind='paragraph', display_mode='PIXMAP'))
        self.w.fields['pixmap_path'].setText(filename);self.w.update_gadget()
        self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(99,47))
        self.assertIn(filename,self.w.form.pml());self.assertEqual(self.w.validation_error,'')

    def test_open_legacy_project_reads_relative_image_and_saves_correct_dimensions(self):
        self.image('relative.png', 157, 61)
        form = Form(gadgets=[Gadget(kind='paragraph', display_mode='PIXMAP', pixmap_path='relative.png', width=100, height=50)])
        path = self.directory / 'design.json';path.write_text(form.dumps(), encoding='utf-8')
        self.assertTrue(self.w.open_design(path, confirmed=True))
        self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(157,61))
        self.assertTrue(self.w.dirty);self.assertTrue(self.w.save())
        loaded=Form.loads(path.read_text(encoding='utf-8'))
        self.assertEqual((loaded.gadgets[0].width,loaded.gadgets[0].height),(157,61))
        self.assertEqual(loaded.gadgets[0].pixmap_path,'relative.png')

    def test_unavailable_share_retains_last_dimensions_and_clears_width_reference(self):
        gadget=Gadget(kind='paragraph',display_mode='PIXMAP',pixmap_path=r'\\server\Images$\missing.png',width=137,height=63,width_ref='other')
        self.assertTrue(sync_image_size(gadget))
        self.assertEqual((gadget.width,gadget.height,gadget.width_ref),(137,63,''))
        self.assertFalse(sync_image_size(gadget))

    def test_unreadable_relative_directory_can_fall_back_to_application_directory(self):
        self.image('source.png',137,63)
        gadget=Gadget(kind='paragraph',display_mode='PIXMAP',pixmap_path='source.png')
        with patch('e3d_designer.images.Path.is_file',side_effect=[PermissionError('share unavailable'),True]):
            self.assertTrue(sync_image_size(gadget,(self.directory/'blocked',self.directory)))
        self.assertEqual((gadget.width,gadget.height),(137,63))

    def test_oversized_image_is_not_silently_scaled_or_moved(self):
        filename=self.image('large.png',900,100)
        self.load(Gadget(kind='paragraph',display_mode='PIXMAP',pixmap_path=filename,x=2,y=1))
        gadget=self.w.form.gadgets[0]
        self.assertEqual((gadget.x,gadget.y,gadget.width,gadget.height),(2,1,900,100))
        self.assertIn('親コンテナ',self.w.validation_error)
        self.w.form.width=100;self.w.refresh();self.assertEqual(self.w.validation_error,'')

    def test_mini_editor_applies_new_image_size_atomically(self):
        old=self.image('old.png',40,20);new=self.image('new.png',117,61)
        self.load(Gadget(kind='paragraph',display_mode='PIXMAP',pixmap_path=old))
        dialog=MiniProperties(self.w,self.w.form,0)
        self.assertFalse(dialog.fields['width'].isEnabled());self.assertFalse(dialog.fields['height'].isEnabled())
        dialog.fields['pixmap_path'].setText(new)
        self.assertEqual((dialog.fields['width'].value(),dialog.fields['height'].value()),(117,61))
        dialog.fields['width'].setValue(200)
        dialog.accept();self.assertIsNotNone(dialog.result_form)
        gadget=dialog.result_form.gadgets[0]
        self.assertEqual((gadget.width,gadget.height),(117,61))
        self.assertEqual(self.w.form.gadgets[0].pixmap_path,old)
        dialog.deleteLater()

    def test_text_height_is_one_line_in_legacy_projects_and_relative_layout(self):
        form=Form(gadgets=[Gadget(kind='text',name='input',height=5),Gadget(name='next',layout_mode='RELATIVE',xref='input',yref='input')])
        data=json.loads(form.dumps());data['form']['gadgets'][0]['height']=5
        loaded=Form.loads(json.dumps(data))
        self.assertEqual(loaded.gadgets[0].height,1)
        self.assertEqual(loaded.geometry(loaded.gadgets[1])[1],2.5)
        self.assertNotIn('HEIGHT',loaded.pml(normalize=False).split('TEXT .input',1)[1].splitlines()[0])

    def test_text_height_locked_and_width_handle_still_resizes(self):
        self.load(Gadget(kind='text',height=5))
        item=self.item();self.assertEqual(item.boundingRect().height(),26)
        self.assertEqual(set(item.handles()),{'width'})
        self.assertFalse(self.w.fields['height'].isEnabled());self.assertTrue(self.w.fields['width'].isEnabled())
        start=self.w.view.mapFromScene(item.mapToScene(item.handles()['width'].center()))
        end=start+QPoint(30,0)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(17,1))
        self.w.undo();self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(14,1))

    def test_other_gadgets_keep_height_controls(self):
        for kind in ('list','textpane','button'):
            with self.subTest(kind=kind):
                self.load(Gadget(kind=kind,height=3))
                self.assertEqual(self.w.form.gadgets[0].height,3)
                self.assertTrue(self.w.fields['height'].isEnabled())
                self.assertIn('height',self.item().handles())

    def test_switching_from_image_restores_dimension_controls(self):
        self.load(Gadget(kind='paragraph',display_mode='PIXMAP',width=100,height=52))
        self.w.fields['display_mode'].setCurrentText('TEXT')
        self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(10,1))
        self.assertTrue(self.w.fields['width'].isEnabled());self.assertFalse(self.w.fields['height'].isEnabled())

    def test_paragraph_declares_filename_once_before_show(self):
        for path in (r'\\server\Images$\Logo One.png',r"C:\Images\O'Brien.png",'assets/red.png'):
            with self.subTest(path=path):
                form=Form(gadgets=[Gadget(kind='paragraph',display_mode='PIXMAP',pixmap_path=path,width=137,height=63)])
                code=form.pml(normalize=False)
                declaration=next(line for line in code.splitlines() if 'PARAGRAPH .' in line)
                self.assertIn(path,declaration);self.assertIn('WIDTH 137 HEIGHT 63',declaration)
                self.assertEqual(code.count(path),1);self.assertNotIn('AddPixmap(',code)
                self.assertLess(code.index(path),code.index('SHOW !!'))

    def test_unset_paragraph_image_does_not_emit_empty_pixmap_lookup(self):
        code=Form(gadgets=[Gadget(kind='paragraph',display_mode='PIXMAP',width=100,height=50)]).pml(normalize=False)
        self.assertIn("PARAGRAPH .button1 AT X 2 Y 1 TEXT '' WIDTH 10",code)
        self.assertNotIn('PIXMAP',code);self.assertNotIn('AddPixmap(',code)
