import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QWizard
from e3d_designer.model import Form, Gadget, Method
from e3d_designer.app import Window
from e3d_designer.toolbar_builder import ToolbarSpec, ToolbarButtonSpec, navigation_buttons
from e3d_designer.toolbar_dialog import ToolbarDialog
from e3d_designer.mac_import import import_mac
from e3d_designer.clipboard import clone_subtree
from e3d_designer.names import rename


class ToolbarRecipeTests(unittest.TestCase):
    def test_dialog_row_has_parented_horizontal_buttons_and_preserves_existing_content(self):
        original=Form(gadgets=[Gadget(name='existing',x=0,y=0,width=20)])
        before=original.dumps()
        form,index=ToolbarSpec(buttons=navigation_buttons()).build(original)
        frame=form.gadgets[index];children=form.children(frame.name)
        self.assertEqual(original.dumps(),before)
        self.assertEqual(form.gadgets[0],original.gadgets[0])
        self.assertEqual((form.form_type,frame.frame_style),('DIALOG','FRAME'))
        self.assertEqual([g.label for g in children],['CE info','Up','Members'])
        self.assertTrue(all(g.parent==frame.name and g.y==1 for g in children))
        self.assertTrue(frame.x >= 20 or frame.y >= 1)
        for left,right in zip(children,children[1:]):self.assertEqual(right.x,left.x+left.width+1)
        form.pml()

    def test_main_toolbar_emits_implicit_child_positions(self):
        original=Form(form_type='MAIN',show_form=False)
        form,index=ToolbarSpec(style='TOOLBAR',buttons=navigation_buttons()).build(original)
        self.assertEqual(form.gadgets[index].frame_style,'TOOLBAR')
        lines=[line.strip() for line in form.pml().splitlines() if line.strip().upper().startswith('BUTTON')]
        self.assertEqual(len(lines),3)
        self.assertTrue(all(' AT ' not in line for line in lines))
        self.assertIn("Frame .tools1 Toolbar 'Tools'",form.pml())

    def test_main_conversion_requires_explicit_choice_and_rejects_incompatible_contents(self):
        original=Form(dock_side='RIGHT',dock_right=True)
        before=original.dumps()
        with self.assertRaisesRegex(ValueError,'チェック'):ToolbarSpec(style='TOOLBAR').build(original)
        form,index=ToolbarSpec(style='TOOLBAR',convert_to_main=True).build(original)
        self.assertEqual(original.dumps(),before)
        self.assertEqual(form.form_type,'MAIN');self.assertEqual(form.show_form,original.show_form)
        self.assertEqual(form.docking_side(),'NONE');form.pml()
        original.gadgets=[Gadget(kind='selector',name='targets',width=20,height=8)]
        before=original.dumps()
        with self.assertRaisesRegex(ValueError,'MAIN'):ToolbarSpec(style='TOOLBAR',convert_to_main=True).build(original)
        self.assertEqual(original.dumps(),before)
        with self.assertRaisesRegex(ValueError,'MAIN'):ToolbarSpec().build(Form(form_type='MAIN'))

    def test_navigation_checks_invalid_ce_and_owner_without_changing_ce_for_queries(self):
        form,_=ToolbarSpec(buttons=navigation_buttons()).build(Form())
        info,owner,members=form.children('tools1')
        for g in (info,owner,members):self.assertIn('BADREF(!element)',g.body)
        self.assertIn('BADREF(!owner)',owner.body)
        self.assertIn('!!CE = !owner',owner.body)
        self.assertNotIn('!!CE =',info.body);self.assertNotIn('!!CE =',members.body)
        self.assertIn('!element.members',members.body)
        self.assertIn('!members.size() eq 0',members.body)

    def test_custom_and_macro_actions_use_existing_editable_code_model(self):
        buttons=[ToolbarButtonSpec('Custom',body='$p Ready\n!n = 3'),
                 ToolbarButtonSpec('Macro','macro',macro_path=r'C:\My Macros\run.mac')]
        form,_=ToolbarSpec(buttons=buttons).build(Form())
        custom,macro=form.children('tools1')
        self.assertEqual(custom.body,'$p Ready\n!n = 3')
        self.assertIn(f'!this.{custom.callback}()',form.pml())
        self.assertIn('$M "C:/My Macros/run.mac"',form.pml())
        self.assertEqual(macro.action_mode,'MACRO');self.assertEqual(macro.macro_flag,'')
        with self.assertRaises(ValueError):ToolbarSpec(buttons=[ToolbarButtonSpec(action='macro')]).build(Form())

    def test_generated_names_avoid_existing_callbacks_and_macro_methods(self):
        form=Form(extra_methods=[Method('on_tools1Button1','()','$p Old'),
                                 Method('macro_tools1Button2','()','$p Old macro')])
        buttons=[ToolbarButtonSpec(),ToolbarButtonSpec('Macro','macro',macro_path='run.mac')]
        result,_=ToolbarSpec(buttons=buttons).build(form)
        self.assertEqual(result.children('tools1')[0].callback,'on_tools1Button1_2')
        self.assertEqual(result.children('tools1')[1].name,'tools1Button3')
        result.pml()

    def test_json_mac_roundtrip_and_frame_copy_preserve_actions(self):
        for style in ('ROW','TOOLBAR'):
            original,_=ToolbarSpec(style=style,convert_to_main=True,buttons=navigation_buttons()).build(Form())
            self.assertEqual(Form.loads(original.dumps()).pml(),original.pml())
            imported=import_mac(original.pml()).form
            self.assertEqual([g.body for g in imported.children('tools1')],
                             [g.body for g in original.children('tools1')])
            self.assertEqual(imported.gadgets[0].frame_style,original.gadgets[0].frame_style)
            copied,index=clone_subtree(original,original,0)
            self.assertEqual(len(copied.children(copied.gadgets[index].name)),3)
            copied.pml()
        row,_=ToolbarSpec(buttons=navigation_buttons()).build(Form())
        copied,index=clone_subtree(Form(),row,0)
        copied.pml()

    def test_rename_updates_parent_and_methods(self):
        form,_=ToolbarSpec(buttons=navigation_buttons()).build(Form())
        renamed=rename(form,'gadget',0,'operations')
        renamed=rename(renamed,'gadget',1,'infoButton')
        self.assertEqual(len(renamed.children('operations')),3)
        self.assertTrue(any(g.name=='infoButton' for g in renamed.children('operations')))
        renamed.pml()

    def test_invalid_input_and_missing_space_never_mutate_original(self):
        form=Form();before=form.dumps()
        specs=[ToolbarSpec(frame_name='bad name'),ToolbarSpec(label='Bad$'),ToolbarSpec(style='BAD'),
               ToolbarSpec(buttons=[]),ToolbarSpec(buttons=[ToolbarButtonSpec()]*17),
               ToolbarSpec(buttons=[ToolbarButtonSpec(label='')]),
               ToolbarSpec(buttons=[ToolbarButtonSpec(width=3)]),
               ToolbarSpec(buttons=[ToolbarButtonSpec(action='BAD')]),
               ToolbarSpec(buttons=[ToolbarButtonSpec(body='-- Empty')]),
               ToolbarSpec(buttons=[ToolbarButtonSpec(body='\x00')]),
               ToolbarSpec(buttons=[ToolbarButtonSpec(body='endmethod\ndefine method .other()\n$p Bad')])]
        for spec in specs:
            with self.assertRaises(ValueError):spec.build(form)
            self.assertEqual(form.dumps(),before)
        small=Form(width=12,height=2);before=small.dumps()
        with self.assertRaisesRegex(ValueError,'空き'):ToolbarSpec().build(small)
        self.assertEqual(small.dumps(),before)
        source=Form(program_mode='SOURCE')
        with self.assertRaisesRegex(ValueError,'自動生成'):ToolbarSpec().build(source)

    def test_auto_form_size_and_long_labels_remain_inside_row(self):
        form,index=ToolbarSpec(buttons=[ToolbarButtonSpec(label='A rather long button title')]).build(Form(size_explicit=False))
        frame=form.gadgets[index];button=form.children(frame.name)[0]
        self.assertGreater(button.width,12)
        self.assertLessEqual(button.x+button.width,frame.width)
        self.assertGreaterEqual(form.width,frame.x+frame.width)
        form.pml()


class ToolbarWizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.show();self.app.processEvents()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_menu_and_palette_open_wizard_without_changing_palette_or_cancelled_project(self):
        w=self.w;before=w.form.dumps()
        with patch('e3d_designer.toolbar_dialog.ToolbarDialog') as dialog:
            dialog.return_value.exec.return_value=QDialog.Rejected
            w.toolbar_builder_action.trigger()
            next(a for a in w.palette_buttons['other'].menu().actions() if a.data()=='toolbar_builder').trigger()
            self.assertEqual(dialog.call_count,2)
        self.assertEqual(w.form.dumps(),before);self.assertEqual(w.history,[])
        self.assertEqual((len(w.palette_buttons),len(w.palette_actions)),(16,23))

    def test_real_guided_workflow_preview_add_and_undo_redo(self):
        w=self.w;before=w.form.dumps();seen=[]
        def accept():
            d=w.findChildren(ToolbarDialog)[-1]
            self.assertEqual(d.currentId(),0);d.next();self.assertEqual(d.currentId(),1)
            d.add_navigation();d.next();self.assertEqual(d.currentId(),2)
            seen.append(d.preview.toPlainText());d.accept()
        QTimer.singleShot(0,accept);w.toolbar_builder_action.trigger()
        self.assertEqual(len(w.history),1);self.assertEqual(len(w.form.gadgets),5)
        self.assertEqual(w.validation_error,'');self.assertEqual(w.form.pml(),seen[0])
        w.undo();self.assertEqual(w.form.dumps(),before)
        w.redo();self.assertEqual(w.form.pml(),seen[0])

    def test_editing_reordering_and_removing_rows_keeps_bodies_with_their_buttons(self):
        d=ToolbarDialog(self.w,Form());d.show();d.next()
        d.body.setPlainText('$p First');d.table.item(0,0).setText('First')
        d.add_button();d.body.setPlainText('$p Second');d.table.item(1,0).setText('Second')
        d.move_button(-1)
        self.assertEqual([b.label for b in d.buttons()],['Second','First'])
        self.assertEqual([b.body for b in d.buttons()],['$p Second','$p First'])
        d.remove_button();self.assertEqual(d.buttons()[0].body,'$p First')
        d.remove_button();self.assertEqual(d.buttons(),[])
        d.next();self.assertEqual(d.currentId(),1);self.assertIn('1〜16',d.button_error.text())
        d.add_navigation();d.next();self.assertEqual(d.currentId(),2)
        d.back();self.assertEqual(d.currentId(),1);d.close()

    def test_macro_field_and_details_survive_action_and_selection_changes(self):
        d=ToolbarDialog(self.w,Form());d.show();d.next()
        action=d.table.cellWidget(0,1);action.setCurrentIndex(action.findData('macro'))
        d.macro_path.setText('C:/macros/run.mac')
        self.assertFalse(d.macro_path.isHidden());self.assertTrue(d.body.isHidden())
        d.add_button();d.body.setPlainText('$p Second');d.table.setCurrentCell(0,0)
        self.assertEqual(d.macro_path.text(),'C:/macros/run.mac')
        action.setCurrentIndex(action.findData('custom'));self.assertEqual(d.body.toPlainText(),'$p Add processing here.')
        d.close()

    def test_main_choice_shows_context_and_requires_conversion(self):
        d=ToolbarDialog(self.w,Form());d.show()
        d.style.setCurrentIndex(d.style.findData('TOOLBAR'))
        self.assertIn('リボン',d.type_note.text());self.assertFalse(d.convert.isHidden())
        d.next();self.assertEqual(d.currentId(),0)
        d.convert.setChecked(True);d.next();d.next()
        self.assertIn('MAINへ変更',d.summary.text());d.accept()
        self.assertEqual(d.result_form.form_type,'MAIN');self.assertIn('Show !!',d.result_form.pml());d.close()

    def test_invalid_body_cannot_advance_and_cancellation_keeps_input(self):
        original=Form();before=original.dumps();d=ToolbarDialog(self.w,original);d.show();d.next()
        d.body.clear();d.next();self.assertEqual(d.currentId(),1);self.assertIn('本文',d.button_error.text())
        d.reject();self.assertIsNone(d.result_form);self.assertEqual(original.dumps(),before);d.close()


if __name__=='__main__':unittest.main()
