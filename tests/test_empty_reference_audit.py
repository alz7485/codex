import unittest

from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget,Method,Menu,MenuItem
from e3d_designer.method_output import check_editable_code


class EmptyReferenceAuditTests(unittest.TestCase):
    def assert_blocked_without_mutation(self,form,name='Empty'):
        before=form.dumps()
        for normalize in (False,True):
            with self.subTest(normalize=normalize):
                with self.assertRaisesRegex(ValueError,r'空メソッド \.'+name):
                    form.pml(normalize=normalize)
                self.assertEqual(form.dumps(),before)

    def test_argument_evaluation_is_not_silently_deleted(self):
        form=Form(extra_methods=[Method('Empty','(!value Is String)'),
                                Method('Effect','() Is String',"$P 'side effect'\nReturn 'value'")],
                  after_show_code='!this.Empty(!this.Effect())')
        self.assert_blocked_without_mutation(form)
        form.extra_methods[0].body='$P !value'
        code=form.pml()
        self.assertIn('!this.Empty(!this.Effect())',code)
        self.assertIn('Define Method .Empty',code)

    def test_empty_returning_method_in_expression_blocks_output(self):
        form=Form(extra_methods=[Method('Empty','() Is Real')],
                  default_body='!value = !this.Empty()')
        self.assert_blocked_without_mutation(form)

    def test_callback_assignments_recognize_all_quotes_and_form_prefixes(self):
        for prefix in ('!!','!','.',''):
            for quote in ("'",'|','"'):
                for attribute in ('callback','initcall','autocall','okcall','cancelcall'):
                    with self.subTest(prefix=prefix,quote=quote,attribute=attribute):
                        form=Form(name='Demo',form_prefix=prefix,gadgets=[Gadget(name='Run')],
                                  extra_methods=[Method('Empty')],
                                  constructor_body=f'!this.Run.{attribute} = {quote}{prefix}Demo.Empty({quote}')
                        self.assert_blocked_without_mutation(form)

    def test_commands_events_pairs_and_menus_reject_remaining_argument_calls(self):
        command="!this.Empty('value')"
        forms=[
            Form(gadgets=[Gadget(name='Run',command=command)]),
            Form(gadgets=[Gadget(kind='option',name='Pick',items=['A'],item_commands=[command])]),
            Form(menus=[Menu(name='Tools',items=[MenuItem('Run',command)])]),
            Form(menus=[Menu(name='Tools',popup=True,items=[MenuItem('Run',command)])]),
            Form(initcall=command),Form(okcall=command),Form(cancelcall=command),
            Form(gadgets=[Gadget(kind='view',name='View',view_code=command)]),
            Form(preamble_code=command),
        ]
        for index,form in enumerate(forms):
            with self.subTest(index=index):
                form.extra_methods=[Method('Empty','(!value Is String)')]
                self.assert_blocked_without_mutation(form)

    def test_empty_constructor_is_also_checked_but_initialized_constructor_is_kept(self):
        form=Form(name='Demo',after_show_code='!!Demo.Demo()')
        self.assert_blocked_without_mutation(form,'Demo')
        form.gadgets=[Gadget(kind='text',name='Input',initial='Ready')]
        code=form.pml()
        self.assertIn('!!Demo.Demo()',code)
        self.assertIn('Define Method .Demo()',code)

    def test_imported_problem_can_be_edited_without_losing_source_or_layout(self):
        source=("Setup Form !!Demo Dialog\nButton .Run 'Run' Call '!this.Empty(1)'\nExit\n"
                "Show !!Demo\nDefine Method .Empty(!value Is Real)\n-- no code\nEndmethod")
        form=import_mac(source).form
        self.assertEqual(form.named('Run').command,'!this.Empty(1)')
        self.assert_blocked_without_mutation(form)
        restored=Form.loads(form.dumps())
        restored.extra_methods[0].body='$P !value'
        self.assertIn("Call '!this.Empty(1)'",restored.pml())

    def test_partial_import_keeps_editable_empty_method_references(self):
        source=("Setup Form !!Demo Dialog\nButton .Run 'Run' Call '!this.Empty(1)'\nExit\n"
                "Show !!Demo\nDefine Method .Empty(!value Is Real)\n-- no code\nEndmethod")
        strict=import_mac(source).form;partial=import_mac(source,partial=True).form
        self.assertEqual(strict.dumps(),partial.dumps())
        self.assert_blocked_without_mutation(partial)

    def test_editable_check_still_rejects_method_cycles(self):
        form=Form(extra_methods=[Method('One',body='!this.Two()'),Method('Two',body='!this.One()')])
        for with_empty_reference in (False,True):
            with self.subTest(with_empty_reference=with_empty_reference):
                if with_empty_reference:
                    form.extra_methods.append(Method('Empty','(!value Is Real)'))
                    form.after_show_code='!this.Empty(1)'
                with self.assertRaisesRegex(ValueError,'循環'):check_editable_code(form)

    def test_data_comments_unknown_methods_and_other_forms_are_preserved(self):
        body=("$P '!this.Empty(1)'\n!text = |!this.Empty()|\n"
              "-- !this.Empty(1)\n$( !this.Run.callback = '!this.Empty(' $)\n"
              "!!Other.Empty(1)\n!this.EmptyOther(1)\n!this.Unknown(1)")
        form=Form(extra_methods=[Method('Empty')],default_body=body,
                  gadgets=[Gadget(kind='text',name='Input',label='!this.Empty(1)',initial='!this.Empty()')],
                  variables={'value':'!this.Empty(1)'})
        for normalize in (False,True):
            code=form.pml(normalize=normalize)
            self.assertIn(body,code)
            self.assertIn("'!this.Empty(1)'",code)
            self.assertIn("'!this.Empty()'",code)

    def test_source_constructor_does_not_validate_discarded_generated_commands(self):
        command='!this.Empty(1)'
        form=Form(constructor_mode='SOURCE',initcall=command,okcall=command,cancelcall=command,
                  menus=[Menu(name='Popup',popup=True,items=[MenuItem('Run',command)])],
                  extra_methods=[Method('Empty','(!value Is Real)')])
        for normalize in (False,True):
            code=form.pml(normalize=normalize)
            self.assertNotIn(command,code)
            self.assertNotIn('Define Method',code)
        form.constructor_body="!this.initcall = '!this.Empty(1)'"
        self.assert_blocked_without_mutation(form)


if __name__=='__main__':unittest.main()
