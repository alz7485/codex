import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem
from e3d_designer.app import Window, Item
from e3d_designer.model import Form, Gadget


class FormMarginAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.w = Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show()
        self.app.processEvents()

    def tearDown(self):
        self.w.dirty = False
        self.w.close()
        self.app.processEvents()
        self.temp.cleanup()

    def load(self, form):
        self.w.form = form
        self.w.selected = None
        self.w.refresh()
        self.w.runtime_action.setChecked(True)
        self.app.processEvents()
        return self.w.runtime_dialog

    def item(self, name):
        return next(i for i in self.w.scene.items() if isinstance(i, Item) and i.gadget.name == name)

    def test_negative_root_coordinate_uses_form_padding_without_touching_the_border(self):
        form = Form(width=20, height=8, gadgets=[Gadget(name='Run', x=-.5, y=1, width=4)])
        before = form.dumps()
        p = self.load(form)
        self.assertTrue(self.item('Run').shape().contains(QPointF(1, 13)))
        self.assertEqual(p.controls['Run'].visibleRegion().boundingRect().left(), 0)
        self.assertFalse(self.item('Run').content_clip_rect().contains(QPointF(-4, 13)))
        self.assertEqual(form.dumps(), before)

    def test_button_padding_at_right_edge_is_visible_in_both_views(self):
        p = self.load(Form(width=4, height=2, gadgets=[Gadget(name='Run', x=0, y=0, width=4)]))
        button = p.controls['Run']
        self.assertEqual(button.visibleRegion().boundingRect().width(), button.width())
        self.assertTrue(self.item('Run').shape().contains(QPointF(button.width()-1, 13)))

    def test_root_content_beyond_padding_is_clipped_but_selection_is_visible(self):
        p = self.load(Form(width=20, height=8, gadgets=[Gadget(name='Run', x=-1.2, y=1, width=4)]))
        item = self.item('Run')
        self.assertFalse(item.shape().contains(QPointF(1, 13)))
        self.assertTrue(item.shape().contains(QPointF(5, 13)))
        self.assertEqual(p.controls['Run'].visibleRegion().boundingRect().left(), 4)
        item.setSelected(True)
        self.assertTrue(item.shape().contains(QPointF(1, 13)))
        self.assertFalse(item.content_clip_rect().contains(QPointF(1, 13)))

    def test_form_padding_does_not_change_nested_frame_coordinates_or_clipping(self):
        p = self.load(Form(width=20, height=8, gadgets=[
            Gadget(kind='frame', name='Group', x=2, y=2, width=12, height=4),
            Gadget(name='Run', parent='Group', x=-.5, y=1, width=4)]))
        self.assertEqual(p.controls['Run'].pos().toTuple(), (-5, 26+round(.05*26)))
        self.assertEqual(p.controls['Run'].visibleRegion().boundingRect().left(), 5)
        self.assertFalse(self.item('Run').shape().contains(QPointF(1, 13)))
        self.assertTrue(self.item('Run').shape().contains(QPointF(6, 13)))

    def test_auto_line_extent_excludes_interaction_target_and_matches_reference(self):
        for orientation in ('HORIZ', 'VERT'):
            with self.subTest(orientation=orientation):
                self.w.runtime_action.setChecked(False)
                form = Form(size_explicit=False, gadgets=[Gadget(kind='line', name='Rule', label='', x=2, y=3,
                    width=8 if orientation=='HORIZ' else 0, height=8 if orientation=='VERT' else 0,
                    orientation=orientation)])
                p = self.load(form)
                before = form.dumps()
                self.assertEqual(self.w.form_item.frame_rect().size().toSize(), p.client.size())
                item = self.item('Rule')
                self.assertEqual(item.boundingRect().height() if orientation=='HORIZ' else item.boundingRect().width(), 8)
                old = self.w.form_item.frame_rect()
                item.setSelected(True)
                self.w.sync_visual_form_size()
                self.assertEqual(self.w.form_item.frame_rect(), old)
                self.assertEqual(form.dumps(), before)

    def test_large_slider_limits_keep_editor_thumb_at_reference_midpoint(self):
        form = Form(gadgets=[Gadget(kind='slider', name='Slide', width=20,
            slider_min=-1e308, slider_max=1e308, slider_value=0)])
        before = form.dumps()
        p = self.load(form)
        item = self.item('Slide')
        image = QImage(220, 60, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        item.paint(painter, QStyleOptionGraphicsItem())
        painter.end()
        self.assertEqual(p.controls['Slide'].value(), 500)
        self.assertEqual(image.pixelColor(100, round(item.boundingRect().center().y())).name(), '#77a9dd')
        self.assertEqual(form.dumps(), before)

    def test_form_resize_resolves_relative_chain_once_and_observes_next_edit(self):
        gadgets = [Gadget(name='Base', width=3)]
        for i in range(1, 35):
            previous = gadgets[-1].name
            gadgets.append(Gadget(name=f'Item{i}', layout_mode='RELATIVE', xref=previous, yref=previous,
                xedge='XMIN', yedge='YMIN', xoffset=0, yoffset=0, width=3))
        self.load(Form(width=70, height=22, gadgets=gadgets))
        counts = Counter()
        original = Form.geometry
        def resolve(model, gadget, *args, **kwargs):
            memo = kwargs.get('_memo')
            if memo is None or id(gadget) not in memo:
                counts[gadget.name] += 1
            return original(model, gadget, *args, **kwargs)
        with patch.object(Form, 'geometry', resolve):
            self.assertTrue(self.w.form_item.resize_to(80, 25))
        self.assertLessEqual(max(counts.values()), 1)
        self.w.form.named('Base').x = 79
        self.assertFalse(self.w.form_item.resize_to(80, 26))
        self.assertEqual((self.w.form.width, self.w.form.height), (80, 25))
