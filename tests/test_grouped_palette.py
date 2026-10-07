import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window
from e3d_designer.model import Form,Menu,MenuItem
from e3d_designer.palette import GadgetPalette


class GroupedPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()
    def test_requested_groups_and_canvas_column_layout(self):
        w=self.w
        groups={'paragraph':['paragraph','image'],'toggle':['toggle','rtoggle'],
            'option':['option','combo','image_option'],'frame':['frame','tabset'],
            'line':['line_horiz','line_vert'],'slider':['slider_horiz','slider_vert'],
            'list':['list','textpane'],'commandline':['commandline','view']}
        self.assertEqual(len(w.palette_buttons),14)
        for group,keys in groups.items():self.assertEqual([a.data() for a in w.palette_buttons[group].menu().actions()],keys)
        self.assertTrue(w.canvas_panel.isAncestorOf(w.palette_panel))
        self.assertEqual(w.palette_panel.width(),w.view.width())
        self.assertLess(w.library_panel.mapTo(w,w.library_panel.rect().topLeft()).y(),w.view.mapTo(w,w.view.rect().topLeft()).y())
        self.assertLess(w.inspector_tabs.mapTo(w,w.inspector_tabs.rect().topLeft()).y(),w.view.mapTo(w,w.view.rect().topLeft()).y())
    def test_actual_menu_choice_and_repeat_button_add_same_variant(self):
        w=self.w;button=w.palette_buttons['line'];menu=button.menu();action=w.palette_actions['line_vert']
        menu.popup(button.mapToGlobal(button.rect().bottomLeft()));self.app.processEvents()
        QTest.mouseClick(menu,Qt.LeftButton,Qt.NoModifier,menu.actionGeometry(action).center());self.app.processEvents()
        self.assertEqual(w.form.gadgets[-1].orientation,'VERT');self.assertIs(button.defaultAction(),action)
        QTest.mouseClick(button,Qt.LeftButton);self.app.processEvents()
        self.assertEqual(len(w.form.gadgets),2);self.assertTrue(all(g.orientation=='VERT' for g in w.form.gadgets))
        self.assertEqual(len(w.history),2);w.form.validate()
        w.undo();w.undo();self.assertEqual(w.form.gadgets,[])

    def test_widened_arrow_opens_choices_without_adding_and_body_repeats_selection(self):
        w=self.w;button=w.palette_buttons['line'];menu=button.menu();action=w.palette_actions['line_vert']
        observations=[]
        def choose():
            observations.append((menu.isVisible(),len(w.form.gadgets)))
            if menu.isVisible():QTest.mouseClick(menu,Qt.LeftButton,Qt.NoModifier,menu.actionGeometry(action).center())
            menu.close()
        QTimer.singleShot(50,choose)
        # 18px from the right is inside the expanded arrow area.
        QTest.mouseClick(button,Qt.LeftButton,Qt.NoModifier,QPoint(button.width()-18,button.height()//2))
        self.app.processEvents()
        QTest.qWait(80);self.app.processEvents()
        self.assertEqual(observations,[(True,0)])
        self.assertEqual(len(w.form.gadgets),1);self.assertEqual(w.form.gadgets[0].orientation,'VERT')
        self.assertIs(button.defaultAction(),action)
        QTest.mouseClick(button,Qt.LeftButton,Qt.NoModifier,QPoint(10,button.height()//2));self.app.processEvents()
        self.assertEqual(len(w.form.gadgets),2);self.assertEqual(w.form.gadgets[1].orientation,'VERT')
    def test_each_choice_emits_correct_kind_and_direction_once(self):
        palette=GadgetPalette();received=[];menus=[]
        palette.addRequested.connect(lambda kind,direction:received.append((kind,direction)))
        palette.menuRequested.connect(lambda:menus.append(True))
        expected={'image':('paragraph','PIXMAP'),'rtoggle':('rtoggle',None),'combo':('combo',None),
            'image_option':('option','PIXMAP'),'tabset':('frame','TABSET'),'line_vert':('line','VERT'),
            'slider_vert':('slider','VERTICAL'),'textpane':('textpane',None),'view':('view',None)}
        for key,pair in expected.items():
            palette.actions[key].trigger();self.assertEqual(received[-1],pair)
        self.assertEqual(len(received),len(expected));palette.actions['menubar'].trigger();self.assertEqual(menus,[True])
        palette.close();palette.deleteLater()
    def test_palette_wraps_without_clipping_in_narrow_canvas(self):
        palette=GadgetPalette();palette.show()
        for width in (724,420,240,120):
            palette.resize(width,palette.height());self.app.processEvents()
            for button in palette.buttons.values():
                self.assertTrue(button.isVisible())
                self.assertGreaterEqual(button.geometry().left(),0)
                self.assertLessEqual(button.geometry().right(),palette.width())
                self.assertLessEqual(button.geometry().bottom(),palette.height())
        palette.close();palette.deleteLater()
    def test_menubar_preview_is_framed_and_popup_only_menus_hide_it(self):
        w=self.w;self.assertNotIn('border: 2px',w.palette_buttons['menubar'].styleSheet())
        w.form=Form(menus=[Menu(name='Tools',items=[MenuItem(label='Run')])]);w.refresh();self.app.processEvents()
        self.assertTrue(w.preview_menu_frame.isVisible())
        self.assertTrue(w.preview_menu_bar.isVisible())
        self.assertGreater(w.preview_menu_bar.height(),15)
        self.assertEqual([a.text() for a in w.preview_menu_bar.actions()],["Tools"])
        self.assertTrue(w.preview_menu_frame.isAncestorOf(w.preview_menu_bar))
        self.assertIn('border: 1px',w.preview_menu_frame.styleSheet())
        w.form.menus[0].popup=True;w.refresh();self.assertFalse(w.preview_menu_frame.isVisible())
