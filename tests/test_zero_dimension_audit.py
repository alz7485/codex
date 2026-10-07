import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication

from e3d_designer.app import Window,Item
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget
from e3d_designer.quick_editor import MiniProperties


def reference_form(own=False):
    return Form(height=40,gadgets=[Gadget(name='Base',width=25.5,hidden=not own,x=30),
        Gadget(kind='slider',name='Follow',width=12.5,hidden=own,width_ref='Base')])


class ZeroDimensionAuditTests(unittest.TestCase):
    def test_hidden_reference_chain_preserves_callbacks_data_and_source(self):
        form=Form(gadgets=[Gadget(kind='text',name='Base',width=20,hidden=True),
            Gadget(kind='text',name='Follow',width_ref='Base',initial='Ready',command='$P !this.Follow.Val'),
            Gadget(kind='list',name='Rows',width_ref='Follow',items=['One'],item_values=['1'])])
        original=form.dumps();code=form.pml(normalize=False)
        for name in ('Base','Follow','Rows'):
            self.assertTrue(form.is_hidden(form.named(name)));self.assertEqual(form.geometry(form.named(name))[2],0)
        self.assertFalse(form.named('Follow').hidden)
        self.assertIn('WIDTH.Base',code);self.assertIn('WIDTH.Follow',code)
        self.assertIn("!this.Follow.val = 'Ready'",code)
        restored=import_mac(code).form
        self.assertTrue(restored.is_hidden(restored.named('Rows')))
        self.assertEqual(restored.named('Follow').command,'$P !this.Follow.Val')
        self.assertEqual(restored.named('Rows').item_values,['1'])
        self.assertEqual(import_mac(code,partial=True).form.dumps(),restored.dumps())
        self.assertEqual(Form.loads(original).dumps(),original);self.assertEqual(form.dumps(),original)
        form.named('Base').hidden=False
        self.assertEqual(form.geometry(form.named('Rows'))[2],20)
        self.assertFalse(form.is_hidden(form.named('Follow')))

    def test_restored_size_and_display_width_are_read_only(self):
        for own in (False,True):
            with self.subTest(own=own):
                form=reference_form(own);original=form.dumps();g=form.named('Follow')
                self.assertEqual(form.restored_size(g),(25.5,1));self.assertEqual(form.display_width(g),0)
                self.assertEqual(form.dumps(),original)
                form.named('Base').hidden=False;g.hidden=False
                self.assertEqual(form.display_width(g),25.5);self.assertEqual(g.width,12.5)

    def test_detached_explicit_hidden_child_keeps_position_and_saved_width(self):
        form=Form(gadgets=[Gadget(kind='frame',name='Group',x=20,y=3,width=30,height=10),
                           Gadget(kind='text',name='State',parent='Group',x=2,y=1,width=18.5,hidden=True,initial='Value')])
        original=form.dumps();cloned,index=clone_subtree(Form(),form,1);g=cloned.gadgets[index]
        self.assertEqual((g.x,g.y,g.width,g.height),(22,4,18.5,1))
        self.assertTrue(g.hidden);self.assertEqual(g.initial,'Value');self.assertEqual(g.parent,'')
        self.assertEqual(cloned.geometry(g)[2],0);self.assertEqual(form.dumps(),original)

    def test_missing_reference_copy_freezes_saved_width_and_hidden_state(self):
        for own in (False,True):
            with self.subTest(own=own):
                form=reference_form(own);original=form.dumps()
                cloned,index=clone_subtree(Form(),form,1);g=cloned.gadgets[index]
                self.assertEqual(g.width,25.5);self.assertTrue(g.hidden);self.assertEqual(g.width_ref,'')
                g.hidden=False;self.assertEqual(cloned.geometry(g)[2],25.5)
                self.assertEqual(form.dumps(),original)

    def test_subtree_copy_keeps_live_hidden_reference(self):
        form=Form(gadgets=[Gadget(kind='frame',name='Group',width=40,height=10),
            Gadget(kind='text',name='Base',parent='Group',hidden=True,width=20),
            Gadget(kind='text',name='Follow',parent='Group',width_ref='Base',x=15)])
        cloned,index=clone_subtree(Form(),form,0)
        base,follow=cloned.children(cloned.gadgets[index].name)
        self.assertTrue(base.hidden);self.assertFalse(follow.hidden)
        self.assertEqual(follow.width_ref,base.name);self.assertTrue(cloned.is_hidden(follow))
        base.hidden=False;self.assertEqual(cloned.geometry(follow)[2],20)

    def test_rotation_freezes_reference_length_and_retains_hidden_state(self):
        for own in (False,True):
            with self.subTest(own=own):
                form=reference_form(own);g=form.named('Follow');original=form.dumps()
                form.rotate_gadget(g,'HORIZONTAL');self.assertEqual(form.dumps(),original)
                form.rotate_gadget(g,'VERTICAL')
                self.assertEqual((g.width,g.height,g.width_ref),(3,25.5,''));self.assertTrue(g.hidden)
                form.rotate_gadget(g,'HORIZONTAL')
                self.assertEqual((g.width,g.height),(25.5,1));self.assertTrue(g.hidden)
                g.hidden=False;form.validate();self.assertEqual(form.geometry(g)[2],25.5)

    def test_suspended_missing_or_cyclic_width_reference_can_be_detached(self):
        for references in (('Missing',''),('B','A')):
            with self.subTest(references=references):
                form=Form(gadgets=[Gadget(kind='text',name='A',hidden=True,width=17.5,width_ref=references[0]),
                                   Gadget(kind='text',name='B',hidden=True,width_ref=references[1])])
                form.validate();cloned,index=clone_subtree(Form(),form,0)
                self.assertEqual(cloned.gadgets[index].width,17.5)
                self.assertTrue(cloned.gadgets[index].hidden)
        invalid=Form(gadgets=[Gadget(width_ref='Missing')])
        with self.assertRaises(ValueError):invalid.restored_size(invalid.gadgets[0])
        with self.assertRaises(ValueError):invalid.validate()

    def test_auto_tab_width_with_omitted_page_width_fits_compact_form(self):
        source="Setup Form !!Small Size 10 10 Dialog\nFrame .Tabs Tabset '' Width 0\nFrame .Page ''\nButton .Run 'Run' Width 2\nExit\nExit\nExit\nShow !!Small"
        form=import_mac(source).form
        self.assertEqual(form.named('Tabs').width,3);self.assertEqual(form.geometry(form.named('Page'))[2],3)
        self.assertEqual(import_mac(source,partial=True).form.dumps(),form.dumps())
        self.assertEqual(import_mac(form.pml()).form.named('Tabs').width,3)


class ZeroDimensionAuditGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.directory=Path(self.folder.name)
        self.w=Window(settings_path=self.directory/'settings.json');self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.folder.cleanup()
    def load(self,form,index=0):
        self.w.form=form;self.w.selected=index;self.w.history.clear();self.w.future.clear();self.w.refresh();self.app.processEvents()
    def item(self,name):return next(i for i in self.w.scene.items() if isinstance(i,Item) and i.gadget.name==name)

    def test_reference_hidden_render_fields_edits_and_unhide(self):
        form=Form(gadgets=[Gadget(kind='text',name='Base',width=20),
                           Gadget(kind='text',name='Follow',width=12.5,width_ref='Base',x=30,initial='Value')])
        self.load(form);self.w.hidden.setChecked(True);self.w.choose_row(1)
        self.assertEqual(self.w.validation_error,'');self.assertEqual(self.w.fields['width'].value(),0)
        self.assertFalse(self.w.fields['width'].isEnabled());self.assertFalse(self.w.hidden.isChecked())
        self.assertIn('幅参照',self.w.objects.item(1).text(0));self.assertIn('幅参照元',self.w.fields['width'].toolTip())
        item=self.item('Follow');item.setSelected(False)
        image=QImage(100,60,QImage.Format_ARGB32);image.fill(Qt.transparent)
        painter=QPainter(image);item.paint(painter,None);painter.end()
        self.assertTrue(all(image.pixelColor(x,y).alpha()==0 for y in range(60) for x in range(100)))
        self.assertTrue(item.shape().isEmpty());self.assertEqual(item.handles(),{})
        self.w.choose_row(1)
        self.w.fields['label'].setText('Edited');self.w.update_gadget()
        follow=self.w.form.named('Follow')
        self.assertEqual(follow.label,'Edited')
        self.assertEqual((follow.width,follow.width_ref,follow.initial),(12.5,'Base','Value'))
        self.w.choose_row(0);self.w.hidden.setChecked(False);self.w.choose_row(1)
        self.assertEqual(self.w.fields['width'].value(),20);self.assertFalse(self.w.form.is_hidden(follow))
        self.assertAlmostEqual(self.w.form.geometry(follow)[2],20)
        # The entry keeps WIDTH 20; the visible tag and native frame add pixels.
        self.w.runtime_action.setChecked(True);self.app.processEvents()
        self.assertEqual(self.item('Follow').boundingRect().size().toSize(),self.w.runtime_dialog.controls['Follow'].size())
        self.w.undo();self.assertTrue(self.w.form.is_hidden(self.w.form.named('Follow')))

    def test_main_and_mini_rotation_keep_hidden_reference_length(self):
        for own in (False,True):
            for editor in ('main','mini'):
                with self.subTest(own=own,editor=editor):
                    form=reference_form(own);self.load(form,1);original=form.dumps()
                    if editor=='main':self.w.fields['slider_orientation'].setCurrentText('VERTICAL')
                    else:
                        def edit(dialog):
                            dialog.fields['slider_orientation'].setCurrentIndex(1);dialog.accept();return dialog.result()
                        with patch.object(MiniProperties,'exec',edit):self.w.edit_object_properties('Follow')
                    g=self.w.form.named('Follow')
                    self.assertEqual((g.width,g.height,g.width_ref),(3,25.5,''));self.assertTrue(g.hidden)
                    self.assertEqual(self.w.validation_error,'');self.assertEqual(len(self.w.history),1)
                    self.w.undo();self.assertEqual(self.w.form.dumps(),original)

    def test_mini_reference_width_fields_follow_hidden_source_without_mutation(self):
        form=Form(gadgets=[Gadget(name='Base',width=20,hidden=True),Gadget(kind='text',name='Follow',width_ref='Base',width=12.5)])
        original=form.dumps();dialog=MiniProperties(self.w,form,1)
        self.assertEqual(dialog.fields['width'].value(),0)
        dialog.hidden.setChecked(True);dialog.hidden.setChecked(False)
        self.assertEqual(dialog.fields['width'].value(),0);dialog.accept()
        self.assertIsNotNone(dialog.result_form);self.assertEqual(dialog.result_form.dumps(),original)
        self.assertEqual(form.dumps(),original);dialog.deleteLater()
        form.named('Base').hidden=False;original=form.dumps();dialog=MiniProperties(self.w,form,1)
        self.assertEqual(dialog.fields['width'].value(),20);dialog.accept()
        self.assertEqual(dialog.result_form.dumps(),original);dialog.deleteLater()

    def test_tree_and_canvas_reparent_preserve_hidden_saved_size_and_undo(self):
        for method in ('tree','canvas'):
            for own in (False,True):
                with self.subTest(method=method,own=own):
                    form=Form(gadgets=[Gadget(kind='frame',name='Group',x=20,y=3,width=30,height=10),
                        Gadget(kind='text',name='Base',width=18.5,hidden=not own,x=45),
                        Gadget(kind='text',name='State',width=12.5,hidden=own,width_ref='Base')])
                    self.load(form,2);original=form.dumps()
                    if method=='tree':self.w.move_tree_gadget(2,'Group')
                    else:self.w.move_committed(copy.deepcopy(form),'State',22,4)
                    self.app.processEvents();g=self.w.form.named('State')
                    self.assertEqual(g.parent,'Group');self.assertTrue(g.hidden)
                    self.assertEqual((g.width,g.width_ref),(18.5,''));self.assertEqual(self.w.validation_error,'')
                    self.assertEqual(len(self.w.history),1);self.w.undo();self.assertEqual(self.w.form.dumps(),original)

    def test_copy_paste_detached_hidden_text_preserves_data_and_undo(self):
        self.load(Form(gadgets=[Gadget(kind='frame',name='Group',x=20,y=3,width=30,height=10),
            Gadget(kind='text',name='State',parent='Group',width=18.5,hidden=True,initial='Ready',command='$P !this.State.Val')]),1)
        source=self.w.form.dumps();self.assertTrue(self.w.copy_gadget());self.w.new()
        self.w.paste_gadget();g=self.w.form.gadgets[self.w.selected]
        self.assertEqual((g.width,g.parent,g.initial),(18.5,'','Ready'));self.assertTrue(g.hidden)
        self.assertIn(g.name+'.Val',g.command);self.assertEqual(self.w.validation_error,'')
        self.w.undo();self.assertEqual(self.w.form.gadgets,[])
        self.assertTrue(Form.loads(source).named('State').hidden)

    def test_gui_mac_hidden_reference_import_json_and_export(self):
        form=Form(gadgets=[Gadget(kind='text',name='Base',hidden=True),
                           Gadget(kind='text',name='Follow',width_ref='Base',initial='Ready')])
        source=self.directory/'source.mac';data=form.pml().replace('\n','\r\n').encode('cp932');source.write_bytes(data)
        with patch('e3d_designer.app.QMessageBox.warning') as warning,patch('e3d_designer.app.QMessageBox.information'):
            self.assertTrue(self.w.open_design(source,confirmed=True));self.assertEqual(self.w.validation_error,'')
            self.w.path=self.directory/'design.json';self.assertTrue(self.w.save())
            self.assertTrue(self.w.open_design(self.w.path,confirmed=True))
            self.assertTrue(self.w.form.is_hidden(self.w.form.named('Follow')))
            output=self.directory/'export.mac'
            with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):self.w.export()
            restored=import_mac(output.read_bytes().decode('cp932')).form
            self.assertTrue(restored.is_hidden(restored.named('Follow')))
            self.assertEqual(restored.named('Follow').initial,'Ready');warning.assert_not_called()
        self.assertEqual(source.read_bytes(),data)


if __name__=='__main__':unittest.main()
