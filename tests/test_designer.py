import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.model import Form, Gadget, literal
from e3d_designer.app import Window, atomic_write, SX, SY


class ModelTests(unittest.TestCase):
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
        self.assertIn('lines 1',pml)
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
        self.assertLess(pml.index('DEFINE METHOD .DEFAULT()'),pml.index('SHOW !!'))
        f.gadgets[0].body='different'
        with self.assertRaises(ValueError): f.pml()

    def test_show_then_program_after_method_definitions(self):
        f=Form(after_show_code="$p 'Ready'",gadgets=[Gadget(callback='onRun')])
        pml=Form.loads(f.dumps()).pml()
        self.assertTrue(pml.endswith("SHOW !!userform\n\n$p 'Ready'\n"))
        self.assertLess(pml.index('define method .onRun()'),pml.index('SHOW !!userform'))
        f.show_form=False
        self.assertNotIn('SHOW !!',f.pml())
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
        self.assertTrue(self.w.code.toPlainText().endswith("SHOW !!userform\n\n$p 'Ready'\n"))
        self.w.show_form.setChecked(False)
        self.assertNotIn('SHOW !!userform', self.w.code.toPlainText())
        loaded=Form.loads(self.w.form.dumps())
        self.assertEqual(loaded.after_show_code,"$p 'Ready'")
        self.assertFalse(loaded.show_form)

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

if __name__=='__main__': unittest.main()
