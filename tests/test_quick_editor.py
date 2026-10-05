import unittest
from PySide6.QtWidgets import QApplication,QTableWidgetItem
from e3d_designer.model import Form,Gadget
from e3d_designer.quick_editor import MiniProperties,ItemsDialog

class QuickEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def tearDown(self):self.app.clipboard().clear()
    def test_transaction_rename_and_precision(self):
        f=Form(gadgets=[Gadget(name='one',width=14.25)],default_body='!this.one.val = 1')
        d=MiniProperties(None,f,0);d.fields['name'].setText('newname');d.fields['label'].setText('New');d.accept()
        self.assertEqual(d.result_form.gadgets[0].width,14.25)
        self.assertIn('!this.newname.val',d.result_form.default_body)
        self.assertEqual(f.gadgets[0].name,'one');d.deleteLater()
    def test_applicable_fields_and_boolean(self):
        d=MiniProperties(None,Form(gadgets=[Gadget(kind='rtoggle',name='radio')]),0)
        self.assertEqual([d.fields['initial'].itemText(i) for i in range(3)],['','TRUE','FALSE'])
        self.assertNotIn('width',d.fields);self.assertNotIn('background',d.fields);d.reject();d.deleteLater()
    def test_combo_and_option_values(self):
        for kind in ('combo','option'):
            g=Gadget(kind=kind,name='choices',items=['A'],item_values=['1'])
            d=ItemsDialog(None,g);d.table.setItem(0,1,QTableWidgetItem('2'));d.accept()
            self.assertEqual(d.gadget.item_values,['2']);self.assertEqual(g.item_values,['1'])
            code=Form(gadgets=[d.gadget]).pml().lower()
            target='_choices' if kind=='option' else 'choices'
            self.assertIn(f'!this.{target}.rtext = !values',code);d.deleteLater()
    def test_list_grid_and_mode_preserves_draft(self):
        d=ItemsDialog(None,Gadget(kind='list',name='grid',items=['A'],item_values=['10']))
        d.table.setItem(0,0,QTableWidgetItem('Edited'));d.mode.setCurrentIndex(1)
        self.assertEqual(d.table.item(1,0).text(),'Edited')
        d.add_column();d.add_row();d.table.setItem(2,2,QTableWidgetItem('Cell'));d.accept()
        self.assertEqual(d.gadget.rows[1][2],'Cell');self.assertEqual(len(d.gadget.headings),3)
        self.assertIn('setrows',Form(gadgets=[d.gadget]).pml().lower());d.deleteLater()
    def test_invalid_name_and_outer_cancel(self):
        f=Form(gadgets=[Gadget(name='one'),Gadget(name='two')]);d=MiniProperties(None,f,0)
        d.fields['name'].setText('two');d.accept();self.assertIsNone(d.result_form);self.assertTrue(d.error.text())
        d.gadget.items=['discard'];d.reject();self.assertEqual(f.gadgets[0].items,[]);d.deleteLater()
