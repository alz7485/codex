import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window,Item,SX,SY,preview_offset
from e3d_designer.clipboard import clone_subtree
from e3d_designer.model import Form,Gadget,Menu,MenuItem


class CloneRegressionTests(unittest.TestCase):
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
                    parent_height=12 if nested else self.w.form.height
                    item.setPos(item.pos().x(),10000)
                    self.assertAlmostEqual(item.pos().y(),(oy+parent_height)*SY-50)
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


if __name__ == '__main__':unittest.main()
