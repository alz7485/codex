import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent, QFont, QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window, Item
from e3d_designer.model import Form, Gadget
from e3d_designer.mac_import import import_mac


class CanvasZoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.form=Form(width=150,height=50,gadgets=[Gadget(name='Run',x=2,y=2,width=8)])
        self.w.refresh();self.w.show();self.app.processEvents()

    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def wheel(self,angle=120,modifiers=Qt.ControlModifier,pixels=0,position=None):
        viewport=self.w.view.viewport();position=position or viewport.rect().center()
        event=QWheelEvent(QPointF(position),QPointF(viewport.mapToGlobal(position)),
            QPoint(0,pixels),QPoint(0,angle),Qt.NoButton,modifiers,Qt.NoScrollPhase,False)
        QApplication.sendEvent(viewport,event);self.app.processEvents()

    def test_ctrl_wheel_and_buttons_update_percent_without_changing_design(self):
        before=self.w.form.dumps();code=self.w.form.pml()
        self.w.choose_row(0);selected=self.w.selection_names()
        self.w.future=[Form(title='Redo')]
        self.w.zoom_in_button.click();self.assertEqual(self.w.zoom_text.text(),'110%')
        self.w.zoom_out_button.click();self.assertEqual(self.w.zoom_text.text(),'100%')
        self.wheel();self.assertEqual(self.w.zoom_text.text(),'110%')
        self.wheel(-120);self.assertEqual(self.w.zoom_text.text(),'100%')
        self.wheel(0,pixels=20);self.assertEqual(self.w.zoom_text.text(),'105%')
        self.w.zoom_reset_button.click();self.assertEqual(self.w.zoom_text.text(),'100%')
        self.assertEqual(self.w.view.transform().m11(),1)
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.form.pml(),code)
        self.assertEqual(self.w.history,[]);self.assertEqual(self.w.future[0].title,'Redo')
        self.assertFalse(self.w.dirty);self.assertEqual(self.w.selection_names(),selected)
        self.assertEqual(self.w.drag_step,.1)

    def test_zoom_text_accepts_number_percent_and_recovers_invalid_input(self):
        for text,expected in [('200%',200),('125.5',125.5),(' 75 % ',75)]:
            self.w.zoom_text.setText(text);QTest.keyClick(self.w.zoom_text,Qt.Key_Return)
            self.assertEqual(self.w.view.zoom_percent,expected)
            self.assertAlmostEqual(self.w.view.transform().m11(),expected/100)
        for text in ('','oops','0','801','nan','inf','1e999'):
            self.w.zoom_text.setText(text);QTest.keyClick(self.w.zoom_text,Qt.Key_Return)
            self.assertEqual(self.w.view.zoom_percent,75)
            self.assertEqual(self.w.zoom_text.text(),'75%')

    def test_zoom_limits_disable_buttons_and_wheel_cannot_overflow(self):
        for percent,direction in ((800,120),(10,-120)):
            self.w.view.set_zoom(percent)
            self.wheel(direction)
            self.assertEqual(self.w.view.zoom_percent,percent)
            self.assertEqual(self.w.zoom_text.text(),f'{percent}%')
        self.assertFalse(self.w.zoom_out_button.isEnabled())
        self.w.view.set_zoom(800);self.assertFalse(self.w.zoom_in_button.isEnabled())
        self.w.zoom_reset_button.click()
        self.assertTrue(self.w.zoom_in_button.isEnabled());self.assertTrue(self.w.zoom_out_button.isEnabled())

    def test_high_resolution_wheel_matches_one_notch_and_reverses_without_drift(self):
        before=self.w.form.dumps()
        for _ in range(120):self.wheel(1)
        self.assertEqual(self.w.view.zoom_percent,110)
        for _ in range(120):self.wheel(-1)
        self.assertEqual(self.w.view.zoom_percent,100)
        self.wheel(120);self.assertEqual(self.w.view.zoom_percent,110)
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(self.w.history,[])

    def test_manual_zoom_resets_pending_wheel_fraction_even_when_display_is_unchanged(self):
        self.w.view.set_zoom(100.04)
        self.assertEqual(self.w.zoom_text.text(),'100%')
        self.w.zoom_reset_button.click()
        self.wheel(-1);self.assertEqual(self.w.view.zoom_percent,99.9)
        self.wheel(1)
        self.assertEqual(self.w.view.zoom_percent,100)
        self.wheel(120);self.assertEqual(self.w.view.zoom_percent,110)

    def test_plain_wheel_scrolls_without_zoom_and_ctrl_zoom_keeps_cursor_point(self):
        self.w.view.centerOn(700,500);self.app.processEvents()
        before=self.w.view.verticalScrollBar().value();self.wheel(-120,Qt.NoModifier)
        self.assertGreater(self.w.view.verticalScrollBar().value(),before)
        self.assertEqual(self.w.view.zoom_percent,100)
        point=QPoint(200,200);before=self.w.view.mapToScene(point)
        self.wheel(position=point);after=self.w.view.mapToScene(point)
        self.assertLess((before-after).manhattanLength(),2)

    def test_drag_at_double_zoom_still_uses_pml_units_and_undo(self):
        before=self.w.form.dumps();self.w.view.set_zoom(200);self.w.view.centerOn(150,150)
        self.w.choose_row(0);self.app.processEvents()
        item=next(i for i in self.w.scene.items() if isinstance(i,Item))
        start=self.w.view.mapFromScene(item.mapToScene(item.boundingRect().center()))
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(self.w.view.viewport(),start+QPoint(20,0),30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start+QPoint(20,0));self.app.processEvents()
        self.assertEqual(self.w.form.named('Run').x,3)
        self.w.undo();self.assertEqual(self.w.form.dumps(),before)
        self.assertEqual(self.w.view.zoom_percent,200)

    def test_refresh_and_reference_window_keep_independent_zoom(self):
        self.w.view.set_zoom(150);self.w.refresh();self.w.runtime_action.setChecked(True);self.app.processEvents()
        self.assertEqual(self.w.view.zoom_percent,150)
        self.assertEqual(self.w.runtime_dialog.controls['Run'].x(),28)
        self.assertEqual(self.w.runtime_dialog.controls['Run'].height(),round(.9*26))
        self.w.zoom_reset_button.click();self.assertEqual(self.w.zoom_text.text(),'100%')

    def test_processing_editors_use_height_and_can_be_resized(self):
        self.w.inspector_tabs.setCurrentIndex(1);self.app.processEvents()
        for editor in (self.w.after_show,self.w.default_body,self.w.body):
            self.assertGreaterEqual(editor.height(),120)
            self.assertGreaterEqual(editor.viewport().height()//editor.fontMetrics().lineSpacing(),6)
        before=self.w.body.height();sizes=self.w.method_splitter.sizes()
        self.w.method_splitter.setSizes([120,120,sum(sizes)-240]);self.app.processEvents()
        self.assertGreater(self.w.body.height(),before)

    def test_measurement_label_gap_is_smaller_with_same_source_coordinates(self):
        path=Path(__file__).parents[1]/'examples/user-supplied/HsMacMSR.mac'
        raw=path.read_bytes()
        # The photo transcription contains $$DIALOG. Resolve that header only
        # for this static comparison; the supplied file remains byte-identical.
        form=import_mac(raw.decode('cp932').replace('$$DIALOG','DIALOG',1)).form
        self.w.form=form;self.w.selected=None;self.w.refresh();self.w.runtime_action.setChecked(True);self.app.processEvents()
        label=self.w.runtime_dialog.controls['PARAGRAPHxA0002'];entry=self.w.runtime_dialog.controls['TEXTxA0002']
        old=QFont(label.font());old.setPointSizeF(9)
        old_gap=entry.x()-label.x()-QFontMetrics(old).horizontalAdvance(label.text())
        new_gap=entry.x()-label.x()-label.fontMetrics().horizontalAdvance(label.text())
        self.assertLess(new_gap,old_gap);self.assertGreater(new_gap,0)
        self.assertEqual(form.named('TEXTxA0002').x,7)
        self.assertEqual(label.font(),self.w.appearance.preview_font)
        self.assertEqual(self.w.history,[]);self.assertEqual(path.read_bytes(),raw)
