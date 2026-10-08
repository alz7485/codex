import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QRectF, QPointF, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from e3d_designer.app import Window
from e3d_designer.model import Form, Gadget, Menu, MenuItem
from e3d_designer.runtime_preview import RuntimePreview


class FullFormPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):self.preview=RuntimePreview()
    def tearDown(self):self.preview.close();self.preview.deleteLater();self.app.processEvents()

    def show_form(self,form):
        self.preview.set_form(form);self.preview.show();self.app.processEvents()
        return self.preview

    def assert_whole_form_visible(self):
        view=self.preview.form_view
        visible=QRectF(view.viewport().rect()).adjusted(-1,-1,1,1)
        mapped=view.viewportTransform().mapRect(view.sceneRect())
        self.assertTrue(visible.contains(mapped),(visible,mapped))
        self.assertFalse(view.horizontalScrollBar().isVisible())
        self.assertFalse(view.verticalScrollBar().isVisible())

    def test_fitting_form_uses_native_scale_and_shows_bottom_edge(self):
        form=Form(width=40,height=18,gadgets=[Gadget(name='Bottom',x=30,y=17,width=8)])
        before=form.dumps();code=form.pml();self.show_form(form)
        self.assertEqual(self.preview.form_view.display_scale,1)
        self.assert_whole_form_visible()
        self.assertEqual(form.dumps(),before);self.assertEqual(form.pml(),code)

    def test_large_form_menu_and_warning_fit_without_changing_native_geometry(self):
        form=Form(width=250,height=100,menus=[Menu(name='Tools',label='Tools',items=[MenuItem('Run','SAVEWORK')])],
            gadgets=[Gadget(name='Bottom',label='Bottom right',x=230,y=98,width=18)])
        before=form.dumps();code=form.pml();self.show_form(form)
        self.assertLess(self.preview.form_view.display_scale,1)
        self.assert_whole_form_visible()
        control=self.preview.controls['Bottom']
        self.assertEqual(control.pos().x(),2300+self.preview.layout_origin.x())
        self.assertGreater(control.width(),180)
        self.assertEqual(self.preview.menu_bar.actions()[0].text(),'Tools')
        self.assertEqual(form.dumps(),before);self.assertEqual(form.pml(),code)
        form.gadgets[0].initial='bad\ninitial';form.gadgets[0].kind='text'
        self.show_form(form);self.assertTrue(self.preview.preview_warning);self.assert_whole_form_visible()

    def test_resize_updates_fit_and_reopen_returns_to_native_scale(self):
        self.show_form(Form(width=150,height=70))
        scale=self.preview.form_view.display_scale
        self.preview.resize(320,240);self.app.processEvents()
        self.assertLess(self.preview.form_view.display_scale,scale);self.assert_whole_form_visible()
        root=self.preview.form_root
        self.show_form(Form(width=20,height=8,gadgets=[Gadget(name='New',label='New')]))
        self.assertFalse(isValid(root));self.assertEqual(list(self.preview.controls),['New'])
        self.assertEqual(self.preview.form_view.display_scale,1);self.assert_whole_form_visible()

    def test_scaled_preview_paints_bottom_right_and_switches_tabs(self):
        form=Form(width=160,height=80,gadgets=[
            Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=2,y=2,width=130,height=65,
                tabs=[Gadget(kind='frame',name='A',label='First'),Gadget(kind='frame',name='B',label='Second')]),
            Gadget(name='Bottom',label='',background='2',x=145,y=78,width=8)])
        before=form.dumps();self.show_form(form)
        view=self.preview.form_view;tabs=self.preview.controls['Tabs'];bar=tabs.tabBar()
        source=bar.mapTo(self.preview.form_root,bar.tabRect(1).center())
        QTest.mouseClick(view.viewport(),Qt.LeftButton,Qt.NoModifier,view.mapFromScene(QPointF(source)))
        self.app.processEvents();self.assertEqual(tabs.currentIndex(),1)
        button=self.preview.controls['Bottom']
        source=button.mapTo(self.preview.form_root,QPoint(button.width()//2,button.height()//2))
        pixel=view.mapFromScene(QPointF(source))
        image=view.viewport().grab().toImage();color=image.pixelColor(pixel)
        self.assertGreater(color.red(),color.green()+50)
        self.assertGreater(color.red(),color.blue()+50)
        self.assertEqual(form.dumps(),before);self.assert_whole_form_visible()

    def test_fit_preserves_editor_zoom_pan_coordinates_and_history(self):
        with tempfile.TemporaryDirectory() as folder:
            w=Window(settings_path=Path(folder)/'settings.json')
            try:
                w.form=Form(width=180,height=100,gadgets=[Gadget(name='Run',x=160,y=90,width=8)])
                w.refresh();w.show();self.app.processEvents();w.choose_row(0)
                w.view.set_zoom(200);w.pan_center_button.click();self.app.processEvents()
                before=w.form.dumps();code=w.form.pml();center=w.view.mapToScene(w.view.viewport().rect().center())
                selected=w.selection_names();history=list(w.history);dirty=w.dirty
                w.runtime_action.setChecked(True);self.app.processEvents()
                self.assertLess(w.runtime_dialog.form_view.display_scale,1)
                self.assertEqual(w.form.dumps(),before);self.assertEqual(w.form.pml(),code)
                self.assertEqual(w.view.zoom_percent,200);self.assertEqual(w.selection_names(),selected)
                self.assertEqual(w.history,history);self.assertEqual(w.dirty,dirty)
                self.assertEqual(w.view.mapToScene(w.view.viewport().rect().center()),center)
            finally:w.dirty=False;w.close();self.app.processEvents()
