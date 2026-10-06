"""Lexical PML highlighting; display formatting never changes source text."""
import re
from PySide6.QtGui import QSyntaxHighlighter,QTextCharFormat,QColor,QFont

COLORS={'command':'#1755ad','object':'#007b83','variable':'#7c3eaa',
        'string':'#26713b','number':'#a34a12','method':'#946500',
        'property':'#516779','comment':'#738078'}
from .pml_syntax import KEYWORDS

PROPERTIES=set('VAL DTEXT RTEXT VISIBLE ACTIVE WIDTH HEIGHT CALLBACK INITCALL OKCALL CANCELCALL CONTROL'.split())
TOKEN=re.compile(r"--.*|\$\*.*|\$\(|['\"|]|!![A-Za-z][A-Za-z0-9_]*|![A-Za-z_][A-Za-z0-9_]*|\.[A-Za-z_][A-Za-z0-9_]*|(?<![\w.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?(?!\w)|\$[A-Za-z][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*")
QUOTES={"'":1,'"':2,'|':3}
BLOCK_COMMENT=4


class PmlHighlighter(QSyntaxHighlighter):
    def __init__(self,document):
        super().__init__(document)
        self.form_name='';self.objects=set()
        self.formats={}
        for kind,color in COLORS.items():
            fmt=QTextCharFormat();fmt.setForeground(QColor(color))
            if kind=='command':fmt.setFontWeight(QFont.Bold)
            if kind=='comment':fmt.setFontItalic(True)
            self.formats[kind]=fmt

    def set_symbols(self,form):
        from .names import actual_name
        objects={actual_name(g).lower() for g in form.gadgets}|{g.name.lower() for g in form.gadgets}|{m.name.lower() for m in form.menus}
        if self.form_name==form.name.lower() and self.objects==objects:return
        self.form_name=form.name.lower();self.objects=objects;self.rehighlight()

    def highlightBlock(self,text):
        # QTextDocument uses UTF-16 offsets; Python indexes Unicode code points.
        offsets=[0]
        for char in text:offsets.append(offsets[-1]+(2 if ord(char)>0xffff else 1))
        def paint(start,end,kind):self.setFormat(offsets[start],offsets[end]-offsets[start],self.formats[kind])
        self.setCurrentBlockState(0)
        start=0;state=self.previousBlockState()
        if state==BLOCK_COMMENT:
            end=text.find('$)')
            if end<0:
                paint(0,len(text),'comment');self.setCurrentBlockState(state);return
            paint(0,end+2,'comment');start=end+2
        elif state in QUOTES.values():
            quote=next(char for char,value in QUOTES.items() if value==state)
            end=text.find(quote)
            if end<0:
                paint(0,len(text),'string');self.setCurrentBlockState(state);return
            paint(0,end+1,'string');start=end+1
        while start<len(text):
            match=TOKEN.search(text,start)
            if not match:break
            token=match.group();end=match.end();kind=None
            if token.startswith(('--','$*')):
                paint(match.start(),len(text),'comment');break
            if token=='$(':
                close=text.find('$)',end)
                end=len(text) if close<0 else close+2
                paint(match.start(),end,'comment')
                if close<0:self.setCurrentBlockState(BLOCK_COMMENT)
            elif token in QUOTES:
                close=text.find(token,end)
                end=len(text) if close<0 else close+1
                paint(match.start(),end,'string')
                if close<0:self.setCurrentBlockState(QUOTES[token])
            else:
                if token.startswith('!!'):kind='object' if token[2:].lower()==self.form_name else 'variable'
                elif token.startswith('!'):kind='variable'
                elif token.startswith('.') and (token[1].isalpha() or token[1]=='_'):
                    kind='method' if text[end:].lstrip().startswith('(') else 'property' if token[1:].upper() in PROPERTIES else 'object'
                elif token.startswith('$'):kind='command'
                elif token.upper() in ('TRUE','FALSE','UNSET'):kind='number'
                elif token.upper() in KEYWORDS:kind='command'
                elif token.lower() in self.objects:kind='object'
                elif token[0].isdigit() or token[0] in '+-.':kind='number'
                if kind:paint(match.start(),end,kind)
            start=end
