import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication,QLineEdit
from e3d_designer.app import Window,Item
from e3d_designer.model import Form,Gadget


class InitialPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json');self.w.show();self.app.processEvents()

    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_boolean_dropdown_changes_values_and_undo_without_free_text(self):
        w=self.w
        for kind in ('toggle','rtoggle'):
            w.new();w.add(kind)
            name=w.form.gadgets[w.selected].name
            self.assertFalse(w.initial_choice.isEditable());self.assertTrue(w.initial_choice.isVisible())
            self.assertFalse(w.fields['initial'].isVisible())
            self.assertEqual([w.initial_choice.itemData(i) for i in range(3)],['','TRUE','FALSE'])
            for value in ('TRUE','FALSE',''):
                if value=='':w.initial_choice.setCurrentIndex(w.initial_choice.findData('TRUE'))
                previous=w.form.named(name).initial
                w.initial_choice.setCurrentIndex(w.initial_choice.findData(value))
                self.assertEqual(w.form.named(name).initial,value)
                self.assertEqual(Form.loads(w.form.dumps()).named(name).initial,value)
                if value and kind=='toggle':self.assertIn('.VAL = '+value,w.form.pml())
                w.undo();self.assertEqual(w.form.named(name).initial,previous)
                w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name==name))
            w.dirty=False

    def test_switch_between_boolean_and_string_preserves_values(self):
        w=self.w;w.form=Form(gadgets=[Gadget(kind='toggle',name='enabled',initial='true'),Gadget(kind='text',name='name',x=30,initial='P-101')])
        w.selected=0;w.refresh();w.set_workflow('layout');before=w.form.dumps()
        self.assertEqual(w.initial_choice.currentData(),'TRUE')
        w.choose_row(1)
        self.assertFalse(w.initial_choice.isVisible());self.assertTrue(w.fields['initial'].isVisible())
        self.assertIsInstance(w.fields['initial'],QLineEdit);self.assertEqual(w.fields['initial'].text(),'P-101')
        w.choose_row(0);self.assertEqual(w.initial_choice.currentData(),'TRUE')
        self.assertEqual(w.form.dumps(),before);self.assertFalse(w.dirty)

    def test_text_label_and_entry_are_separate_without_geometry_or_code_change(self):
        form=Form(gadgets=[Gadget(kind='text',name='name',label='Equipment',initial='P-101',width=24)])
        before=form.dumps();code=form.pml()
        item=Item(form.gadgets[0],form)
        label,entry=item.text_regions(QFontMetrics(self.app.font()))
        self.assertGreater(label.width(),0);self.assertLess(label.right(),entry.left())
        self.assertGreater(entry.width(),0);self.assertLessEqual(entry.right(),item.boundingRect().right())
        self.assertEqual(form.dumps(),before);self.assertEqual(form.pml(),code)
        form.gadgets[0].label=''
        label,entry=item.text_regions(QFontMetrics(self.app.font()))
        self.assertEqual(label.width(),0);self.assertEqual(entry.left(),1)
