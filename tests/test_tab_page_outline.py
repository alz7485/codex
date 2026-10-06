import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QStyleOptionGraphicsItem
from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.model import Form,Gadget


class TabPageOutlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.form=Form(height=30,gadgets=[Gadget(kind='frame',name='Outer',x=3,y=2,width=55,height=25),
            Gadget(kind='frame',name='Tabs',parent='Outer',frame_style='TABSET',x=10,y=3,width=40,height=20,
                tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')])])
        self.w.selected=next(i for i,g in enumerate(self.w.form.gadgets) if g.name=='PageA')
        self.w.refresh();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def test_selected_page_outline_starts_below_header(self):
        page=self.item('PageA')
        image=QImage(400,520,QImage.Format_ARGB32);image.fill(Qt.transparent)
        painter=QPainter(image)
        try:page.paint(painter,QStyleOptionGraphicsItem())
        finally:painter.end()
        self.assertEqual(image.pixelColor(1,1).alpha(),0)
        self.assertEqual(image.pixelColor(1,27).name(),'#2277cc')
        self.assertTrue(page.shape().contains(page.mapFromScene(13*SX+20,5*SY+40)))
    def test_page_outline_follows_tabset_properties_and_undo(self):
        w=self.w;original=w.form.dumps()
        w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name=='Tabs'))
        w.fields['x'].setValue(12.3);w.fields['y'].setValue(4.1)
        for name in ('Tabs','PageA','PageB'):
            item=self.item(name)
            self.assertAlmostEqual(item.pos().x()/SX,15.3)
            self.assertAlmostEqual(item.pos().y()/SY,6.1)
        page=w.form.named('PageA');self.assertEqual(w.form.geometry(page)[:2],(0,0))
        w.undo();w.undo();self.assertEqual(w.form.dumps(),original)
        self.assertEqual((self.item('PageA').pos().x()/SX,self.item('PageA').pos().y()/SY),(13,5))
    def test_page_switch_and_roundtrip_keep_outline_in_parent_coordinates(self):
        w=self.w;original=w.form.dumps();w.form=Form.loads(original);w.refresh()
        w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name=='PageB'))
        page=self.item('PageB');self.assertTrue(page.isVisible());self.assertTrue(page.isSelected())
        self.assertFalse(self.item('PageA').isVisible())
        self.assertEqual((page.pos().x()/SX,page.pos().y()/SY),(13,5))
        outline=page.mapRectToScene(page.shape().boundingRect())
        self.assertEqual((outline.left(),outline.top()),(13*SX,5*SY+26))
        self.assertEqual(w.form.dumps(),original)
