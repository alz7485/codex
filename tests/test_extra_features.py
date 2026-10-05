from e3d_designer.formatting import canonical_pml
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMenu
from e3d_designer.app import Window,Item
from e3d_designer.model import Form,Gadget,Menu,MenuItem
from e3d_designer.names import rename,reference_locations,actual_name


class ExtraModelTests(unittest.TestCase):
    def test_pixmap_paragraph_button_toggle_and_option(self):
        gadgets=[Gadget(kind=kind,name=kind+'Pic',display_mode='PIXMAP',pixmap_path=r'C:\Images\sample.png') for kind in ('paragraph','button','toggle')]
        gadgets.append(Gadget(kind='option',name='imageChoice',display_mode='PIXMAP',items=[r'/C:\Images\red.gif',r'/C:\Images\yellow.gif'],item_values=['RED','YELLOW'],callback='imageChanged'))
        form=Form(gadgets=gadgets);pml=Form.loads(form.dumps()).pml(normalize=False)
        self.assertIn('PARAGRAPH .paragraphPic AT X 2 Y 1 PIXMAP WIDTH 14 HEIGHT 1',pml)
        for name in ('paragraphPic','buttonPic','togglePic'): self.assertIn(f"!this.{name}.AddPixmap('C:\\Images\\sample.png')",pml)
        self.assertIn("OPTION .imageChoice AT X 2 Y 1 'Run' PIXMAP WIDTH 14 HEIGHT 1 callback '!this.imageChanged()'",pml)
        self.assertIn('!this.imageChoice.dtext = !choices',pml);self.assertIn('!this.imageChoice.rtext = !values',pml)
        self.assertNotIn('VAR LIST',pml);self.assertEqual(actual_name(gadgets[-1]),'imageChoice')
        gadgets[-1].item_values=['RED']
        with self.assertRaises(ValueError): form.validate()

    def test_textpane_selector_and_legacy_defaults(self):
        form=Form(gadgets=[Gadget(kind='textpane',name='notes',pane_lines=['A    B','  1    2'],height=4),Gadget(kind='selector',name='owners',database='OWNERS',selection_mode='MULTIPLE',height=4)])
        pml=Form.loads(form.dumps()).pml(normalize=False)
        self.assertIn("TEXTPANE .notes 'Run' FIXCHARS AT X 2 Y 1 WIDTH 14 HEIGHT 4",pml)
        self.assertIn("!paneLines[2] = '  1    2'",pml);self.assertIn('!this.notes.val = !paneLines',pml)
        self.assertIn("SELECTOR .owners AT X 2 Y 1 'Run' MULTIPLE WIDTH 14 HEIGHT 4 DATABASE OWNERS",pml)
        form.gadgets[0].fixed_font=False;self.assertNotIn('FIXCHARS',form.pml(normalize=False))
        legacy=json.loads(Form(gadgets=[Gadget()]).dumps())
        for key in ('form_type','initcall','okcall','cancelcall'): legacy['form'].pop(key)
        for key in ('display_mode','pixmap_path','popup_menu','fixed_font','pane_lines','database','button_role'): legacy['form']['gadgets'][0].pop(key)
        loaded=Form.loads(json.dumps(legacy));self.assertEqual(loaded.form_type,'DIALOG');self.assertEqual(loaded.gadgets[0].display_mode,'TEXT')

    def test_popup_and_form_callbacks_rename_and_validation(self):
        form=Form(initcall='!!value = !this.results.val',okcall='SAVEWORK',cancelcall="$p 'cancel'",variables={'value':''},menus=[Menu(name='context',popup=True,items=[MenuItem('Query','Q ATT')])],gadgets=[Gadget(kind='list',name='results',popup_menu='context')])
        pml=form.pml(normalize=False)
        self.assertIn('menu .context POPUP',pml);self.assertIn("!this.context.Add('CALLBACK', 'Query', 'Q ATT')",pml)
        self.assertIn('!this.results.SetPopup(!this.context)',pml)
        self.assertIn("!this.okcall = 'SAVEWORK'",pml)
        self.assertLess(pml.index('SHOW !!'),pml.index('define method'))
        renamed=rename(form,'menu',0,'actions',False);self.assertEqual(renamed.gadgets[0].popup_menu,'actions')
        renamed=rename(renamed,'variable','value','newValue');self.assertIn('!!newValue',renamed.initcall)
        renamed=rename(renamed,'gadget',0,'output');self.assertIn('!this.output.val',renamed.initcall)
        self.assertEqual(reference_locations(form,'menu','context'),[('results: popup_menu',1)])
        form.menus[0].popup=False
        with self.assertRaises(ValueError): form.validate()

    def test_main_toolbar_order_and_restrictions(self):
        toolbar=Gadget(kind='frame',name='tools',frame_style='TOOLBAR',width=60,height=4,x=0,y=0)
        first=Gadget(name='first',parent='tools',width=10,x=50)
        second=Gadget(name='second',parent='tools',width=10,x=0)
        form=Form(form_type='MAIN',gadgets=[toolbar,first,second]);pml=form.pml(normalize=False)
        self.assertIn('setup form !!userform MAIN',pml);self.assertIn("FRAME .tools TOOLBAR 'Run'",pml)
        self.assertIn("BUTTON .first  'Run' WIDTH 10",pml)
        self.assertEqual(form.geometry(first)[:2],(1,1));self.assertEqual(form.geometry(second)[:2],(12,1))
        form.gadgets=[toolbar,second,first];self.assertEqual(form.geometry(first)[:2],(12,1))
        form.form_type='DIALOG'
        with self.assertRaises(ValueError): form.validate()
        form.form_type='MAIN';first.kind='list'
        with self.assertRaises(ValueError): form.validate()

    def test_button_roles_and_invalid_new_settings(self):
        for role in ('OK','CANCEL','APPLY','RESET','HELP'):
            form=Form(gadgets=[Gadget(button_role=role)])
            self.assertIn("'Run' "+role+' WIDTH',form.pml(normalize=False))
        cases=[Gadget(kind='combo',display_mode='PIXMAP'),Gadget(fixed_font='yes'),Gadget(database='BAD'),Gadget(button_role='OK',command='SAVEWORK'),Gadget(kind='paragraph',button_role='OK'),Gadget(pixmap_path='bad\nfile'),Gadget(popup_menu='missing')]
        for gadget in cases:
            with self.subTest(gadget=gadget),self.assertRaises(ValueError): Form(gadgets=[gadget]).validate()


class ExtraGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self): self.w=Window();self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear()
        self.w.dirty=False;self.w.close();self.app.processEvents()

    def test_menu_palette_opens_editor_and_supports_undo(self):
        self.w.palette_buttons['menubar'].click();self.app.processEvents()
        self.assertEqual(len(self.w.form.menus),1)
        self.assertEqual(self.w.selected_menu,0)
        self.assertEqual(self.w.menu_name.text(),'menu1')
        self.assertEqual(len(self.w.form.gadgets),0)
        self.w.add_menu_item()
        self.assertIn('menu .menu1',self.w.form.pml(normalize=False).lower())
        self.w.undo();self.w.undo()
        self.assertEqual(self.w.form.menus,[])

    def test_image_picker_preview_save_and_undo(self):
        self.w.palette_buttons['image'].click();self.assertEqual(self.w.form.gadgets[0].display_mode,'PIXMAP')
        with tempfile.TemporaryDirectory() as folder:
            filename=Path(folder)/'sample.png';pixmap=QPixmap(20,10);pixmap.fill(QColor('red'));pixmap.save(str(filename))
            with patch('e3d_designer.app.QFileDialog.getOpenFileName',return_value=(str(filename),'')): self.w.browse_image.click()
            self.assertEqual(self.w.form.gadgets[0].pixmap_path,str(filename))
            item=next(item for item in self.w.scene.items() if isinstance(item,Item));self.assertFalse(item.pixmap.isNull())
            self.w.path=Path(folder)/'design.json';self.assertTrue(self.w.save())
            self.assertEqual(Form.loads(self.w.path.read_text()).gadgets[0].pixmap_path,str(filename))
        self.w.undo();self.assertEqual(self.w.form.gadgets[0].pixmap_path,'')

    def test_image_option_and_textpane_editor(self):
        self.w.palette_buttons['image_option'].click();self.w.choices.setPlainText('/C:/red.gif\n/C:/yellow.gif')
        self.w.item_values.setPlainText('RED\nYELLOW');self.assertIn(canonical_pml('!this.option1.rtext'),self.w.code.toPlainText())
        with patch('e3d_designer.app.QFileDialog.getOpenFileNames',return_value=(['/C:/blue.gif'],'')): self.w.browse_image.click()
        self.assertEqual(self.w.form.gadgets[0].items,['/C:/red.gif','/C:/yellow.gif','/C:/blue.gif'])
        self.assertEqual(self.w.form.gadgets[0].item_values,['RED','YELLOW',''])
        self.w.undo();self.w.choose_row(0)
        self.assertTrue(self.w.choice_commands.isHidden() or not self.w.choice_commands.isVisible())
        self.w.fields['display_mode'].setCurrentText('TEXT');self.assertIn(canonical_pml('VAR LIST _option1'),self.w.code.toPlainText())
        self.w.undo();self.assertEqual(self.w.form.gadgets[0].item_values,['RED','YELLOW'])
        self.w.selected=None;self.w.add('textpane');self.w.pane_lines.setPlainText('A    B\n  C')
        self.assertEqual(self.w.form.gadgets[-1].pane_lines,['A    B','  C'])
        self.w.fixed_font.setChecked(False);self.assertNotIn(canonical_pml('FIXCHARS'),self.w.code.toPlainText())
        self.w.selected=None;self.w.add('selector');self.w.fields['database'].setCurrentText('MEMBERS')
        self.assertIn(canonical_pml('DATABASE MEMBERS'),self.w.code.toPlainText())

    def test_popup_editor_rename_delete_and_preview(self):
        self.w.add_menu();self.w.add_menu_item();self.w.menu_popup.setChecked(True)
        self.assertFalse(self.w.preview_menu_bar.isVisible())
        self.w.add('list');self.w.fields['popup_menu'].setCurrentIndex(1)
        self.assertEqual(self.w.form.gadgets[0].popup_menu,'menu1')
        self.w.menu_name.setFocus();self.w.menu_name.selectAll();QTest.keyClicks(self.w.menu_name,'actions')
        self.assertEqual(self.w.form.gadgets[0].popup_menu,'actions')
        item=next(item for item in self.w.scene.items() if isinstance(item,Item))
        position=self.w.view.mapFromScene(item.sceneBoundingRect().center())
        self.w.preview_popup(position);self.app.processEvents()
        popup=QApplication.activePopupWidget();self.assertIsInstance(popup,QMenu)
        popup.actions()[0].trigger();popup.close()
        self.w.delete_menu();self.assertEqual(self.w.form.gadgets[0].popup_menu,'')
        self.w.undo();self.assertEqual(self.w.form.gadgets[0].popup_menu,'actions')

    def test_toolbar_palette_callbacks_role_and_history(self):
        self.w.palette_buttons['toolbar'].click();self.assertEqual(self.w.form.gadgets,[])
        self.w.docking.setCurrentIndex(2);self.w.palette_buttons['toolbar'].click()
        self.assertEqual(self.w.form.gadgets[0].frame_style,'TOOLBAR')
        self.w.add('button');self.assertIn(canonical_pml('MAIN'),self.w.code.toPlainText())
        self.assertFalse(self.w.fields['x'].isEnabled())
        before=len(self.w.history);self.w.add('selector');self.assertEqual(len(self.w.history),before)
        self.w.fields['command'].setText('SAVEWORK');self.w.update_gadget()
        self.w.fields['button_role'].setCurrentText('OK');self.assertEqual(self.w.form.gadgets[1].command,'')
        editor=self.w.form_callbacks['okcall'];editor.setFocus();QTest.keyClicks(editor,'SAVEWORK')
        self.assertEqual(self.w.form.okcall,'SAVEWORK');self.assertIn(canonical_pml("!this.okcall = 'SAVEWORK'"),self.w.code.toPlainText())

    def test_toolbar_image_height_and_full_width_noop(self):
        self.w.docking.setCurrentIndex(2);self.w.palette_buttons['toolbar'].click()
        self.w.palette_buttons['image_option'].click();self.w.form.validate()
        self.assertEqual(self.w.form.gadgets[1].height,78)
        self.w.fields['width'].setValue(690);self.w.form.validate()
        before=self.w.form.dumps();history=len(self.w.history);self.w.dirty=False
        self.w.add('button')
        self.assertEqual(self.w.form.dumps(),before);self.assertEqual(len(self.w.history),history);self.assertFalse(self.w.dirty)

    def test_new_settings_saved_immediately_and_clipboard_preserved(self):
        self.w.add('textpane');self.w.pane_lines.setFocus();QTest.keyClicks(self.w.pane_lines,'  Indented')
        with tempfile.TemporaryDirectory() as folder:
            self.w.path=Path(folder)/'project.json'
            QTest.keyClick(self.w.pane_lines,Qt.Key_S,Qt.ControlModifier);self.app.processEvents()
            self.assertEqual(Form.loads(self.w.path.read_text()).gadgets[0].pane_lines,['  Indented'])
        self.assertTrue(self.w.copy_gadget());self.w.paste_gadget()
        self.assertEqual(self.w.form.gadgets[1].pane_lines,['  Indented'])
        self.w.undo();self.assertEqual(len(self.w.form.gadgets),1)
        editor=self.w.form_callbacks['initcall'];editor.setFocus();QTest.keyClicks(editor,'Q ATT')
        with tempfile.TemporaryDirectory() as folder:
            self.w.path=Path(folder)/'project.json'
            QTest.keyClick(editor,Qt.Key_S,Qt.ControlModifier);self.app.processEvents()
            self.assertEqual(Form.loads(self.w.path.read_text()).initcall,'Q ATT')


if __name__ == '__main__': unittest.main()
