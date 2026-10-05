import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import json
import sys
from unittest.mock import patch
import unittest
from pathlib import Path
from PySide6.QtCore import Qt, QPoint, QEvent, QCoreApplication, QTimer, QModelIndex
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.model import Form, Gadget, Menu, MenuItem, literal
from e3d_designer.app import Window, atomic_write, SX, SY


class ModelTests(unittest.TestCase):
    def test_list_background_precedes_position(self):
        listing=Gadget(kind='list',name='results',label='Results',background='5',height=4)
        form=Form(gadgets=[listing]);pml=Form.loads(form.dumps()).pml()
        self.assertIn("list .results BACKGROUND 5 AT X 2 Y 1 'Results' SINGLE WIDTH 14 HEIGHT 4",pml)
        listing.list_mode='TABLE';listing.headings=['Name'];listing.rows=[['Pump']]
        self.assertIn('list .results BACKGROUND 5 AT X 2 Y 1',form.pml())
        for invalid in ('-1','5.5','5 AT X 10'):
            listing.background=invalid
            with self.subTest(value=invalid),self.assertRaises(ValueError): form.pml()
        listing.background=''
        self.assertNotIn('BACKGROUND',form.pml())

    def test_view_aspect_export_validation_and_legacy_default(self):
        view=Gadget(kind='view',name='model',width=30,height=8,view_aspect='1.5')
        form=Form(gadgets=[view]);pml=Form.loads(form.dumps()).pml()
        self.assertIn('WIDTH 30 HEIGHT 8 ASPECT 1.5',pml)
        for value in ('0','-1','nan','inf','command',None,1.5):
            view.view_aspect=value
            with self.subTest(value=value),self.assertRaises(ValueError): form.pml()
        view.view_aspect=''
        raw=json.loads(form.dumps());del raw['form']['gadgets'][0]['view_aspect']
        self.assertNotIn('ASPECT',Form.loads(json.dumps(raw)).pml())

    def test_simple_multiple_list_and_legacy_selection(self):
        listing=Gadget(kind='list',name='results',label='Results',selection_mode='MULTIPLE',width=20,height=4,items=['First','Second'])
        pml=Form(gadgets=[listing]).pml()
        self.assertIn("list .results AT X 2 Y 1 'Results' MULTIPLE WIDTH 20 HEIGHT 4",pml)
        self.assertIn("!choices[1] = 'First'",pml)
        self.assertIn("!choices[2] = 'Second'",pml)
        self.assertIn('!this.results.dtext = !choices',pml)
        self.assertNotIn('setheadings',pml)
        raw=json.loads(Form(gadgets=[listing]).dumps());raw['form']['gadgets'][0]['selection_mode']='MULTI'
        loaded=Form.loads(json.dumps(raw))
        self.assertEqual(loaded.gadgets[0].selection_mode,'MULTIPLE')
        self.assertIn('MULTIPLE WIDTH 20 HEIGHT 4',loaded.pml())

    def test_table_list_arrays_method_and_dimensions(self):
        table=Gadget(kind='list',name='equipment',list_mode='TABLE',table_method='fillEquipment',
                     height=5,headings=['Name','Type'],rows=[['P-101','Pump'],['T-201','Tank']])
        form=Form(gadgets=[table]);pml=Form.loads(form.dumps()).pml()
        self.assertIn("list .equipment AT X 2 Y 1 'Run' SINGLE WIDTH 14 HEIGHT 5",pml)
        self.assertIn('!this.fillEquipment()',pml)
        self.assertIn("define method .fillEquipment()\n  !HEAD = ARRAY()\n  !HEAD[1] = 'Name'\n  !HEAD[2] = 'Type'\n  !THIS.equipment.setheadings(!HEAD)",pml)
        self.assertIn("!ROWS[1] = ARRAY()\n  !ROWS[1][1] = 'P-101'\n  !ROWS[1][2] = 'Pump'",pml)
        self.assertIn("!ROWS[2] = ARRAY()\n  !ROWS[2][1] = 'T-201'\n  !ROWS[2][2] = 'Tank'",pml)
        self.assertIn('!THIS.equipment.setrows(!ROWS)',pml)
        self.assertLess(pml.index('SHOW !!'),pml.index('define method .fillEquipment()'))
        self.assertNotIn('.dtext',pml)
        table.selection_mode='MULTI';self.assertIn("'Run' MULTIPLE",form.pml())
        table.rows=[];self.assertIn('!ROWS = ARRAY()\n  !THIS.equipment.setrows(!ROWS)',form.pml())

    def test_table_validation_and_method_collision(self):
        table=Gadget(kind='list',name='equipment',list_mode='TABLE',headings=['A','B'],rows=[['1','2']])
        form=Form(gadgets=[table])
        for key,value in [('headings',[]),('headings','A'),('rows',[['one']]),('rows',[['a',1]]),('rows','bad'),('rows',[['a\nb','c']]),('table_method','default'),('table_method','bad name')]:
            old=getattr(table,key);setattr(table,key,value)
            with self.subTest(key=key),self.assertRaises(ValueError): form.pml()
            setattr(table,key,old)
        form.gadgets.append(Gadget(name='run',callback='populate_equipment'))
        with self.assertRaises(ValueError): form.pml()

    def test_menu_export_and_legacy_roundtrip(self):
        form = Form(menus=[Menu(name='tools',items=[MenuItem('Run','!this.run()'),MenuItem('Show','$p !!value')]),Menu(name='other')])
        pml = Form.loads(form.dumps()).pml()
        self.assertIn("  menu .tools\n    add 'Run' '!this.run()'\n    add 'Show' '$p !!value'\n  exit",pml)
        self.assertIn('  menu .other\n  exit',pml)
        raw = json.loads(form.dumps()); del raw['form']['menus']
        self.assertEqual(Form.loads(json.dumps(raw)).menus,[])

    def test_invalid_menu_names_and_items(self):
        for menus in ([Menu(name='bad name')], [Menu(name='tools'),Menu(name='TOOLS')],
                      [Menu(items=[MenuItem('bad\nlabel','run')])],
                      [Menu(items=[MenuItem('Run',123)])]):
            with self.subTest(menus=menus),self.assertRaises(ValueError): Form(menus=menus).pml()
        with self.assertRaises(ValueError): Form(menus=[Menu(name='button1')],gadgets=[Gadget()]).pml()
        raw=json.loads(Form(menus=[Menu(items=[MenuItem()])]).dumps())
        for value in (None,'not an array',[{'name':'menu1','items':[{'label':1,'command':'run'}]}]):
            changed=json.loads(json.dumps(raw));changed['form']['menus']=value
            with self.subTest(value=value),self.assertRaises(ValueError): Form.loads(json.dumps(changed))

    def test_list_position_precedes_label_in_each_layout_mode(self):
        base=Gadget(name='base',x=2,y=1)
        listing=Gadget(kind='list',name='results',label='Results',x=4,y=5,width=20,height=3,callback='onSelect')
        form=Form(gadgets=[base,listing])
        self.assertIn("list .results AT X 4 Y 5 'Results' SINGLE WIDTH 20 HEIGHT 3 callback '!this.onSelect()'",form.pml())
        listing.layout_mode='RELATIVE';listing.xref='base';listing.yref='base';listing.width_ref='base'
        self.assertIn("list .results AT XMIN.base YMAX.base+0.5 'Results' SINGLE WIDTH.base HEIGHT 3",form.pml())
        listing.layout_mode='AUTO'
        line=next(line for line in form.pml().splitlines() if 'list .results' in line)
        self.assertNotIn('AT ',line)
        self.assertIn("'Results' SINGLE WIDTH.base HEIGHT 3",line)

    def test_slider_export_open_callback_and_bounds(self):
        slider=Gadget(kind='slider',name='level',slider_min=-10,slider_max=90,slider_step=5,slider_value=30,
                      callback='onLevel',body='  q var !event')
        f=Form(gadgets=[slider]);pml=Form.loads(f.dumps()).pml()
        self.assertIn('HORIZONTAL RANGE -10 90 STEP 5 VAL 30',pml)
        self.assertIn("!this.level.callback = '!this.onLevel('",pml)
        self.assertIn('define method .onLevel(!gad is GADGET, !event is STRING)',pml)
        slider.slider_orientation='VERTICAL';slider.height=8
        self.assertIn('HEIGHT 8',f.pml())
        for field,value in [('slider_min',90),('slider_step',0),('slider_value',100)]:
            old=getattr(slider,field);setattr(slider,field,value)
            with self.assertRaises(ValueError): f.pml()
            setattr(slider,field,old)
        f.gadgets.append(Gadget(name='run',callback='onLevel',body=slider.body))
        with self.assertRaisesRegex(ValueError,'分けて'): f.pml()
        f.gadgets.pop();slider.callback='default'
        with self.assertRaises(ValueError): f.pml()

    def test_radio_group_export_and_parent_validation(self):
        group=Gadget(kind='frame',name='group',width=24,height=6)
        radios=[Gadget(kind='rtoggle',name=name,parent='group',y=i*2+1,on_value=value)
                for i,(name,value) in enumerate([('pump','PUMP'),('tank','TANK')])]
        f=Form(gadgets=[group,*radios]);pml=Form.loads(f.dumps()).pml()
        self.assertIn("RTOGGLE .pump 'Run' AT X 2 Y 1 STATES '' 'PUMP'",pml)
        self.assertLess(pml.index('FRAME .group'),pml.index('RTOGGLE .pump'))
        radios[0].parent=''
        with self.assertRaisesRegex(ValueError,'FRAME'): f.pml()
        radios[0].parent='group';radios[0].callback='onRadio'
        with self.assertRaises(ValueError): f.pml()

    def test_list_combo_display_real_values_and_multiselect(self):
        gadgets=[Gadget(kind=kind,name=kind+'1',y=i*5,items=['Pump','Tank'],item_values=['/P-1','/T-1'])
                 for i,kind in enumerate(('list','combo'))]
        gadgets[0].selection_mode='MULTI';gadgets[0].height=3
        f=Form(gadgets=gadgets);pml=Form.loads(f.dumps()).pml()
        self.assertIn("list .list1 AT X 2 Y 0 'Run' MULTIPLE",pml)
        self.assertIn('COMBO .combo1',pml)
        self.assertIn("!values[1] = '/P-1'",pml)
        for g in gadgets:
            self.assertIn(f'!this.{g.name}.dtext = !choices',pml)
            self.assertIn(f'!this.{g.name}.rtext = !values',pml)
        gadgets[1].combo_keyword='COMBOBOX'
        self.assertIn('COMBOBOX .combo1',f.pml())
        gadgets[0].item_values=['only one']
        with self.assertRaisesRegex(ValueError,'行数'): f.pml()

    def test_views_channels_and_container_connection(self):
        model=Gadget(kind='view',name='model',height=5,view_code='LIMITS AUTO\nISOMETRIC 3')
        alpha=Gadget(kind='commandline',name='commands',y=7,height=5,channels='COMMANDS')
        host=Gadget(kind='container',name='grid',y=14,height=5,assembly='uGrid',namespace='Aveva.Gadgets.uGrid',control_type='userGrid')
        f=Form(gadgets=[model,alpha,host]);pml=Form.loads(f.dumps()).pml()
        self.assertIn('VIEW .model AT X 2 Y 1 VOLUME',pml)
        self.assertIn('LIMITS AUTO\n    ISOMETRIC 3\n  EXIT',pml)
        self.assertIn('VIEW .commands AT X 2 Y 7 ALPHA',pml)
        self.assertIn('CHANNEL COMMANDS',pml);self.assertNotIn('CHANNEL REQUESTS',pml)
        self.assertIn("import 'uGrid'",pml)
        self.assertIn("using namespace 'Aveva.Gadgets.uGrid'",pml)
        self.assertIn('member .gridControl is userGrid',pml)
        self.assertIn('CONTAINER .grid AT X 2 Y 14 PMLNETCONTROL',pml)
        self.assertIn('!this.grid.Control = !this.gridControl.handle()',pml)
        host.namespace=''
        with self.assertRaises(ValueError): f.pml()
        host.namespace='Aveva.Gadgets.uGrid';host.control_type='userGrid()'
        with self.assertRaises(ValueError): f.pml()
        host.control_type='userGrid';f.gadgets.append(Gadget(name='gridControl'))
        with self.assertRaisesRegex(ValueError,'重複'): f.pml()

    def test_new_gadget_json_types_and_legacy_defaults(self):
        raw=json.loads(Form(gadgets=[Gadget()]).dumps())
        for key,value in [('slider_value',True),('slider_step',float('nan')),('item_values','bad'),('item_values',[1]),('channels',None)]:
            changed=json.loads(json.dumps(raw));changed['form']['gadgets'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): Form.loads(json.dumps(changed))
        for key in ('item_values','slider_min','slider_max','slider_step','slider_value','channels'):
            del raw['form']['gadgets'][0][key]
        self.assertEqual(Form.loads(json.dumps(raw)).gadgets[0].slider_value,50)

    def test_relative_layout_order_geometry_and_roundtrip(self):
        base = Gadget(name='base', x=10, y=5, width=14, height=2)
        follower = Gadget(name='follower', layout_mode='RELATIVE', xref='base', yref='base',
                          xedge='XMAX', xanchor='RIGHT', xoffset=-1, yoffset=1,
                          width=8)
        form = Form(gadgets=[follower,base])
        self.assertEqual(form.geometry(follower), (15,8,8,1))
        pml = Form.loads(form.dumps()).pml()
        self.assertIn('AT XMAX.base-SIZE-1 YMAX.base+1',pml)
        self.assertLess(pml.index('BUTTON .base'),pml.index('BUTTON .follower'))
        follower.width_ref='base'
        self.assertEqual(form.geometry(follower), (9,8,14,1))
        self.assertIn('WIDTH.base',form.pml())
        base.width=18
        self.assertEqual(form.geometry(follower), (9,8,18,1))

    def test_auto_alignment_and_path(self):
        base=Gadget(name='base',x=20,y=10,width=14,height=4)
        follower=Gadget(name='follower',layout_mode='AUTO',width=8,height=2,vgap=1,hgap=2)
        form=Form(gadgets=[base,follower])
        for alignment,x in [('LEFT',20),('CENTRE',23),('RIGHT',26)]:
            follower.halign=alignment
            self.assertEqual(form.geometry(follower),(x,15,8,2))
            self.assertIn('HALIGN '+alignment,form.pml())
        follower.path='UP'
        self.assertEqual(form.geometry(follower),(26,7,8,2))
        follower.path='RIGHT'; follower.valign='BOTTOM'
        self.assertEqual(form.geometry(follower),(36,12,8,2))
        follower.path='LEFT'; follower.valign='CENTRE'
        self.assertEqual(form.geometry(follower),(10,11,8,2))
        self.assertIn('PATH LEFT',form.pml())

    def test_invalid_layout_references_and_export_order(self):
        base=Gadget(name='base')
        other=Gadget(name='other',y=5)
        follower=Gadget(name='follower',layout_mode='RELATIVE',xref='base',yref='base')
        form=Form(gadgets=[base,other,follower])
        for reference in ('missing','follower'):
            follower.xref=reference
            with self.assertRaises(ValueError): form.pml()
        follower.xref='base';base.width_ref='follower'
        with self.assertRaises(ValueError): form.pml()
        base.width_ref=''; follower.layout_mode='AUTO';follower.width_ref='other'
        form.gadgets=[base,follower,other]
        with self.assertRaisesRegex(ValueError,'直前'): form.pml()
        form.gadgets=[follower]
        with self.assertRaises(ValueError): form.pml()
        form.gadgets=[base,other];other.kind='toggle';other.width_ref='base'
        with self.assertRaisesRegex(ValueError,'幅参照'): form.pml()

    def test_malformed_project_field_types_are_rejected(self):
        base=json.loads(Form(gadgets=[Gadget(callback='run')]).dumps())
        for key,value in [('body',123),('parent',123),('label',None),('items','ABC'),('item_commands',[123]),('width','10')]:
            with self.subTest(key=key):
                raw=json.loads(json.dumps(base));raw['form']['gadgets'][0][key]=value
                with self.assertRaises(ValueError): Form.loads(json.dumps(raw))

    def test_full_form_roundtrip_and_export(self):
        f = Form(gadgets=[Gadget(kind=k, name=k+'1', y=i*2, height=1,
                items=['A','B'] if k in ('option','list') else [],
                callback='runAction' if k=='button' else '',
                body="  $p 'clicked'" if k=='button' else '')
                for i,k in enumerate(('button','paragraph','text','toggle','option','list'))])
        f.gadgets[2].value_type='REAL'; f.gadgets[2].initial='12.5'
        pml=Form.loads(f.dumps()).pml()
        self.assertIn("CALL '!this.runAction()'",pml)
        self.assertIn('!this.text1.val = 12.5',pml)
        self.assertIn("OPTION _option1",pml)
        self.assertIn("CALL '$$_option1'",pml)
        self.assertIn("VAR LIST _option1 PAIRS",pml)
        self.assertIn('list .list1',pml)
        self.assertIn('HEIGHT 1',pml)
        self.assertEqual(pml.count('define method .runAction()'),1)
        self.assertIn("  $p 'clicked'",pml)

    def test_variables_before_kill_and_form_definition(self):
        f = Form(variables={'projectName':'Project A', 'mode':'Default'})
        pml = Form.loads(f.dumps()).pml()
        self.assertTrue(pml.startswith("VAR !!projectName 'Project A'\nVAR !!mode 'Default'\nkill !!userform\n"))
        self.assertLess(pml.index('kill !!userform'), pml.index('setup form'))
        self.assertIn('setup form !!userform DIALOG DOCK RIGHT',pml)
        self.assertIn('size 70 22 DIALOG',Form(dock_right=False).pml())
        with self.assertRaises(ValueError): Form(variables={'userform':'bad'}).pml()

    def test_line_orientations_and_roundtrip(self):
        for orientation in ('HORIZ', 'VERT'):
            f=Form(gadgets=[Gadget(kind='line',name='separator',label='',x=2,y=3,width=20,height=2,orientation=orientation)])
            self.assertIn(f"LINE .separator AT X 2 Y 3 '' {orientation} WIDTH 20 HEIGHT 2",Form.loads(f.dumps()).pml())
        f.gadgets[0].orientation='INVALID'
        with self.assertRaises(ValueError): f.pml()

    def test_paragraph_background_syntax(self):
        f=Form(gadgets=[Gadget(kind='paragraph',name='message',label='Message',x=2,y=3,background='5')])
        self.assertIn("PARAGRAPH .message AT X 2 Y 3 BACKGROUND 5 TEXT 'Message' WIDTH 14",Form.loads(f.dumps()).pml())
        f.gadgets[0].background='5 TEXT hacked'
        with self.assertRaises(ValueError): f.pml()
        f.gadgets[0].background=''
        self.assertNotIn('BACKGROUND',f.pml())
        self.assertIn("PARAGRAPH .message AT X 2 Y 3 TEXT 'Message' WIDTH 14",f.pml())

    def test_tabset_frame_syntax_and_validation(self):
        f=Form(gadgets=[Gadget(kind='frame',frame_style='TABSET',name='tabs',label='TABSET',x=2,y=3,width=40)])
        self.assertIn("FRAME .tabs TABSET AT X 2 Y 3 'TABSET' WIDTH 40\n  EXIT",Form.loads(f.dumps()).pml())
        f.gadgets[0].frame_style='INVALID'
        with self.assertRaises(ValueError): f.pml()
        f.gadgets[0].frame_style='TABSET'; f.gadgets[0].kind='button'
        with self.assertRaises(ValueError): f.pml()

    def test_nested_tabset_frames_and_relative_coordinates(self):
        f=Form(gadgets=[
            Gadget(kind='button',name='run',label='Run',parent='page1',x=1,y=1),
            Gadget(kind='frame',frame_style='TABSET',name='tabs',label='TABSET',x=2,y=3,width=50,height=15),
            Gadget(kind='frame',name='page1',label='Page 1',parent='tabs',width=45,height=12),
            Gadget(kind='frame',name='page2',label='Page 2',parent='tabs',width=45,height=12)])
        restored=Form.loads(f.dumps())
        pml=restored.pml()
        self.assertIn("  FRAME .tabs TABSET AT X 2 Y 3 'TABSET' WIDTH 50\n    FRAME .page1 'Page 1'\n      BUTTON .run AT X 1 Y 1 'Run' WIDTH 14\n    EXIT\n    FRAME .page2 'Page 2'\n    EXIT\n  EXIT\nexit",pml)
        self.assertEqual(restored.offset(restored.gadgets[0]),(4,4)) # page default X=2, Y=1
        restored.gadgets[0].parent='tabs'
        with self.assertRaises(ValueError): restored.pml()

    def test_parent_validation_cycles_missing_and_bounds(self):
        for gadgets in ([Gadget(parent='missing')],
            [Gadget(kind='frame',name='a',parent='b'),Gadget(kind='frame',name='b',parent='a')],
            [Gadget(kind='frame',name='f',width=5,height=5),Gadget(name='child',parent='f',width=14)]):
            with self.assertRaises(ValueError): Form(gadgets=gadgets).pml()

    def test_empty_frame_closes_before_form_exit(self):
        f=Form(gadgets=[Gadget(kind='frame',name='group1',label='Settings')])
        pml=Form.loads(f.dumps()).pml()
        self.assertIn("  FRAME .group1 'Settings'\n  EXIT\nexit",pml)
        f.gadgets[0].callback='go'
        with self.assertRaises(ValueError): f.pml()

    def test_default_method_body_and_no_duplicate_definition(self):
        f=Form(default_body="$p 'Default'",gadgets=[Gadget(callback='DEFAULT')])
        pml=Form.loads(f.dumps()).pml()
        self.assertIn("DEFINE METHOD .DEFAULT()\n$p 'Default'\nENDMETHOD",pml)
        self.assertEqual(pml.lower().count('define method .default()'),1)
        self.assertLess(pml.index('SHOW !!'),pml.index('define method .userform()'))
        self.assertLess(pml.index('SHOW !!'),pml.index('DEFINE METHOD .DEFAULT()'))
        f.gadgets[0].body='different'
        with self.assertRaises(ValueError): f.pml()

    def test_show_then_program_before_method_definitions(self):
        f=Form(after_show_code="$p 'Ready'",gadgets=[Gadget(callback='onRun')])
        pml=Form.loads(f.dumps()).pml()
        self.assertIn("exit\n\nSHOW !!userform\n\n$p 'Ready'\n\ndefine method .userform()",pml)
        self.assertLess(pml.index('SHOW !!userform'),pml.index('define method .onRun()'))
        self.assertEqual(pml.count('SHOW !!userform'),1)
        f.show_form=False
        self.assertIn('SHOW !!userform',f.pml())
        self.assertIn("$p 'Ready'",f.pml())

    def test_option_pairs_commands_and_existing_underscore(self):
        for name in ('mode','_mode'):
            f=Form(gadgets=[Gadget(kind='option',name=name,label='Mode',x=2,y=3,items=['First','Second','Third'],item_commands=['FIRST','SECOND',"$p 'third'"])])
            self.assertIn("OPTION _mode AT X 2 Y 3 'Mode' CALL '$$_mode'\n  VAR LIST _mode PAIRS\n  'First' 'FIRST'\n  'Second' 'SECOND'\n  'Third' |$p 'third'|\n  EXIT",Form.loads(f.dumps()).pml())
            self.assertNotIn('!this.'+name+'.dtext',f.pml())
        f.gadgets[0].item_commands=['FIRST']
        with self.assertRaises(ValueError): f.pml()
        with self.assertRaises(ValueError):
            Form(gadgets=[Gadget(kind='option',name='mode'),Gadget(kind='option',name='_mode')]).pml()

    def test_button_background_and_call_order(self):
        f=Form(gadgets=[Gadget(kind='button',name='apply',label='Apply',x=2,y=3,width=20,background='5',command='SAVEWORK')])
        self.assertIn("BUTTON .apply AT X 2 Y 3 BACKGROUND 5 'Apply' CALL 'SAVEWORK' WIDTH 20",Form.loads(f.dumps()).pml())
        f.gadgets[0].background=''; f.gadgets[0].command=''; f.gadgets[0].callback='onApply'
        self.assertIn("BUTTON .apply AT X 2 Y 3 'Apply' CALL '!this.onApply()' WIDTH 20",f.pml())
        self.assertIn('define method .onApply()',f.pml())
        f.gadgets[0].callback=''
        self.assertIn("BUTTON .apply AT X 2 Y 3 'Apply' WIDTH 20",f.pml())

    def test_text_call_order_and_types(self):
        for value_type in ('STRING', 'REAL'):
            f=Form(gadgets=[Gadget(kind='text',name='input1',label='Input',x=2,y=3,width=20,value_type=value_type,command='SAVEWORK')])
            self.assertIn(f"TEXT .input1 AT X 2 Y 3 'Input' CALL 'SAVEWORK' WIDTH 20 IS {value_type}",Form.loads(f.dumps()).pml())
        f.gadgets[0].command=''; f.gadgets[0].callback='onInput'
        self.assertIn("CALL '!this.onInput()' WIDTH 20 IS REAL", f.pml())
        self.assertIn('define method .onInput()',f.pml())
        f.gadgets[0].callback=''
        self.assertIn("'Input' WIDTH 20 IS REAL",f.pml())
        self.assertNotIn(' CALL ',f.pml())

    def test_toggle_call_syntax(self):
        f=Form(gadgets=[Gadget(kind='toggle',name='enabled',label='Enabled',x=2,y=7,command="$p 'clicked'")])
        self.assertIn("TOGGLE .enabled AT X 2 Y 7 'Enabled' CALL |$p 'clicked'|",f.pml())
        f.gadgets[0].command=''; f.gadgets[0].callback='toggleAction'
        self.assertIn("CALL '!this.toggleAction()'",f.pml())
        f.gadgets[0].command='SAVEWORK'
        with self.assertRaises(ValueError): f.pml()

    def test_invalid_names_geometry_and_numbers(self):
        for g in (Gadget(name='bad-name'),Gadget(x=100),Gadget(x=float('nan')),
                  Gadget(kind='text',value_type='REAL',initial='inf')):
            with self.assertRaises(ValueError): Form(gadgets=[g]).pml()
        with self.assertRaises(ValueError):
            Form(gadgets=[Gadget(name='Run'),Gadget(name='run')]).pml()
        with self.assertRaises(ValueError): Form.loads('{"version":2}')

    def test_literals_and_callback_conflict(self):
        self.assertEqual(literal("O'Brien"),"|O'Brien|")
        for value in ('$!this.name', 'a\nb', "'|\""):
            with self.assertRaises(ValueError): literal(value)
        with self.assertRaises(ValueError):
            Form(gadgets=[Gadget(name='a',callback='go',body='a'),Gadget(name='b',callback='GO',body='b')]).pml()

    def test_encoding_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'form.pmlfrm'; atomic_write(path,b'old')
            with self.assertRaises(UnicodeEncodeError):
                atomic_write(path,Form(title='😀').pml().encode('cp932'))
            self.assertEqual(path.read_bytes(),b'old')


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self): self.w=Window(); self.w.show(); self.app.processEvents()
    def tearDown(self): self.w.dirty=False; self.w.close(); self.app.processEvents()

    def test_keyboard_copy_paste_cut_delete_and_undo(self):
        self.w.add('frame');self.w.add('button');self.w.choose_row(0)
        self.w.objects.setFocus();self.app.processEvents()
        QTest.keyClick(self.w.objects,Qt.Key_C,Qt.ControlModifier)
        QTest.keyClick(self.w.objects,Qt.Key_V,Qt.ControlModifier);self.app.processEvents()
        self.assertEqual(len(self.w.form.gadgets),4)
        copied = self.w.form.gadgets[self.w.selected]
        self.assertEqual(len(self.w.form.children(copied.name)),1)
        QTest.keyClick(self.w.objects,Qt.Key_Delete);self.app.processEvents()
        self.assertEqual(len(self.w.form.gadgets),2)
        self.w.undo();self.assertEqual(len(self.w.form.gadgets),4)
        self.w.choose_row(0);self.w.objects.setFocus();self.app.processEvents()
        QTest.keyClick(self.w.objects,Qt.Key_X,Qt.ControlModifier);self.app.processEvents()
        self.assertEqual(len(self.w.form.gadgets),2)
        QTest.keyClick(self.w.objects,Qt.Key_V,Qt.ControlModifier);self.app.processEvents()
        self.assertEqual(len(self.w.form.gadgets),4)

    def test_text_shortcuts_do_not_edit_gadgets(self):
        self.w.add('button');editor=self.w.fields['label']
        editor.setFocus();editor.setText('ABC');editor.selectAll();self.app.processEvents()
        QTest.keyClick(editor,Qt.Key_C,Qt.ControlModifier)
        QTest.keyClick(editor,Qt.Key_Delete)
        self.assertEqual(len(self.w.form.gadgets),1);self.assertEqual(editor.text(),'')
        QTest.keyClick(editor,Qt.Key_V,Qt.ControlModifier)
        self.assertEqual(editor.text(),'ABC');self.assertEqual(len(self.w.form.gadgets),1)

    def test_clipboard_snapshot_references_and_invalid_payload(self):
        self.w.form=Form(gadgets=[Gadget(kind='frame',name='group',width=30,height=10),Gadget(name='run',parent='group',command='!this.run.val = !!myform.run.val')])
        self.w.selected=0;self.w.refresh();self.assertTrue(self.w.copy_gadget())
        self.w.form.gadgets[1].label='Changed'
        self.w.paste_gadget();self.assertEqual(len(self.w.form.gadgets),4)
        child=self.w.form.children(self.w.form.gadgets[self.w.selected].name)[0]
        self.assertNotEqual(child.label,'Changed');self.assertIn('!this.'+child.name+'.val',child.command)
        from PySide6.QtCore import QMimeData
        from e3d_designer.app import GADGET_MIME
        data=QMimeData();data.setData(GADGET_MIME,b'{}');self.app.clipboard().setMimeData(data)
        before=self.w.form.dumps();self.w.paste_gadget();self.assertEqual(before,self.w.form.dumps())

    def test_view_aspect_property_edit_and_roundtrip(self):
        self.w.add('view');editor=self.w.fields['view_aspect']
        self.assertTrue(editor.isEnabled())
        editor.setFocus();QTest.keyClicks(editor,'1.5')
        self.assertIn('HEIGHT 5 ASPECT 1.5',self.w.code.toPlainText())
        self.assertEqual(Form.loads(self.w.form.dumps()).gadgets[0].view_aspect,'1.5')
        editor.selectAll();QTest.keyClick(editor,Qt.Key_Backspace)
        self.assertNotIn('ASPECT',self.w.code.toPlainText())
        self.w.selected=None;self.w.refresh();self.w.add('button')
        self.assertFalse(self.w.fields['view_aspect'].isEnabled())

    def test_list_background_property_enabled_and_saved(self):
        self.w.add('list');editor=self.w.fields['background']
        self.assertTrue(editor.isEnabled())
        editor.setFocus();QTest.keyClicks(editor,'5')
        self.assertIn('list .list1 BACKGROUND 5 AT X 0 Y 0',self.w.code.toPlainText())
        self.assertEqual(Form.loads(self.w.form.dumps()).gadgets[0].background,'5')

    def test_menu_edit_save_preview_and_undo(self):
        self.w.add_menu(); self.w.add_menu_item()
        editor=self.w.menu_items.cellWidget(0,0)
        editor.setFocus(); editor.selectAll(); QTest.keyClicks(editor,'Run')
        command=self.w.menu_items.cellWidget(0,1)
        command.setFocus(); QTest.keyClicks(command,'RUN')
        self.assertEqual(self.w.form.menus[0].items[0],MenuItem('Run','RUN'))
        self.assertIs(command,self.w.menu_items.cellWidget(0,1))
        preview=self.w.preview_menu_bar.actions()[0].menu()
        self.assertEqual(preview.actions()[0].text(),'Run')
        with tempfile.TemporaryDirectory() as folder:
            self.w.path=Path(folder)/'menu.json'
            QTest.keyClick(command,Qt.Key_S,Qt.ControlModifier);self.app.processEvents()
            self.assertEqual(Form.loads(self.w.path.read_text()).menus[0].items[0].command,'RUN')
        self.w.delete_menu_item(0);self.assertEqual(self.w.form.menus[0].items,[])
        self.w.undo();self.assertEqual(self.w.form.menus[0].items[0].command,'RUN')
        self.w.delete_menu();self.assertEqual(self.w.form.menus,[])
        self.w.undo();self.assertEqual(len(self.w.form.menus),1)
        self.w.redo();self.assertEqual(self.w.form.menus,[])

    def test_menu_item_actions_reorder_copy_and_roundtrip(self):
        self.w.form=Form(menus=[Menu(name='tools',items=[MenuItem('A','runA'),MenuItem('B','runB')])])
        self.w.refresh()
        actions=self.w.menu_items.cellWidget(0,2).menu().actions()
        self.assertFalse(actions[0].isEnabled())
        actions[1].trigger()
        self.assertEqual([item.label for item in self.w.form.menus[0].items],['B','A'])
        self.assertEqual([action.text() for action in self.w.preview_menus[0].actions()],['B','A'])
        pml=self.w.form.pml();self.assertLess(pml.index("add 'B'"),pml.index("add 'A'"))
        self.w.menu_items.cellWidget(1,2).menu().actions()[2].trigger()
        self.assertEqual([item.label for item in self.w.form.menus[0].items],['B','A','A'])
        copied=self.w.menu_items.cellWidget(2,0);copied.setFocus();copied.selectAll();QTest.keyClicks(copied,'Copy')
        self.assertEqual(self.w.form.menus[0].items[1].label,'A')
        self.assertEqual(Form.loads(self.w.form.dumps()).menus[0].items[2],MenuItem('Copy','runA'))
        self.w.menu_items.cellWidget(2,2).menu().actions()[3].trigger()
        self.assertEqual(len(self.w.form.menus[0].items),2)
        self.w.undo();self.assertEqual(self.w.form.menus[0].items[2].label,'Copy')

    def test_menu_duplicate_order_controls_and_undo(self):
        self.assertFalse(self.w.menu_actions['duplicate'].isEnabled())
        self.w.form=Form(gadgets=[Gadget(name='menu1')],menus=[Menu(name='tools',items=[MenuItem('A','runA')]),Menu(name='other')])
        self.w.refresh()
        self.assertFalse(self.w.menu_actions['left'].isEnabled())
        QTest.mouseClick(self.w.menu_actions['duplicate'],Qt.LeftButton)
        self.assertEqual([menu.name for menu in self.w.form.menus],['tools','menu2','other'])
        self.assertEqual(self.w.selected_menu,1)
        copied=self.w.menu_items.cellWidget(0,1);copied.setFocus();QTest.keyClicks(copied,'Changed')
        self.assertEqual(self.w.form.menus[0].items[0].command,'runA')
        QTest.mouseClick(self.w.menu_actions['right'],Qt.LeftButton)
        self.assertEqual(self.w.selected_menu,2)
        self.assertFalse(self.w.menu_actions['right'].isEnabled())
        self.assertEqual([action.text() for action in self.w.preview_menu_bar.actions()],['tools','other','menu2'])
        self.w.undo();self.assertEqual([menu.name for menu in self.w.form.menus],['tools','menu2','other'])
        self.w.redo();self.assertEqual([menu.name for menu in Form.loads(self.w.form.dumps()).menus],['tools','other','menu2'])

    def test_menu_reorder_boundaries_do_not_change_history(self):
        self.w.move_menu(1);self.w.move_menu_item(0,1);self.w.duplicate_menu_item(0)
        self.assertEqual(self.w.history,[])
        self.w.add_menu();self.w.add_menu_item()
        self.w.dirty=False;before=len(self.w.history)
        for direction in (-1,1,2):
            self.w.move_menu(direction);self.w.move_menu_item(0,direction)
        self.w.move_menu_item(-1,1);self.w.duplicate_menu_item(-1)
        self.assertEqual(len(self.w.history),before);self.assertFalse(self.w.dirty)

    def test_menu_switching_rename_and_unique_names(self):
        self.w.add('button');self.w.form.gadgets[0].name='menu1';self.w.refresh()
        self.w.add_menu();self.assertEqual(self.w.form.menus[0].name,'menu2')
        self.w.add_menu_item();self.w.add_menu()
        self.w.menu_list.setCurrentRow(0)
        editor=self.w.menu_name;editor.setFocus();editor.selectAll();QTest.keyClicks(editor,'tools')
        self.assertEqual(self.w.form.menus[0].name,'tools')
        self.assertEqual(self.w.preview_menu_bar.actions()[0].text(),'tools')
        self.w.menu_list.setCurrentRow(1)
        self.assertEqual(self.w.menu_items.rowCount(),0)
        self.w.menu_list.setCurrentRow(0)
        self.assertEqual(self.w.menu_items.rowCount(),1)
        self.w.form.menus[0].name='button2'; self.w.selected=None; self.w.refresh()
        self.w.add('button')
        self.assertNotEqual(self.w.form.gadgets[-1].name,'button2')

    def test_new_gadgets_add_edit_undo_and_render(self):
        self.w.add('rtoggle')
        self.assertEqual(len(self.w.form.gadgets),0)
        self.w.add('frame');group=self.w.form.gadgets[0]
        self.w.add('rtoggle');radio=self.w.form.gadgets[1]
        self.assertEqual(radio.parent,group.name)
        self.assertTrue(self.w.fields['on_value'].isEnabled())
        self.assertFalse(self.w.fields['callback'].isEnabled())
        for kind in ('slider','combo','view','commandline','container'):
            self.w.selected=None;self.w.refresh();self.w.add(kind)
            self.assertEqual(self.w.form.gadgets[-1].kind,kind)
            self.assertNotIn('出力できません',self.w.code.toPlainText())
            self.w.view.viewport().repaint();self.app.processEvents()
        self.w.undo();self.assertNotEqual(self.w.form.gadgets[-1].kind,'container')
        self.w.redo();self.assertEqual(self.w.form.gadgets[-1].kind,'container')
        self.assertEqual(len(Form.loads(self.w.form.dumps()).gadgets),7)

    def test_table_edit_columns_rows_save_and_duplicate(self):
        self.w.add('list');self.w.fields['list_mode'].setCurrentText('TABLE')
        g=self.w.form.gadgets[0]
        self.assertEqual(self.w.list_table.columnCount(),2)
        self.assertEqual(self.w.list_table.rowCount(),2)
        editor=self.w.list_table.cellWidget(0,1);editor.setFocus();editor.selectAll();QTest.keyClicks(editor,'Type')
        cell=self.w.list_table.cellWidget(1,1);cell.setFocus();QTest.keyClicks(cell,'Pump')
        self.assertIs(cell,self.w.list_table.cellWidget(1,1))
        self.assertEqual((g.headings[1],g.rows[0][1]),('Type','Pump'))
        with tempfile.TemporaryDirectory() as folder:
            self.w.path=Path(folder)/'table.json';QTest.keyClick(cell,Qt.Key_S,Qt.ControlModifier);self.app.processEvents()
            self.assertEqual(Form.loads(self.w.path.read_text()).gadgets[0].rows[0][1],'Pump')
        self.w.add_table_column();self.w.add_table_row()
        self.assertEqual((len(g.headings),len(g.rows),len(g.rows[1])),(3,2,3))
        self.w.list_table.cellWidget(1,2).setFocus();self.w.delete_table_column()
        self.assertEqual(len(g.headings),2)
        self.w.list_table.cellWidget(2,0).setFocus();self.w.delete_table_row()
        self.assertEqual(len(g.rows),1)
        self.w.undo();self.assertEqual(len(self.w.form.gadgets[0].rows),2)
        self.w.selected=0;self.w.refresh();self.w.fields['table_method'].setFocus();QTest.keyClicks(self.w.fields['table_method'],'fillTable')
        self.w.duplicate();self.assertEqual(self.w.form.gadgets[1].table_method,'')
        copied=self.w.list_table.cellWidget(1,1);copied.setFocus();copied.selectAll();QTest.keyClicks(copied,'Tank')
        self.assertEqual(self.w.form.gadgets[0].rows[0][1],'Pump')
        self.assertNotIn('出力できません',self.w.code.toPlainText())

    def test_table_and_simple_modes_keep_separate_data(self):
        self.w.add('list');self.w.fields['list_mode'].setCurrentText('TABLE')
        cell=self.w.list_table.cellWidget(1,0);cell.setFocus();QTest.keyClicks(cell,'P-101')
        self.w.fields['list_mode'].setCurrentText('SIMPLE')
        self.assertEqual(self.w.form.gadgets[0].items,['Item A','Item B'])
        self.assertNotIn('setheadings',self.w.code.toPlainText())
        self.w.fields['list_mode'].setCurrentText('TABLE')
        self.assertEqual(self.w.list_table.cellWidget(1,0).text(),'P-101')
        self.assertIn("!ROWS[1][1] = 'P-101'",self.w.code.toPlainText())

    def test_real_value_editor_typing_keeps_cursor_and_save(self):
        self.w.add('combo')
        editor=self.w.item_values;editor.setFocus();QTest.keyClicks(editor,'/P-1')
        QTest.keyClick(editor,Qt.Key_Return);QTest.keyClicks(editor,'/T-1');self.app.processEvents()
        self.assertEqual(self.w.form.gadgets[0].item_values,['/P-1','/T-1'])
        self.assertTrue(editor.toPlainText().endswith('/T-1'))
        self.assertEqual(editor.textCursor().position(),len(editor.toPlainText()))
        with tempfile.TemporaryDirectory() as d:
            self.w.path=Path(d)/'combo.json';QTest.keyClick(editor,Qt.Key_S,Qt.ControlModifier);self.app.processEvents()
            self.assertEqual(Form.loads(self.w.path.read_text()).gadgets[0].item_values,['/P-1','/T-1'])
        self.w.selected=None;self.w.refresh();self.w.add('view')
        self.w.view_code.setPlainText('LIMITS AUTO')
        self.assertIn('LIMITS AUTO',self.w.code.toPlainText())
        self.assertFalse(self.w.item_values.isEnabled())

    def test_relative_controls_preview_and_rename(self):
        self.w.form=Form(gadgets=[Gadget(name='base',x=10,y=5),Gadget(name='follow',y=8)])
        self.w.selected=1;self.w.refresh()
        self.w.fields['layout_mode'].setCurrentText('RELATIVE')
        follower=self.w.form.gadgets[1]
        self.assertEqual((follower.xref,follower.yref),('base','base'))
        self.assertFalse(self.w.fields['x'].isEnabled())
        self.w.fields['width_ref'].setCurrentIndex(self.w.fields['width_ref'].findData('base'))
        self.assertFalse(self.w.fields['width'].isEnabled())
        self.w.selected=0;self.w.refresh()
        editor=self.w.fields['name'];editor.selectAll();QTest.keyClicks(editor,'renamed')
        self.assertEqual((follower.xref,follower.yref,follower.width_ref),('renamed',)*3)
        self.w.fields['x'].setValue(12)
        item=next(item for item in self.w.scene.items() if item.data(0)==1)
        self.assertAlmostEqual(item.pos().x(),12*SX)
        self.assertAlmostEqual(item.pos().y(),6.5*SY)
        self.assertEqual(Form.loads(self.w.form.dumps()).gadgets[1].xref,'renamed')

    def test_ctrl_s_saves_current_line_edit_without_focus_change(self):
        self.w.add('button')
        with tempfile.TemporaryDirectory() as d:
            self.w.path=Path(d)/'design.json'
            for editor,value in [(self.w.fields['label'],'Changed'),(self.w.fname,'changedform')]:
                editor.setFocus();self.app.processEvents();editor.selectAll();QTest.keyClicks(editor,value)
                QTest.keyClick(editor,Qt.Key_S,Qt.ControlModifier);self.app.processEvents()
            loaded=Form.loads(self.w.path.read_text())
            self.assertEqual(loaded.gadgets[0].label,'Changed')
            self.assertEqual(loaded.name,'changedform')
            self.assertEqual(self.w.fields['label'].text(),'Changed')

    def test_option_newline_typing_preserves_text_and_cursor(self):
        self.w.add('option')
        self.w.choice_commands.setPlainText('FIRST\nSECOND')
        for editor in (self.w.choices,self.w.choice_commands):
            editor.setFocus();self.app.processEvents()
            editor.moveCursor(editor.textCursor().MoveOperation.End)
            QTest.keyClick(editor,Qt.Key_Return);QTest.keyClicks(editor,'Third')
            self.assertTrue(editor.toPlainText().endswith('\nThird'))
            self.assertEqual(editor.textCursor().position(),len(editor.toPlainText()))
        self.assertEqual(self.w.form.gadgets[0].items,['Item A','Item B','Third'])
        self.assertEqual(self.w.form.gadgets[0].item_commands,['FIRST','SECOND','Third'])
        self.assertIn("'Third' 'Third'",self.w.form.pml())

    def test_extra_option_commands_are_not_silently_deleted(self):
        self.w.add('option')
        self.w.choice_commands.setPlainText('FIRST\nSECOND\nTHIRD')
        self.assertEqual(self.w.choice_commands.toPlainText(),'FIRST\nSECOND\nTHIRD')
        self.assertEqual(self.w.form.gadgets[0].item_commands,['FIRST','SECOND','THIRD'])
        with self.assertRaises(ValueError): self.w.form.pml()
        self.w.choices.setPlainText('A\nB\nC')
        self.assertIn("'C' 'THIRD'",self.w.form.pml())

    def test_close_with_selected_item_and_queued_callback_has_no_exception(self):
        errors=[]
        with patch.object(sys,'excepthook',lambda *args: errors.append(args)):
            w=Window();w.show();w.add('button');w.selection_changed()
            QTimer.singleShot(0,w.refresh)
            w.dirty=False;w.close();w.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            self.app.processEvents()
        self.assertEqual(errors,[])

    def test_palette_properties_history_and_save(self):
        self.w.add('text')
        self.w.fields['name'].setText('inputName'); self.w.update_gadget()
        self.w.fields['initial'].setText('ABC'); self.w.update_gadget()
        self.assertIn("!this.inputName.val = 'ABC'",self.w.code.toPlainText())
        self.w.duplicate(); self.assertEqual(len(self.w.form.gadgets),2)
        self.w.undo(); self.assertEqual(len(self.w.form.gadgets),1)
        self.w.redo(); self.assertEqual(len(self.w.form.gadgets),2)
        with tempfile.TemporaryDirectory() as d:
            self.w.path=Path(d)/'design.json'; self.assertTrue(self.w.save())
            loaded=Form.loads(self.w.path.read_text())
            self.assertEqual(loaded.gadgets[0].name,'inputName')
            self.assertEqual(loaded.gadgets[0].initial,'ABC')
        self.w.delete(); self.assertEqual(len(self.w.form.gadgets),2) # redo cleared selection

    def test_nested_frame_add_rename_copy_delete_and_switch(self):
        self.w.add('frame'); self.w.fields['frame_style'].setCurrentText('TABSET')
        self.w.fields['height'].setValue(10)
        self.w.add('frame')
        self.assertEqual(self.w.form.gadgets[1].parent,'frame1')
        self.w.add('button')
        self.assertEqual(self.w.form.gadgets[2].parent,'frame2')
        self.w.choose_row(1)
        self.w.fields['name'].setText('pageA'); self.w.update_gadget()
        self.assertEqual(self.w.form.gadgets[2].parent,'pageA')
        self.w.duplicate()
        self.assertEqual(len(self.w.form.gadgets),5)
        copied=self.w.form.gadgets[self.w.selected]
        self.assertEqual(len(self.w.form.children(copied.name)),1)
        visible_names={item.gadget.name for item in self.w.scene.items() if item.isVisible()}
        self.assertIn(copied.name,visible_names); self.assertNotIn('pageA',visible_names)
        self.w.delete(); self.assertEqual(len(self.w.form.gadgets),3)
        self.w.undo(); self.assertEqual(len(self.w.form.gadgets),5)
        self.w.choose_row(1)
        visible_names={item.gadget.name for item in self.w.scene.items() if item.isVisible()}
        self.assertIn('pageA',visible_names); self.assertNotIn(copied.name,visible_names)
        self.assertEqual(Form.loads(self.w.form.dumps()).gadgets[2].parent,'pageA')

    def test_default_body_editor(self):
        self.w.default_body.setPlainText("$p 'Default'")
        self.assertIn("DEFINE METHOD .DEFAULT()\n$p 'Default'\nENDMETHOD",self.w.code.toPlainText())
        self.assertEqual(Form.loads(self.w.form.dumps()).default_body,"$p 'Default'")

    def test_after_show_program_editor(self):
        self.w.after_show.setPlainText("$p 'Ready'")
        self.assertIn("SHOW !!userform\n\n$p 'Ready'\n\ndefine method .userform()",self.w.code.toPlainText())
        self.assertFalse(hasattr(self.w,'show_form'))
        self.assertIn('SHOW !!userform', self.w.code.toPlainText())
        loaded=Form.loads(self.w.form.dumps())
        self.assertEqual(loaded.after_show_code,"$p 'Ready'")
        self.assertTrue(loaded.show_form)

    def test_option_pair_commands_edit_and_save(self):
        self.w.add('option')
        self.w.choice_commands.setPlainText('FIRST\nSECOND')
        self.assertIn("'Item A' 'FIRST'\n  'Item B' 'SECOND'",self.w.code.toPlainText())
        self.assertEqual(Form.loads(self.w.form.dumps()).gadgets[0].item_commands,['FIRST','SECOND'])
        self.assertFalse(self.w.fields['callback'].isEnabled())

    def test_tab_header_mouse_click_switches_page(self):
        self.w.form=Form(gadgets=[
            Gadget(kind='frame',name='tabs',label='Tabs',frame_style='TABSET',x=2,y=1,width=50,height=15),
            Gadget(kind='frame',name='first',label='First',parent='tabs',x=0,y=0,width=45,height=12),
            Gadget(kind='frame',name='second',label='Second',parent='tabs',x=0,y=0,width=45,height=12)])
        self.w.selected=None; self.w.refresh(); self.app.processEvents()
        pos=self.w.view.mapFromScene(2*SX+40*SX,1*SY+12)
        QTest.mouseClick(self.w.view.viewport(),Qt.LeftButton,Qt.NoModifier,pos)
        self.app.processEvents()
        self.assertEqual(self.w.selected,2)
        self.assertEqual(self.w.active_pages['tabs'],'second')

    def test_tabset_property_and_undo(self):
        self.w.add('frame')
        self.assertTrue(self.w.fields['frame_style'].isEnabled())
        self.w.fields['frame_style'].setCurrentText('TABSET')
        self.assertIn("FRAME .frame1 TABSET AT X 0 Y 0 'Group' WIDTH 18",self.w.code.toPlainText())
        self.w.undo()
        self.assertEqual(self.w.form.gadgets[0].frame_style,'FRAME')

    def test_frame_palette(self):
        self.w.add('frame')
        self.assertIn("FRAME .frame1 'Group'\n  EXIT",self.w.code.toPlainText())
        self.assertFalse(self.w.fields['callback'].isEnabled())

    def test_button_command_and_background_properties(self):
        self.w.add('button')
        self.assertTrue(self.w.fields['command'].isEnabled())
        self.assertTrue(self.w.fields['background'].isEnabled())
        self.w.fields['command'].setText('SAVEWORK')
        self.w.fields['background'].setText('5'); self.w.update_gadget()
        self.assertIn("BUTTON .button1 AT X 0 Y 0 BACKGROUND 5 'Run' CALL 'SAVEWORK' WIDTH 18",self.w.code.toPlainText())

    def test_text_command_property(self):
        self.w.add('text')
        self.assertTrue(self.w.fields['command'].isEnabled())
        self.w.fields['command'].setText('SAVEWORK'); self.w.update_gadget()
        self.w.fields['value_type'].setCurrentText('REAL')
        self.assertIn("TEXT .text1 AT X 0 Y 0 'Name' CALL 'SAVEWORK' WIDTH 18 IS REAL",self.w.code.toPlainText())

    def test_line_palette_and_direction_edit(self):
        self.w.add('line')
        self.assertFalse(self.w.fields['label'].isEnabled())
        self.w.fields['orientation'].setCurrentText('VERT')
        self.assertIn("LINE .line1 AT X 0 Y 0 '' VERT WIDTH 18 HEIGHT 1",self.w.code.toPlainText())
        self.w.undo()
        self.assertEqual(self.w.form.gadgets[0].orientation,'HORIZ')

    def test_directional_palette_buttons_create_oriented_gadgets(self):
        for key,kind,direction in [('line_horiz','line','HORIZ'),('line_vert','line','VERT'),
                                   ('slider_horiz','slider','HORIZONTAL'),('slider_vert','slider','VERTICAL')]:
            self.w.selected=None;self.w.refresh()
            QTest.mouseClick(self.w.palette_buttons[key],Qt.LeftButton)
            g=self.w.form.gadgets[-1]
            self.assertEqual(g.kind,kind)
            self.assertEqual(g.orientation if kind == 'line' else g.slider_orientation,direction)
            if direction in ('VERT','VERTICAL'): self.assertGreater(g.height,g.width)
            self.assertIn(direction,self.w.code.toPlainText())

    def test_variable_edit_and_invalid_edit_blocks_output(self):
        self.w.variables.setPlainText('projectName=Demo')
        self.assertIn("VAR !!projectName 'Demo'", self.w.code.toPlainText())
        self.w.variables.setPlainText('invalid syntax')
        self.assertTrue(self.w.variable_error)
        self.w.add('button')
        self.assertIn('変数欄', self.w.code.toPlainText())
        self.w.variables.setPlainText('mode=Default')
        self.assertFalse(self.w.variable_error)
        self.assertIn("VAR !!mode 'Default'",self.w.code.toPlainText())
        self.w.docking.setCurrentIndex(1)
        self.assertIn("size 70 22 DIALOG",self.w.code.toPlainText())

    def test_mouse_drag_updates_model_and_undo(self):
        self.w.add('button'); self.app.processEvents()
        view=self.w.view; item=self.w.scene.items()[0]
        start=view.mapFromScene(item.sceneBoundingRect().center())
        end=start+QPoint(40,52)
        QTest.mousePress(view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
        self.app.processEvents()
        QTest.mouseMove(view.viewport(),end,50)
        QTest.mouseRelease(view.viewport(),Qt.LeftButton,Qt.NoModifier,end)
        self.app.processEvents()
        self.assertEqual((self.w.form.gadgets[0].x,self.w.form.gadgets[0].y),(4,2))
        self.assertIn('AT X 4 Y 2',self.w.code.toPlainText())
        self.w.undo()
        self.assertEqual((self.w.form.gadgets[0].x,self.w.form.gadgets[0].y),(0,0))

    def drag_handle(self, handle, delta):
        self.app.processEvents()
        item=next(item for item in self.w.scene.items() if item.data(0)==self.w.selected)
        start=self.w.view.mapFromScene(item.mapToScene(item.handles()[handle].center()))
        end=start+delta;view=self.w.view.viewport()
        QTest.mousePress(view,Qt.LeftButton,Qt.NoModifier,start);self.app.processEvents()
        QTest.mouseMove(view,end,30);QTest.mouseRelease(view,Qt.LeftButton,Qt.NoModifier,end)
        self.app.processEvents()

    def test_handles_resize_dimensions_and_undo(self):
        self.w.add('view')
        self.drag_handle('width',QPoint(40,0))
        self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(22,5))
        self.drag_handle('height',QPoint(0,52))
        self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(22,7))
        before=len(self.w.history)
        self.drag_handle('both',QPoint(30,26))
        self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(25,8))
        self.assertEqual(len(self.w.history),before+1)
        self.assertIn('WIDTH 25 HEIGHT 8',self.w.code.toPlainText())
        self.assertEqual(self.w.fields['width'].value(),25)
        self.w.undo();self.assertEqual((self.w.form.gadgets[0].width,self.w.form.gadgets[0].height),(22,7))
        self.w.redo();self.assertEqual(Form.loads(self.w.form.dumps()).gadgets[0].width,25)

    def test_resize_constraints_children_relative_and_width_reference(self):
        group=Gadget(kind='frame',name='group',width=24,height=10)
        child=Gadget(name='child',parent='group',x=2,y=2,width=18)
        follower=Gadget(name='follow',layout_mode='RELATIVE',xref='group',yref='group',xedge='XMAX',xoffset=1)
        self.w.form=Form(gadgets=[group,child,follower]);self.w.selected=0;self.w.refresh()
        self.drag_handle('width',QPoint(-80,0))
        self.assertEqual(group.width,24)
        self.drag_handle('width',QPoint(30,0))
        self.assertEqual(group.width,27)
        follow=next(item for item in self.w.scene.items() if item.data(0)==2)
        self.assertAlmostEqual(follow.pos().x(),(group.x+27+1)*SX)
        self.w.selected=2;follower.width_ref='group';self.w.refresh()
        follow=next(item for item in self.w.scene.items() if item.data(0)==2)
        self.assertEqual(set(follow.handles()),{'height'})
        self.drag_handle('height',QPoint(0,26))
        self.assertEqual(follower.height,2)
        self.assertEqual(self.w.form.geometry(follower)[2],27)

    def test_resize_no_change_or_outside_bounds_leaves_history_unchanged(self):
        self.w.add('button');before=len(self.w.history);self.w.dirty=False
        self.drag_handle('both',QPoint(0,0))
        self.assertEqual(len(self.w.history),before);self.assertFalse(self.w.dirty)
        self.drag_handle('width',QPoint(600,0))
        self.assertEqual(self.w.form.gadgets[0].width,18)
        self.assertEqual(len(self.w.history),before)

    def test_native_list_move_preserves_selection_save_and_undo(self):
        self.w.form=Form(gadgets=[Gadget(name='first'),Gadget(name='second',y=4),Gadget(name='third',y=7)])
        self.w.selected=1;self.w.refresh()
        self.assertTrue(self.w.objects.model().moveRows(QModelIndex(),1,1,QModelIndex(),3))
        self.app.processEvents()
        self.assertEqual([g.name for g in self.w.form.gadgets],['first','third','second'])
        self.assertEqual(self.w.form.gadgets[self.w.selected].name,'second')
        pml=self.w.form.pml();self.assertLess(pml.index('BUTTON .third'),pml.index('BUTTON .second'))
        self.assertEqual([g.name for g in Form.loads(self.w.form.dumps()).gadgets],['first','third','second'])
        self.w.undo();self.assertEqual([g.name for g in self.w.form.gadgets],['first','second','third'])
        self.w.redo();self.assertEqual([g.name for g in self.w.form.gadgets],['first','third','second'])

    def test_list_mouse_selection_keeps_item_alive_for_drag(self):
        self.w.form=Form(gadgets=[Gadget(name='first'),Gadget(name='second',y=4)])
        self.w.refresh();item=self.w.objects.item(1)
        position=self.w.objects.visualItemRect(item).center()
        QTest.mousePress(self.w.objects.viewport(),Qt.LeftButton,Qt.NoModifier,position)
        self.assertIs(self.w.objects.item(1),item)
        self.assertEqual(self.w.selected,1)
        QTest.mouseRelease(self.w.objects.viewport(),Qt.LeftButton,Qt.NoModifier,position)
        self.assertEqual(self.w.fields['name'].text(),'second')

    def test_list_move_preserves_parents_and_reports_invalid_auto_order(self):
        group=Gadget(kind='frame',name='group',width=30,height=10)
        a=Gadget(name='a',parent='group')
        b=Gadget(name='b',parent='group',layout_mode='AUTO')
        self.w.form=Form(gadgets=[group,a,b]);self.w.selected=2;self.w.refresh()
        self.assertTrue(self.w.objects.model().moveRows(QModelIndex(),2,1,QModelIndex(),1))
        self.app.processEvents()
        self.assertEqual([g.name for g in self.w.form.gadgets],['group','b','a'])
        self.assertEqual((a.parent,b.parent),('group','group'))
        self.assertIn('出力できません',self.w.code.toPlainText())
        self.w.undo();self.assertNotIn('出力できません',self.w.code.toPlainText())

if __name__=='__main__': unittest.main()
