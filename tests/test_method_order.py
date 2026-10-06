import unittest

from e3d_designer.model import Form,Gadget


class MethodOrderTests(unittest.TestCase):
    def test_default_and_table_methods_are_defined_before_constructor_calls(self):
        form=Form(gadgets=[Gadget(kind='text',name='input',initial='Hello'),
            Gadget(kind='list',name='rows',list_mode='TABLE',headings=['Name'],rows=[['Pump']],initial='1')])
        code=form.pml(normalize=False)
        constructor=code.index('define method .userform()')
        self.assertLess(code.index('DEFINE METHOD .DEFAULT()'),constructor)
        self.assertLess(code.index('define method .populate_rows()'),constructor)
        self.assertLess(constructor,code.index('!this.DEFAULT()'))
        self.assertLess(code.index('!this.populate_rows()'),code.index('!this.DEFAULT()'))
        self.assertLess(code.index('SHOW !!userform'),code.lower().index('define method'))

    def test_default_calls_user_method_chain_in_dependency_order_without_rewriting_input(self):
        form=Form(name='MyForm',default_body='!THIS.Start()\n$p |Keep Case|',gadgets=[
            Gadget(name='startButton',callback='Start',body='!!MyForm.Finish()'),
            Gadget(name='finishButton',callback='Finish',body="!this.Middle()\n$p 'Finish'"),
            Gadget(name='middleButton',callback='Middle',body="$p 'Middle'")])
        for normalize in (False,True):
            with self.subTest(normalize=normalize):
                code=form.pml(normalize=normalize);lower=code.lower()
                order=[lower.index('define method .'+name+'(') for name in ('middle','finish','start','default','myform')]
                self.assertEqual(order,sorted(order))
                self.assertIn('!THIS.Start()\n$p |Keep Case|',code)
                self.assertIn("!!MyForm.Finish()",code)
                self.assertEqual(Form.loads(form.dumps()).pml(normalize=normalize),code)

    def test_strings_comments_and_other_forms_do_not_create_false_dependencies(self):
        default="-- !this.Run()\n$* !!userform.Run()\n$p '!this.Run()'\n$p |!!userform.Run()|\n$p \"!this.Run()\""
        form=Form(default_body=default,gadgets=[Gadget(callback='Run',body='!this.DEFAULT()\n!!OtherForm.Run()')])
        for normalize in (False,True):
            with self.subTest(normalize=normalize):
                code=form.pml(normalize=normalize)
                self.assertIn(default,code)
                self.assertLess(code.lower().index('define method .default()'),code.lower().index('define method .run()'))

    def test_recursive_method_can_reference_itself(self):
        code=Form(gadgets=[Gadget(callback='Recursive',body='!this.Recursive()')]).pml(normalize=False)
        self.assertEqual(code.count('define method .Recursive()'),1)
        self.assertLess(code.index('define method .Recursive()'),code.index('define method .userform()'))

    def test_cycle_is_reported_without_changing_project(self):
        form=Form(gadgets=[Gadget(name='a',callback='First',body='!this.Second()'),Gadget(name='b',callback='Second',body='!this.First()')])
        original=form.dumps()
        with self.assertRaisesRegex(ValueError,'First → Second → First'):form.pml()
        self.assertEqual(form.dumps(),original)

    def test_default_can_use_generated_table_and_macro_methods(self):
        form=Form(default_body='!this.populate_rows()\n!this.macro_launch()',gadgets=[
            Gadget(kind='list',name='rows',list_mode='TABLE',headings=['Name'],rows=[['Pump']]),
            Gadget(name='launch',action_mode='MACRO',macro_path='C:/Run.mac')])
        code=form.pml(normalize=False)
        default=code.index('DEFINE METHOD .DEFAULT()')
        self.assertLess(code.index('define method .populate_rows()'),default)
        self.assertLess(code.index('define method .macro_launch()'),default)
        self.assertLess(default,code.index('define method .userform()'))
