import unittest
from e3d_designer.formatting import canonical_pml
from e3d_designer.model import Form,Gadget,Menu,MenuItem
from e3d_designer.macro_actions import branch_template

class FormattingTests(unittest.TestCase):
    def test_only_generated_keywords_are_formatted(self):
        source="BUTTON .RunButton AT X 2 Y 3 'Run now' CALL 'SaVeWoRk' WIDTH 14\nVAR !!Mode 'Mixed'\nOPTION _Choice CALL '$$_Choice'\n-- Keep Comment"
        expected="Button .RunButton At X 2 Y 3 'Run now' Call 'SaVeWoRk' Width 14\nVar !!Mode 'Mixed'\nOption _Choice Call '$$_Choice'\n-- Keep Comment"
        self.assertEqual(canonical_pml(source),expected);self.assertEqual(canonical_pml(expected),expected)
    def test_user_code_names_values_and_paths_are_preserved(self):
        body="iF (!!Mode EQ 'a') tHeN\n  $p 'Mixed Value'\neNdIf"
        form=Form(name='MyForm',variables={'Mode':'Mixed'},default_body=body,after_show_code='sAvEwOrK',gadgets=[Gadget(name='RunButton',label='Run now',callback='DoWork',body=body),Gadget(kind='text',name='InputValue',initial='MiXeD')],menus=[Menu(name='Tools',items=[MenuItem(label='Run menu',command='SaVeWoRk')])])
        before=form.dumps();code=form.pml()
        for value in ("Var !!Mode 'Mixed'",'Setup Form !!MyForm',"'Run now'","Call '!this.DoWork()'",'Define Method .DoWork()',body,'sAvEwOrK',"Add 'Run menu' 'SaVeWoRk'","!this.InputValue.val = 'MiXeD'"):self.assertIn(value,code)
        self.assertEqual(form.dumps(),before);self.assertEqual(Form.loads(before).pml(),code)
    def test_option_commands_combo_values_and_view_code(self):
        raw='  iF TRUE tHeN\n  $p |Mixed|\n  eNdIf'
        f=Form(gadgets=[Gadget(kind='option',name='MyChoice',items=['First'],item_commands=['SaVeWoRk']),Gadget(kind='combo',name='ComboChoice',items=['Label'],item_values=['ActualValue']),Gadget(kind='view',name='MyView',view_code=raw)])
        code=f.pml()
        self.assertIn("'First' 'SaVeWoRk'",code);self.assertIn("'ActualValue'",code)
        self.assertIn('\n'.join('  '+line for line in raw.split('\n')),code)
    def test_branch_values_are_case_sensitive_and_match_macro_calls(self):
        f=Form(variables={'Flag':''},gadgets=[Gadget(name='a',action_mode='MACRO',macro_path='C:/MyFolder/Code.mac',macro_flag='Flag',macro_value='modeA'),Gadget(name='b',action_mode='MACRO',macro_path='C:/MyFolder/Code.mac',macro_flag='Flag',macro_value='ModeA')])
        code=f.pml();template=branch_template(f,'C:/MyFolder/Code.mac')
        for value in ('modeA','ModeA'):
            self.assertIn(f"!!Flag = '{value}'",code);self.assertIn(f"!!Flag Eq '{value}'",template)
        self.assertIn('$M "C:/MyFolder/Code.mac"',code)
