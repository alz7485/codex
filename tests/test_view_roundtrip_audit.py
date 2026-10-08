import unittest
from pathlib import Path
from e3d_designer.model import Form,Gadget
from e3d_designer.mac_import import import_mac
from e3d_designer.pml_syntax import dedent_code,indent_code


class ViewRoundtripAuditTests(unittest.TestCase):
    def test_generated_views_roundtrip_without_indentation_growth(self):
        for normalize in (False,True):
            form=Form(gadgets=[Gadget(kind='view',name='Scene',x=1,y=1,view_code='LIMITS AUTO\nISOMETRIC 3')])
            original=form.pml(normalize=normalize)
            for _ in range(3):
                form=import_mac(original).form;self.assertEqual(form.named('Scene').view_code,'LIMITS AUTO\nISOMETRIC 3')
                next_code=form.pml(normalize=normalize);self.assertEqual(next_code,original);original=next_code

    def test_view_within_frame_keeps_relative_indentation_and_case(self):
        body='If !!Ready Then\n  $P |MiXeD  value|\nEndif'
        f=Form(gadgets=[Gadget(kind='frame',name='Group',width=60,height=20,x=1,y=1,frame_at=True,frame_size_axes='WH'),
                       Gadget(kind='view',name='Scene',parent='Group',x=1,y=1,view_code=body)])
        original=f.pml()
        for _ in range(3):
            f=import_mac(original).form;self.assertEqual(f.named('Scene').view_code,body);self.assertEqual(f.pml(),original)

    def test_user_common_indentation_is_not_removed_with_structural_prefix(self):
        body='  iF TRUE tHeN\n    $p |Mixed|\n  eNdIf'
        for normalize in (False,True):
            f=Form(gadgets=[Gadget(kind='view',name='Scene',x=1,y=1,view_code=body)])
            code=f.pml(normalize=normalize)
            for _ in range(3):
                f=import_mac(code).form;self.assertEqual(f.named('Scene').view_code,body)
                self.assertEqual(f.pml(normalize=normalize),code)

    def test_multiline_quoted_values_keep_leading_spaces(self):
        body="$P 'First\n    MiXeD line\n last'\n-- comment\n$P |Done|"
        for normalize in (False,True):
            f=Form(gadgets=[Gadget(kind='view',name='Scene',x=1,y=1,view_code=body)])
            original=f.pml(normalize=normalize)
            self.assertIn("'First\n    MiXeD line\n last'",original)
            for _ in range(3):
                f=import_mac(original).form;self.assertEqual(f.named('Scene').view_code,body);self.assertEqual(f.pml(normalize=normalize),original)

    def test_view_keywords_within_multiline_data_are_not_attributes_or_exit(self):
        body="$P 'First\nEXIT\nWIDTH 999\nCHANNEL COMMANDS\nDone'\nLIMITS AUTO"
        f=Form(gadgets=[Gadget(kind='view',name='Scene',x=1,y=1,width=20,height=5,view_code=body)])
        code=f.pml();loaded=import_mac(code).form
        self.assertEqual(loaded.named('Scene').view_code,body);self.assertEqual(loaded.named('Scene').width,20)
        self.assertEqual(loaded.pml(),code)

    def test_indentation_helpers_preserve_quoted_line_starts_and_tabs(self):
        raw="\t\t$P |A\n  exact\n end|\n\t\t$P 'B'"
        normalized=dedent_code(raw);self.assertEqual(normalized,"$P |A\n  exact\n end|\n$P 'B'")
        shifted=indent_code(normalized,'    ');self.assertEqual(shifted,"    $P |A\n  exact\n end|\n    $P 'B'")
        self.assertEqual(dedent_code(shifted),normalized)

    def test_container_hint_does_not_become_repeated_preamble(self):
        f=Form(gadgets=[Gadget(kind='container',name='Host',x=1,y=1,width=20,height=6)])
        original=f.pml()
        for _ in range(3):
            f=import_mac(original).form;self.assertEqual(f.preamble_code,'');self.assertEqual(f.named('Host').comment,'')
            self.assertEqual(f.pml(),original);self.assertEqual(original.count('Set Control handle'),1)

    def test_regular_container_comments_are_kept(self):
        f=Form(gadgets=[Gadget(kind='container',name='Host',x=1,y=1,width=20,height=6,comment='User comment')])
        loaded=import_mac(f.pml()).form;self.assertEqual(loaded.named('Host').comment,'User comment')

    def test_legacy_gadget_sample_becomes_stable_after_first_import(self):
        text=Path('examples/gadgets.mac').read_text(encoding='cp932')
        output=import_mac(text).form.pml()
        for _ in range(3):
            text=import_mac(output).form.pml();self.assertEqual(text,output);output=text
