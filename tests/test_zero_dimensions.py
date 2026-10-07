import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window,Item,SX,SY
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget,change_orientation
from e3d_designer.quick_editor import MiniProperties


SOURCE="""Setup Form !!Demo Size 70 22 Dialog
Frame .Tabs Tabset At X 2 Y 2 '' Width 0.0
Frame .Tab1 '' Width 0.0
Text .State At X 0 Y 0 '' Call '!this.Work()' Width 0.0 Is String
Line .H At X 2 Y 2 '' Horiz Width 12 Height 0.0
Line .V At X 20 Y 0 '' Vert Width 0.0 Height 4
Exit
Frame .Tab2 '' Width 0.0
Button .Run At X 3 Y 3 'Run' Width 10
Exit
Exit
Exit
Show !!Demo
Define Method .DEFAULT()
!this.State.Val = 'Ready'
Endmethod
Define Method .Work()
$P 'Run'
Endmethod
"""


class ZeroDimensionsTests(unittest.TestCase):
    def test_mac_zero_dimensions_build_hidden_text_lines_and_auto_tabs(self):
        form=import_mac(SOURCE).form
        self.assertEqual(form.dumps(),import_mac(SOURCE,partial=True).form.dumps())
        state=form.named('State')
        self.assertTrue(state.hidden);self.assertEqual(form.geometry(state)[2],0)
        self.assertEqual((state.initial,state.callback,state.body),('Ready','Work',"$P 'Run'"))
        self.assertEqual((form.named('H').width,form.named('H').height),(12,0))
        self.assertEqual((form.named('V').width,form.named('V').height),(0,4))
        self.assertFalse(form.named('V').hidden)
        self.assertEqual(form.named('Tabs').width,21)
        self.assertEqual([form.named(n).width for n in ('Tab1','Tab2')],[21,21])
        code=form.pml(normalize=False)
        self.assertIn("TEXT .State AT X 0 Y 0 '' CALL '!this.Work()' WIDTH 0 IS STRING",code)
        self.assertIn("!this.State.val = 'Ready'",code)
        self.assertEqual(Form.loads(form.dumps()).pml(),form.pml())
        restored=import_mac(code).form
        self.assertTrue(restored.named('State').hidden)
        self.assertEqual(restored.named('State').body,state.body)
        self.assertEqual(restored.named('Tabs').width,21)

    def test_zero_page_width_uses_explicit_parent_width(self):
        form=import_mac(SOURCE.replace("'' Width 0.0\nFrame .Tab1","'' Width 40\nFrame .Tab1",1)).form
        self.assertEqual([form.named(n).width for n in ('Tabs','Tab1','Tab2')],[40,40,40])
        self.assertEqual(form.geometry(form.named('Tab1')),(0,0,40,5))
        self.assertTrue(any('WIDTH 0' in warning for warning in import_mac(SOURCE).warnings))

    def test_compact_auto_tabs_do_not_inherit_a_fourteen_unit_minimum(self):
        source="Setup Form !!Small Size 10 10 Dialog\nFrame .Tabs Tabset '' Width 0\nFrame .Page '' Width 0\nButton .Run 'Run' Width 2\nExit\nExit\nExit\nShow !!Small"
        form=import_mac(source).form
        self.assertEqual([form.named(n).width for n in ('Tabs','Page')],[3,3])
        form.validate()
        tabs=Gadget(kind='frame',name='Tabs',frame_style='TABSET',width=0,height=5,
                    tabs=[Gadget(kind='frame',name='Page',width=0)])
        form=Form(width=10,height=10,gadgets=[tabs,Gadget(name='Run',parent='Page',x=0,y=0,width=2)])
        self.assertEqual(tabs.width,3);form.validate()

    def test_tab_zero_width_json_is_resolved_without_hiding_pages(self):
        tabs=Gadget(kind='frame',name='Tabs',frame_style='TABSET',width=0,height=10,
                    tabs=[Gadget(kind='frame',name='Page',width=0,height=10)])
        form=Form(gadgets=[tabs,Gadget(name='Run',parent='Page',x=20,width=10)])
        self.assertEqual((tabs.width,tabs.tabs[0].width),(31,31))
        self.assertFalse(tabs.hidden);self.assertFalse(tabs.tabs[0].hidden)
        form.validate()
        raw=json.loads(form.dumps());raw['form']['gadgets'][0]['width']=0
        raw['form']['gadgets'][0]['tabs'][0]['width']=0
        self.assertEqual(Form.loads(json.dumps(raw)).named('Tabs').width,31)

    def test_width_zero_supported_gadgets_round_trip_and_keep_processing(self):
        for kind in ('button','text','paragraph','list','combo','textpane','view','commandline','container','selector','slider','option'):
            with self.subTest(kind=kind):
                gadget=Gadget(kind=kind,name='State',width=0,option_style='GADGET')
                form=Form(gadgets=[gadget]);code=form.pml(normalize=False)
                self.assertTrue(gadget.hidden);self.assertEqual(form.geometry(gadget)[2],0)
                self.assertIn('WIDTH 0',code)
                self.assertTrue(import_mac(code).form.named('State').hidden)
                self.assertTrue(Form.loads(form.dumps()).named('State').hidden)

    def test_hidden_width_restores_saved_size_and_clone_keeps_state(self):
        form=Form(gadgets=[Gadget(kind='text',name='State',width=23.5,hidden=True,initial='Value')])
        restored=Form.loads(form.dumps());gadget=restored.named('State')
        self.assertEqual(gadget.width,23.5);self.assertTrue(gadget.hidden)
        cloned,index=clone_subtree(Form(),restored,0)
        self.assertTrue(cloned.gadgets[index].hidden);self.assertEqual(cloned.gadgets[index].width,23.5)
        gadget.hidden=False
        self.assertIn('WIDTH 23.5',restored.pml(normalize=False));self.assertEqual(restored.geometry(gadget)[2],23.5)

    def test_hidden_width_reference_is_suspended_and_restored(self):
        form=Form(gadgets=[Gadget(name='Base',width=20),
                           Gadget(kind='text',name='State',width_ref='Base',hidden=True),
                           Gadget(name='Next',layout_mode='RELATIVE',xref='State',yref='State',xedge='XMAX',xoffset=1)])
        self.assertEqual(form.geometry(form.named('State'))[2],0)
        self.assertEqual(form.geometry(form.named('Next'))[0],3)
        self.assertIn("TEXT .State AT X 2 Y 1 'Run' WIDTH 0",form.pml(normalize=False))
        form.named('State').hidden=False
        self.assertEqual(form.geometry(form.named('State'))[2],20)
        self.assertIn('WIDTH.Base',form.pml(normalize=False))

    def test_line_rotation_preserves_length_and_zero_thickness(self):
        gadget=Gadget(kind='line',label='',width=12.5,height=0)
        change_orientation(gadget,'VERT')
        self.assertEqual((gadget.width,gadget.height),(0,12.5))
        change_orientation(gadget,'HORIZ')
        self.assertEqual((gadget.width,gadget.height),(12.5,0))
        Form(gadgets=[gadget]).validate()

    def test_hidden_slider_rotation_uses_saved_length(self):
        gadget=Gadget(kind='slider',hidden=True,width=12.5)
        change_orientation(gadget,'VERTICAL',(0,1))
        self.assertEqual((gadget.width,gadget.height),(3,12.5))
        change_orientation(gadget,'HORIZONTAL',(0,12.5))
        self.assertEqual((gadget.width,gadget.height),(12.5,1))
        self.assertTrue(gadget.hidden);Form(gadgets=[gadget]).validate()

    def test_nested_auto_tabsets_resolve_from_inside_out(self):
        outer=Gadget(kind='frame',name='Outer',frame_style='TABSET',width=0,height=15)
        page=Gadget(kind='frame',name='Page',parent='Outer',width=0,height=15)
        inner=Gadget(kind='frame',name='Inner',parent='Page',frame_style='TABSET',x=2,y=2,width=0,height=10)
        inner_page=Gadget(kind='frame',name='InnerPage',parent='Inner',width=0,height=10)
        run=Gadget(name='Run',parent='InnerPage',x=20,width=10)
        form=Form(gadgets=[outer,page,inner,inner_page,run]);form.validate()
        self.assertEqual([form.named(n).width for n in ('Outer','Page','Inner','InnerPage')],[34,34,31,31])
        self.assertEqual(Form.loads(form.dumps()).dumps(),form.dumps())

    def test_invalid_sizes_and_hidden_flags_still_fail(self):
        for gadget in (Gadget(width=-1),Gadget(kind='text',height=0),
                       Gadget(kind='line',label='',width=0),
                       Gadget(kind='line',label='',orientation='VERT',height=0),
                       Gadget(kind='line',label='',height=-1),Gadget(hidden='yes'),
                       Gadget(kind='frame',hidden=True),Gadget(kind='rtoggle',hidden=True)):
            with self.subTest(gadget=gadget),self.assertRaises(ValueError):Form(gadgets=[gadget]).validate()


class ZeroDimensionsGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.directory=Path(self.folder.name)
        self.w=Window(settings_path=self.directory/'settings.json');self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.folder.cleanup()
    def load(self,form):
        self.w.form=form;self.w.selected=0;self.w.history.clear();self.w.future.clear();self.w.refresh();self.app.processEvents()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)

    def test_hidden_checkbox_keeps_initial_and_command_and_undo_restores_width(self):
        form=Form(gadgets=[Gadget(kind='text',name='State',width=23.5,initial='Value',command='$P !this.State.Val')])
        self.load(form);original=form.dumps()
        self.w.hidden.setChecked(True)
        self.assertTrue(self.w.form.named('State').hidden)
        self.assertEqual(self.w.fields['width'].value(),0);self.assertFalse(self.w.fields['width'].isEnabled())
        self.assertIn('Width 0',self.w.code.toPlainText());self.assertIn('非表示',self.w.objects.item(0).text(0))
        self.assertEqual(self.w.validation_error,'');self.assertEqual(self.item('State').handles(),{})
        self.assertEqual(len(self.w.history),1)
        self.w.hidden.setChecked(False)
        self.assertEqual(self.w.fields['width'].value(),23.5);self.assertTrue(self.w.fields['width'].isEnabled())
        self.assertEqual(self.w.form.dumps(),original)
        self.w.undo();self.assertTrue(self.w.form.named('State').hidden)
        self.w.undo();self.assertEqual(self.w.form.dumps(),original)

    def test_mini_editor_hide_restore_accept_and_cancel_are_atomic(self):
        self.load(Form(gadgets=[Gadget(kind='text',name='State',width=17.5)]))
        original=self.w.form.dumps();dialog=MiniProperties(self.w,self.w.form,0)
        dialog.fields['width'].setValue(19.8);dialog.hidden.setChecked(True)
        self.assertEqual(dialog.fields['width'].value(),0);self.assertFalse(dialog.fields['width'].isEnabled())
        dialog.hidden.setChecked(False);self.assertEqual(dialog.fields['width'].value(),19.8)
        dialog.hidden.setChecked(True);dialog.accept()
        self.assertTrue(dialog.result_form.named('State').hidden)
        self.assertEqual(dialog.result_form.named('State').width,19.8)
        self.assertEqual(self.w.form.dumps(),original);dialog.deleteLater()
        dialog=MiniProperties(self.w,self.w.form,0);dialog.hidden.setChecked(True);dialog.reject()
        self.assertIsNone(dialog.result_form);self.assertEqual(self.w.form.dumps(),original);dialog.deleteLater()

    def test_hidden_unselected_draws_nothing_and_selection_does_not_draw_control(self):
        self.load(Form(gadgets=[Gadget(kind='text',name='State',hidden=True)]));item=self.item('State')
        for selected in (False,True):
            item.setSelected(selected);image=QImage(100,60,QImage.Format_ARGB32);image.fill(Qt.transparent)
            painter=QPainter(image);painter.translate(10,10);item.paint(painter,None);painter.end()
            self.assertEqual(image.pixelColor(30,20).alpha(),0)
            if not selected:
                self.assertTrue(item.shape().isEmpty())
                self.assertTrue(all(image.pixelColor(x,y).alpha()==0 for y in range(60) for x in range(100)))
            else:self.assertFalse(item.shape().isEmpty())
            self.assertEqual(item.handles(),{})

    def test_line_at_zero_extent_draws_on_its_coordinate_and_remains_selectable(self):
        for direction in ('HORIZ','VERT'):
            with self.subTest(direction=direction):
                self.load(Form(gadgets=[Gadget(kind='line',name='Line',label='',orientation=direction,width=12,height=5)]))
                item=self.item('Line');item.setSelected(False)
                image=QImage(180,180,QImage.Format_ARGB32);image.fill(Qt.transparent)
                painter=QPainter(image);painter.translate(10,10);item.paint(painter,None);painter.end()
                self.assertGreater(image.pixelColor(40,10).alpha() if direction=='HORIZ' else image.pixelColor(10,40).alpha(),0)
                self.assertEqual(image.pixelColor(40,15).alpha() if direction=='HORIZ' else image.pixelColor(15,40).alpha(),0)
                self.assertGreater(item.shape().boundingRect().width(),0);self.assertGreater(item.shape().boundingRect().height(),0)
                fixed='height' if direction=='HORIZ' else 'width'
                self.assertEqual(self.w.fields[fixed].value(),0);self.assertFalse(self.w.fields[fixed].isEnabled())
                self.assertFalse(self.w.hidden.isVisible())

    def test_hidden_text_can_be_selected_moved_and_deleted_from_tree(self):
        self.load(Form(gadgets=[Gadget(kind='text',name='State',hidden=True),Gadget(name='Run',x=20)]))
        self.w.choose_row(1);self.w.objects.setCurrentRow(0);self.app.processEvents()
        self.assertEqual(self.w.selected,0)
        self.assertTrue(self.item('State').isSelected())
        self.w.view.setFocus();QTest.keyClick(self.w.view,Qt.Key_Right)
        self.assertEqual(self.w.form.named('State').x,2.1);self.assertEqual(self.w.validation_error,'')
        self.w.undo();self.assertEqual(self.w.form.named('State').x,2)
        self.w.choose_row(0)
        self.w.delete();self.assertIsNone(self.w.form.named('State'))
        self.w.undo();self.assertTrue(self.w.form.named('State').hidden)

    def test_gui_zero_mac_open_save_reload_and_export(self):
        source=self.directory/'zero.mac';data=SOURCE.replace('\n','\r\n').encode('cp932');source.write_bytes(data)
        with patch('e3d_designer.app.QMessageBox.warning') as warning,patch('e3d_designer.app.QMessageBox.information'):
            self.assertTrue(self.w.open_design(source,confirmed=True))
            self.assertEqual(self.w.validation_error,'');self.assertTrue(self.w.form.named('State').hidden)
            self.w.path=self.directory/'zero.json';self.assertTrue(self.w.save())
            self.assertTrue(self.w.open_design(self.w.path,confirmed=True))
            export=self.directory/'export.mac'
            with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(export),'')):self.w.export()
            restored=import_mac(export.read_bytes().decode('cp932')).form
            self.assertTrue(restored.named('State').hidden);self.assertEqual(restored.named('State').initial,'Ready')
            self.assertEqual(restored.named('V').width,0);warning.assert_not_called()
        self.assertEqual(source.read_bytes(),data)

    def test_hidden_pixmap_keeps_intrinsic_size_and_zero_width_in_mini_editor(self):
        path=self.directory/'picture.png';image=QImage(100,52,QImage.Format_ARGB32);image.fill(Qt.red);self.assertTrue(image.save(str(path)))
        self.load(Form(gadgets=[Gadget(kind='paragraph',name='Picture',display_mode='PIXMAP',pixmap_path=str(path),hidden=True)]))
        self.assertEqual((self.w.form.named('Picture').width,self.w.form.named('Picture').height),(100,52))
        self.assertEqual(self.w.fields['width'].value(),0)
        dialog=MiniProperties(self.w,self.w.form,0);dialog.preview_image_dimensions()
        self.assertEqual(dialog.fields['width'].value(),0);dialog.accept()
        self.assertIsNotNone(dialog.result_form);code=dialog.result_form.pml(normalize=False)
        self.assertIn('WIDTH 0 HEIGHT 52',code)
        self.assertTrue(import_mac(code).form.named('Picture').hidden);dialog.deleteLater()


if __name__=='__main__':unittest.main()
