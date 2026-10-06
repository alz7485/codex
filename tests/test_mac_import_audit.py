import unittest
from e3d_designer.model import Form
from e3d_designer.mac_import import import_mac,MacImportError
from e3d_designer.names import rename


def source(declarations,constructor='',methods=''):
    return (f"Setup Form !!Imported Dialog Size 70 22\n{declarations}\nExit\n"
            f"Show !!Imported\nDefine Method .Imported()\n{constructor}\nEndmethod\n{methods}")


CHOICES="!Labels = ARRAY()\n!Labels[1] = 'A'\n!this.Choices.Dtext = !Labels"
LIST="List .Choices At X 2 Y 1 'Choices' Multiple Width 20 Height 5"


class ImportAuditTests(unittest.TestCase):
    def test_early_and_repeated_default_calls_keep_execution_order(self):
        for body in ('!this.DEFAULT()\n'+CHOICES,
                     '!this.DEFAULT()\n'+CHOICES+'\n!this.DEFAULT()'):
            with self.subTest(body=body):
                f=import_mac(source(LIST,body,"Define Method .DEFAULT()\n$P 'Ready'\nEndmethod")).form
                self.assertEqual(f.constructor_mode,'SOURCE')
                self.assertIn(body,f.pml())
                self.assertEqual(f.pml().count('!this.DEFAULT()'),body.count('!this.DEFAULT()'))
                self.assertEqual(Form.loads(f.dumps()).constructor_body,body)

    def test_default_array_local_used_later_is_not_removed(self):
        for suffix in ("$P !Selected[1]", "!Saved = !selected", "!Call = '!Selected[1]'"):
            body="!Selected = ARRAY()\n!Selected[1] = 1\n!this.Choices.Val = !Selected\n"+suffix
            f=import_mac(source(LIST,CHOICES,f"Define Method .DEFAULT()\n{body}\nEndmethod")).form
            self.assertIn(body,f.pml());self.assertEqual(f.gadgets[0].initial,'')

    def test_choice_initial_types_and_clear_selection_stay_in_code(self):
        for value in ("'A'",'0','-1'):
            body='!this.Choices.Val = '+value
            f=import_mac(source(LIST,CHOICES,f'Define Method .DEFAULT()\n{body}\nEndmethod')).form
            self.assertEqual(f.gadgets[0].initial,'')
            self.assertIn(body,f.pml())
        body="!Empty = ARRAY()\n!this.Choices.Val = !Empty"
        f=import_mac(source(LIST,CHOICES,f'Define Method .DEFAULT()\n{body}\nEndmethod')).form
        self.assertIn(body,f.pml())

    def test_decimal_integer_array_initial_selection_is_editable(self):
        body="!Chosen = ARRAY()\n!Chosen[1] = 1.0\n!this.Choices.Val = !Chosen"
        f=import_mac(source(LIST,CHOICES,f'Define Method .DEFAULT()\n{body}\nEndmethod')).form
        self.assertEqual(f.gadgets[0].initial,'1')
        self.assertIn('!initialSelection[1] = 1',f.pml())

    def test_empty_referenced_default_definition_is_retained(self):
        for body in ('','-- retained comment'):
            f=import_mac(source(LIST,CHOICES+'\n!this.DEFAULT()',f'Define Method .DEFAULT()\n{body}\nEndmethod')).form
            p=f.pml()
            self.assertEqual(p.count('Define Method .DEFAULT()'),1)
            self.assertIn('!this.DEFAULT()',p)
            self.assertLess(p.index('Define Method .DEFAULT()'),p.index('Define Method .Imported()'))
            if body:self.assertIn(body,p)
            self.assertTrue(Form.loads(f.dumps()).keep_default)

    def test_default_can_be_a_list_callback(self):
        f=import_mac(source(LIST+" Callback '!this.DEFAULT()'",CHOICES,
                            "Define Method .DEFAULT()\n$P 'shared default'\nEndmethod")).form
        self.assertEqual(f.gadgets[0].callback,'DEFAULT')
        self.assertEqual(f.gadgets[0].body,'')
        self.assertIn("Callback '!this.DEFAULT()'",f.pml())
        self.assertEqual(f.pml().count('Define Method .DEFAULT()'),1)
        f.default_body="$P 'changed'"
        self.assertIn("$P 'changed'",f.pml())

    def test_pairs_option_relative_and_width_references_round_trip_and_rename(self):
        declarations="""Option _Pick At X 1 Y 1 'Pick' Call '$$_Pick'
Var List _Pick Pairs
'A' 'cmd'
Exit
Button .Run At Xmax._Pick+1 Ymin._Pick 'Run' Width._Pick"""
        f=import_mac(source(declarations)).form
        g=f.named('Run');self.assertEqual((g.xref,g.yref,g.width_ref),('Pick','Pick','Pick'))
        self.assertIn('Xmax._Pick+1',f.pml());self.assertIn('WIDTH._Pick',f.pml(normalize=False))
        again=import_mac(f.pml()).form
        self.assertEqual(again.named('Run').width_ref,'Pick')
        renamed=rename(f,'gadget',0,'Material')
        self.assertIn('Xmax._Material+1',renamed.pml())
        self.assertIn('WIDTH._Material',renamed.pml(normalize=False))

    def test_wrong_kind_attributes_fail_at_source_line(self):
        for attr in ('SCROLL 3','IS REAL','VAL 2','TABSET','FIXCHARS','BACKGROUND 2','DATABASE OWNERS'):
            with self.subTest(attr=attr),self.assertRaises(MacImportError) as error:
                import_mac(source("Line .Separator At X 1 Y 1 '' Horiz Width 20 Height 1 "+attr))
            self.assertEqual(error.exception.line,2)

    def test_shared_macro_helper_is_kept_as_one_method(self):
        declarations="""Button .A At X 1 Y 1 'A' Width 10 Call '!this.macro_A()'
Button .B At X 1 Y 3 'B' Width 10 Call '!this.macro_A()'"""
        f=import_mac(source(declarations,'',"Define Method .macro_A()\n$M \"C:/macros/task.mac\"\nEndmethod")).form
        self.assertEqual([g.action_mode for g in f.gadgets],['CODE','CODE'])
        self.assertEqual(f.pml().count('Define Method .macro_A()'),1)
        self.assertEqual(f.pml().count("Call '!this.macro_A()'"),2)

    def test_multiple_table_initializers_do_not_drop_a_helper(self):
        def table(name,value):
            return f"""Define Method .{name}()
!HEAD = ARRAY()
!HEAD[1] = 'Header'
!this.Choices.Setheadings(!HEAD)
!ROWS = ARRAY()
!ROWS[1] = ARRAY()
!ROWS[1][1] = '{value}'
!this.Choices.Setrows(!ROWS)
Endmethod"""
        f=import_mac(source(LIST,'!this.First()\n!this.Second()',table('First','A')+'\n'+table('Second','B'))).form
        self.assertEqual(f.constructor_mode,'SOURCE')
        p=f.pml();self.assertIn('Define Method .First',p);self.assertIn('Define Method .Second',p)
        self.assertIn('!this.First()\n!this.Second()',p)

    def test_table_initializer_used_as_callback_keeps_both_calls(self):
        method="""Define Method .Fill()
!HEAD = ARRAY()
!HEAD[1] = 'Header'
!this.Choices.Setheadings(!HEAD)
!ROWS = ARRAY()
!this.Choices.Setrows(!ROWS)
Endmethod"""
        f=import_mac(source(LIST+" Callback '!this.Fill()'",'!this.Fill()',method)).form
        self.assertEqual(f.constructor_mode,'SOURCE')
        p=f.pml();self.assertIn("Callback '!this.Fill()'",p)
        self.assertIn('!this.Fill()',f.constructor_body)
        self.assertEqual(p.count('Define Method .Fill()'),1)

    def test_sparse_table_keeps_code_without_allocating_missing_rows(self):
        method="""Define Method .Fill()
!HEAD = ARRAY()
!HEAD[1] = 'Header'
!this.Choices.Setheadings(!HEAD)
!ROWS = ARRAY()
!ROWS[1000000000] = ARRAY()
!ROWS[1000000000][1] = 'Sparse'
!this.Choices.Setrows(!ROWS)
Endmethod"""
        f=import_mac(source(LIST,'!this.Fill()',method)).form
        self.assertEqual(f.constructor_mode,'SOURCE')
        self.assertIn('!ROWS[1000000000]',f.pml())

    def test_popup_arguments_without_spaces_and_with_quoted_commas(self):
        declarations="""Menu .Popup Popup
Exit
Button .Run At X 1 Y 1 'Run' Width 10"""
        body="!this.Popup.Add('callback','Label, comma','command(1,2)')\n!this.Run.Setpopup(!this.Popup)"
        f=import_mac(source(declarations,body)).form
        self.assertEqual(f.constructor_mode,'GENERATED')
        self.assertEqual(f.menus[0].items[0].label,'Label, comma')
        self.assertEqual(f.menus[0].items[0].command,'command(1,2)')
        self.assertEqual(f.gadgets[0].popup_menu,'Popup')

    def test_comments_crossing_removed_statement_boundaries_remain_complete(self):
        code="""VAR !!Flag 'ready' $( variable comment
variable end $)
Kill !!Imported $( kill comment
kill end $)
Setup Form !!Imported Dialog Size 70 22
Button .Run At X 1 Y 1 'Run' Width 12 Call '!this.Work()'
Exit
Show !!Imported $( show comment
show end $)
Define Method .Work() $( header comment
header end $)
$P 'work'
Endmethod $( endmethod comment
endmethod end $)"""
        f=import_mac(code).form;p=f.pml()
        for comment in ("$( variable comment\nvariable end $)", "$( kill comment\nkill end $)",
                        "$( show comment\nshow end $)", "$( header comment\nheader end $)",
                        "$( endmethod comment\nendmethod end $)"):
            self.assertIn(comment,p)
        self.assertEqual(f.variables,{'Flag':'ready'})
        self.assertEqual(p.count('Show !!Imported'),1)
        import_mac(p).form.pml()

    def test_show_inside_block_comment_is_preserved(self):
        code=source('',methods="")+"\n$( documentation\nSHOW !!Imported\n$)\n"
        f=import_mac(code).form
        self.assertIn('$( documentation\nSHOW !!Imported\n$)',f.after_show_code)

    def test_array_redeclared_for_another_textpane_restores_both_contents(self):
        declarations="""Textpane .First 'First' At X 1 Y 1 Width 20 Height 3
Textpane .Second 'Second' At X 1 Y 5 Width 20 Height 3"""
        body="""!Pane = ARRAY()
!Pane[1] = 'First value'
!this.First.Val = !Pane
!Pane = ARRAY()
!Pane[1] = 'Second value'
!this.Second.Val = !Pane"""
        f=import_mac(source(declarations,'!this.DEFAULT()',f'Define Method .DEFAULT()\n{body}\nEndmethod')).form
        self.assertEqual([g.pane_lines for g in f.gadgets],[['First value'],['Second value']])


if __name__=='__main__':unittest.main()
