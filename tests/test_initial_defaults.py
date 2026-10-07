from e3d_designer.formatting import canonical_pml
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication
from e3d_designer.model import Form,Gadget
from e3d_designer.app import Window


class InitialTests(unittest.TestCase):
    def test_values_in_default_after_choices_with_custom_code(self):
        form=Form(default_body="$p 'ready'",gadgets=[
            Gadget(kind='text',name='name',initial='Pump'),
            Gadget(kind='text',name='size',value_type='REAL',initial='0'),
            Gadget(kind='paragraph',name='label',initial='Ready'),
            Gadget(kind='toggle',name='enabled',initial='false'),
            Gadget(kind='option',name='mode',items=['A','B'],initial='2'),
            Gadget(kind='combo',name='combo',items=['A'],initial='1'),
            Gadget(kind='list',name='rows',items=['A','B','C'],selection_mode='MULTIPLE',initial='1,3'),
            Gadget(kind='slider',name='level',slider_value=25),
            Gadget(kind='textpane',name='notes',pane_lines=['  line'])])
        pml=form.pml(normalize=False)
        default=pml.split('DEFINE METHOD .DEFAULT()',1)[1].split('ENDMETHOD',1)[0]
        constructor=pml.split('define method .userform()',1)[1].split('endmethod',1)[0]
        self.assertLess(pml.index('DEFINE METHOD .DEFAULT()'),pml.index('define method .userform()'))
        self.assertNotIn("!this.name.val = 'Pump'",constructor)
        self.assertIn('!this.DEFAULT()',constructor)
        self.assertLess(constructor.index('!this.rows.dtext'),constructor.index('!this.DEFAULT()'))
        for line in ("!this.name.val = 'Pump'",'!this.size.val = 0',"!this.label.val = 'Ready'",'!this.enabled.val = FALSE','!this._mode.val = 2','!this.combo.val = 1','!initialSelection[2] = 3','!this.rows.val = !initialSelection','!this.level.val = 25',"!paneLines[1] = '  line'"):
            self.assertIn(line,default)
        self.assertLess(default.index('!this.name.val'),default.index("$p 'ready'"))
        self.assertEqual(Form.loads(form.dumps()).pml(normalize=False),pml)

    def test_radio_parent_index_and_validation(self):
        form=Form(gadgets=[Gadget(kind='frame',name='group',width=30,height=10),Gadget(kind='rtoggle',name='a',parent='group',initial='FALSE'),Gadget(kind='rtoggle',name='b',parent='group',initial='TRUE',y=3)])
        self.assertIn('!this.group.val = 2',form.pml(normalize=False))
        form.gadgets[1].initial='TRUE'
        with self.assertRaises(ValueError):form.validate()
        for gadget in (Gadget(kind='toggle',initial='bad'),Gadget(kind='option',items=['A'],initial='2'),Gadget(kind='list',items=['A'],selection_mode='MULTIPLE',initial='1,1'),Gadget(kind='combo',items=['A'],initial='1,2')):
            with self.subTest(kind=gadget.kind),self.assertRaises(ValueError):Form(gadgets=[gadget]).validate()

    def test_repeated_export_no_duplicates_and_always_show(self):
        form=Form(show_form=False,gadgets=[Gadget(kind='text',initial='A')])
        one=form.pml(normalize=False);two=form.pml(normalize=False);self.assertEqual(one,two)
        self.assertEqual(one.count("!this.button1.val = 'A'"),1)
        self.assertEqual(one.count('SHOW !!userform'),1)
        self.assertLess(one.index('SHOW !!'),one.index('define method'))
        self.assertEqual(form.default_body,'')

    def test_gui_initial_fields_and_resizable_processing_editors(self):
        app=QApplication.instance() or QApplication([]);window=Window()
        try:
            self.assertFalse(hasattr(window,'show_form'))
            for kind,value in (('toggle','TRUE'),('option','1'),('combo','1'),('list','1'),('paragraph','Ready')):
                window.add(kind)
                if kind in ('option','combo','list'):window.choices.setPlainText('A\nB')
                self.assertTrue(window.fields['initial'].isEnabled())
                window.fields['initial'].setText(value);window.update_gadget()
                self.assertIn(canonical_pml('DEFINE METHOD .DEFAULT()'),window.code.toPlainText())
                self.assertEqual(window.form.gadgets[-1].initial,value)
                window.undo();self.assertEqual(window.form.gadgets[-1].initial,'')
            self.assertGreaterEqual(window.default_body.minimumHeight(),96)
            self.assertGreaterEqual(window.body.minimumHeight(),96)
            self.assertEqual(window.inspector_tabs.tabText(1),'処理')
            self.assertTrue(window.inspector_tabs.widget(1).isAncestorOf(window.default_body))
            self.assertEqual(window.method_splitter.count(),3)
        finally:
            app.clipboard().clear();window.dirty=False;window.close();app.processEvents()
