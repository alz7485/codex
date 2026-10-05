import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
import json
from dataclasses import asdict
from unittest.mock import patch
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QScrollArea
from e3d_designer.app import Window,Item,SX,SY,preview_offset
from e3d_designer.clipboard import clone_subtree
from e3d_designer.model import Form,Gadget,Menu,MenuItem


class CloneRegressionTests(unittest.TestCase):
    def test_tabset_owns_tab_information_roundtrip_and_legacy_import(self):
        page=Gadget(kind='frame',name='settings',label='Settings',x=0,y=0,width=40,height=12)
        tabs=Gadget(kind='frame',name='tabs',frame_style='TABSET',width=40,height=12,tabs=[page])
        form=Form(gadgets=[tabs,Gadget(name='run',parent='settings',x=1,y=2)])
        self.assertIs(tabs.tabs[0],form.named('settings'))
        data=json.loads(form.dumps())
        self.assertEqual(data['version'],2)
        self.assertNotIn('settings',[g['name'] for g in data['form']['gadgets']])
        self.assertEqual(data['form']['gadgets'][0]['tabs'][0]['name'],'settings')
        restored=Form.loads(json.dumps(data))
        self.assertEqual([g.name for g in restored.gadgets],[g.name for g in form.gadgets])
        self.assertEqual(restored.dumps(),form.dumps())
        self.assertEqual(restored.pml(),form.pml())
        legacy=asdict(form)
        for gadget in legacy['gadgets']:gadget.pop('tabs',None)
        imported=Form.loads(json.dumps({'version':1,'form':legacy}))
        self.assertEqual(imported.named('tabs').tabs[0].name,'settings')
        self.assertEqual(imported.pml(),form.pml())
        draft,index=clone_subtree(form,form,0)
        self.assertEqual(len(draft.gadgets[index].tabs),1)
        self.assertNotEqual(draft.gadgets[index].tabs[0].name,'settings')
        self.assertEqual(Form.loads(draft.dumps()).pml(),draft.pml())
        for bad in ('bad', [{'kind':'button','name':'bad'}]):
            data['form']['gadgets'][0]['tabs']=bad
            with self.assertRaises(ValueError):Form.loads(json.dumps(data))
    def test_callback_copy_is_independent_and_transactional(self):
        source=Form(gadgets=[Gadget(name='run',callback='clicked',body='!this.run.val = TRUE\n!this.clicked()')])
        before=source.dumps();draft,selected=clone_subtree(source,source,0)
        gadget=draft.gadgets[selected]
        self.assertNotEqual(gadget.callback,'clicked')
        self.assertIn('!this.'+gadget.name+'.val',gadget.body)
        self.assertIn('!this.'+gadget.callback+'()',gadget.body)
        self.assertEqual(source.dumps(),before)
        self.assertIn('define method .'+gadget.callback+'()',draft.pml(normalize=False))

    def test_table_helpers_container_members_and_method_aliases(self):
        source=Form(gadgets=[Gadget(kind='frame',name='group',x=0,y=0,width=60,height=10),
            Gadget(kind='list',name='results',parent='group',list_mode='TABLE',table_method='fillTable',headings=['Name'],rows=[['P-101']],height=4),
            Gadget(kind='container',name='grid',parent='group',assembly='Controls',namespace='Company.Controls',control_type='Widget'),
            Gadget(name='refresh',parent='group',callback='refreshAll')])
        source.gadgets[-1].body='!this.fillTable()\n!this.gridControl.Refresh()\n!!userform.results.val = 1'
        draft,_=clone_subtree(source,source,0);table,container,button=draft.gadgets[-3:]
        self.assertIn('!this.populate_'+table.name+'()',button.body)
        self.assertIn('!this.'+container.name+'Control.Refresh()',button.body)
        self.assertIn('!!userform.'+table.name+'.val',button.body)
        self.assertNotIn('fillTable',button.body);self.assertNotIn('gridControl',button.body)
        source.gadgets[1].table_method='';source.gadgets[-1].body='!this.populate_results()'
        draft,_=clone_subtree(source,source,0)
        self.assertEqual(draft.gadgets[-1].body,'!this.populate_'+draft.gadgets[-3].name+'()')

    def test_shared_callbacks_default_and_slider_signatures(self):
        source=Form(default_body='!this.first.val = TRUE',gadgets=[Gadget(kind='frame',name='group',x=0,y=0,width=50,height=10),
            Gadget(name='first',parent='group',callback='shared',body='!this.first.val = TRUE'),
            Gadget(name='second',parent='group',callback='shared',body='!this.first.val = TRUE'),
            Gadget(name='reset',parent='group',callback='DEFAULT'),
            Gadget(kind='slider',name='level',parent='group',callback='levelChanged',body='!this.level.val = !gad.val')])
        draft,_=clone_subtree(source,source,0);first,second,reset,slider=draft.gadgets[-4:]
        self.assertEqual(first.callback,second.callback);self.assertNotEqual(first.callback,'shared')
        self.assertEqual(reset.body,'!this.'+first.name+'.val = TRUE');self.assertNotEqual(reset.callback.lower(),'default')
        self.assertIn('define method .'+slider.callback+'(!gad is GADGET, !event is STRING)',draft.pml(normalize=False))

    def test_detached_child_keeps_global_coordinates_and_native_sizes(self):
        source=Form(gadgets=[Gadget(kind='frame',name='outer',x=20,y=5,width=30,height=10),
                            Gadget(kind='paragraph',name='image',parent='outer',x=3,y=2,width=150,height=50,display_mode='PIXMAP')])
        draft,index=clone_subtree(Form(name='target'),source,1);gadget=draft.gadgets[index]
        self.assertEqual(draft.geometry(gadget)[:2],(23,7));self.assertEqual((gadget.width,gadget.height),(150,50))
        self.assertEqual(gadget.parent,'')

    def test_missing_relative_reference_keeps_resolved_pixel_width(self):
        source=Form(gadgets=[Gadget(name='base',width=12),Gadget(kind='paragraph',name='image',x=0,y=0,width=150,height=50,display_mode='PIXMAP',layout_mode='RELATIVE',xref='base',yref='base',width_ref='base')])
        expected=source.geometry(source.gadgets[1]);draft,index=clone_subtree(Form(name='target'),source,1)
        self.assertEqual(draft.geometry(draft.gadgets[index]),expected)
        self.assertEqual(draft.gadgets[index].width,120)


class AuditGuiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self): self.w=Window();self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents()
    def load(self,form,index=0):
        form.validate();self.w.form=form;self.w.selected=index;self.w.refresh()

    def test_cut_restore_references_order_repeated_paste_and_undo(self):
        form=Form(gadgets=[Gadget(name='base',width=10),Gadget(kind='text',name='follower',layout_mode='RELATIVE',xref='base',yref='base',xedge='XMAX',yedge='YMIN',width=10)])
        self.load(form);self.w.cut_gadget();self.w.paste_gadget()
        self.assertEqual([g.name for g in self.w.form.gadgets],['base','follower'])
        self.assertEqual(self.w.form.gadgets[1].xref,'base');self.w.form.validate()
        with tempfile.TemporaryDirectory() as folder:
            self.w.path=Path(folder)/'design.json';self.assertTrue(self.w.save())
        self.w.paste_gadget();self.assertEqual(len(self.w.form.gadgets),3)
        self.w.undo();self.w.undo();self.w.paste_gadget();self.w.form.validate()
        self.assertEqual([g.name for g in self.w.form.gadgets],['base','follower'])

    def test_cut_restore_auto_layout(self):
        self.load(Form(gadgets=[Gadget(name='base'),Gadget(name='auto',layout_mode='AUTO')]),1)
        expected=self.w.form.geometry(self.w.form.gadgets[1]);self.w.cut_gadget();self.w.paste_gadget()
        self.assertEqual(self.w.form.gadgets[1].name,'auto');self.assertEqual(self.w.form.gadgets[1].layout_mode,'AUTO')
        self.assertEqual(self.w.form.geometry(self.w.form.gadgets[1]),expected)

    def test_duplicate_and_paste_update_callbacks_and_preserve_undo(self):
        self.load(Form(gadgets=[Gadget(name='run',callback='clicked',body='!this.run.val = TRUE')]))
        self.w.duplicate();self.assertEqual(len(self.w.form.gadgets),2)
        self.w.undo();self.w.choose_row(0);self.w.copy_gadget();self.w.paste_gadget()
        self.assertEqual(len(self.w.form.gadgets),2);self.w.form.validate()
        self.assertIn('!this.'+self.w.form.gadgets[1].name+'.val',self.w.form.gadgets[1].body)

    def test_option_mode_rewrites_all_known_code_and_undo(self):
        self.load(Form(default_body='!this._mode.val = 1',initcall='!!userform._mode.val = 1',menus=[Menu(name='actions',items=[MenuItem('Set','!this._mode.val = 1')])],gadgets=[Gadget(kind='option',name='_mode',items=['One']),Gadget(name='run',command='!this._mode.val = 1')]))
        self.w.fields['display_mode'].setCurrentText('PIXMAP')
        self.assertEqual(self.w.form.gadgets[0].name,'mode');self.w.form.validate()
        self.assertEqual(self.w.form.default_body,'!this.mode.val = 1');self.assertIn('!!userform.mode.val',self.w.form.initcall)
        self.assertEqual(self.w.form.gadgets[1].command,'!this.mode.val = 1');self.assertEqual(self.w.form.menus[0].items[0].command,'!this.mode.val = 1')
        self.w.fields['display_mode'].setCurrentText('TEXT');self.assertEqual(self.w.form.default_body,'!this._mode.val = 1')
        self.w.undo();self.assertEqual(self.w.form.default_body,'!this.mode.val = 1')

    def test_popup_uncheck_detaches_and_undo_restores(self):
        self.load(Form(menus=[Menu(name='context',popup=True)],gadgets=[Gadget(kind='list',name='results',popup_menu='context')]))
        self.w.menu_popup.setChecked(False);self.assertEqual(self.w.form.gadgets[0].popup_menu,'');self.w.form.validate()
        self.w.undo();self.assertTrue(self.w.form.menus[0].popup);self.assertEqual(self.w.form.gadgets[0].popup_menu,'context')

    def test_pixel_dimensions_preview_bounds_save_and_resize(self):
        self.load(Form(gadgets=[Gadget(kind='paragraph',name='image',display_mode='PIXMAP',width=150,height=50,x=2,y=1)]))
        item=next(item for item in self.w.scene.items() if isinstance(item,Item))
        self.assertEqual((item.boundingRect().width(),item.boundingRect().height()),(150,50))
        self.assertIn('PIXMAP WIDTH 150 HEIGHT 50',self.w.form.pml(normalize=False))
        self.w.fields['width'].setValue(200);self.assertEqual(self.w.form.gadgets[0].width,200)
        with tempfile.TemporaryDirectory() as folder:
            self.w.path=Path(folder)/'image.json';self.assertTrue(self.w.save())
            self.assertEqual(Form.loads(self.w.path.read_text()).gadgets[0].width,200)
        self.app.processEvents();item=next(item for item in self.w.scene.items() if isinstance(item,Item))
        start=self.w.view.mapFromScene(item.mapToScene(item.handles()['width'].center()))
        end=start+type(start)(30,0)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        self.app.processEvents();QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        self.assertEqual(self.w.form.gadgets[0].width,230);self.w.undo();self.assertEqual(self.w.form.gadgets[0].width,200)
        self.w.choose_row(0);self.app.processEvents()
        item=next(item for item in self.w.scene.items() if isinstance(item,Item))
        start=self.w.view.mapFromScene(item.mapToScene(item.handles()['height'].center()));end=start+type(start)(0,30)
        QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        self.app.processEvents();QTest.mouseMove(self.w.view.viewport(),end,30)
        QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);self.app.processEvents()
        self.assertEqual(self.w.form.gadgets[0].height,80);self.w.undo();self.assertEqual(self.w.form.gadgets[0].height,50)
        self.w.form.gadgets[0].width=800
        with self.assertRaises(ValueError):self.w.form.validate()

    def test_image_and_image_option_move_below_top_and_clamp_to_bottom(self):
        for kind in ('paragraph','option'):
            for nested in (False,True):
                with self.subTest(kind=kind,nested=nested):
                    gadgets=[Gadget(kind='frame',name='group',x=3,y=2,width=35,height=12)] if nested else []
                    image=Gadget(kind=kind,name='image',display_mode='PIXMAP',width=100,height=50,
                                 x=2,y=1,parent='group' if nested else '')
                    gadgets.append(image);self.load(Form(gadgets=gadgets),len(gadgets)-1)
                    item=next(item for item in self.w.scene.items() if isinstance(item,Item) and item.gadget is image)
                    ox,oy=preview_offset(self.w.form,image)
                    item.setPos((ox+5)*SX,(oy+6)*SY)
                    self.assertEqual(item.pos().y(),(oy+6)*SY)
                    self.assertEqual(item.pos().x(),(ox+5)*SX)
                    item.setPos(item.pos().x(),10000)
                    self.assertAlmostEqual(item.pos().y(),self.w.form.height*SY-50)
                    item.setPos((ox+2)*SX,(oy+1)*SY)
                    start=self.w.view.mapFromScene(item.mapToScene(item.boundingRect().center()))
                    end=start+type(start)(SX*3,SY*3)
                    QTest.mousePress(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
                    QTest.mouseMove(self.w.view.viewport(),end,30)
                    QTest.mouseRelease(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end)
                    self.app.processEvents()
                    moved=self.w.form.gadgets[-1]
                    self.assertEqual((moved.x,moved.y),(5,4))
                    self.w.form.validate()
                    self.assertIn('AT X 5 Y 4',self.w.form.pml(normalize=False))
                    self.w.undo();self.assertEqual((self.w.form.gadgets[-1].x,self.w.form.gadgets[-1].y),(2,1))

    def test_tab_editor_switches_pages_and_adds_to_active_page(self):
        w=self.w
        self.load(Form(gadgets=[Gadget(kind='frame',name='tabs',frame_style='TABSET',width=40,height=12)]))
        w.add_page_button.click()
        first=w.form.gadgets[-1]
        self.assertEqual((first.parent,first.x,first.y,first.width,first.height),('tabs',0,0,40,12))
        w.add('button');button=w.form.gadgets[-1]
        self.assertEqual(button.parent,first.name)
        w.add_page_button.click();second=w.form.gadgets[-1]
        self.assertTrue(w.objects.item(1).isHidden());self.assertTrue(w.objects.item(3).isHidden())
        w.add('text');text=w.form.gadgets[-1]
        self.assertEqual(text.parent,second.name)
        def visible(name):
            return next(item for item in w.scene.items() if isinstance(item,Item) and item.gadget.name==name).isVisible()
        self.assertFalse(visible(button.name));self.assertTrue(visible(text.name))
        original=w.form.dumps();history=len(w.history)
        w.page_tabs.setCurrentIndex(0)
        self.assertTrue(visible(button.name));self.assertFalse(visible(text.name))
        self.assertEqual(w.form.dumps(),original);self.assertEqual(len(w.history),history)
        w.choose_row(0);w.add('toggle')
        self.assertEqual(w.form.gadgets[-1].parent,first.name)
        w.form.validate()
        w.undo();self.assertEqual(w.form.dumps(),original)
        w.choose_row(4)
        self.assertEqual(w.page_tabs.currentIndex(),1)
        self.assertTrue(visible(text.name));self.assertFalse(visible(button.name))

    def test_tab_settings_reorder_delete_and_undo(self):
        w=self.w
        self.load(Form(gadgets=[Gadget(kind='frame',name='tabs',frame_style='TABSET',width=40,height=12)]))
        w.add_page_button.click();first=w.form.gadgets[-1].name
        w.add_page_button.click();second=w.form.gadgets[-1].name
        w.update_page(first,'settings','設定')
        self.assertEqual(w.form.named('tabs').tabs[0].label,'設定')
        original=w.form.dumps();history=len(w.history)
        w.update_page('settings',second,'重複')
        self.assertEqual(w.form.dumps(),original);self.assertEqual(len(w.history),history)
        w.page_tabs.moveTab(0,1)
        self.assertEqual([g.name for g in w.form.named('tabs').tabs],[second,'settings'])
        w.undo();self.assertEqual(w.form.dumps(),original)
        w.tabset_picker.setCurrentIndex(w.tabset_picker.findData('tabs'))
        w.page_tabs.setCurrentIndex(1);w.delete_page_button.click()
        self.assertEqual(len(w.form.named('tabs').tabs),1)
        w.undo();self.assertEqual(w.form.dumps(),original)

    def test_blank_selection_keeps_tab_placement_and_form_target_is_explicit(self):
        w=self.w
        self.load(Form(gadgets=[Gadget(kind='frame',name='tabs',frame_style='TABSET',width=40,height=12)]))
        w.add_page_button.click();page=w.form.gadgets[-1].name
        w.choose_row(-1);w.add('button')
        self.assertEqual(w.form.gadgets[-1].parent,page)
        w.tabset_picker.setCurrentIndex(0);w.add('button')
        self.assertEqual(w.form.gadgets[-1].parent,'')
        w.choose_row(0);w.fields['width'].setValue(50);w.fields['height'].setValue(14)
        self.assertEqual(w.form.geometry(w.form.named(page)),(0,0,50,14))
        w.form.validate()

    def test_double_click_canvas_and_list_changes_label_only(self):
        w=self.w
        self.load(Form(gadgets=[Gadget(name='first',x=2,y=2),Gadget(name='second',x=20,y=2)],default_body='!this.first.val = 1'))
        item=next(item for item in w.scene.items() if isinstance(item,Item) and item.gadget.name=='first')
        point=w.view.mapFromScene(item.mapToScene(item.boundingRect().center()))
        with patch('e3d_designer.app.QInputDialog.getText',return_value=('renamed',True)) as dialog:
            QTest.mouseDClick(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,point)
            self.app.processEvents();dialog.assert_called_once()
        self.assertEqual(w.form.gadgets[0].label,'renamed')
        self.assertEqual(w.form.gadgets[0].name,'first')
        self.assertEqual(w.form.default_body,'!this.first.val = 1')
        point=w.objects.visualItemRect(w.objects.item(0)).center()
        with patch('e3d_designer.app.QInputDialog.getText',return_value=('listed',True)) as dialog:
            QTest.mouseClick(w.objects.viewport(),Qt.LeftButton,Qt.NoModifier,point)
            QTest.mouseDClick(w.objects.viewport(),Qt.LeftButton,Qt.NoModifier,point)
            self.app.processEvents();dialog.assert_called_once()
        self.assertEqual(w.form.gadgets[0].label,'listed')
        self.assertEqual(w.form.gadgets[0].name,'first')
        self.assertEqual(w.form.default_body,'!this.first.val = 1')
        w.undo();self.assertEqual(w.form.gadgets[0].label,'renamed')
        original=w.form.dumps();history=len(w.history)
        for result in (('$bad',True),('bad\nlabel',True),('ignored',False),('renamed',True)):
            with patch('e3d_designer.app.QInputDialog.getText',return_value=result):w.edit_object_label('first')
            self.assertEqual(w.form.dumps(),original);self.assertEqual(len(w.history),history)

        for label in ('Run',''):
            with patch('e3d_designer.app.QInputDialog.getText',return_value=(label,True)):w.edit_object_label('first')
            self.assertEqual(w.form.gadgets[0].name,'first')
            self.assertEqual(w.form.gadgets[0].label,label)
            w.undo();self.assertEqual(w.form.dumps(),original)

    def test_inspector_pages_and_separate_menu_editor(self):
        w=self.w;w.add('button')
        self.assertEqual([w.inspector_tabs.tabText(i) for i in range(w.inspector_tabs.count())],['部品','フォーム','処理'])
        self.assertEqual([w.props.tabText(i) for i in range(w.props.count())],['基本','配置','内容','動作'])
        self.assertEqual(w.inspector_tabs.findChildren(QScrollArea),[])
        self.assertFalse(w.menu_dialog.isVisible())
        w.palette_buttons['menubar'].click();self.app.processEvents()
        self.assertTrue(w.menu_dialog.isVisible())
        self.assertIs(w.menu_group.parentWidget(),w.menu_dialog)
        self.assertNotIn(w.menu_group,w.inspector_tabs.findChildren(type(w.menu_group)))
        w.add_menu_item();w.menu_dialog.close()
        original=w.form.dumps();history=len(w.history)
        w.palette_buttons['menubar'].click();self.app.processEvents()
        self.assertEqual(w.form.dumps(),original);self.assertEqual(len(w.history),history)
        w.dirty=False;w.close();self.assertFalse(w.menu_dialog.isVisible())

    def test_inspector_fits_requested_window_height_for_gadget_categories(self):
        w=self.w
        for kind in ('button','text','list','option','view','container','slider','textpane'):
            with self.subTest(kind=kind):
                w.add(kind);self.app.processEvents()
                self.assertLessEqual(w.height(),880)
                self.assertLess(w.inspector_tabs.minimumSizeHint().height(),750)

    def drag_object(self,name,x,y):
        w=self.w
        item=next(item for item in w.scene.items() if isinstance(item,Item) and item.gadget.name==name)
        start=w.view.mapFromScene(item.mapToScene(item.boundingRect().center()))
        end=start+type(start)(round(x*SX-item.pos().x()),round(y*SY-item.pos().y()))
        QTest.mousePress(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        QTest.mouseMove(w.view.viewport(),end,30)
        QTest.mouseRelease(w.view.viewport(),Qt.LeftButton,Qt.NoModifier,end)
        self.app.processEvents()

    def test_drag_changes_parent_and_rebases_local_coordinates_with_undo(self):
        w=self.w
        self.load(Form(gadgets=[Gadget(kind='frame',name='group',x=10,y=3,width=20,height=10),
                               Gadget(name='run',x=2,y=1,width=8)]),1)
        original=w.form.dumps()
        self.drag_object('run',12,5)
        g=w.form.named('run')
        self.assertEqual((g.parent,g.x,g.y),('group',2,2))
        self.assertIn("BUTTON .run AT X 2 Y 2",w.form.pml(normalize=False))
        inside=w.form.dumps()
        self.drag_object('run',45,15)
        g=w.form.named('run');self.assertEqual((g.parent,g.x,g.y),('',45,15))
        w.undo();self.assertEqual(w.form.dumps(),inside)
        w.undo();self.assertEqual(w.form.dumps(),original)
        self.drag_object('run',25,5)
        self.assertEqual(w.form.named('run').parent,'') # Center is inside, right edge is outside.

    def test_slider_drag_moves_only_pressed_object_even_with_stale_multi_selection(self):
        w=self.w
        self.load(Form(gadgets=[Gadget(kind='slider',name='level',x=2,y=2,width=8),Gadget(name='run',x=20,y=2,width=8)]))
        for item in w.scene.items():
            if isinstance(item,Item):item.setSelected(True)
        self.app.processEvents()
        self.assertEqual(len(w.scene.selectedItems()),2)
        original=w.form.dumps();history=len(w.history)
        self.drag_object('level',5,5)
        self.assertEqual((w.form.named('level').x,w.form.named('level').y),(5,5))
        self.assertEqual((w.form.named('run').x,w.form.named('run').y),(20,2))
        self.assertEqual(len(w.history),history+1)
        w.undo();self.assertEqual(w.form.dumps(),original)

    def test_radio_auto_group_and_reject_root_drop(self):
        w=self.w;w.add('rtoggle')
        self.assertEqual(len(w.form.gadgets),2)
        group,radio=w.form.gadgets
        self.assertEqual(radio.parent,group.name)
        self.assertIn('RTOGGLE .'+radio.name,w.form.pml(normalize=False))
        self.drag_object(radio.name,2,2)
        original=w.form.dumps();history=len(w.history)
        self.drag_object(radio.name,40,15)
        self.assertEqual(w.form.dumps(),original);self.assertEqual(len(w.history),history)
        w.undo();w.undo();self.assertEqual(w.form.gadgets,[])

    def test_new_slider_button_and_radios_do_not_overlap_when_frame_has_space(self):
        w=self.w
        self.load(Form(gadgets=[Gadget(kind='frame',name='group',x=4,y=2,width=30,height=10)]))
        for kind in ('button','slider','rtoggle','rtoggle'):w.add(kind)
        children=w.form.children('group')
        self.assertEqual([g.y for g in children],[1,2.5,4,5.5])
        self.assertEqual([g.parent for g in children],['group']*4)
        w.form.validate()

    def test_nested_frame_drop_uses_deepest_frame_origin(self):
        w=self.w
        self.load(Form(gadgets=[Gadget(kind='frame',name='outer',x=10,y=2,width=30,height=15),
                               Gadget(kind='frame',name='inner',parent='outer',x=3,y=4,width=20,height=8),
                               Gadget(name='run',x=1,y=1,width=5)]),2)
        self.drag_object('run',15,8)
        g=w.form.named('run')
        self.assertEqual((g.parent,g.x,g.y),('inner',2,2))
        self.assertEqual(w.form.offset(g),(13,6))

    def test_full_frame_addition_preserves_form_and_full_undo_redo_history(self):
        w=self.w
        self.load(Form(gadgets=[Gadget(kind='frame',name='group',x=0,y=0,width=18,height=2),
                               Gadget(name='run',parent='group',x=0,y=1,width=18)]))
        w.history=[Form(title=f'History {i}') for i in range(100)]
        w.future=[Form(title='Redo')];w.dirty=False
        original=w.form.dumps();history=[g.dumps() for g in w.history];future=[g.dumps() for g in w.future]
        w.add('button')
        self.assertEqual(w.form.dumps(),original)
        self.assertEqual([g.dumps() for g in w.history],history)
        self.assertEqual([g.dumps() for g in w.future],future)
        self.assertFalse(w.dirty)
        self.assertIn('空きがありません',w.statusBar().currentMessage())

    def test_context_hints_and_empty_property_tab_switch(self):
        w=self.w;w.add('list');w.props.setCurrentIndex(2)
        self.assertTrue(w.props.isTabEnabled(2))
        w.add('button')
        self.assertFalse(w.props.isTabEnabled(2));self.assertEqual(w.props.currentIndex(),0)
        self.assertIn('.'+w.form.gadgets[-1].name,w.selection_hint.text())
        self.assertIn('フォーム直下',w.placement_hint.text())
        w.choose_row(-1);self.assertIn('部品を選択',w.selection_hint.text())
        w.add('rtoggle');group=w.form.gadgets[-2];radio=w.form.gadgets[-1]
        self.assertGreaterEqual(radio.y,1)
        self.assertIn(group.name,w.placement_hint.text())
        self.assertIn(group.name,w.selection_hint.text())

    def test_full_form_addition_does_not_overlap_existing_object(self):
        w=self.w
        self.load(Form(width=18,height=1,gadgets=[Gadget(name='run',x=0,y=0,width=18)]))
        w.choose_row(-1);original=w.form.dumps();history=len(w.history)
        w.add('button')
        self.assertEqual(w.form.dumps(),original);self.assertEqual(len(w.history),history)
        self.assertIn('空きがありません',w.statusBar().currentMessage())

    def test_exact_fit_is_available_when_borders_touch_without_overlap(self):
        w=self.w
        self.load(Form(width=36,height=1,gadgets=[Gadget(name='run',x=0,y=0,width=18)]))
        w.choose_row(-1);w.add('button')
        self.assertEqual(len(w.form.gadgets),2)
        self.assertEqual((w.form.gadgets[-1].x,w.form.gadgets[-1].y),(18,0))
        w.form.validate()


if __name__ == '__main__':unittest.main()
