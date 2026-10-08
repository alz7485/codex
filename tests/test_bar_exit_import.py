import unittest

from e3d_designer.mac_import import import_mac, MacImportError
from e3d_designer.model import Form
from e3d_designer.partial_import import declaration_spans


def source(body, program='Show !!Demo'):
    return 'Setup Form !!Demo Dialog Size 70 22\n'+body+'\nExit\n'+program


class ExplicitBarExitImportTests(unittest.TestCase):
    def test_explicit_bar_exit_keeps_referenced_menu_and_following_gadget(self):
        text=source("BAR\nADD 'add' .ad01\nEXIT\nMENU .ad01\nADD 'Run' 'Mixed Command $server'\nEXIT\nButton .Run 'Run'")
        for partial in (False, True):
            with self.subTest(partial=partial):
                result=import_mac(text,partial=partial);menu=result.form.menus[0]
                self.assertEqual((menu.name,menu.label,menu.popup,menu.on_bar),('ad01','add',False,True))
                self.assertEqual(menu.items[0].command,'Mixed Command $server')
                self.assertIsNotNone(result.form.named('Run'))
                self.assertTrue(any('BAR直後のEXIT' in message for message in result.warnings))
                self.assertEqual(result.form.partial_import_notes,[])
                roundtrip=import_mac(Form.loads(result.form.dumps()).pml()).form
                self.assertEqual(roundtrip.menus,result.form.menus)

    def test_case_spacing_comments_and_all_literal_delimiters(self):
        for quote in ("'",'|','"'):
            with self.subTest(quote=quote):
                body=f"bar\nadd   {quote}Mixed Title{quote}    .Ad01\n  exit -- close BAR\n\n-- MENU follows\nmenu .aD01\nadd {quote}Run{quote} {quote}MiXeD{quote}\nexit"
                result=import_mac(source(body))
                self.assertEqual(result.form.menus[0].name,'aD01')
                self.assertEqual(result.form.menus[0].display_label,'Mixed Title')
                self.assertEqual(result.form.menus[0].items[0].command,'MiXeD')
                _,spans=declaration_spans(source(body))
                self.assertEqual(spans[0],(1,4,'BAR'))

    def test_multiple_forward_menus_keep_bar_order(self):
        result=import_mac(source("BAR\nADD 'A' .First\nADD 'B' .Second\nEXIT\nMENU .Second\nADD 'Two' 'two'\nEXIT\nMENU .First\nADD 'One' 'one'\nEXIT"))
        self.assertEqual([m.name for m in result.form.menus],['First','Second'])
        self.assertEqual([m.label for m in result.form.menus],['A','B'])

    def test_menu_precedes_bar_so_final_form_exit_is_not_claimed(self):
        result=import_mac(source("MENU .ad01\nADD 'Run' 'run'\nEXIT\nBAR\nADD 'add' .ad01"))
        self.assertEqual(result.form.menus[0].label,'add')
        self.assertFalse(any('BAR直後のEXIT' in message for message in result.warnings))
        self.assertNotIn('MENU',result.form.after_show_code.upper())

    def test_existing_no_bar_exit_format_remains_valid(self):
        result=import_mac(source("BAR\nADD 'add' .ad01\nMENU .ad01\nADD 'Run' 'run'\nEXIT"))
        self.assertEqual(result.form.menus[0].items[0].label,'Run')
        self.assertFalse(any('BAR直後のEXIT' in message for message in result.warnings))

    def test_explicit_exit_does_not_change_nested_frame_exit_ownership(self):
        body="BAR\nADD 'add' .ad01\nEXIT\nMENU .ad01\nADD 'Run' 'run'\nEXIT\nFRAME .Group 'Group'\nBUTTON .Child 'Child'\nEXIT\nBUTTON .Root 'Root'"
        result=import_mac(source(body))
        self.assertEqual(result.form.named('Child').parent,'Group')
        self.assertEqual(result.form.named('Root').parent,'')

    def test_form_show_boundary_is_never_crossed_to_find_menu(self):
        text=source("BAR\nADD 'add' .ad01", "Show !!Demo\nMENU .ad01\nADD 'Run' 'run'\nEXIT")
        with self.assertRaisesRegex(MacImportError,'終了後') as error:import_mac(text)
        self.assertEqual(error.exception.line,3)

    def test_unrelated_menu_cannot_relabel_the_form_exit_as_bar_exit(self):
        text=source("BAR\nADD 'add' .ad01\nEXIT\nMENU .Other\nADD 'Run' 'run'\nEXIT")
        with self.assertRaisesRegex(MacImportError,'参照先MENUが見つかりません'):import_mac(text)

    def test_missing_menu_and_popup_report_separate_actionable_errors(self):
        with self.assertRaisesRegex(MacImportError,r'MENU \.ad01.*ADD'):import_mac(source("BAR\nADD 'add' .ad01"))
        text=source("BAR\nADD 'add' .ad01\nEXIT\nMENU .ad01 POPUP\nEXIT")
        with self.assertRaisesRegex(MacImportError,'POPUP') as error:import_mac(text)
        self.assertEqual(error.exception.line,3)

    def test_partial_spans_include_bar_exit_and_continue_after_it(self):
        text=source("BAR\nADD 'add' .ad01\nEXIT\nMENU .ad01\nADD 'Run' 'run'\nEXIT\nFRAME .Group 'Group'\nBUTTON .Child 'Child'\nEXIT")
        _,spans=declaration_spans(text)
        self.assertIn((1,4,'BAR'),spans);self.assertIn((4,7,'MENU'),spans)
        self.assertIn((7,10,'FRAME'),spans)

    def test_partial_recovery_does_not_treat_bar_exit_as_unknown_gadget_exit(self):
        text=source("FUTURE .Unknown 'Future'\nBAR\nADD 'add' .ad01\nEXIT\nMENU .ad01\nADD 'Run' 'run'\nEXIT\nBUTTON .Kept 'Kept'")
        result=import_mac(text,partial=True)
        self.assertEqual([g.name for g in result.form.gadgets],['Kept'])
        self.assertEqual(result.form.menus[0].name,'ad01')
        self.assertEqual(len(result.form.partial_import_notes),1)
        self.assertIn('FUTURE',result.form.partial_import_notes[0])

    def test_partial_bad_menu_recovery_can_continue_to_gadgets(self):
        text=source("BAR\nADD 'add' .ad01\nEXIT\nMENU .ad01\nADD 'Broken'\nEXIT\nBUTTON .Kept 'Kept'")
        result=import_mac(text,partial=True)
        self.assertEqual([g.name for g in result.form.gadgets],['Kept'])
        self.assertEqual(result.form.menus,[])
        self.assertTrue(any('MENU' in note for note in result.form.partial_import_notes))
        self.assertTrue(any('BAR' in note for note in result.form.partial_import_notes))

