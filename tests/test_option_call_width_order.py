import unittest

from e3d_designer.mac_import import import_mac
from e3d_designer.model import Form, Gadget


class OptionCallWidthOrderTests(unittest.TestCase):
    def test_text_command_and_method_put_width_after_call(self):
        for attributes in ({'command':'$M //Server/Share/MixedCase.mac'},
                           {'callback':'Changed','body':"!value = 'MixedCase'"}):
            with self.subTest(attributes=attributes):
                form=Form(gadgets=[Gadget(kind='option',option_style='GADGET',name='Pick',items=['A'],**attributes)])
                code=form.pml();declaration=next(line for line in code.splitlines() if line.strip().startswith('Option '))
                self.assertLess(declaration.index('Call '),declaration.index('Width '))
                restored=import_mac(code).form.gadgets[0]
                self.assertEqual(restored.command,form.gadgets[0].command)
                self.assertEqual(restored.callback,form.gadgets[0].callback)

    def test_image_callback_precedes_width_and_height(self):
        form=Form(gadgets=[Gadget(kind='option',name='Pictures',display_mode='PIXMAP',items=['red.png'],
            width=100,height=50,callback='Changed',body='!value = !this.Pictures.val')])
        code=form.pml();declaration=next(line for line in code.splitlines() if line.strip().startswith('Option '))
        self.assertLess(declaration.index('Callback '),declaration.index('Width '))
        self.assertLess(declaration.index('Width '),declaration.index('Height '))
        g=import_mac(code).form.gadgets[0]
        self.assertEqual((g.callback,g.width,g.height),('Changed',100,50))

    def test_pairs_call_order_remains_correct_and_no_empty_call_is_added(self):
        form=Form(gadgets=[Gadget(kind='option',name='Pairs',items=['A'],item_commands=['SAVEWORK'],option_width_explicit=True)])
        declaration=next(line for line in form.pml().splitlines() if line.strip().startswith('Option '))
        self.assertLess(declaration.index('Call '),declaration.index('Width '))
        for style in ('PAIRS','GADGET'):
            g=Gadget(kind='option',name='Pick',option_style=style,items=['A'],item_values=['1'])
            declaration=next(line for line in Form(gadgets=[g]).pml().splitlines() if line.strip().startswith('Option '))
            self.assertNotIn('Call',declaration)

    def test_hidden_and_automatic_width_keep_order(self):
        for hidden,automatic in ((False,False),(True,False),(False,True)):
            with self.subTest(hidden=hidden,automatic=automatic):
                g=Gadget(kind='option',option_style='GADGET',name='Pick',label='Pick',y=3,command='SAVEWORK',
                    hidden=hidden,width_explicit=not automatic)
                form=Form(gadgets=[Gadget(name='Anchor',width=8),g]);code=form.pml()
                declaration=next(line for line in code.splitlines() if line.strip().startswith('Option '))
                if automatic:self.assertNotIn('Width',declaration)
                else:self.assertLess(declaration.index('Call '),declaration.index('Width'))
                restored=import_mac(code).form.named('Pick')
                self.assertEqual(restored.command,'SAVEWORK');self.assertEqual(restored.hidden,hidden)
