import re
import tempfile
import unittest
from pathlib import Path

from e3d_designer.mac_import import import_mac,read_mac,MacImportError
from e3d_designer.model import Form
from e3d_designer.pml_syntax import mask_non_code


SOURCE="""Setup Form !!Demo Dialog Size 70 22
Button .Run At X 1 Y 1 'Run' Call '!this.Apply()'
Exit
Show !!Demo
Define Method .Apply()
$P 'Run'
Endmethod
"""


class MacTerminatorTests(unittest.TestCase):
    def assert_removed(self,result):
        self.assertIsNone(re.search(r'(?m)^\s*\$\.\s*$',mask_non_code(result.form.pml())))
        self.assertEqual(len(result.warnings),1)
        self.assertIn('除去',result.warnings[0])
        self.assertEqual(Form.loads(result.form.dumps()).pml(),result.form.pml())

    def test_trailing_terminator_removed_in_strict_and_partial_import(self):
        for partial in (False,True):
            with self.subTest(partial=partial):
                result=import_mac(SOURCE+'  $.  \n',partial=partial)
                self.assert_removed(result)
                self.assertIn("$P 'Run'",result.form.named('Run').body)
                self.assertEqual(result.form.pml(),import_mac(SOURCE).form.pml())
                self.assertEqual(import_mac(result.form.pml()).form.pml(),result.form.pml())

    def test_terminator_between_show_and_methods_does_not_precede_generated_methods(self):
        result=import_mac(SOURCE.replace('Define Method','$.\nDefine Method'))
        self.assert_removed(result)
        self.assertIn('Define Method .Apply()',result.form.pml())
        self.assertNotIn('$.',result.form.after_show_code)

    def test_multiple_terminators_and_method_body_removed(self):
        result=import_mac('$.\n'+SOURCE.replace("$P 'Run'","$.\n$P 'Run'")+'$.')
        self.assert_removed(result)
        self.assertIn('3個',result.warnings[0])
        self.assertNotIn('$.',result.form.named('Run').body)

    def test_comments_next_to_token_are_preserved(self):
        for suffix in ('-- ending $.','$* ending $.','$( ending $. $)'):
            with self.subTest(suffix=suffix):
                result=import_mac(SOURCE+'$. '+suffix+'\n')
                self.assert_removed(result)
                self.assertIn(suffix,result.form.pml())

    def test_comment_and_string_occurrences_are_not_removed(self):
        body="$P '$.'\n$P |$.|\n$P \"$.\"\n-- $.\n$* $.\n$(\n$.\n$)\n$M |$.mac|"
        result=import_mac(SOURCE.replace("$P 'Run'",body))
        self.assertEqual(result.warnings,[])
        self.assertIn(body,result.form.pml())

    def test_standalone_line_inside_multiline_literal_is_preserved(self):
        body="$P |first\n$.\nlast|"
        result=import_mac(SOURCE.replace("$P 'Run'",body)+'$.')
        self.assert_removed(result)
        self.assertIn(body,result.form.pml())

    def test_error_line_numbers_are_unchanged(self):
        text='$.\n'+SOURCE.replace("$P 'Run'\nEndmethod","$P 'Run'")
        with self.assertRaises(MacImportError) as error:import_mac(text)
        self.assertEqual(error.exception.line,6)

    def test_partial_source_keeps_original_for_review_but_not_output(self):
        text=SOURCE.replace('Button .Run',"Mystery .Unknown 'Unknown'\nButton .Run")+'$.\n'
        result=import_mac(text,partial=True)
        self.assertEqual(result.form.partial_import_source,text)
        self.assertIn('2〜2行',result.form.partial_import_notes[0])
        self.assertNotIn('Mystery',result.form.pml())
        self.assertNotIn('$.',mask_non_code(result.form.pml()))

    def test_cp932_file_and_source_bytes_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.mac'
            data=(SOURCE.replace("'Run'","'実行'")+'$.\n').replace('\n','\r\n').encode('cp932')
            path.write_bytes(data)
            for partial in (False,True):
                result=read_mac(path,partial=partial)
                self.assert_removed(result)
                self.assertEqual(result.form.source_mac_path,str(path.resolve()))
                self.assertEqual(path.read_bytes(),data)
                self.assertEqual(result.encoding,'SJIS（CP932）')

    def test_dollar_dot_in_a_command_or_filename_is_preserved(self):
        text=SOURCE.replace("$P 'Run'","$M |C:/macros/$.mac|\n$P 'value $. still here'")+'$.\n'
        result=import_mac(text)
        self.assert_removed(result)
        self.assertIn("$M |C:/macros/$.mac|",result.form.pml())
        self.assertIn("$P 'value $. still here'",result.form.pml())
