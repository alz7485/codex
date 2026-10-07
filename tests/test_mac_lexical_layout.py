"""MAC whitespace, interchangeable delimiters, and EXIT-based nesting."""
import unittest

from e3d_designer.callbacks import join_callback
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac, MacImportError
from e3d_designer.model import Form, Gadget, literal
from e3d_designer.partial_import import declaration_spans


def source(declarations, methods='', title="'Title'"):
    return (f"Setup    Form   !!Demo    Dialog    Size   70   22\n"
            f"Title    {title}\n{declarations}\nExit\n"
            f"Show    !!Demo\n{methods}")


class MacLexicalLayoutTests(unittest.TestCase):
    def roundtrip(self, text):
        strict = import_mac(text).form
        self.assertEqual(strict.dumps(), import_mac(text, partial=True).form.dumps())
        restored = Form.loads(strict.dumps())
        return strict, import_mac(restored.pml()).form

    def test_option_content_indents_one_level_below_declaration(self):
        for parent in ('', 'Group'):
            with self.subTest(parent=parent):
                gadgets = [Gadget(kind='frame', name='Group', width=30, height=10)] if parent else []
                gadgets.append(Gadget(kind='option', name='Pick', label='Pick',
                                      items=['One', "O'Brien"], item_commands=['Q CE', "$P 'ok'"],
                                      parent=parent))
                form = Form(gadgets=gadgets)
                indent = '    ' if parent else '  '
                expected = (indent + "Option _Pick At X 2 Y 1 'Pick' Call '$$_Pick'\n" +
                            indent + "  Var List _Pick Pairs\n" +
                            indent + "  'One' 'Q CE'\n" +
                            indent + "  |O'Brien| |$P 'ok'|\n" +
                            indent + "Exit")
                self.assertIn(expected, form.pml())
                imported = import_mac(form.pml()).form.named('Pick')
                self.assertEqual(imported.parent, parent)
                self.assertEqual(imported.items, ['One', "O'Brien"])
                self.assertEqual(imported.item_commands, ['Q CE', "$P 'ok'"])

    def test_empty_option_still_closes_at_its_own_indentation(self):
        code = Form(gadgets=[Gadget(kind='option', name='Pick')]).pml()
        self.assertIn("Call '$$_Pick'\n    Var List _Pick Pairs\n  Exit", code)
        self.assertEqual(import_mac(code).form.named('Pick').items, [])

    def test_single_quote_and_pipe_mean_the_same_for_all_data(self):
        forms = []
        for quote in ("'", '|', '"'):
            forms.append(import_mac(source(
                f"Option _Pick At X 1 Y 1 {quote}Pick    label{quote} Call {quote}$$_Pick{quote}\n"
                f"Var List _Pick Pairs\n"
                f"{quote}One    label{quote}    {quote}Q    CE{quote}\n"
                "Exit", title=quote+'Title    text'+quote)).form)
        self.assertEqual([form.dumps() for form in forms], [forms[0].dumps()]*3)

    def test_apostrophe_in_pipe_string_and_pipe_in_single_quoted_string(self):
        text = source("Button .Run At X 1 Y 1 |O'Brien    says \"hi\"| Call |$P 'O'    --note|\n"
                      "Paragraph .Label At X 1 Y 3 Text 'A|B    \"quoted\"' Width 20")
        for form in self.roundtrip(text):
            self.assertEqual(form.named('Run').label, "O'Brien    says \"hi\"")
            self.assertEqual(form.named('Run').command, "$P 'O'    --note")
            self.assertEqual(form.named('Label').label, 'A|B    "quoted"')

    def test_punctuation_and_keywords_in_strings_never_change_scope(self):
        text = source("Frame .Outer 'Outer'\n"
                      "Button .Run At X 1 Y 1 |Exit -- ' comma, () [1] ! / \\ & < > : ;| "
                      "Call |$P 'Exit'    $* $( $) !!Flag|\nExit\n"
                      "Button .Outside At X 1 Y 8 'Outside'")
        for form in self.roundtrip(text):
            self.assertEqual(form.named('Run').parent, 'Outer')
            self.assertEqual(form.named('Outside').parent, '')
            self.assertEqual(form.named('Run').command, "$P 'Exit'    $* $( $) !!Flag")
            self.assertEqual(form.named('Run').comment, '')

    def test_repeated_separators_are_ignored_but_quoted_spaces_and_tabs_survive(self):
        text = source("Text\t .Input    At\t X    2   Y  1   '  A    B\tC  '  Width   18   Is   String",
                      "Define    Method   .DEFAULT(   )\n"
                      "!this.Input.Val     =    |  mixed    value\tend  |\nEndmethod")
        for form in self.roundtrip(text):
            self.assertEqual(form.named('Input').label, '  A    B\tC  ')
            self.assertEqual(form.named('Input').initial, '  mixed    value\tend  ')
            self.assertEqual(form.default_mode, 'GENERATED')

    def test_unquoted_method_spacing_is_ignored_without_normalizing_raw_body(self):
        body = "  $P    |Case    sensitive|\n    -- Keep    spaces"
        text = source("Button .Run 'Run' Call '!this.Work()'",
                      f"Define    Method   .Work(   )\n{body}\nEndmethod\n"
                      "Define   Method   .Demo(\t)\nEndmethod")
        for form in self.roundtrip(text):
            self.assertEqual(form.named('Run').callback, 'Work')
            self.assertEqual(form.named('Run').body, body)
            self.assertEqual(form.constructor_mode, 'GENERATED')

    def test_array_and_table_whitespace_preserves_each_quoted_value(self):
        text = source("Option .Pick 'Pick'\nList .Table At X 1 Y 5 'Table' Single Width 25 Height 5",
                      "Define    Method   .Demo(   )\n"
                      "!Labels    =    Object    Array(   )\n"
                      "!Labels[1]    =   |  One    label  |\n"
                      "!this.Pick.Dtext    =    !Labels\n"
                      "!Values    =    Array(   )\n"
                      "!Values[1]    =    '  real    value  '\n"
                      "!this.Pick.Rtext    =    !Values\n"
                      "!this.FillTable   (   )\nEndmethod\n"
                      "Define    Method   .FillTable(   )\n"
                      "!HEAD    =   Array(   )\n!HEAD[1] = |  Head    one  |\n"
                      "!this.Table.Setheadings(   !HEAD   )\n"
                      "!ROWS[1]   =   Array(   )\n!ROWS[1][1] = '  Cell    one  '\n"
                      "!this.Table.Setrows(   !ROWS   )\nEndmethod")
        for form in self.roundtrip(text):
            self.assertEqual(form.named('Pick').items, ['  One    label  '])
            self.assertEqual(form.named('Pick').item_values, ['  real    value  '])
            self.assertEqual(form.named('Table').headings, ['  Head    one  '])
            self.assertEqual(form.named('Table').rows, [['  Cell    one  ']])
            self.assertEqual(form.constructor_mode, 'GENERATED')

    def test_noncanonical_quoted_callback_is_preserved_and_still_linked(self):
        for kind in ('Button', 'Text', 'Toggle', 'Option', 'List', 'Selector'):
            with self.subTest(kind=kind):
                expression = '   !THIS.Work  (   )   '
                text = source(f"{kind} .Run 'Run' Call |{expression}|",
                              "Define Method .Work(   )\n$P 'work'\nEndmethod")
                for form in self.roundtrip(text):
                    gadget = form.named('Run')
                    self.assertEqual(gadget.callback, 'Work')
                    self.assertEqual(gadget.callback_expression, expression)
                    self.assertIn(literal(expression), form.pml())
                    self.assertEqual(form.pml().count('Define Method .Work'), 1)

    def test_noncanonical_default_callback_preserves_literal(self):
        expression = ' !this.DEFAULT (  ) '
        text = source(f"Button .Run 'Run' Call |{expression}|",
                      "Define Method .DEFAULT(   )\n$P 'default'\nEndmethod")
        for form in self.roundtrip(text):
            self.assertEqual(form.named('Run').callback_expression, expression)
            self.assertIn(literal(expression), form.pml())

    def test_callback_copy_and_edit_preserve_spaces_and_follow_target(self):
        text = source("Button .Run 'Run' Call |  !this.Work (   )  |",
                      "Define Method .Work()\n$P 'work'\nEndmethod")
        form = import_mac(text).form
        copied, index = clone_subtree(form, form, 0)
        gadget = copied.gadgets[index]
        self.assertEqual(gadget.callback_expression, f'  !this.{gadget.callback} (   )  ')
        self.assertIn(literal(gadget.callback_expression), copied.pml())
        previous = gadget.callback
        gadget.callback = 'Changed'
        join_callback(copied, gadget, previous)
        self.assertEqual(gadget.callback_expression, '')
        self.assertIn("Call '!this.Changed()'", copied.pml())

    def test_invalid_callback_source_is_rejected_and_stale_target_never_emitted(self):
        form = Form(gadgets=[Gadget(name='Run', callback='Work', body="$P 'work'",
                                   callback_expression='!this.Other()')])
        self.assertIn("Call '!this.Work()'", form.pml())
        self.assertNotIn("Call '!this.Other()'", form.pml())
        for value in (None, 3, '\x00', '\n'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                form.gadgets[0].callback_expression = value
                form.pml()

    def test_indentation_does_not_determine_parent_and_leaf_exits_do_not_close_frame(self):
        declarations = (
            "        Frame .Outer 'Outer'\n"
            "Frame .Inner 'Inner'\n"
            "    Option _Pick 'Pick' Call '$$_Pick'\n"
            "Var     List    _Pick    Pairs\n"
            "  |Exit|     |$P 'Exit'|\n"
            "              Exit\n"
            "Button .Inside 'Inside'\n"
            "              Exit\n"
            "View .Display At X 1 Y 5 Area Width 20 Height 4\n"
            "                  Exit\n"
            "Button .AfterView At X 1 Y 10 'After view'\n"
            "Exit\n"
            "                 Button .Outside At X 1 Y 17 'Outside'")
        expected = {'Outer':'', 'Inner':'Outer', 'Pick':'Inner', 'Inside':'Inner',
                    'Display':'Outer', 'AfterView':'Outer', 'Outside':''}
        for form in self.roundtrip(source(declarations)):
            self.assertEqual({g.name:g.parent for g in form.gadgets}, expected)

    def test_partial_unknown_block_after_option_does_not_steal_frame_exit(self):
        text = source("Frame .Outer 'Outer'\nOption _Pick 'Pick' Call '$$_Pick'\n"
                      "   Var List _Pick Pairs\n   'Exit' |$P 'Exit'|\nExit\n"
                      "Grid .Unsupported 'Grid'\nStuff 'Unknown'\nExit\n"
                      "Button .Inside At X 1 Y 3 'Inside'\nExit\n"
                      "        Button .Outside At X 1 Y 12 'Outside'")
        form = import_mac(text, partial=True).form
        self.assertEqual(form.named('Inside').parent, 'Outer')
        self.assertEqual(form.named('Outside').parent, '')
        self.assertEqual(form.named('Pick').items, ['Exit'])
        self.assertEqual(len(form.partial_import_notes), 1)
        self.assertIn('Grid', form.partial_import_notes[0])

    def test_recovery_spans_are_independent_of_indentation(self):
        text = source("Frame .Outer 'Outer'\nOption _Pick 'Pick' Call '$$_Pick'\n"
                      "Var List _Pick Pairs\n'Exit' |$P 'Exit'|\nExit\n"
                      "Button .Inside 'Inside'\nExit")
        variants = [text, '\n'.join((' '*(index%4)*5)+line for index,line in enumerate(text.splitlines()))]
        spans = [declaration_spans(variant)[1] for variant in variants]
        self.assertEqual(spans[0], spans[1])

    def test_real_arguments_and_missing_delimiters_are_not_accepted_as_empty(self):
        for signature in ('(!Value Is String)', '() Is String'):
            with self.subTest(signature=signature), self.assertRaises(MacImportError):
                import_mac(source('', f"Define Method .DEFAULT{signature}\nEndmethod"))
        for label in ("|unclosed", "'unclosed", "'one' 'two'"):
            with self.subTest(label=label), self.assertRaises(MacImportError):
                import_mac(source('Button .Run '+label))


if __name__ == '__main__':
    unittest.main()
