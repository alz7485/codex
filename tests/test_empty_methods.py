import unittest
from e3d_designer.model import Form,Gadget

class EmptyMethodTests(unittest.TestCase):
    def test_empty_or_comment_only_methods_have_no_calls_or_definitions(self):
        for body in ('','  \n','-- 説明\n  $* コメント'):
            for kind in ('button','text','toggle','list','combo','slider','selector'):
                with self.subTest(kind=kind,body=body):
                    f=Form(default_body=body,gadgets=[Gadget(kind=kind,name='part',callback='onPart',body=body)])
                    code=f.pml(normalize=False)
                    self.assertNotIn('onPart',code)
                    if kind!='slider':self.assertNotIn('DEFINE METHOD .DEFAULT()',code)
                    else:self.assertIn('!this.part.val = 50',code)
                    self.assertEqual(f.gadgets[0].callback,'onPart');self.assertEqual(f.gadgets[0].body,body)
    def test_code_and_generated_initial_values_keep_methods(self):
        f=Form(gadgets=[Gadget(name='part',callback='run',body="-- Note\n$p 'Run'"),Gadget(kind='text',name='input',initial='Hello',callback='DEFAULT')])
        code=f.pml(normalize=False)
        self.assertIn('define method .run()',code);self.assertIn("CALL '!this.run()'",code)
        self.assertIn('DEFINE METHOD .DEFAULT()',code);self.assertIn("CALL '!this.DEFAULT()'",code)
        self.assertIn("!this.input.val = 'Hello'",code)
        f.gadgets[0].body='';code=f.pml(normalize=False);self.assertNotIn('!this.run()',code)
    def test_explicit_command_and_generated_macros_are_preserved(self):
        f=Form(gadgets=[Gadget(name='part',command='SAVEWORK'),Gadget(name='macro',x=20,action_mode='MACRO',macro_path='C:/run.mac')])
        code=f.pml(normalize=False)
        self.assertIn("CALL 'SAVEWORK'",code);self.assertIn('define method .macro_macro()',code)
        self.assertNotIn('DEFINE METHOD .DEFAULT()',code)
