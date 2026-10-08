import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window
from e3d_designer.model import Form,Gadget
from e3d_designer.mac_import import import_mac


class FrameCopyWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.form=Form(width=90,height=60,gadgets=[
            Gadget(kind='frame',name='Outer',x=10,y=5,width=60,height=40,frame_at=True,frame_size_axes='WH'),
            Gadget(kind='frame',name='Inner',parent='Outer',x=3,y=4,width=30,height=20,frame_at=True,frame_size_axes='WH'),
            Gadget(kind='text',name='Value',parent='Inner',x=1,y=2,initial='001'),
            Gadget(name='Run',parent='Inner',x=1,y=4,callback='Changed',body="!this.Value.val = '002'"),
            Gadget(kind='option',name='Choice',parent='Outer',x=35,y=2,items=['A','B'],item_values=['1','2']),
        ]);self.w.selected=0;self.w.refresh()
    def tearDown(self):self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def assert_copy(self):
        form=self.w.form;outer=form.gadgets[self.w.selected];self.assertNotEqual(outer.name,'Outer')
        self.assertEqual((outer.x,outer.y),(10,5));self.assertEqual(len(form.descendants(outer.name)),4)
        inner=next(g for g in form.children(outer.name) if g.kind=='frame');self.assertEqual((inner.x,inner.y),(3,4))
        text=next(g for g in form.children(inner.name) if g.kind=='text');self.assertEqual(text.initial,'001')
        run=next(g for g in form.children(inner.name) if g.kind=='button');self.assertIn(f'!this.{text.name}.val',run.body);self.assertNotEqual(run.callback,'Changed')
        option=next(g for g in form.children(outer.name) if g.kind=='option');self.assertEqual(option.item_values,['1','2'])
        form.validate();loaded=import_mac(form.pml()).form;self.assertEqual(len(loaded.descendants(outer.name)),4)

    def test_frame_duplicate_and_single_undo(self):
        before=self.w.form.dumps();self.w.duplicate();self.assert_copy();self.assertEqual(len(self.w.history),1)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_copy_paste_snapshot_nested_frames_and_undo(self):
        before=self.w.form.dumps();self.assertTrue(self.w.copy_gadget());self.assertEqual(self.w.form.dumps(),before)
        self.w.paste_gadget();self.assert_copy();self.assertEqual(len(self.w.history),1)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)
