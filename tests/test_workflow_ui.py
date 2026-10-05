import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window,Item
from e3d_designer.model import Form,Gadget


class WorkflowUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json');self.w.show();self.app.processEvents()

    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_view_switches_do_not_change_design_or_history(self):
        w=self.w;original=w.form.dumps()
        self.assertEqual(w.current_workflow,'form');self.assertEqual(w.inspector_tabs.currentIndex(),1)
        for stage in ('layout','action','output','form'):
            w.workflow_buttons[stage].click();self.app.processEvents()
            self.assertEqual(w.current_workflow,stage)
            self.assertEqual(w.workspace_tabs.currentIndex(),1 if stage=='output' else 0)
            self.assertEqual(w.library_panel.isVisible(),stage!='output')
            self.assertEqual(w.inspector_tabs.isVisible(),stage!='output')
            self.assertTrue(w.workflow_buttons[stage].isChecked())
        self.assertEqual(w.form.dumps(),original);self.assertEqual(w.history,[]);self.assertFalse(w.dirty)
        w.workspace_tabs.setCurrentIndex(1);self.assertEqual(w.current_workflow,'output')
        w.workspace_tabs.setCurrentIndex(0);self.assertEqual(w.current_workflow,'layout')
        self.assertGreater(w.view.viewport().height(),500)
        self.assertTrue(all(button.isVisible() for button in w.palette_buttons.values()))

    def test_actual_form_tab_parts_action_save_export_workflow(self):
        w=self.w
        w.fname.selectAll();QTest.keyClicks(w.fname,'DEMO')
        w.ftitle.selectAll();QTest.keyClicks(w.ftitle,'Equipment')
        w.workflow_buttons['layout'].click()
        QTest.mouseClick(w.palette_buttons['tabset'],Qt.LeftButton)
        tabs=next(g for g in w.form.gadgets if g.frame_style=='TABSET')
        self.assertEqual(len(tabs.tabs),2)
        QTest.mouseClick(w.palette_buttons['text'],Qt.LeftButton)
        text=w.form.gadgets[w.selected]
        self.assertEqual(text.parent,tabs.tabs[0].name)
        w.fields['initial'].setFocus();QTest.keyClicks(w.fields['initial'],'P-101')
        QTest.mouseClick(w.palette_buttons['button'],Qt.LeftButton)
        button=w.form.gadgets[w.selected]
        w.workflow_buttons['action'].click();self.assertEqual(w.props.currentIndex(),3)
        w.fields['callback'].setFocus();w.fields['callback'].selectAll();QTest.keyClicks(w.fields['callback'],'RUN')
        self.assertTrue(w.edit_method_button.isVisible());w.edit_method_button.click()
        self.assertEqual(w.inspector_tabs.currentIndex(),2)
        w.body.setPlainText('$p |Run|')
        w.workflow_buttons['output'].click()
        self.assertIn('問題なし',w.output_validation.text())
        self.assertIn('未保存の変更',w.output_summary.text())
        target=self.folder/'demo.json'
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(target),'')):self.assertTrue(w.save())
        self.assertIn('保存済み',w.output_summary.text())
        restored=Form.loads(target.read_text());self.assertEqual(restored.name,'DEMO')
        self.assertEqual(restored.named(text.name).initial,'P-101')
        self.assertEqual(restored.named(button.name).body,'$p |Run|')
        output=self.folder/'demo.mac';w.output_folder.setText(str(self.folder))
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):w.export()
        self.assertEqual(output.read_bytes(),restored.pml().replace('\n','\r\n').encode('cp932'))
        w.workflow_buttons['layout'].click();self.assertTrue(w.inspector_tabs.isVisible())

    def test_tab_palette_is_one_undo_and_each_page_has_own_parts(self):
        w=self.w;before=w.form.dumps();w.palette_buttons['tabset'].click()
        self.assertEqual(len(w.history),1);tabs=w.form.gadgets[0]
        w.form.validate();self.assertEqual(len(tabs.tabs),2)
        w.add('button');first=w.form.gadgets[w.selected]
        w.page_tabs.setCurrentIndex(1);w.add('text');second=w.form.gadgets[w.selected]
        self.assertNotEqual(first.parent,second.parent)
        visibility={item.gadget.name:item.isVisible() for item in w.scene.items() if isinstance(item,Item)}
        self.assertFalse(visibility[first.name]);self.assertTrue(visibility[second.name])
        w.undo();w.undo();w.undo();self.assertEqual(w.form.dumps(),before)
        w.redo();self.assertEqual(len(w.form.gadgets),3);w.form.validate()

    def test_tab_palette_rejects_no_space_without_mutation(self):
        w=self.w;w.form=Form(width=4,height=1,gadgets=[Gadget(kind='frame',name='frame',width=4,height=1,x=0,y=0)])
        w.selected=0;w.refresh();before=w.form.dumps()
        w.palette_buttons['tabset'].click()
        self.assertEqual(w.form.dumps(),before);self.assertEqual(w.history,[])
        self.assertIn('空きがありません',w.statusBar().currentMessage())

    def test_action_selection_routes_to_part_actions_without_data_changes(self):
        w=self.w;w.form=Form(gadgets=[Gadget(name='run',callback='run'),Gadget(name='stop',x=30,callback='stop')])
        w.selected=0;w.refresh();before=w.form.dumps()
        w.workflow_buttons['action'].click();w.choose_row(1)
        self.assertEqual(w.current_workflow,'action');self.assertEqual(w.props.currentIndex(),3)
        self.assertEqual(w.fields['callback'].text(),'stop')
        self.assertEqual(w.form.dumps(),before);self.assertFalse(w.dirty)

    def test_output_reports_model_and_encoding_errors_before_export(self):
        w=self.w;w.form.title='😀';w.refresh();w.set_workflow('output')
        self.assertIn('CP932',w.output_validation.text())
        w.form.title='Equipment';w.refresh();w.variables.setPlainText('unfinished')
        self.assertIn('名前=初期値',w.output_validation.text())
        w.variables.setPlainText('mode=A');self.assertIn('問題なし',w.output_validation.text())

    def test_new_parts_export_without_editing_any_symbol_name(self):
        w=self.w
        for kind in ('button','text','toggle','list','combo','slider','selector'):
            w.add(kind);g=w.form.gadgets[w.selected]
            self.assertTrue(g.name);self.assertTrue(g.callback)
            self.assertNotIn(g.callback.lower(),w.code.toPlainText().lower())
        names=[g.name.lower() for g in w.form.gadgets]
        methods=[g.callback.lower() for g in w.form.gadgets]
        self.assertEqual(len(set(names)),len(names));self.assertEqual(len(set(methods)),len(methods))
        output=self.folder/'automatic.mac';w.output_folder.setText(str(self.folder))
        with patch('e3d_designer.app.QFileDialog.getSaveFileName',return_value=(str(output),'')):w.export()
        self.assertTrue(output.exists());self.assertNotIn('Define Method .ON_BUTTON1()',output.read_bytes().decode('cp932'))

    def test_generated_names_avoid_existing_variables_and_member_names(self):
        w=self.w;w.form=Form(variables={'button1':''},gadgets=[Gadget(kind='paragraph',name='on_button2',x=40,width=1)])
        w.selected=None;w.refresh();w.add('button');g=w.form.gadgets[w.selected]
        self.assertEqual(g.name,'button2');self.assertEqual(g.callback,'on_button2_2')
        w.form.validate()

    def test_call_overrides_automatic_method_and_undo_restores_it(self):
        w=self.w;w.add('button');method=w.form.gadgets[0].callback
        w.fields['command'].setText('SAVEWORK');w.update_gadget()
        self.assertEqual(w.form.gadgets[0].callback,'');self.assertEqual(w.form.gadgets[0].command,'SAVEWORK')
        w.form.validate();w.undo();self.assertEqual(w.form.gadgets[0].callback,method)
        w.choose_row(0);w.fields['command'].setText('SAVEWORK');w.update_gadget()
        w.fields['callback'].setText('customAction');w.update_gadget()
        self.assertEqual(w.form.gadgets[0].command,'');self.assertEqual(w.form.gadgets[0].callback,'customAction')
        w.form.validate()

    def test_macro_flag_and_branch_value_are_automatic(self):
        w=self.w;w.add('button')
        w.fields['action_mode'].setCurrentIndex(w.fields['action_mode'].findData('MACRO'))
        w.fields['macro_path'].setText('CODE1.MAC');w.update_gadget()
        gadget=w.form.gadgets[0]
        self.assertIn(gadget.macro_flag,w.form.variables);self.assertEqual(gadget.macro_value,gadget.name)
        w.form.validate();self.assertIn('Var !!BUTTONFLAG',w.form.pml())

    def test_legacy_part_gets_method_on_edit_without_typing_a_name(self):
        w=self.w;w.form=Form(gadgets=[Gadget(name='legacy')]);w.selected=0;w.refresh()
        before=w.form.dumps();w.set_workflow('action');w.edit_method_button.click()
        self.assertEqual(w.form.gadgets[0].callback,'on_legacy')
        self.assertEqual(w.inspector_tabs.currentIndex(),2)
        self.assertEqual(len(w.history),1);w.undo();self.assertEqual(w.form.dumps(),before)

    def test_method_edit_does_not_replace_existing_direct_call(self):
        w=self.w;w.form=Form(gadgets=[Gadget(name='legacy',command='SAVEWORK')]);w.selected=0;w.refresh()
        before=w.form.dumps();w.show_method_editor()
        self.assertEqual(w.form.dumps(),before);self.assertEqual(w.history,[])
