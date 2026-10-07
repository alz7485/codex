import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication,QPushButton,QComboBox,QLabel,QGroupBox,
    QTabWidget,QCheckBox,QRadioButton,QFrame,QTableWidget,QSlider,QGraphicsView)
from e3d_designer.app import Window
from e3d_designer.model import Form,Gadget,Menu,MenuItem,CHAR_WIDTH,LINE_HEIGHT
from e3d_designer.runtime_preview import RuntimePreview
from e3d_designer.colors import preview_color


class RuntimePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.preview=RuntimePreview()
    def tearDown(self):
        self.preview.close();self.preview.deleteLater();self.app.processEvents();self.temp.cleanup()
    def show_form(self,form,**kwargs):
        self.preview.set_form(form,**kwargs);self.preview.show();self.app.processEvents()
        return self.preview.controls

    def test_native_controls_without_editor_names_or_graphics_and_no_mutation(self):
        form=Form(title='Equipment',gadgets=[
            Gadget(name='InternalButton',label='Run',command='SAVEWORK'),
            Gadget(kind='text',name='InternalText',label='Name',initial='P-101',y=3,width=30),
            Gadget(kind='option',name='InternalChoice',label='Type',items=['Pipe','Pump'],initial='2',y=5),
            Gadget(kind='paragraph',name='InternalLabel',label='<b>Literal text</b>',y=7,width=25)])
        before=form.dumps();code=form.pml();controls=self.show_form(form)
        self.assertIsInstance(controls['InternalButton'],QPushButton)
        self.assertEqual(controls['InternalButton'].text(),'Run')
        self.assertEqual(controls['InternalText'].entry.text(),'P-101')
        self.assertEqual(controls['InternalChoice'].entry.currentText(),'Pump')
        self.assertEqual(controls['InternalLabel'].textFormat(),Qt.PlainText)
        self.assertEqual(self.preview.windowTitle(),'Equipment')
        self.assertFalse(self.preview.findChildren(QGraphicsView))
        visible_text=[widget.text() for widget in self.preview.findChildren(QLabel)]
        self.assertFalse(any('Internal' in text for text in visible_text))
        controls['InternalButton'].click();controls['InternalChoice'].entry.setCurrentIndex(0)
        self.assertEqual(form.dumps(),before);self.assertEqual(form.pml(),code)

    def test_menu_bar_titles_and_items_have_no_execution_or_internal_names(self):
        form=Form(menus=[Menu(name='InternalMenu',label='File',items=[MenuItem('Run','SAVEWORK')]),
            Menu(name='HiddenMenu',label='Hidden',on_bar=False),Menu(name='Popup',popup=True)])
        before=form.dumps();self.show_form(form)
        self.assertEqual([a.text() for a in self.preview.menu_bar.actions()],['File'])
        action=self.preview.menu_bar.actions()[0].menu().actions()[0]
        self.assertEqual(action.text(),'Run');action.trigger()
        self.assertEqual(form.dumps(),before)
        self.assertGreater(self.preview.menu_bar.height(),0)

    def test_tab_pages_nested_frames_and_local_coordinates(self):
        form=Form(gadgets=[Gadget(kind='frame',name='Tabs',frame_style='TABSET',x=3,y=2,width=40,height=15,tabs=[
            Gadget(kind='frame',name='PageA',label='First'),Gadget(kind='frame',name='PageB',label='Second')]),
            Gadget(kind='frame',name='Group',parent='PageB',label='Group',x=2,y=2,width=30,height=10),
            Gadget(name='Inside',parent='Group',x=1,y=1,label='Inside')])
        active={'tabs':'pageb'};before=form.dumps();controls=self.show_form(form,active_pages=active)
        tabs=controls['Tabs'];self.assertIsInstance(tabs,QTabWidget)
        self.assertEqual(tabs.currentIndex(),1);self.assertEqual(tabs.tabText(1),'Second')
        self.assertIs(tabs.widget(1),controls['PageB'])
        self.assertIs(controls['Inside'].parent(),controls['Group'])
        self.assertIsInstance(controls['Group'],QGroupBox)
        self.assertEqual(controls['Inside'].pos().toTuple(),(CHAR_WIDTH,LINE_HEIGHT))
        self.assertEqual(controls['Group'].pos().toTuple(),(2*CHAR_WIDTH,2*LINE_HEIGHT))
        tabs.setCurrentIndex(0)
        self.assertEqual(form.dumps(),before);self.assertEqual(active,{'tabs':'pageb'})

    def test_pairs_option_uses_native_content_size_while_gadget_option_uses_width(self):
        form=Form(gadgets=[Gadget(kind='option',name='Pairs',label='Choice',items=['Longer option content'],width=3),
            Gadget(kind='option',name='GadgetOption',option_style='GADGET',label='Choice',items=['Item'],width=20,y=3)])
        before=form.dumps();controls=self.show_form(form)
        self.assertEqual(controls['Pairs'].width(),controls['Pairs'].sizeHint().width())
        self.assertGreater(controls['Pairs'].width(),3*CHAR_WIDTH)
        self.assertEqual(controls['GadgetOption'].width(),20*CHAR_WIDTH)
        self.assertEqual(form.dumps(),before)

    def test_explicit_width_and_combo_tagwid_scroll_are_not_mutated(self):
        form=Form(gadgets=[Gadget(name='Button',width=12.5),Gadget(kind='combo',name='Combo',y=3,width=24,
            label='Choice',combo_tagwid='6.5',combo_scroll='7',items=['A','B'])])
        before=form.dumps();controls=self.show_form(form)
        self.assertEqual(controls['Button'].width(),125)
        self.assertEqual(controls['Combo'].width(),240)
        self.assertEqual(controls['Combo'].findChild(QLabel).width(),65)
        self.assertEqual(controls['Combo'].entry.maxVisibleItems(),7)
        self.assertEqual(form.dumps(),before)

    def test_boolean_initials_radio_group_and_multiple_list_selection(self):
        form=Form(gadgets=[Gadget(kind='toggle',name='Check',initial='TRUE'),
            Gadget(kind='frame',name='Group',y=3,width=30,height=5),
            Gadget(kind='rtoggle',name='RadioA',parent='Group',x=1,y=1,initial='FALSE'),
            Gadget(kind='rtoggle',name='RadioB',parent='Group',x=1,y=3,initial='TRUE'),
            Gadget(kind='list',name='List',x=35,items=['A','B','C'],selection_mode='MULTIPLE',initial='1,3',height=5)])
        controls=self.show_form(form)
        self.assertIsInstance(controls['Check'],QCheckBox);self.assertTrue(controls['Check'].isChecked())
        self.assertIsInstance(controls['RadioB'],QRadioButton);self.assertTrue(controls['RadioB'].isChecked())
        self.assertFalse(controls['RadioA'].isChecked())
        self.assertEqual([item.text() for item in controls['List'].selectedItems()],['A','C'])

    def test_table_headings_rows_and_multiple_initial_selection(self):
        form=Form(gadgets=[Gadget(kind='list',name='Table',list_mode='TABLE',headings=['Name','Value'],
            rows=[['A','1'],['B','2'],['C','3']],selection_mode='MULTIPLE',initial='1,3',height=8,width=30)])
        control=self.show_form(form)['Table'];self.assertIsInstance(control,QTableWidget)
        self.assertEqual(control.horizontalHeaderItem(1).text(),'Value');self.assertEqual(control.item(1,1).text(),'2')
        self.assertEqual([index.row() for index in control.selectionModel().selectedRows()],[0,2])

    def test_paragraph_is_plain_and_transparent_without_background(self):
        form=Form(gadgets=[Gadget(kind='paragraph',name='Plain',label='Label',initial='Initial'),
            Gadget(kind='paragraph',name='Colored',background='4',y=3),
            Gadget(kind='paragraph',name='UnknownColor',background='999',y=5)])
        controls=self.show_form(form)
        self.assertFalse(controls['Plain'].autoFillBackground());self.assertEqual(controls['Plain'].text(),'Initial')
        self.assertTrue(controls['Colored'].autoFillBackground())
        self.assertEqual(controls['Colored'].palette().window().color().name(),preview_color('4'))
        self.assertFalse(controls['UnknownColor'].autoFillBackground())

    def test_hidden_parts_are_not_drawn_and_negative_children_clip_to_parent(self):
        form=Form(gadgets=[Gadget(kind='text',name='Hidden',hidden=True),
            Gadget(kind='frame',name='Group',width=20,height=8,x=5,y=2),
            Gadget(kind='paragraph',name='Negative',parent='Group',label='Visible',background='4',x=-2,y=2,width=12)])
        controls=self.show_form(form)
        self.assertNotIn('Hidden',controls);self.assertLess(controls['Negative'].x(),0)
        group=controls['Group'];child=controls['Negative']
        self.assertEqual(child.visibleRegion().boundingRect().left(),2*CHAR_WIDTH)
        image=self.preview.surface.grab().toImage()
        self.assertNotEqual(image.pixelColor(group.x()-5,group.y()+child.y()+5).name(),preview_color('4'))

    def test_native_pixmap_dimensions_not_scaled_by_pml_character_size(self):
        path=self.folder/'image.png';image=QImage(45,30,QImage.Format_RGB32);image.fill(Qt.red);image.save(str(path))
        form=Form(gadgets=[Gadget(kind='paragraph',name='Image',display_mode='PIXMAP',pixmap_path=path.name,width=45,height=30)])
        control=self.show_form(form,image_directories=[self.folder])['Image']
        self.assertEqual(control.size().toTuple(),(45,30));self.assertEqual(control.pixmap().size().toTuple(),(45,30))

    def test_image_choice_keeps_original_icon_size(self):
        path=self.folder/'choice.png';image=QImage(45,30,QImage.Format_RGB32);image.fill(Qt.red);image.save(str(path))
        form=Form(gadgets=[Gadget(kind='option',name='Images',label='',display_mode='PIXMAP',
            items=[path.name],width=45,height=30,initial='1')])
        control=self.show_form(form,image_directories=[self.folder])['Images']
        self.assertIsInstance(control.entry,QComboBox);self.assertEqual(control.entry.iconSize().toTuple(),(45,30))
        self.assertEqual(control.size().toTuple(),(45,30))

    def test_textpane_fixed_font_and_empty_view_have_no_internal_debug_labels(self):
        form=Form(gadgets=[Gadget(kind='textpane',name='InternalPane',label='Text',pane_lines=['  A','    B'],
            fixed_font=True,height=5,width=25),Gadget(kind='view',name='InternalView',label='View',y=8,width=25,height=5)])
        before=form.dumps();controls=self.show_form(form)
        self.assertEqual(controls['InternalPane'].toPlainText(),'  A\n    B')
        self.assertTrue(controls['InternalPane'].isReadOnly());self.assertEqual(controls['InternalPane'].font().family(),'monospace')
        self.assertFalse(controls['InternalView'].findChildren(QLabel));self.assertEqual(form.dumps(),before)

    def test_lines_have_only_a_stroke_and_slider_uses_static_value(self):
        form=Form(gadgets=[Gadget(kind='line',name='H',label='',width=20),
            Gadget(kind='line',name='V',label='',orientation='VERT',x=25,height=8),
            Gadget(kind='slider',name='Slider',y=4,slider_min=0,slider_max=10,slider_value=2.5,width=20)])
        before=form.dumps();controls=self.show_form(form)
        self.assertEqual(controls['H'].height(),2);self.assertEqual(controls['H'].frameShape(),QFrame.HLine)
        self.assertEqual(controls['V'].width(),2);self.assertEqual(controls['V'].frameShape(),QFrame.VLine)
        self.assertIsInstance(controls['Slider'],QSlider);self.assertEqual(controls['Slider'].value(),250)
        controls['Slider'].setValue(900);self.assertEqual(form.dumps(),before)

    def test_reopening_rebuilds_snapshot_without_stale_widgets(self):
        form=Form(gadgets=[Gadget(name='First')]);self.show_form(form)
        form.gadgets=[Gadget(name='Second',label='Second')]
        controls=self.show_form(form)
        self.assertEqual(list(controls),['Second']);self.assertEqual(controls['Second'].text(),'Second')

    def test_custom_dimension_conversion_does_not_change_export(self):
        preview=RuntimePreview(char_width=8,line_height=20)
        try:
            form=Form(gadgets=[Gadget(name='Button',x=3,y=2,width=12)]);code=form.pml()
            preview.set_form(form)
            self.assertEqual(preview.controls['Button'].geometry().getRect(),(24,40,96,20))
            self.assertEqual(preview.surface.size().toTuple(),(560,440));self.assertEqual(form.pml(),code)
        finally:preview.close();preview.deleteLater()


class RuntimePreviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_toggle_close_and_reopen_preserve_editor_geometry_history_and_design(self):
        w=self.w;w.add('button');w.dirty=False
        before=w.form.dumps();history=list(w.history);rect=w.view.geometry();sizes=w.columns.sizes();selected=w.selected
        w.runtime_action.trigger();self.app.processEvents()
        self.assertTrue(w.runtime_dialog.isVisible());self.assertTrue(w.runtime_dialog.isWindow())
        self.assertEqual(w.runtime_dialog.windowModality(),Qt.NonModal)
        self.assertTrue(w.runtime_action.isChecked())
        self.assertEqual(w.view.geometry(),rect);self.assertEqual(w.columns.sizes(),sizes)
        self.assertEqual(w.selected,selected);self.assertEqual(w.form.dumps(),before);self.assertEqual(w.history,history)
        self.assertFalse(w.dirty)
        w.runtime_dialog.close();self.app.processEvents();self.assertFalse(w.runtime_action.isChecked())
        w.runtime_action.trigger();self.app.processEvents();self.assertTrue(w.runtime_dialog.isVisible())
        w.runtime_action.trigger();self.app.processEvents();self.assertFalse(w.runtime_dialog.isVisible())

    def test_f6_opens_from_editor_and_closes_from_preview(self):
        w=self.w;w.activateWindow();self.app.processEvents()
        QTest.keyClick(w,Qt.Key_F6);self.app.processEvents()
        self.assertTrue(w.runtime_dialog.isVisible())
        QTest.keyClick(w.runtime_dialog,Qt.Key_F6);self.app.processEvents()
        self.assertFalse(w.runtime_dialog.isVisible());self.assertFalse(w.runtime_action.isChecked())

    def test_reopen_shows_latest_design_and_main_close_closes_preview(self):
        w=self.w;w.add('button');name=w.form.gadgets[0].name
        w.runtime_action.trigger();self.app.processEvents();w.runtime_dialog.close()
        w.form.gadgets[0].label='Updated';w.refresh();w.runtime_action.trigger();self.app.processEvents()
        self.assertEqual(w.runtime_dialog.controls[name].text(),'Updated')
        w.dirty=False;w.close();self.assertFalse(w.runtime_dialog.isVisible())

    def test_invalid_design_does_not_open_preview_or_change_history(self):
        w=self.w;w.add('button');w.form.width=1
        before=copy.deepcopy(w.form);history=list(w.history);w.runtime_action.trigger();self.app.processEvents()
        self.assertFalse(w.runtime_action.isChecked());self.assertFalse(w.runtime_dialog.isVisible())
        self.assertIn('親コンテナ',w.statusBar().currentMessage())
        self.assertEqual(w.form,before);self.assertEqual(w.history,history)
