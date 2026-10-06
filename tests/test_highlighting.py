import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication,QPlainTextEdit
from PySide6.QtGui import QTextDocument
from PySide6.QtTest import QTest
from e3d_designer.model import Form,Gadget
from e3d_designer.highlighting import PmlHighlighter,COLORS
from e3d_designer.app import Window


class HighlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def make_document(self,text):
        document=QTextDocument(text);highlighter=PmlHighlighter(document)
        highlighter.set_symbols(Form(gadgets=[Gadget(name='a'),Gadget(kind='option',name='mode')]))
        highlighter.rehighlight();return document,highlighter

    def color_at(self,document,token,block_number=0):
        block=document.findBlockByNumber(block_number);text=block.text();index=text.index(token)
        position=len(text[:index].encode('utf-16-le'))//2
        for value in block.layout().formats():
            if value.start<=position<value.start+value.length:return value.format.foreground().color().name()
        return None

    def test_categories_and_case_insensitive_keywords(self):
        text="button .a CALL '!this.run()' WIDTH 12.5 !!userform !this !!flag .val .run() TRUE _mode"
        document,highlighter=self.make_document(text)
        for token,kind in [('button','command'),('.a','object'),('CALL','command'),("'!this.run()'",'string'),('12.5','number'),('!!userform','object'),('!this !!','variable'),('!!flag','variable'),('.val','property'),('.run() TRUE','method'),('TRUE','number'),('_mode','object')]:
            with self.subTest(token=token):self.assertEqual(self.color_at(document,token),COLORS[kind])
        self.assertEqual(document.toPlainText(),text)

    def test_string_comment_precedence_and_unicode_offsets(self):
        document,highlighter=self.make_document("$P '🛠️ -- IF !!flag' -- BUTTON !!other\n$* comment !!other\nREAL -2.5e-3 .5E2")
        self.assertEqual(self.color_at(document,'IF'),COLORS['string'])
        self.assertEqual(self.color_at(document,'!!flag'),COLORS['string'])
        self.assertEqual(self.color_at(document,'BUTTON'),COLORS['comment'])
        self.assertEqual(self.color_at(document,'!!other',1),COLORS['comment'])
        for token in ('-2.5e-3','.5E2'):self.assertEqual(self.color_at(document,token,2),COLORS['number'])

    def test_multiline_quote_state_rehighlight_after_edit(self):
        document,highlighter=self.make_document("|first\n!!flag| SHOW\n!!flag")
        self.assertEqual(self.color_at(document,'!!flag',1),COLORS['string'])
        self.assertEqual(self.color_at(document,'SHOW',1),COLORS['command'])
        self.assertEqual(self.color_at(document,'!!flag',2),COLORS['variable'])
        document.setPlainText('-- comment\n!!flag');highlighter.rehighlight()
        self.assertEqual(self.color_at(document,'!!flag',1),COLORS['variable'])

    def test_symbol_rename_updates_bare_option_and_form_colors(self):
        document,highlighter=self.make_document('!!userform !!newform _mode _choice')
        highlighter.set_symbols(Form(name='newform',gadgets=[Gadget(kind='option',name='choice')]))
        self.assertEqual(self.color_at(document,'!!newform'),COLORS['object'])
        self.assertEqual(self.color_at(document,'!!userform'),COLORS['variable'])
        self.assertEqual(self.color_at(document,'_choice'),COLORS['object'])
        self.assertIsNone(self.color_at(document,'_mode'))

    def test_block_comment_state_and_code_after_closing_delimiter(self):
        text="$( 開始 🛠️\n!this.Run() ' -- $* \n$) SHOW !!flag\n$p '$( text $)' $( comment $) WIDTH"
        document,highlighter=self.make_document(text)
        self.assertEqual(self.color_at(document,'開始'),COLORS['comment'])
        self.assertEqual(self.color_at(document,'!this.Run()',1),COLORS['comment'])
        self.assertEqual(self.color_at(document,'$)',2),COLORS['comment'])
        self.assertEqual(self.color_at(document,'SHOW',2),COLORS['command'])
        self.assertEqual(self.color_at(document,'!!flag',2),COLORS['variable'])
        self.assertEqual(self.color_at(document,'text',3),COLORS['string'])
        self.assertEqual(self.color_at(document,'comment',3),COLORS['comment'])
        self.assertEqual(self.color_at(document,'WIDTH',3),COLORS['command'])
        self.assertEqual(document.toPlainText(),text)
        document.setPlainText('$( closed $) SHOW\n!!flag');highlighter.rehighlight()
        self.assertEqual(self.color_at(document,'SHOW'),COLORS['command'])
        self.assertEqual(self.color_at(document,'!!flag',1),COLORS['variable'])

    def test_highlighting_does_not_modify_text_or_undo_history(self):
        editor=QPlainTextEdit();highlighter=PmlHighlighter(editor.document())
        editor.setPlainText('!!flag = 1');editor.document().setModified(False)
        highlighter.rehighlight();self.assertFalse(editor.document().isModified())
        editor.moveCursor(editor.textCursor().MoveOperation.End);QTest.keyClicks(editor,'2')
        highlighter.rehighlight();editor.undo()
        self.assertEqual(editor.toPlainText(),'!!flag = 1');editor.close()

    def test_all_pml_editors_attached_and_refresh_does_not_dirty_project(self):
        window=Window()
        try:
            self.assertEqual(len(window.pml_highlighters),6)
            for editor in (window.code,window.after_show,window.default_body,window.body,window.view_code,window.choice_commands):
                self.assertIsInstance(editor.pml_highlighter,PmlHighlighter)
            window.refresh();self.assertFalse(window.dirty);self.assertEqual(window.history,[])
        finally:
            self.app.clipboard().clear();window.dirty=False;window.close();self.app.processEvents()
