import copy
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from e3d_designer.app import Window
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form,Gadget,Method
from e3d_designer.names import rename_many,reference_locations,deletion_dependencies,rewrite_code


class StrictAuditRepairs(unittest.TestCase):
    def test_user_supplied_mac_is_cp932_crlf_and_retains_original_calls(self):
        path=Path(__file__).resolve().parents[1]/'examples/user-supplied/HsMacMSR.mac'
        data=path.read_bytes();text=data.decode('cp932')
        self.assertNotIn(b'\n',data.replace(b'\r\n',b''))
        self.assertIn('kill !!HsMacMSR\r\n',text)
        self.assertIn('setup form !!HsMacMSR $$DIALOG DOCK RIGHT',text)
        for number in range(1,5):self.assertIn(f'$M /%PDMSUSER%/SUB/MSRsub{number}.mac',text)
        self.assertIn('TEXT .TEXTxA0001 AT X 7.0 Y 1.0',text)
        self.assertIn("!!DCP = 'D4'",text)
        self.assertIn('!THIS.OPTIONxA0001.VAL = 5',text)

    def test_rename_preserves_data_and_comments_but_updates_callback_code(self):
        source="!this.Run.val = !!Flag\n!message = '!!Flag !this.Run'\n-- !!Flag !this.Run\n$* !!Flag\n$( !!Flag $)\n!this.Run.callback = |!this.Run.val = !!Flag|"
        form=Form(variables={'Flag':'!!Flag'},gadgets=[Gadget(name='Run')],default_body=source)
        result=rename_many(form,[('variable','Flag','Mode'),('gadget',0,'Go')])
        self.assertEqual(result.default_body,source.replace('!this.Run.val = !!Flag','!this.Go.val = !!Mode').replace('!this.Run.callback','!this.Go.callback'))
        self.assertEqual(result.variables,{'Mode':'!!Flag'})
        self.assertEqual(reference_locations(form,'variable','Flag'),[('DEFAULT',2)])
        self.assertEqual(rewrite_code("'!this.Run' -- !this.Run",form,form,{'Run':'Go'}),"'!this.Run' -- !this.Run")

    def test_real_initial_preserves_original_precision_and_spelling(self):
        for value in ('123456789.123456789','+1.234567890123456789e-12','.1234567890123456789','-0.000000000000123456789'):
            with self.subTest(value=value):
                form=Form(gadgets=[Gadget(kind='text',name='Value',value_type='REAL',initial=value)])
                self.assertIn('!this.Value.val = '+value,form.pml())
                restored=import_mac(form.pml()).form
                self.assertIn('!this.Value.val = '+value,restored.pml())
                self.assertEqual(Form.loads(form.dumps()).gadgets[0].initial,value)
        for value in ('1_000','1+2','NaN','Infinity','1e999','１２'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                Form(gadgets=[Gadget(kind='text',name='Value',value_type='REAL',initial=value)]).pml()

    def test_float_dimensions_and_slider_use_round_trip_precision(self):
        value=1.2345678901234567
        form=Form(gadgets=[Gadget(kind='slider',name='Level',x=value,width=14.123456789012345,slider_value=value)])
        output=form.pml()
        self.assertIn(str(value),output)
        self.assertIn(str(form.gadgets[0].width),output)
        restored=import_mac(output).form
        self.assertEqual(restored.gadgets[0].slider_value,value)

    def test_geometry_resolves_branching_dependencies_once_and_never_goes_stale(self):
        gadgets=[Gadget(name='G0',x=0,y=0,width=1),Gadget(name='G1',x=0,y=0,width=1)]
        gadgets.extend(Gadget(name=f'G{i}',layout_mode='RELATIVE',xref=f'G{i-1}',yref=f'G{i-2}',xoffset=0,yoffset=0,width=1) for i in range(2,50))
        form=Form(gadgets=gadgets)
        with patch.object(Form,'layout_dependencies',autospec=True,side_effect=Form.layout_dependencies) as calls:
            form.geometry(gadgets[-1]);self.assertEqual(calls.call_count,50)
        gadgets[1].x=5
        self.assertEqual(form.geometry(gadgets[-1])[0],5)
        gadgets[1].hidden=True
        self.assertEqual(form.geometry(gadgets[1])[2],0)
        self.assertEqual(form.geometry(gadgets[1],reveal=True)[2],1)
        gadgets[0].layout_mode='RELATIVE';gadgets[0].xref='G49';gadgets[0].yref='G1'
        with self.assertRaises(ValueError):form.geometry(gadgets[-1])

    def test_deletion_dependencies_include_geometry_code_and_generated_methods(self):
        form=Form(gadgets=[Gadget(name='Base',callback='Apply',body='$P \'ok\''),Gadget(name='Follower',layout_mode='RELATIVE',xref='Base',yref='Base')],default_body='!this.Base.val = 1\n!this.Apply()')
        self.assertEqual(deletion_dependencies(form,{'base'}),['Follower: xref','Follower: yref','DEFAULT'])
        form.default_body="!text = '!this.Base.val' -- !this.Apply()"
        self.assertEqual(deletion_dependencies(form,{'Base','Follower'}),[])

    def test_incomplete_draft_saves_and_recovers_without_allowing_mac_export(self):
        form=Form(gadgets=[Gadget(kind='slider',name='Level',slider_step=0)])
        with self.assertRaises(ValueError):form.dumps()
        data=form.dumps(allow_incomplete=True)
        self.assertTrue(json.loads(data)['incomplete'])
        restored=Form.loads(data)
        self.assertEqual(restored.gadgets[0].slider_step,0)
        with self.assertRaises(ValueError):restored.pml()
        restored.gadgets[0].slider_step=1
        self.assertNotIn('incomplete',json.loads(restored.dumps(allow_incomplete=True)))
        record=json.loads(data);record.pop('incomplete')
        with self.assertRaises(ValueError):Form.loads(json.dumps(record))

    def test_incomplete_tabs_are_serialized_without_losing_pages(self):
        form=Form(gadgets=[Gadget(kind='frame',frame_style='TABSET',name='Tabs',width=40,height=15),Gadget(kind='frame',name='Page',parent='Tabs'),Gadget(kind='text',name='Value',parent='Page',value_type='REAL',initial='broken')])
        restored=Form.loads(form.dumps(allow_incomplete=True))
        self.assertEqual([g.name for g in restored.gadgets],['Tabs','Page','Value'])
        self.assertEqual(restored.gadgets[2].initial,'broken')

    def test_oversized_auto_form_draft_keeps_position_but_bounds_editing_canvas(self):
        form=Form(size_explicit=False,gadgets=[Gadget(name='Outside',x=299,width=6)])
        restored=Form.loads(form.dumps(allow_incomplete=True))
        self.assertEqual(restored.width,300);self.assertEqual(restored.gadgets[0].x,299)
        with self.assertRaises(ValueError):restored.pml()

    def test_unsafe_incomplete_records_are_rejected(self):
        base=json.loads(Form(gadgets=[Gadget(name='Run')]).dumps());base['incomplete']=True
        changes=(('width',float('inf')),('name','bad name'),('kind','unknown'),('layout_mode','unknown'),('x','oops'),('parent','Missing'))
        for field,value in changes:
            with self.subTest(field=field),self.assertRaises(ValueError):
                record=copy.deepcopy(base);record['form']['gadgets'][0][field]=value;Form.loads(json.dumps(record))
        record=copy.deepcopy(base);record['form']['gadgets'][0]['parent']='Run'
        with self.assertRaises(ValueError):Form.loads(json.dumps(record))

    def test_cross_form_copy_rejects_missing_direct_and_helper_dependencies(self):
        source=Form(name='Source',gadgets=[Gadget(name='Run',command="!this.Value.val = 'changed'"),Gadget(kind='text',name='Value')])
        target=Form(name='Target');before=target.dumps();original=source.dumps()
        with self.assertRaisesRegex(ValueError,'Value'):clone_subtree(target,source,0)
        self.assertEqual(target.dumps(),before);self.assertEqual(source.dumps(),original)
        source.gadgets[0].command='!this.Apply()';source.extra_methods=[Method(name='Apply',body="!this.Value.val = 'changed'")]
        with self.assertRaisesRegex(ValueError,'Value'):clone_subtree(target,source,0)
        destination=Form(name='Target',gadgets=[Gadget(kind='text',name='Value')])
        with self.assertRaisesRegex(ValueError,'同名部品'):clone_subtree(destination,source,0)
        result,_=clone_subtree(source,source,0)
        self.assertEqual(len(result.extra_methods),2)
        result,_=clone_subtree(source,source,0);self.assertEqual(len(result.gadgets),3)

    def test_external_form_and_literal_references_remain_valid_when_copying(self):
        source=Form(name='Source',gadgets=[Gadget(name='Run',command="!!Source.Value.val = '!this.Value.val'"),Gadget(kind='text',name='Value')])
        result,index=clone_subtree(Form(name='Target'),source,0)
        self.assertEqual(result.gadgets[index].command,source.gadgets[0].command)
        source.gadgets[0].command="!this.Run.callback = |!this.Value.val = 'changed'|"
        with self.assertRaisesRegex(ValueError,'Value'):clone_subtree(Form(name='Target'),source,0)


class StrictAuditWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.w=Window(settings_path=self.folder/'settings.json')
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.app.clipboard().clear();self.app.processEvents();self.temp.cleanup()

    def test_blocked_delete_preserves_history_and_selection(self):
        w=self.w;w.form=Form(gadgets=[Gadget(name='Base'),Gadget(name='Follower',layout_mode='RELATIVE',xref='Base',yref='Base')]);w.refresh();w.choose_row(0)
        before=w.form.dumps();history=len(w.history);dirty=w.dirty;w.delete()
        self.assertEqual(w.form.dumps(),before);self.assertEqual(len(w.history),history);self.assertEqual(w.dirty,dirty);self.assertEqual(w.selected,0)
        self.assertIn('Follower',w.statusBar().currentMessage())
        self.app.clipboard().setText('previous clipboard');w.cut_gadget()
        self.assertEqual(self.app.clipboard().text(),'previous clipboard');self.assertEqual(w.form.dumps(),before)
        w.form.gadgets[1].xref=w.form.gadgets[1].yref='';w.form.gadgets[1].layout_mode='ABSOLUTE';w.delete()
        self.assertEqual([g.name for g in w.form.gadgets],['Follower']);w.undo();self.assertEqual(len(w.form.gadgets),2)

    def test_explicit_save_and_backup_preserve_invalid_initial(self):
        w=self.w;w.form=Form(gadgets=[Gadget(kind='text',name='Value',value_type='REAL',initial='broken')]);w.path=self.folder/'draft.json';w.dirty=True;w.refresh()
        w.backup_work();restored,_=w.recovery.read(w.recovery.path)
        self.assertEqual(restored.gadgets[0].initial,'broken')
        self.assertTrue(w.save());self.assertFalse(w.dirty)
        self.assertIn('MAC出力には修正',w.statusBar().currentMessage())
        self.assertTrue(w.open_design(w.path,confirmed=True));self.assertEqual(w.form.gadgets[0].initial,'broken')
        self.assertIn('MAC出力には修正',w.statusBar().currentMessage())
        with self.assertRaises(ValueError):w.form.pml()
