import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog

from e3d_designer.app import Window,Item
from e3d_designer.model import Form,Gadget
from e3d_designer.quick_editor import MiniProperties


class DirectionalDimensionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.folder.name)/'settings.json')
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.folder.cleanup()
    def load(self,gadgets,index=0):
        for gadget in gadgets:
            if gadget.kind=='line':gadget.label=''
        self.w.form=Form(gadgets=gadgets);self.w.selected=index;self.w.history.clear();self.w.future.clear()
        self.w.refresh();self.app.processEvents()
    def item(self,name=None):
        return next(item for item in self.w.scene.items() if isinstance(item,Item) and (name is None or item.gadget.name==name))
    def direction_key(self,kind):return 'orientation' if kind=='line' else 'slider_orientation'
    def vertical(self,kind):return 'VERT' if kind=='line' else 'VERTICAL'
    def thickness(self,kind):return 1 if kind=='line' else 3

    def test_legacy_projects_normalize_text_paragraph_line_and_slider_thickness(self):
        form=Form(gadgets=[Gadget(kind='paragraph',name='label'),Gadget(kind='line',name='horizontalLine',label='',width=12),
            Gadget(kind='line',name='verticalLine',label='',orientation='VERT',height=12),
            Gadget(kind='slider',name='horizontalSlider',width=12),
            Gadget(kind='slider',name='verticalSlider',slider_orientation='VERTICAL',height=12)])
        data=json.loads(form.dumps())
        for record in data['form']['gadgets']:
            record['width']=12;record['height']=5
            if record['name'].startswith('vertical'):record['width_ref']='horizontalLine'
        loaded=Form.loads(json.dumps(data))
        self.assertEqual([(g.width,g.height) for g in loaded.gadgets],[(12,1),(12,1),(1,5),(12,1),(3,5)])
        self.assertTrue(all(not g.width_ref for g in loaded.gadgets))
        self.assertEqual(Form.loads(loaded.dumps()).dumps(),loaded.dumps())

    def test_text_paragraph_has_one_line_and_only_width_control(self):
        self.load([Gadget(kind='paragraph',height=5)])
        self.assertEqual(self.w.form.gadgets[0].height,1)
        self.assertEqual(self.item().boundingRect().height(),26)
        self.assertEqual(set(self.item().handles()),{'width'})
        self.assertFalse(self.w.fields['height'].isEnabled());self.assertTrue(self.w.fields['width'].isEnabled())
        dialog=MiniProperties(self.w,self.w.form,0)
        self.assertNotIn('height',dialog.fields);dialog.reject();dialog.deleteLater()

    def test_line_and_slider_only_expose_length_handle_and_input(self):
        for kind in ('line','slider'):
            for vertical in (False,True):
                with self.subTest(kind=kind,vertical=vertical):
                    gadget=Gadget(kind=kind,width=12,height=10)
                    if vertical:setattr(gadget,self.direction_key(kind),self.vertical(kind))
                    self.load([gadget])
                    length='height' if vertical else 'width';fixed='width' if vertical else 'height'
                    self.assertEqual(set(self.item().handles()),{length})
                    self.assertTrue(self.w.fields[length].isEnabled());self.assertFalse(self.w.fields[fixed].isEnabled())
                    self.assertEqual(getattr(gadget,fixed),self.thickness(kind) if vertical else 1)
                    self.w.fields[fixed].setValue(20)
                    self.assertEqual(getattr(gadget,fixed),self.thickness(kind) if vertical else 1)

    def test_main_panel_orientation_swap_preserves_length_precision_and_undo(self):
        for kind in ('line','slider'):
            with self.subTest(kind=kind):
                self.load([Gadget(kind=kind,width=14.25,height=5)])
                key=self.direction_key(kind)
                self.w.fields[key].setCurrentText(self.vertical(kind))
                gadget=self.w.form.gadgets[0]
                self.assertEqual((gadget.width,gadget.height),(self.thickness(kind),14.25))
                self.assertEqual(set(self.item().handles()),{'height'})
                self.assertEqual(len(self.w.history),1)
                self.w.fields[key].setCurrentText('HORIZ' if kind=='line' else 'HORIZONTAL')
                self.assertEqual((gadget.width,gadget.height),(14.25,1))
                self.assertEqual(len(self.w.history),2)
                self.w.undo();self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(self.thickness(kind),14.25))
                self.w.redo();self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(14.25,1))

    def test_double_click_opens_direction_editor_and_commits_once(self):
        for kind in ('line','slider'):
            with self.subTest(kind=kind):
                self.load([Gadget(kind=kind,width=14.25)])
                key=self.direction_key(kind);target=self.vertical(kind)
                def edit(dialog):
                    dialog.fields[key].setCurrentIndex(dialog.fields[key].findData(target))
                    self.assertFalse(dialog.fields['width'].isEnabled());self.assertTrue(dialog.fields['height'].isEnabled())
                    dialog.accept();return QDialog.Accepted
                point=self.w.view.mapFromScene(self.item().sceneBoundingRect().center())
                with patch.object(MiniProperties,'exec',edit):
                    QTest.mouseDClick(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,point);self.app.processEvents()
                self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(self.thickness(kind),14.25))
                self.assertEqual(len(self.w.history),1)
                self.w.undo();self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(14.25,1))

    def test_mini_editor_retains_length_edits_when_switching_both_ways(self):
        for kind in ('line','slider'):
            with self.subTest(kind=kind):
                self.load([Gadget(kind=kind,width=12)])
                original=self.w.form.dumps();dialog=MiniProperties(self.w,self.w.form,0)
                key=self.direction_key(kind)
                dialog.fields['width'].setValue(17.6);dialog.fields[key].setCurrentIndex(1)
                self.assertEqual(dialog.fields['height'].value(),17.6)
                self.assertEqual(dialog.fields['width'].value(),self.thickness(kind))
                dialog.fields['height'].setValue(19.8);dialog.fields[key].setCurrentIndex(0)
                self.assertEqual(dialog.fields['width'].value(),19.8);self.assertEqual(dialog.fields['height'].value(),1)
                dialog.accept();self.assertIsNotNone(dialog.result_form)
                self.assertEqual((dialog.result_form.gadgets[0].width,dialog.result_form.gadgets[0].height),(19.8,1))
                self.assertEqual(self.w.form.dumps(),original);dialog.deleteLater()

    def test_cancelled_direction_edit_preserves_original_project(self):
        self.load([Gadget(kind='slider',width=14.25)])
        original=self.w.form.dumps();dialog=MiniProperties(self.w,self.w.form,0)
        dialog.fields['slider_orientation'].setCurrentIndex(1);dialog.reject()
        self.assertIsNone(dialog.result_form);self.assertEqual(self.w.form.dumps(),original);dialog.deleteLater()

    def test_rotating_referenced_length_resolves_value_and_undo_restores_reference(self):
        for kind in ('line','slider'):
            with self.subTest(kind=kind):
                self.load([Gadget(name='base',width=15.5,x=25),Gadget(kind=kind,name='directional',width_ref='base')],1)
                self.w.fields[self.direction_key(kind)].setCurrentText(self.vertical(kind))
                gadget=self.w.form.gadgets[1]
                self.assertEqual((gadget.width,gadget.height,gadget.width_ref),(self.thickness(kind),15.5,''))
                self.assertFalse(self.w.fields['width_ref'].isEnabled())
                self.w.undo();self.assertEqual(self.w.form.gadgets[1].width_ref,'base')
                self.assertEqual(self.w.form.geometry(self.w.form.gadgets[1])[2],15.5)

    def test_dragging_length_handle_preserves_thickness_and_creates_one_undo_step(self):
        for kind in ('line','slider'):
            for vertical in (False,True):
                with self.subTest(kind=kind,vertical=vertical):
                    kwargs={self.direction_key(kind):self.vertical(kind)} if vertical else {}
                    self.load([Gadget(kind=kind,width=10,height=10,**kwargs)])
                    length='height' if vertical else 'width';fixed='width' if vertical else 'height'
                    item=self.item();start=self.w.view.mapFromScene(item.mapToScene(item.handles()[length].center()))
                    end=start+(QPoint(0,52) if vertical else QPoint(45,0))
                    QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
                    QTest.mouseMove(self.w.view.viewport(),end,30)
                    QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
                    gadget=self.w.form.gadgets[0]
                    self.assertEqual(getattr(gadget,length),12 if vertical else 14.5)
                    self.assertEqual(getattr(gadget,fixed),self.thickness(kind) if vertical else 1)
                    self.assertEqual(len(self.w.history),1)
                    self.w.undo();self.assertEqual(getattr(self.w.form.gadgets[0],length),10)

    def test_vertical_palette_additions_keep_default_length_five(self):
        for action,kind in (('line_vert','line'),('slider_vert','slider')):
            with self.subTest(kind=kind):
                self.load([]);self.w.selected=None
                self.w.palette_actions[action].trigger()
                self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(self.thickness(kind),5))

    def test_locked_thickness_is_used_in_generated_code_after_direct_model_change(self):
        line=Gadget(kind='line',name='line',label='',width=12);line.height=7
        slider=Gadget(kind='slider',name='slider',slider_orientation='VERTICAL',height=12);slider.width=20
        code=Form(gadgets=[line,slider]).pml(normalize=False)
        self.assertIn("LINE .line AT X 2 Y 1 '' HORIZ WIDTH 12 HEIGHT 1",code)
        self.assertIn('VAL 50 WIDTH 3 HEIGHT 12',code)
