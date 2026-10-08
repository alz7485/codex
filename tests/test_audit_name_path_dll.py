import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from e3d_designer.app import Window
from e3d_designer.model import Form,Gadget,Menu


class AuditFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.window=Window()
    def tearDown(self):
        self.app.clipboard().clear();self.window.dirty=False;self.window.close();self.app.processEvents()

    def test_live_gadget_rename_updates_code_editors_and_undo(self):
        w=self.window;w.form=Form(gadgets=[Gadget(name='button1',callback='run',body='!this.button1.visible = TRUE')],default_body='!!userform.button1.val = 1');w.selected=0;w.refresh()
        editor=w.fields['name'];editor.selectAll();QTest.keyClicks(editor,'renamed')
        self.assertEqual(w.form.gadgets[0].name,'renamed')
        self.assertIn('.renamed',w.form.default_body)
        self.assertEqual(w.form.gadgets[0].body,'!this.renamed.visible = TRUE')
        self.assertEqual(w.body.toPlainText(),w.form.gadgets[0].body)
        w.fields['width'].setValue(20)
        self.assertEqual(w.form.gadgets[0].body,'!this.renamed.visible = TRUE')
        while w.history:w.undo()
        self.assertEqual(w.form.gadgets[0].name,'button1')
        self.assertIn('.button1',w.form.default_body)

    def test_form_and_menu_rename_updates_raw_references_and_popup(self):
        w=self.window;w.form=Form(gadgets=[Gadget(name='run',popup_menu='tools')],menus=[Menu(name='tools',popup=True)],after_show_code='!!userform.DEFAULT()',default_body='!!userform.run.val = 1\n!this.tools.add()');w.selected_menu=0;w.refresh()
        w.fname.setText('otherform');w.update_form()
        self.assertEqual(w.form.after_show_code,'!!otherform.DEFAULT()')
        self.assertIn('!!otherform.run',w.form.default_body)
        w.update_menu_name('actions')
        self.assertEqual(w.form.gadgets[0].popup_menu,'actions')
        self.assertIn('!this.actions.add()',w.form.default_body)
        w.undo();self.assertIn('!this.tools.add()',w.form.default_body)

    def test_invalid_intermediate_and_duplicate_names_preserve_state_history(self):
        w=self.window;w.form=Form(gadgets=[Gadget(name='first'),Gadget(name='second')],default_body='!this.first.val = 1');w.selected=0;w.refresh()
        source=w.form.dumps();history=len(w.history)
        for name in ('','bad name','second'):
            w.fields['name'].setText(name);w.update_gadget()
            self.assertEqual(w.form.dumps(),source);self.assertEqual(len(w.history),history);self.assertFalse(w.dirty)
        w.fields['name'].setText('valid');w.update_gadget()
        self.assertEqual(w.form.default_body,'!this.valid.val = 1')
        w.undo();future=list(w.future);w.choose_row(0)
        w.fields['name'].setText('second');w.update_gadget()
        self.assertEqual(w.future,future)

    def test_macro_table_option_and_container_generated_symbols(self):
        cases=[
            (Gadget(name='old',action_mode='MACRO',macro_path='C:/code.mac'),'!this.macro_old()','!this.macro_new()'),
            (Gadget(kind='list',name='old',list_mode='TABLE',headings=['A']),'!this.populate_old()','!this.populate_new()'),
            (Gadget(kind='option',name='old',items=['A']),'!this._old.val = 1','!this._new.val = 1'),
            (Gadget(kind='container',name='old',assembly='Widget.dll',namespace='Vendor.Widgets',control_type='MyControl'),'!this.oldControl.handle()','!this.newControl.handle()')]
        for gadget,source,expected in cases:
            with self.subTest(kind=gadget.kind):
                w=self.window;w.form=Form(gadgets=[gadget],default_body=source);w.selected=0;w.refresh();w.fields['name'].setText('new');w.update_gadget()
                self.assertEqual(w.form.default_body,expected)

    def test_rejected_rename_preserves_full_history_and_redo(self):
        w=self.window
        w.form=Form(gadgets=[Gadget(name='first'),Gadget(name='second')])
        w.selected=0;w.refresh()
        w.history=[Form(title=f'History {index}') for index in range(100)]
        w.future=[Form(title='Redo')]
        expected_history=[form.dumps() for form in w.history]
        expected_future=[form.dumps() for form in w.future]
        original=w.form.dumps()
        for dirty in (False,True):
            w.dirty=dirty
            for name in ('second','bad name','', 'second'):
                with self.subTest(dirty=dirty,name=name):
                    w.fields['name'].setText(name);w.update_gadget()
                    self.assertEqual(w.form.dumps(),original)
                    self.assertEqual([form.dumps() for form in w.history],expected_history)
                    self.assertEqual([form.dumps() for form in w.future],expected_future)
                    self.assertEqual(w.dirty,dirty)
        w.fields['name'].setText('valid');w.update_gadget()
        self.assertEqual(len(w.history),100)
        self.assertEqual([form.dumps() for form in w.history[:-1]],expected_history[1:])
        self.assertEqual(w.history[-1].dumps(),original)
        self.assertEqual(w.future,[])
        w.undo();self.assertEqual(w.form.dumps(),original)
        w.redo();self.assertEqual(w.form.gadgets[0].name,'valid')

    def test_rejected_form_menu_names_preserve_full_history(self):
        w=self.window
        w.form=Form(menus=[Menu(name='first'),Menu(name='second')])
        w.selected_menu=0;w.refresh()
        w.history=[Form(title=f'History {index}') for index in range(100)]
        w.future=[Form(title='Redo')]
        original=w.form.dumps()
        history=[form.dumps() for form in w.history]
        future=[form.dumps() for form in w.future]
        for name in ('','  '):
            w.fname.setText(name);w.update_form()
            self.assertEqual(w.form.dumps(),original)
        for name in ('','bad name','second'):
            w.update_menu_name(name)
            self.assertEqual(w.form.dumps(),original)
        self.assertEqual([form.dumps() for form in w.history],history)
        self.assertEqual([form.dumps() for form in w.future],future)
        self.assertFalse(w.dirty)

    def test_control_characters_rejected_in_macro_path_and_json(self):
        for char in ('\x00','\t','\x1b','\n'):
            form=Form(gadgets=[Gadget(action_mode='MACRO',macro_path='C:/co'+char+'de.mac')])
            with self.subTest(char=repr(char)),self.assertRaises(ValueError):form.pml()
            import json
            from dataclasses import asdict
            with self.assertRaises(ValueError):Form.loads(json.dumps({'version':1,'form':asdict(form)}))

    def test_external_namespace_type_and_pml_names_preserved(self):
        form=Form(gadgets=[Gadget(kind='container',name='host',assembly='Widget.dll',namespace='Vendor.Widgets',control_type='MyControl')],default_body="!this.hostControl = object MyControl()")
        code=form.pml()
        self.assertIn("Using Namespace 'Vendor.Widgets'",code)
        self.assertIn('Member .hostControl Is MyControl',code)
        self.assertIn('!this.hostControl = Object MyControl()',code)
        self.assertNotIn('MYCONTROL()',code)
        self.assertEqual(Form.loads(form.dumps()).pml(),code)
