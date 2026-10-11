import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog
from e3d_designer.model import Form, Gadget, Method, Menu, MenuItem
from e3d_designer.selector_methods import SelectorMethodSpec
from e3d_designer.selector_method_dialog import SelectorMethodDialog
from e3d_designer.app import Window
from e3d_designer.names import rename, deletion_dependencies
from e3d_designer.clipboard import clone_subtree
from e3d_designer.mac_import import import_mac
from e3d_designer.method_manager import update_helpers


def selector_form(mode='MULTIPLE', **kwargs):
    return Form(gadgets=[Gadget(kind='selector', name='targets', label='Targets',
                               database='MEMBERS', selection_mode=mode, width=32, height=8, **kwargs)])


class SelectorRecipeTests(unittest.TestCase):
    def test_single_and_multiple_process_selected_rows_and_snapshot_before_actions(self):
        for mode in ('SINGLE', 'MULTIPLE'):
            original=selector_form(mode); before=original.dumps()
            form=SelectorMethodSpec().build(original,0)
            self.assertEqual(original.dumps(),before)
            self.assertEqual(form.gadgets[0].selection_mode,mode)
            dispatcher=next(m for m in form.extra_methods if m.name=='processSelector1').body
            self.assertIn('do !selected selector !this.targets',dispatcher)
            self.assertLess(dispatcher.index('!selectedNames.append'),dispatcher.index('object DBREF'))
            self.assertIn('!selectedNames.size() eq 0',dispatcher)
            self.assertNotIn('.val',dispatcher)
            self.assertEqual([g.kind for g in form.gadgets],['selector','button','button'])
            self.assertIn('Processed count:',dispatcher)
            form.pml()

    def test_name_type_owner_settings_and_null_owner(self):
        form=SelectorMethodSpec(report_name=False,report_type=False,report_owner=True).build(selector_form(),0)
        worker=form.extra_methods[1].body
        self.assertIn('BADREF(!owner)',worker)
        self.assertNotIn('!element.name',worker)
        self.assertIn('!owner.name',worker)
        with self.assertRaisesRegex(ValueError,'1つ以上'):
            SelectorMethodSpec(report_name=False,report_type=False).build(selector_form(),0)

    def test_navigation_requires_single_button_and_handles_auto_refresh_by_snapshot(self):
        original=selector_form('SINGLE');original.gadgets[0].database='AUTO'
        result=SelectorMethodSpec(recipe='navigate').build(original,0)
        self.assertIn('!!CE = !element',result.extra_methods[1].body)
        self.assertIn('!selectedNames.append',result.extra_methods[0].body)
        for form,spec in ((selector_form(),SelectorMethodSpec(recipe='navigate')),
                          (selector_form('SINGLE'),SelectorMethodSpec(recipe='navigate',trigger='SELECTION'))):
            with self.assertRaises(ValueError):spec.build(form,0)

    def test_mydata_requires_button_and_imports_correct_api(self):
        form=SelectorMethodSpec(recipe='mydata').build(selector_form(),0)
        worker=form.extra_methods[1].body
        self.assertIn("import 'MyDataAddin'",worker)
        self.assertIn('!myData.AddElement(!name)',worker)
        self.assertNotIn('!!CE =',worker)
        with self.assertRaisesRegex(ValueError,'処理ボタン'):
            SelectorMethodSpec(recipe='mydata',trigger='SELECTION').build(selector_form(),0)

    def test_custom_receives_dbref_and_rejects_nested_method_definition(self):
        form=SelectorMethodSpec(recipe='custom',custom_body='!owner = !element.owner\nq var !owner').build(selector_form(),0)
        self.assertEqual(form.extra_methods[1].signature,'(!element is DBREF)')
        self.assertIn('!owner = !element.owner',form.extra_methods[1].body)
        self.assertIn('processSelector1Element(!element)',form.extra_methods[0].body)
        for code in ('\x00', 'endmethod\ndefine method .other()\n$p changed'):
            with self.assertRaises(ValueError):SelectorMethodSpec(recipe='custom',custom_body=code).build(selector_form(),0)
        self.assertIn('Selected element:',SelectorMethodSpec(recipe='custom').build(selector_form(),0).pml())

    def test_button_mode_preserves_existing_callback_and_all_shared_bodies(self):
        original=selector_form(callback='existing',body='$p Existing processing')
        original.gadgets.append(Gadget(name='other',callback='existing',body='$p Existing processing',x=40,y=0))
        result=SelectorMethodSpec().build(original,0)
        self.assertEqual(result.gadgets[0].callback,'existing')
        self.assertEqual(result.gadgets[0].body,'$p Existing processing')
        self.assertEqual(result.gadgets[1],original.gadgets[1])

    def test_selection_mode_requires_acknowledgement_and_preserves_explicit_callers(self):
        original=selector_form('SINGLE',callback='existing',body='$p Original processing')
        original.menus=[Menu(name='tools',items=[MenuItem('Existing','!this.existing()')])]
        with self.assertRaisesRegex(ValueError,'既存'):
            SelectorMethodSpec(trigger='SELECTION').build(original,0)
        form=SelectorMethodSpec(trigger='SELECTION',replace_existing=True).build(original,0)
        self.assertNotEqual(form.gadgets[0].callback,'existing')
        retained=next(m for m in form.extra_methods if m.name=='existing')
        self.assertEqual(retained.body,'$p Original processing')
        self.assertIn('!this.existing()',form.menus[0].items[0].command)
        form.pml()

    def test_shared_callback_and_default_are_not_overwritten(self):
        original=selector_form('SINGLE',callback='shared',body='$p Shared')
        original.gadgets.append(Gadget(name='other',callback='shared',body='$p Shared',x=40,y=0))
        changed=SelectorMethodSpec(trigger='SELECTION',replace_existing=True).build(original,0)
        self.assertEqual(changed.gadgets[1].callback,'shared')
        self.assertEqual(changed.gadgets[1].body,'$p Shared')
        self.assertFalse(any(m.name=='shared' for m in changed.extra_methods))
        original=selector_form('SINGLE',callback='default');original.default_body='$p Original default'
        changed=SelectorMethodSpec(trigger='SELECTION',replace_existing=True).build(original,0)
        self.assertEqual(changed.default_body,original.default_body)
        changed.pml()

    def test_comment_only_callback_can_be_replaced_without_acknowledgement(self):
        original=selector_form(callback='empty',body='-- Placeholder')
        changed=SelectorMethodSpec(trigger='SELECTION',refresh=False).build(original,0)
        self.assertEqual(len(changed.gadgets),1)
        self.assertIn('!this.processSelector1()',changed.gadgets[0].body)

    def test_save_rename_and_helper_rename_update_dispatch_and_refresh(self):
        form=SelectorMethodSpec().build(selector_form(),0)
        restored=Form.loads(form.dumps());self.assertEqual(restored.pml(),form.pml())
        renamed=rename(restored,'gadget',0,'chosen')
        self.assertIn('selector !this.chosen',renamed.extra_methods[0].body)
        self.assertIn('!this.chosen.Refresh()',renamed.gadgets[-1].body)
        entries=[(m.name,copy.deepcopy(m)) for m in renamed.extra_methods]
        entries[1][1].name='handleElement'
        edited=update_helpers(renamed,entries)
        self.assertIn('!this.handleElement(!element)',edited.extra_methods[0].body)

    def test_frame_copy_and_cross_project_copy_keep_method_graph_and_selection_target(self):
        form=selector_form();form.gadgets[0].parent='group'
        form.gadgets.insert(0,Gadget(kind='frame',name='group',width=60,height=15,x=0,y=0))
        form=SelectorMethodSpec().build(form,1)
        for target in (form,Form(name='destination')):
            copied,index=clone_subtree(target,form,0)
            selector=next(g for g in copied.children(copied.gadgets[index].name) if g.kind=='selector')
            methods=[m for m in copied.extra_methods if f'selector !this.{selector.name}\n' in m.body]
            self.assertEqual(len(methods),1)
            self.assertIn('!this.',methods[0].body)
            copied.pml()
        self.assertTrue(deletion_dependencies(form,{'targets'}))

    def test_selection_callback_copy_carries_helpers(self):
        form=SelectorMethodSpec(trigger='SELECTION',refresh=False).build(selector_form(),0)
        copied,index=clone_subtree(Form(name='destination'),form,0)
        self.assertEqual(len(copied.extra_methods),2)
        self.assertIn(f'selector !this.{copied.gadgets[index].name}',copied.extra_methods[0].body)
        copied.pml()

    def test_mac_import_preserves_methods_and_button_bodies(self):
        for mode in ('SINGLE','MULTIPLE'):
            original=SelectorMethodSpec(report_owner=True).build(selector_form(mode),0)
            imported=import_mac(original.pml()).form
            self.assertEqual({m.name:m.body for m in imported.extra_methods},
                             {m.name:m.body for m in original.extra_methods})
            self.assertEqual(imported.gadgets[1].body,original.gadgets[1].body)
            imported.pml()

    def test_invalid_names_missing_space_and_source_mode_leave_input_untouched(self):
        cases=[(selector_form(),SelectorMethodSpec(method_name='bad name')),
               (selector_form(callback='used'),SelectorMethodSpec(method_name='used')),
               (selector_form(),SelectorMethodSpec(recipe='BAD')),
               (selector_form(),SelectorMethodSpec(trigger='BAD'))]
        small=selector_form();small.width=34;small.height=9
        cases.append((small,SelectorMethodSpec()))
        source=selector_form();source.program_mode='SOURCE'
        cases.append((source,SelectorMethodSpec()))
        for form,spec in cases:
            before=form.dumps()
            with self.assertRaises(ValueError):spec.build(form,0)
            self.assertEqual(form.dumps(),before)

    def test_multiple_auto_is_rejected_but_single_auto_remains_valid(self):
        form=selector_form();form.gadgets[0].database='AUTO'
        for mode in ('MULTIPLE','MULTI'):
            form.gadgets[0].selection_mode=mode
            with self.assertRaisesRegex(ValueError,'AUTOとMULTIPLE'):form.pml()
        form.gadgets[0].selection_mode='SINGLE';form.pml()


class SelectorWizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Window(settings_path=Path(self.temp.name)/'settings.json')
        self.w.form=selector_form();self.w.selected=0;self.w.refresh()
    def tearDown(self):
        self.app.clipboard().clear();self.w.dirty=False;self.w.close();self.app.processEvents();self.temp.cleanup()

    def test_existing_selector_property_button_and_menu_cancel_are_nonmutating(self):
        w=self.w;self.assertFalse(w.selector_method_button.isHidden())
        before=w.form.dumps()
        with patch('e3d_designer.selector_method_dialog.SelectorMethodDialog') as dialog:
            dialog.return_value.exec.return_value=QDialog.Rejected
            w.selector_method_button.click();w.selector_method_action.trigger()
            next(a for a in w.palette_buttons['other'].menu().actions() if a.data()=='db_selector_methods').trigger()
            self.assertEqual(dialog.call_count,3)
        self.assertEqual(w.form.dumps(),before);self.assertEqual(w.history,[])
        self.assertEqual(len(w.palette_buttons),16)

    def test_real_dialog_addition_is_one_undo_step(self):
        w=self.w;before=w.form.dumps()
        def accept():
            dialog=w.findChildren(SelectorMethodDialog)[-1]
            dialog.report_owner.setChecked(True);dialog.accept()
        QTimer.singleShot(0,accept);w.selector_method_action.trigger()
        self.assertEqual(len(w.history),1);self.assertEqual(len(w.form.gadgets),3)
        self.assertEqual(w.validation_error,'')
        generated=w.form.pml();w.undo();self.assertEqual(w.form.dumps(),before)
        w.redo();self.assertEqual(w.form.pml(),generated)

    def test_preview_and_explicit_replacement_without_losing_original_method(self):
        self.w.form=selector_form('SINGLE',callback='existing',body='$p Original')
        d=SelectorMethodDialog(self.w,self.w.form,0)
        d.trigger.setCurrentIndex(d.trigger.findData('SELECTION'))
        self.assertIn('置き換え',d.error.text());self.assertIn('processSelector1',d.preview.toPlainText())
        d.accept();self.assertIsNone(d.result_form)
        d.replace_existing.setChecked(True);self.assertEqual(d.error.text(),'')
        d.accept();self.assertTrue(any(m.name=='existing' for m in d.result_form.extra_methods));d.close()

    def test_recipe_constraints_and_target_switch(self):
        self.w.form.gadgets.append(Gadget(kind='selector',name='single',database='OWNERS',width=22,height=8,x=40,y=2))
        d=SelectorMethodDialog(self.w,self.w.form,0)
        d.recipe.setCurrentIndex(d.recipe.findData('navigate'))
        self.assertIn('SINGLE',d.error.text())
        d.target.setCurrentIndex(d.target.findData(1));self.assertEqual(d.error.text(),'')
        self.assertIn('単一選択',d.target_info.text())
        d.refresh.setChecked(False);d.accept();self.assertEqual(len(d.result_form.gadgets),3)
        d.close()

    def test_no_selector_or_invalid_recipe_does_not_add_history(self):
        w=self.w;w.form=Form();w.selected=None;w.refresh()
        w.selector_method_action.trigger();self.assertEqual(w.history,[])
        self.assertIn('先に',w.statusBar().currentMessage())
        w.form=selector_form();w.refresh()
        d=SelectorMethodDialog(w,w.form,0)
        d.method_name.setText('bad name');d.accept();self.assertIsNone(d.result_form)
        self.assertEqual(w.history,[]);d.close()


if __name__=='__main__':unittest.main()
