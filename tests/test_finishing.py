import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtGui import QAction, QColor, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox
from e3d_designer.app import Window, Item
from e3d_designer.model import Form, Gadget


class FinishingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json')

    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close()
        self.app.processEvents();self.temp.cleanup()

    def test_save_as_action_keeps_original_and_selects_new_json(self):
        w=self.w;w.path=self.folder/'original.json';self.assertTrue(w.save())
        before=w.path.read_bytes();w.form.title='変更';w.dirty=True
        action=next(a for a in w.findChildren(QAction) if a.text()=='名前を付けて保存')
        self.assertEqual(action.shortcut().toString(),'Ctrl+Shift+S')
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(self.folder/'copy'),'')):
            action.trigger()
        self.assertEqual(w.path,self.folder/'copy.json')
        self.assertEqual((self.folder/'original.json').read_bytes(),before)
        self.assertEqual(Form.loads(w.path.read_text()).title,'変更')
        self.assertFalse(w.dirty)
        self.assertIn(str(w.path),w.statusBar().currentMessage())
        with patch('e3d_designer.app.QFileDialog.getSaveFileName') as dialog:
            self.assertTrue(w.save());dialog.assert_not_called()

    def test_save_as_cancel_write_failure_and_normalized_overwrite_keep_state(self):
        w=self.w;w.path=self.folder/'original.json';self.assertTrue(w.save());w.dirty=True
        original=w.path;before=w.form.dumps()
        target=self.folder/'copy.json';target.write_bytes(b'keep')
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(target.with_suffix('.txt')),'')),patch('e3d_designer.app.QMessageBox.question',return_value=QMessageBox.No):
            self.assertFalse(w.save_as())
        self.assertEqual(target.read_bytes(),b'keep')
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=('', '')):
            self.assertFalse(w.save_as())
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(target),'')),patch('e3d_designer.app.atomic_write',side_effect=OSError('read only')),patch('e3d_designer.app.QMessageBox.warning') as warning:
            self.assertFalse(w.save_as());warning.assert_called_once()
        self.assertEqual(target.read_bytes(),b'keep')
        self.assertEqual(w.path,original);self.assertTrue(w.dirty);self.assertEqual(w.form.dumps(),before)

    def test_relative_images_use_project_then_application_without_changing_paths(self):
        project=self.folder/'project';project.mkdir()
        appdir=self.folder/'app';appdir.mkdir()
        for folder,color in ((project,'red'),(appdir,'blue')):
            image=QPixmap(20,10);image.fill(QColor(color));image.save(str(folder/'sample.png'))
        w=self.w;w.settings.app_directory=appdir;w.path=project/'design.json'
        w.form=Form(gadgets=[Gadget(kind='paragraph',name='image',display_mode='PIXMAP',width=100,height=50,pixmap_path='sample.png'),
            Gadget(kind='option',name='choice',display_mode='PIXMAP',width=100,height=50,x=20,items=['sample.png'])])
        before=w.form.dumps();w.refresh()
        for item in w.scene.items():
            if isinstance(item,Item):self.assertEqual(item.pixmap.toImage().pixelColor(0,0),QColor('red'))
        (project/'sample.png').unlink();w.refresh()
        for item in w.scene.items():
            if isinstance(item,Item):self.assertEqual(item.pixmap.toImage().pixelColor(0,0),QColor('blue'))
        self.assertEqual(w.form.dumps(),before)
        self.assertIn("'sample.png'",w.form.pml())

    def test_icon_and_sample_image_load_from_other_working_directory(self):
        self.assertFalse(self.w.windowIcon().isNull())
        for size in (16,32,48,256):self.assertFalse(self.w.windowIcon().pixmap(size,size).isNull())
        project=Path(__file__).resolve().parent.parent/'examples'/'extra-features.json'
        original=Path.cwd()
        try:
            os.chdir(self.folder)
            with patch('e3d_designer.app.QFileDialog.getOpenFileName',return_value=(str(project),'')):self.w.open()
            images=[item for item in self.w.scene.items() if isinstance(item,Item) and item.gadget.display_mode=='PIXMAP']
            self.assertTrue(images)
            self.assertTrue(all(not item.pixmap.isNull() for item in images))
        finally:os.chdir(original)

    def test_all_sample_projects_open_save_and_export(self):
        w=self.w
        for project in sorted((Path(__file__).resolve().parent.parent/'examples').glob('*.json')):
            with self.subTest(project=project.name):
                with patch('e3d_designer.app.QFileDialog.getOpenFileName',return_value=(str(project),'')):w.open()
                expected=w.form.pml();target=self.folder/project.name
                with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(target),'')):self.assertTrue(w.save_as())
                self.assertEqual(Form.loads(target.read_text()).pml(),expected)
                output=target.with_suffix('.mac')
                with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):w.export()
                self.assertEqual(output.read_bytes(),expected.replace('\n','\r\n').encode('cp932'))
                self.assertIn(str(output),w.statusBar().currentMessage())
