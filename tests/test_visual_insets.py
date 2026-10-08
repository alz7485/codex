import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QFont,QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.model import Form,Gadget


class VisualInsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json');self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.clipboard().clear();self.app.processEvents();self.temp.cleanup()
    def load(self,form):
        self.w.form=form;self.w.selected=None;self.w._multi_selection.clear()
        self.w.history=[];self.w.future=[];self.w.dirty=False;self.w.refresh();self.app.processEvents()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)
    def preview(self):
        self.w.toggle_runtime_preview(True);self.app.processEvents();return self.w.runtime_dialog
    def tab_form(self):
        return Form(height=30,gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=2,y=2,width=50,height=25,
            tabs=[Gadget(kind='frame',name='PageA'),Gadget(kind='frame',name='PageB')]),
            Gadget(kind='paragraph',name='Zero',parent='PageA',x=0,y=0,width=10,label='0行目'),
            Gadget(kind='frame',name='Nested',parent='PageA',x=15,y=0,width=25,height=15),
            Gadget(name='Run',parent='Nested',x=0,y=0,width=8),
            Gadget(kind='paragraph',name='Hidden',parent='PageB',x=0,y=0,width=10,label='別タブ')])

    def test_zero_row_and_nested_content_start_below_tab_header_and_match_reference(self):
        self.load(self.tab_form());before=self.w.form.dumps();code=self.w.form.pml();p=self.preview()
        header=self.w.appearance.tab_header_height();tabs=self.item('Tabs')
        for name in ('Zero','Nested','Run'):
            item=self.item(name)
            self.assertAlmostEqual(item.pos().y(),tabs.pos().y()+header)
            control=p.controls[name]
            reference=control.mapTo(p.surface,QPoint())-p.layout_origin
            self.assertAlmostEqual(reference.y(),item.sceneBoundingRect().top(),delta=.5)
        self.assertGreaterEqual(self.item('Zero').sceneBoundingRect().top(),tabs.pos().y()+header)
        self.assertEqual(self.item('Hidden').pos().y(),tabs.pos().y()+header)
        self.assertFalse(self.item('Hidden').isVisible())
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.form.pml(),code)
        self.assertEqual(self.w.history,[])

    def test_zero_row_drag_keeps_page_coordinates_and_undo(self):
        form=self.tab_form();form.gadgets.append(Gadget(name='Movable',parent='PageA',x=0,y=0,width=8))
        self.load(form);before=self.w.form.dumps();item=self.item('Movable')
        start=self.w.view.mapFromScene(item.mapToScene(item.boundingRect().center()));end=start+QPoint(20,26)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        g=self.w.form.named('Movable')
        self.assertEqual((g.parent,g.x,g.y),('PageA',2,1))
        self.assertEqual((self.w.form.named('Tabs').x,self.w.form.named('Tabs').y),(2,2))
        self.assertEqual(len(self.w.history),1);self.w.undo();self.assertEqual(self.w.form.dumps(),before)

    def test_tab_origin_tracks_font_and_accumulates_for_nested_tabsets(self):
        form=self.tab_form()
        form.gadgets.extend([Gadget(kind='frame',name='InnerTabs',parent='Nested',frame_style='TABSET',x=0,y=0,width=20,height=10,
            tabs=[Gadget(kind='frame',name='InnerPage')]),Gadget(kind='paragraph',name='InnerZero',parent='InnerPage',x=0,y=0,label='0')])
        self.load(Form(height=form.height,gadgets=form.gadgets));before=self.w.form.dumps()
        for size in (10,14):
            font=QFont(self.w.appearance.preview_font);font.setPointSize(size);self.w.set_display_font(font);p=self.preview()
            header=self.w.appearance.tab_header_height()
            self.assertAlmostEqual(self.item('InnerZero').pos().y(),self.item('Tabs').pos().y()+2*header)
            for name in ('Zero','InnerZero'):
                reference=p.controls[name].mapTo(p.surface,QPoint())-p.layout_origin
                self.assertAlmostEqual(reference.y(),self.item(name).pos().y(),delta=.5)
        self.assertEqual(self.w.form.dumps(),before)

    def test_label_text_moves_right_but_background_origin_and_image_size_stay_fixed(self):
        image=QImage(25,15,QImage.Format_RGB32);image.fill(Qt.red);image.save(str(self.folder/'image.png'))
        self.load(Form(gadgets=[Gadget(kind='paragraph',name='Plain',x=0,y=0,label='Label',width=10),
            Gadget(kind='paragraph',name='Colored',x=0,y=2,label='Label',background='4',width=10),
            Gadget(kind='paragraph',name='Image',x=0,y=4,display_mode='PIXMAP',pixmap_path=str(self.folder/'image.png'),width=25,height=15)]))
        before=self.w.form.dumps();p=self.preview()
        for name in ('Plain','Colored'):
            self.assertEqual(p.controls[name].contentsMargins().left(),round(.8*SX))
            self.assertEqual(self.item(name).pos().x(),0)
            pixmap=self.item(name)._control_pixmap.toImage()
            ink=[x for x in range(pixmap.width()) for y in range(pixmap.height())
                 if pixmap.pixelColor(x,y).alpha()>0 and max(pixmap.pixelColor(x,y).red(),pixmap.pixelColor(x,y).green(),pixmap.pixelColor(x,y).blue())<100]
            self.assertTrue(ink);self.assertGreaterEqual(min(ink),round(.8*SX))
        self.assertEqual(self.item('Plain')._control_pixmap.toImage().pixelColor(1,1).alpha(),0)
        self.assertEqual(self.item('Colored')._control_pixmap.toImage().pixelColor(1,1).alpha(),255)
        self.assertEqual(p.controls['Image'].contentsMargins().left(),0)
        self.assertEqual(p.controls['Image'].size().toTuple(),(25,15));self.assertEqual(self.w.form.dumps(),before)

    def test_button_display_height_is_point_nine_rows_and_source_remains_one_row(self):
        self.load(Form(gadgets=[Gadget(name='Run',x=0,y=0,label='計測',width=4,height=1),
            Gadget(kind='text',name='Entry',x=0,y=2,label='',height=1)]))
        before=self.w.form.dumps();code=self.w.form.pml();p=self.preview();item=self.item('Run');button=p.controls['Run']
        self.assertEqual(button.height(),round(.9*SY))
        self.assertEqual(button.y()-p.layout_origin.y(),round(.05*SY))
        self.assertEqual(item.boundingRect().height(),button.height())
        self.assertEqual(item.boundingRect().top(),round(.05*SY))
        self.assertEqual(item.pos().toTuple(),(0,0))
        self.assertEqual(p.controls['Entry'].height(),SY)
        self.assertEqual(self.w.form.named('Run').height,1)
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.form.pml(),code)
        self.w.choose_row(0)
        self.assertEqual(item.handles()['height'].bottom(),item.boundingRect().bottom())
