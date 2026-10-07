"""Geometry reproduced from the supplied measurement-form photographs."""
import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QStyleOptionComboBox,QStyle
from e3d_designer.app import Window,SX,SY
from e3d_designer.mac_import import import_mac,read_mac
from e3d_designer.model import Form,Gadget
from e3d_designer.quick_editor import FormProperties,MiniProperties
from e3d_designer.runtime_preview import RuntimePreview
from e3d_designer.appearance import FORM_PADDING


def measurement_source():
    lines=['Kill !!MeasureExample','Setup Form !!MeasureExample Dialog',"Title |<Mesure>|"]
    for index,(label,x,y) in enumerate((('距離',1,1),('Xの距離',0,1.9),('Yの距離',0,2.8),
            ('Zの距離',0,3.7),('角度',1,4.6),('P1座標',.4,5.5),('P2座標',.4,6.4)),1):
        lines.append(f'Paragraph .Label{index} At X {x} Y {y} Text |{label}| Width 8')
        lines.append(f'Text .Value{index} At X 7 Y {y} || Call || Width 30 Is String')
    for index,(label,x,width) in enumerate((('計測',0,4),('結果',6,4),('▲',25,1.2),('▼',27,1.2),('PIN消',33,4)),1):
        color=' Background 48' if index==1 else ' Background 168' if index==2 else ''
        command='$M /%PDMSUSER%/SUB/MSRsub1.mac' if index==1 else ''
        lines.append(f'Button .Button{index} At X {x} Y 0{color} |{label}| Call |{command}| Width {width}')
    lines.extend(['Toggle .Decimals At X 12 Y 0 |小数点| Call ||',
        'Option _Digits At X 19 Y 0 || Call |$$_Digits| Width 2',
        'Var List _Digits Pairs'])
    lines.extend(f'|{i}| |!!DCP = {i}|' for i in range(10))
    lines.extend(['Exit','Exit','Show !!MeasureExample','Define Method .Default()',
        '!this.Digits.Val = 5','!this.Decimals.Val = TRUE','Endmethod'])
    return '\n'.join(lines)+'\n'


class MeasureDimensionTests(unittest.TestCase):
    def test_unsized_form_is_compact_and_does_not_gain_size_on_export(self):
        form=import_mac(measurement_source()).form
        self.assertFalse(form.size_explicit)
        self.assertEqual(form.width,38);self.assertAlmostEqual(form.height,8.4)
        setup=next(line for line in form.pml().splitlines() if line.lower().startswith('setup '))
        self.assertNotIn('size',setup.lower())
        self.assertEqual(form.named('Value7').label,'');self.assertEqual(form.named('Value7').width,30)

    def test_pairs_explicit_width_initial_and_items_survive_all_round_trips(self):
        strict=import_mac(measurement_source()).form
        self.assertEqual(import_mac(measurement_source(),partial=True).form.dumps(),strict.dumps())
        for form in (strict,Form.loads(strict.dumps()),import_mac(strict.pml()).form):
            option=form.named('Digits')
            self.assertTrue(option.option_width_explicit);self.assertEqual(option.width,2)
            self.assertEqual(option.items,[str(i) for i in range(10)]);self.assertEqual(option.initial,'5')
            declaration=next(line for line in form.pml().splitlines() if line.strip().lower().startswith('option '))
            self.assertIn('Width 2',declaration)
            self.assertLess(declaration.index('Call'),declaration.index('Width'))

    def test_button_widths_and_server_command_are_not_rewritten(self):
        form=import_mac(measurement_source()).form
        self.assertEqual([g.width for g in form.gadgets if g.kind=='button'],[4,4,1.2,1.2,4])
        self.assertIn('$M /%PDMSUSER%/SUB/MSRsub1.mac',form.pml())
        self.assertEqual(import_mac(form.pml()).form.named('Button3').width,1.2)

    def test_explicit_size_is_retained_for_ordinary_dialog(self):
        source=measurement_source().replace('Setup Form !!MeasureExample Dialog','Setup Form !!MeasureExample Size 70 22 Dialog')
        form=import_mac(source).form
        self.assertTrue(form.size_explicit);self.assertEqual((form.width,form.height),(70,22))
        self.assertIn('Size 70 22 Dialog',form.pml())

    def test_new_and_legacy_json_keep_existing_size_and_pairs_defaults(self):
        fresh=Form(gadgets=[Gadget(kind='option',name='Pick',items=['A'])])
        legacy=Form.loads('{"version":2,"form":{"gadgets":[{"kind":"option","name":"Pick","items":["A"]}]}}')
        for form in (fresh,legacy):
            self.assertTrue(form.size_explicit);self.assertFalse(form.named('Pick').option_width_explicit)
            declaration=next(line for line in form.pml().splitlines() if line.strip().lower().startswith('option '))
            self.assertNotIn('Width',declaration);self.assertIn('Size 70 22',form.pml())

    def test_omitted_option_width_remains_automatic(self):
        form=import_mac(measurement_source().replace(' Call |$$_Digits| Width 2',' Call |$$_Digits|')).form
        self.assertFalse(form.named('Digits').option_width_explicit)
        declaration=next(line for line in form.pml().splitlines() if line.strip().lower().startswith('option '))
        self.assertNotIn('Width',declaration)

    def test_automatic_size_follows_moves_and_deletions_without_adding_size(self):
        form=import_mac(measurement_source()).form;form.named('Button5').x=50
        form.validate();self.assertEqual(form.width,55)
        form.gadgets=[g for g in form.gadgets if g.name!='Button5'];form.validate();self.assertEqual(form.width,38)
        self.assertFalse(import_mac(form.pml()).form.size_explicit)

    def test_unsized_nested_frame_and_negative_coordinates_fit_right_bottom(self):
        source="Setup Form !!Small Dialog\nFrame .Outer At X -2 Y -1 'Outer' Width 20 Height 8\nButton .Inside At X -1 Y 1 'Inside' Width 5\nExit\nExit\nShow !!Small"
        form=import_mac(source).form
        self.assertEqual((form.width,form.height),(19,8));self.assertEqual(form.named('Inside').parent,'Outer')
        self.assertEqual(import_mac(form.pml()).form.dumps(),form.dumps())

    def test_zero_width_hidden_control_keeps_layout_extent_and_macro_state(self):
        source="Setup Form !!Small Dialog\nText .Hidden At X 50 Y 10 '' Width 0 Is String\nExit\nShow !!Small"
        form=import_mac(source).form
        self.assertTrue(form.named('Hidden').hidden);self.assertEqual((form.width,form.height),(51,12))
        self.assertTrue(import_mac(form.pml()).form.named('Hidden').hidden)

    def test_cp932_source_file_is_not_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'measure.mac';data=measurement_source().replace('\n','\r\n').encode('cp932');path.write_bytes(data)
            form=read_mac(path).form;self.assertEqual(path.read_bytes(),data)
            self.assertFalse(form.size_explicit);self.assertTrue(form.named('Digits').option_width_explicit)

    def test_flag_types_are_validated(self):
        for form in (Form(size_explicit='False'),Form(gadgets=[Gadget(option_width_explicit=1)])):
            with self.assertRaises(ValueError):form.validate()


class MeasureAppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.form=import_mac(measurement_source()).form;self.preview=RuntimePreview()
    def tearDown(self):
        self.preview.close();self.preview.deleteLater();self.app.processEvents();self.temp.cleanup()
    def show(self):
        self.preview.set_form(self.form);self.preview.show();self.app.processEvents();return self.preview.controls

    def test_width_two_leaves_space_for_value_and_dropdown_arrow(self):
        before=self.form.dumps();controls=self.show();combo=controls['Digits'].entry
        option=QStyleOptionComboBox();combo.initStyleOption(option)
        content=combo.style().subControlRect(QStyle.CC_ComboBox,option,QStyle.SC_ComboBoxEditField,combo)
        arrow=combo.style().subControlRect(QStyle.CC_ComboBox,option,QStyle.SC_ComboBoxArrow,combo)
        self.assertGreaterEqual(content.width(),2*self.preview.char_width)
        self.assertGreater(arrow.width(),0);self.assertEqual(combo.currentText(),'4')
        self.assertEqual(self.form.dumps(),before);self.assertEqual(self.form.named('Digits').width,2)

    def test_buttons_include_native_padding_but_keep_source_width(self):
        code=self.form.pml();controls=self.show()
        self.assertGreater(controls['Button1'].width(),4*self.preview.char_width)
        self.assertGreater(controls['Button3'].width(),1.2*self.preview.char_width)
        self.assertEqual(self.form.named('Button1').width,4);self.assertEqual(self.form.pml(),code)

    def test_auto_surface_encloses_native_controls_without_large_empty_form(self):
        controls=self.show();surface=self.preview.surface
        self.assertLess(surface.width(),70*self.preview.char_width);self.assertLess(surface.height(),22*self.preview.line_height)
        for control in controls.values():
            if control.parent() is surface:self.assertTrue(surface.rect().contains(control.geometry()))
        roots=[control.geometry() for control in controls.values() if control.parent() is surface]
        self.assertEqual(surface.height()-max(r.y()+r.height() for r in roots),FORM_PADDING)
        self.assertEqual(surface.width()-max(r.x()+r.width() for r in roots),FORM_PADDING)
        self.assertTrue(controls['Decimals'].isChecked());self.assertEqual(controls['Value7'].entry.text(),'')

    def test_editor_size_override_and_undo_preserve_automatic_intent(self):
        w=Window(settings_path=self.folder/'settings.json')
        try:
            w.form=copy.deepcopy(self.form);w.selected=None;w.refresh();before=w.form.dumps()
            self.assertTrue(w.auto_form_size.isChecked());self.assertEqual(w.fw.value(),38)
            w.fw.setValue(45);self.assertTrue(w.form.size_explicit);self.assertFalse(w.auto_form_size.isChecked())
            w.undo();self.assertFalse(w.form.size_explicit);self.assertEqual(w.form.dumps(),before)
            w.ftitle.setText('Renamed title');w.update_form();self.assertFalse(w.form.size_explicit)
        finally:w.dirty=False;w.close();self.app.processEvents()

    def test_auto_checkbox_fits_manual_form_and_undo_restores_size(self):
        w=Window(settings_path=self.folder/'settings.json')
        try:
            w.form=Form(gadgets=[Gadget(name='Run',x=2,y=1,width=4)]);w.refresh();before=w.form.dumps()
            w.auto_form_size.setChecked(True)
            self.assertEqual((w.form.width,w.form.height),(7,3));self.assertFalse(w.form.size_explicit)
            w.undo();self.assertEqual(w.form.dumps(),before);self.assertFalse(w.auto_form_size.isChecked())
        finally:w.dirty=False;w.close();self.app.processEvents()

    def test_mini_form_title_preserves_auto_but_dimension_edit_overrides(self):
        for resize in (False,True):
            dialog=FormProperties(None,self.form)
            try:
                dialog.title.setText('Updated')
                if resize:dialog.width.setValue(45)
                dialog.accept();self.assertIsNotNone(dialog.result_form)
                self.assertEqual(dialog.result_form.size_explicit,resize)
                self.assertEqual(dialog.result_form.width,45 if resize else 38)
            finally:dialog.deleteLater();self.app.processEvents()

    def test_form_handle_cancel_restores_automatic_size_and_history(self):
        w=Window(settings_path=self.folder/'settings.json');w.form=copy.deepcopy(self.form);w.selected=None;w.refresh();w.show();self.app.processEvents()
        try:
            before=w.form.dumps();item=w.form_item
            start=w.view.mapFromScene(item.mapToScene(item.handles()['width'].center()))
            QTest.mousePress(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
            QTest.mouseMove(w.view.viewport(),start+QPoint(60,0),30)
            self.assertTrue(w.form.size_explicit)
            QTest.keyClick(w.view,Qt.Key_Escape);self.app.processEvents()
            QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start+QPoint(60,0))
            self.assertEqual(w.form.dumps(),before);self.assertEqual(w.history,[])
            self.assertTrue(w.auto_form_size.isChecked())
        finally:w.dirty=False;w.close();self.app.processEvents()

    def test_pairs_width_checkbox_edit_and_undo_affect_output(self):
        w=Window(settings_path=self.folder/'settings.json')
        try:
            w.form=copy.deepcopy(self.form);w.selected=next(i for i,g in enumerate(w.form.gadgets) if g.name=='Digits');w.refresh()
            self.assertTrue(w.option_width_check.isChecked())
            w.fields['width'].setValue(3);self.assertIn("Call '$$_Digits' Width 3",w.form.pml())
            w.undo();self.assertEqual(w.form.named('Digits').width,2)
            w.choose_row(next(i for i,g in enumerate(w.form.gadgets) if g.name=='Digits'))
            w.option_width_check.setChecked(False)
            declaration=next(line for line in w.form.pml().splitlines() if line.strip().startswith('Option '))
            self.assertNotIn('Width',declaration);w.undo();self.assertTrue(w.form.named('Digits').option_width_explicit)
        finally:w.dirty=False;w.close();self.app.processEvents()

    def test_mini_pairs_width_checkbox_is_saved_with_width(self):
        index=next(i for i,g in enumerate(self.form.gadgets) if g.name=='Digits')
        dialog=MiniProperties(None,self.form,index)
        try:
            self.assertTrue(dialog.option_width.isChecked());dialog.fields['width'].setValue(3)
            dialog.accept();self.assertIsNotNone(dialog.result_form)
            self.assertTrue(dialog.result_form.named('Digits').option_width_explicit)
            self.assertIn("Call '$$_Digits' Width 3",dialog.result_form.pml())
        finally:dialog.deleteLater();self.app.processEvents()

    def test_form_handle_return_to_start_preserves_auto_and_history(self):
        w=Window(settings_path=self.folder/'settings.json');w.form=copy.deepcopy(self.form);w.selected=None;w.refresh();w.show();self.app.processEvents()
        try:
            before=w.form.dumps();item=w.form_item
            start=w.view.mapFromScene(item.mapToScene(item.handles()['width'].center()))
            QTest.mousePress(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
            QTest.mouseMove(w.view.viewport(),start+QPoint(60,0),30)
            self.assertTrue(w.form.size_explicit)
            QTest.mouseMove(w.view.viewport(),start,30)
            QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start);self.app.processEvents()
            self.assertEqual(w.form.dumps(),before);self.assertEqual(w.history,[])
            self.assertTrue(w.auto_form_size.isChecked())
        finally:w.dirty=False;w.close();self.app.processEvents()
