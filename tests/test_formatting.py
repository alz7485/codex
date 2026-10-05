import unittest
from e3d_designer.formatting import canonical_pml
from e3d_designer.model import Form,Gadget,Menu,MenuItem
from e3d_designer.macro_actions import branch_template


class FormattingTests(unittest.TestCase):
    def test_commands_names_values_and_comments(self):
        source="VAR !!mode 'mixed Value'\nsetup form !!myForm DIALOG DOCK RIGHT\nBUTTON .run AT X 2 Y 3 'Run now' CALL '!this.applySettings()' WIDTH 14\nDEFINE METHOD .applySettings()\n!this.run.val = !!mode\nIF (!!mode EQ 'a') THEN\n$P 'Ready'\nENDIF\nENDMETHOD\n-- Keep this Mixed Comment !!name\n$* Keep This Too"
        expected="Var !!MODE 'MIXED VALUE'\nSetup Form !!MYFORM Dialog Dock Right\nButton .RUN At X 2 Y 3 'RUN NOW' Call '!THIS.APPLYSETTINGS()' Width 14\nDefine Method .APPLYSETTINGS()\n!THIS.RUN.VAL = !!MODE\nIf (!!MODE Eq 'A') Then\n$P 'READY'\nEndif\nEndmethod\n-- Keep this Mixed Comment !!name\n$* Keep This Too"
        self.assertEqual(canonical_pml(source),expected)
        self.assertEqual(canonical_pml(expected),expected)

    def test_quoted_command_context_versus_display_values(self):
        source="BUTTON .run 'savework' CALL 'SAVEWORK'\nOPTION _choice CALL '$$_choice'\nVAR LIST _choice PAIRS\n'if' |IF (!!flag EQ 'a') THEN|\nEXIT\nmenu .tools\nadd 'savework' 'SAVEWORK'\nexit\n!this.initcall = 'SAVEWORK'\n!this.tools.Add('CALLBACK', 'if', 'SAVEWORK')"
        result=canonical_pml(source)
        self.assertIn("Button .RUN 'SAVEWORK' Call 'Savework'",result)
        self.assertIn("'IF' |If (!!FLAG Eq 'A') Then|",result)
        self.assertIn("Add 'SAVEWORK' 'Savework'",result)
        self.assertIn("!THIS.INITCALL = 'Savework'",result)
        self.assertIn("!THIS.TOOLS.ADD('CALLBACK', 'IF', 'Savework')",result)
        self.assertEqual(canonical_pml(result),result)

    def test_multiline_strings_boolean_numeric_and_delimiters(self):
        source="!text = |if -- Keep\nMixed Value|\n!flag = true\n!n = -1.5e-3\n$M \"C:/My Macros/code1.txt\""
        self.assertEqual(canonical_pml(source),"!TEXT = |IF -- KEEP\nMIXED VALUE|\n!FLAG = TRUE\n!N = -1.5E-3\n$M \"C:/MY MACROS/CODE1.TXT\"")

    def test_form_normalizes_raw_code_without_mutating_project(self):
        form=Form(name='mixedForm',variables={'flag':'mixed'},default_body="!!flag = 'ready'",gadgets=[Gadget(name='runButton',label='Run',command='SAVEWORK')])
        before=form.dumps();result=form.pml()
        self.assertIn("Var !!FLAG 'MIXED'",result)
        self.assertIn('Setup Form !!MIXEDFORM Size 70 22 Dialog',result)
        self.assertIn("Call 'Savework'",result)
        self.assertIn("!!FLAG = 'READY'",result)
        self.assertEqual(form.dumps(),before)
        self.assertEqual(result,canonical_pml(form.pml(normalize=False)))
        self.assertEqual(Form.loads(before).pml(),result)

    def test_unknown_command_at_start_of_line_and_uppercase_flag_dedup(self):
        self.assertEqual(canonical_pml('CUSTOMCOMMAND !!flag \'value\''),'Customcommand !!FLAG \'VALUE\'')
        form=Form(variables={'flag':''},gadgets=[Gadget(name='a',action_mode='MACRO',macro_path='C:/code.txt',macro_flag='flag',macro_value='a'),Gadget(name='b',action_mode='MACRO',macro_path='C:/code.txt',macro_flag='flag',macro_value='A')])
        template=branch_template(form,'C:/code.txt')
        self.assertEqual(template.count("Eq 'A'"),1)

    def test_external_macro_and_branch_values_match(self):
        form=Form(variables={'flag':''},gadgets=[Gadget(name='a',action_mode='MACRO',macro_path='C:/code1.txt',macro_flag='flag',macro_value='modeA'),Gadget(name='b',action_mode='MACRO',macro_path='C:/code1.txt',macro_flag='flag',macro_value='modeB')])
        code=form.pml();branches=branch_template(form,'C:/code1.txt')
        self.assertIn("!!FLAG = 'MODEA'",code);self.assertIn("If (!!FLAG Eq 'MODEA') Then",branches)
        self.assertIn("Elseif (!!FLAG Eq 'MODEB') Then",branches)
        self.assertIn('$M "C:/CODE1.TXT"',code)
