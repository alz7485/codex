"""Import declarative PML forms. Source is parsed as data and is never executed."""
import copy
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .model import Form, Gadget, Menu, MenuItem, Method, display_size, normalize_dimensions, uses_pairs, macro_path_supported
from .model import literal as pml_literal, image_path_literal as pml_image_path
from .names import actual_name
from .pml_syntax import mask_non_code, NON_CODE, has_code
from .symbols import split_form_reference

NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
NAME = r'[A-Za-z_][A-Za-z0-9_]*'
TOKEN = re.compile(r"""'[^']*'|"[^"]*"|\|[^|]*\||[^\s]+""")
HEADER = re.compile(r'^\s*DEFINE\s+METHOD\s+\.('+NAME+r')\s*(\(.*\)(?:\s+IS\s+\S+)?)\s*$',re.I)
ARRAY_START = re.compile(r'^!('+NAME+r')\s*=\s*(?:OBJECT\s+)?ARRAY\s*\(\s*\)\s*$',re.I)
CELL = re.compile(r'^!('+NAME+r')\s*((?:\[\d+\])+)\s*=\s*(.*)$',re.I)
PROPERTY = re.compile(r'^!this\.('+NAME+r')\.(DTEXT|RTEXT|VAL)\s*=\s*(.*)$',re.I)
CALL = re.compile(r'^!this\.('+NAME+r')\s*\(\s*\)$',re.I)
ATTRIBUTE_KINDS = {
    'TAGWID':{'combo'},'TAGWIDTH':{'combo'},'SCROLL':{'combo'},
    'ASPECT':{'view'},'BACKGROUND':{'button','paragraph','list'},
    'IS':{'text'},'TABSET':{'frame'},'TOOLBAR':{'frame'},
    'HORIZ':{'line'},'VERT':{'line'},
    'HORIZONTAL':{'slider'},'VERTICAL':{'slider'},
    'RANGE':{'slider'},'STEP':{'slider'},'VAL':{'slider'},
    'SINGLE':{'list','selector'},'MULTIPLE':{'list','selector'},'MULTI':{'list','selector'},
    'STATES':{'rtoggle'},'ALPHA':{'view'},'AREA':{'view'},'PLOT':{'view'},'VOLUME':{'view'},
    'DATABASE':{'selector'},'FIXCHARS':{'textpane'},'FIXED':{'textpane'},
    'PIXMAP':{'button','paragraph','toggle','option'},'PMLNETCONTROL':{'container'},
    **{key:{'button'} for key in ('OK','APPLY','CANCEL','RESET','HELP','NORMAL')},
}


class MacImportError(ValueError):
    def __init__(self,line,message):
        super().__init__(f'MAC {line}行: {message}')
        self.line=line


def empty_signature(signature):
    """Recognize an argument-free method regardless of spacing inside ()."""
    return bool(re.fullmatch(r'\(\s*\)',signature.strip()))


@dataclass
class ImportResult:
    form: Form
    warnings: list[str]
    encoding: str = ''


def decode_mac(data):
    if len(data)>4*1024*1024:raise ValueError('MACは4MB以下にしてください。')
    if data.startswith((b'\xff\xfe',b'\xfe\xff')):
        text=data.decode('utf-16');encoding='UTF-16'
    else:
        try:text=data.decode('utf-8-sig');encoding='UTF-8'
        except UnicodeDecodeError:
            try:text=data.decode('cp932');encoding='SJIS（CP932）'
            except UnicodeDecodeError as error:raise ValueError('MACの文字コードをSJISまたはUTF-8にしてください。') from error
    if '\x00' in text:raise ValueError('MACにNULが含まれています。')
    return text.replace('\r\n','\n').replace('\r','\n'),encoding


def scalar(text):
    text=text.strip()
    if len(text)>=2 and text[0] in "'\"|" and text[-1]==text[0] and text[0] not in text[1:-1]:
        return text[1:-1],'string'
    if re.fullmatch(NUMBER,text):
        value=float(text)
        if math.isfinite(value):return text,'number'
    if text.upper() in ('TRUE','FALSE'):return text,'boolean'
    return None


def editable_string(value,image=False):
    """Only convert literals that the property editor can faithfully emit."""
    try:(pml_image_path if image else pml_literal)(value)
    except ValueError:return False
    return True


def comment_lines(body):
    """Keep complete comment spans, including blocks crossing statement lines."""
    retained=['\n' if char=='\n' else ' ' for char in body]
    for match in NON_CODE.finditer(body):
        if match.group().startswith(('--','$*','$(')):
            retained[match.start():match.end()]=match.group()
    return ''.join(retained).splitlines()


def split_methods(text):
    """Return top-level source and complete method bodies, ignoring comments/strings."""
    raw=text.splitlines();masked=mask_non_code(text).splitlines()
    plain=mask_non_code(text,strings=False).splitlines()
    comments=comment_lines(text)
    methods=[];remaining=[];rows={};index=0;names=set()
    while index<len(raw):
        if not re.match(r'^\s*DEFINE\s+METHOD\b',masked[index],re.I):
            remaining.append(raw[index]);index+=1;continue
        match=HEADER.fullmatch(plain[index])
        if not match:raise MacImportError(index+1,'メソッドの宣言を解釈できません。')
        name,signature=match.groups();key=name.lower()
        if key in names:raise MacImportError(index+1,'メソッド名が重複しています: '+name)
        names.add(key);start=index;index+=1
        while index<len(raw) and not re.fullmatch(r'\s*ENDMETHOD\s*',masked[index],re.I):
            if re.match(r'^\s*DEFINE\s+METHOD\b',masked[index],re.I):raise MacImportError(index+1,'前のメソッドにENDMETHODがありません。')
            index+=1
        if index==len(raw):raise MacImportError(start+1,'メソッドにENDMETHODがありません。')
        body=raw[start+1:index]
        if comments[start].strip():body=[comments[start].rstrip(),*body]
        methods.append(Method(name,signature,'\n'.join(body)))
        rows[key]=start+1
        remaining.extend(['']*(index-start));remaining.append(comments[index].rstrip());index+=1
    return '\n'.join(remaining),methods,rows


class Tokens:
    def __init__(self,text,line):
        self.values=TOKEN.findall(text);self.index=0;self.line=line
    def more(self):return self.index<len(self.values)
    def peek(self):return self.values[self.index] if self.more() else ''
    def pop(self):
        if not self.more():raise MacImportError(self.line,'宣言の値が不足しています。')
        value=self.values[self.index];self.index+=1;return value
    def word(self,expected):
        if self.pop().upper()!=expected:raise MacImportError(self.line,expected+'を指定してください。')
    def quoted(self):
        value=scalar(self.pop())
        if not value or value[1]!='string':raise MacImportError(self.line,'引用符付きの文字列が必要です。')
        return value[0]
    def number(self):
        value=scalar(self.pop())
        if not value or value[1]!='number':raise MacImportError(self.line,'数値を指定してください。式で計算する座標・サイズは未対応です。')
        return float(value[0])


class Importer:
    def __init__(self,text):
        self.text=text;self.raw=text.splitlines()
        self.code=mask_non_code(text,strings=False).splitlines()
        self.structure=mask_non_code(text).splitlines()
        self.comments=comment_lines(text)
        self.warnings=[];self.form=Form(auto_default=False)
        self.explicit={};self.callbacks={};self.setup_size=False
        self.placements={}

    def warn(self,message):
        if message not in self.warnings:self.warnings.append(message)

    def gadget_named(self,name):
        return next((g for g in self.form.gadgets if actual_name(g).lower()==name.lower() or g.name.lower()==name.lower()),None)

    def program_slice(self,index,include_exit=False):
        """Preserve comments that cross the declaration/program boundary."""
        start=index-1 if include_exit and self.comments[index-1].strip() else index
        lines=self.raw[start:].copy()
        if start<index:lines[0]=self.comments[start].rstrip()
        program='\n'.join(lines)
        offset=sum(len(line)+1 for line in self.raw[:start])
        for match in NON_CODE.finditer(self.text):
            if match.start()<offset<match.end() and match.group().startswith(('--','$*','$(')):
                program=self.text[match.start():offset]+program
                start=self.text[:match.start()].count('\n')
                break
        return program,start

    def position(self,tokens,gadget):
        axes=set()
        while tokens.more():
            axis=tokens.peek()[:1].upper()
            if axis not in ('X','Y') or not re.match(r'^[XY](?:$|[+\-\d.]|MIN\.|MAX\.)',tokens.peek(),re.I):break
            if axis in axes:raise MacImportError(tokens.line,'ATで同じ軸を複数回指定できません。')
            axes.add(axis)
            value=tokens.pop();upper=value.upper()
            if upper==axis:setattr(gadget,axis.lower(),tokens.number());continue
            compact=re.fullmatch(axis+'('+NUMBER+')',value,re.I)
            if compact:setattr(gadget,axis.lower(),float(compact.group(1)));continue
            relative=re.fullmatch('('+axis+r'(?:MIN|MAX))\.('+NAME+r')(-SIZE)?('+NUMBER+r')?',value,re.I)
            if not relative:raise MacImportError(tokens.line,'配置指定を解釈できません: '+value)
            edge,name,anchor,offset=relative.groups()
            if axis=='Y' and anchor:raise MacImportError(tokens.line,'Y方向の-SIZE配置は未対応です。')
            gadget.layout_mode='RELATIVE';setattr(gadget,axis.lower()+'ref',name)
            setattr(gadget,axis.lower()+'edge',edge.upper());setattr(gadget,axis.lower()+'offset',float(offset or 0))
            if axis=='X':gadget.xanchor='RIGHT' if anchor else 'LEFT'
        if gadget.layout_mode=='RELATIVE' and (not gadget.xref or not gadget.yref):
            raise MacImportError(tokens.line,'絶対座標と相対座標の混在は未対応です。')
        if not axes:raise MacImportError(tokens.line,'ATにはXまたはYを指定してください。')
        return {axis.lower() for axis in axes}

    def attributes(self,tokens,gadget,present):
        while tokens.more():
            token=tokens.pop();key=token.upper()
            if key in ATTRIBUTE_KINDS and gadget.kind not in ATTRIBUTE_KINDS[key]:
                raise MacImportError(tokens.line,f'{gadget.kind.upper()}には{key}を指定できません。')
            if token[0] in "'\"|":
                value=scalar(token)
                if not value or value[1]!='string':raise MacImportError(tokens.line,'文字列の引用符を確認してください。')
                if 'label' in present:raise MacImportError(tokens.line,'表示名が複数あります。')
                gadget.label=value[0];present.add('label')
            elif key=='AT':
                if 'position' in present:raise MacImportError(tokens.line,'ATを複数回指定できません。')
                present.update(self.position(tokens,gadget));present.add('position')
            elif key=='WIDTH':
                gadget.width=tokens.number();present.add('width')
            elif key.startswith('WIDTH.'):
                gadget.width_ref=token.split('.',1)[1];present.add('width')
            elif key=='HEIGHT':
                gadget.height=tokens.number();present.add('height')
            elif key in ('TAGWID','TAGWIDTH','SCROLL','ASPECT'):
                value=tokens.pop()
                setattr(gadget,{'TAGWID':'combo_tagwid','TAGWIDTH':'combo_tagwid','SCROLL':'combo_scroll','ASPECT':'view_aspect'}[key],value)
            elif key=='BACKGROUND':gadget.background=tokens.pop()
            elif key in ('CALL','CALLBACK'):self.callbacks[gadget.name]=(tokens.quoted(),tokens.line)
            elif key in ('TEXT','TAG'):gadget.label=tokens.quoted();present.add('label')
            elif key=='IS':gadget.value_type=tokens.pop().upper()
            elif key in ('TABSET','TOOLBAR'):gadget.frame_style=key
            elif key in ('HORIZ','VERT'):gadget.orientation=key
            elif key in ('HORIZONTAL','VERTICAL'):gadget.slider_orientation=key
            elif key=='RANGE':gadget.slider_min=tokens.number();gadget.slider_max=tokens.number()
            elif key=='STEP':gadget.slider_step=tokens.number()
            elif key=='VAL':gadget.slider_value=tokens.number()
            elif key in ('SINGLE','MULTIPLE','MULTI'):gadget.selection_mode='MULTIPLE' if key=='MULTI' else key
            elif key=='STATES':gadget.off_value=tokens.quoted();gadget.on_value=tokens.quoted()
            elif key in ('ALPHA','AREA','PLOT','VOLUME'):gadget.view_type=key
            elif key=='DATABASE':gadget.database=tokens.pop().upper()
            elif key in ('FIXCHARS','FIXED'):
                gadget.fixed_font=True
                if key=='FIXED':tokens.word('SPACE');tokens.word('FONT')
            elif key=='PIXMAP':
                gadget.display_mode='PIXMAP'
                if gadget.kind in ('paragraph','button','toggle') and tokens.peek()[:1] in ("'",'"','|'):
                    gadget.pixmap_path=tokens.quoted()
            elif key in ('OK','APPLY','CANCEL','RESET','HELP','NORMAL'):gadget.button_role=key
            elif key=='PMLNETCONTROL':pass
            else:raise MacImportError(tokens.line,'未対応の部品指定です: '+token)

    def parse(self):
        starts=[i for i,line in enumerate(self.structure) if re.match(r'^\s*SETUP\s+FORM\b',line,re.I)]
        if len(starts)!=1:raise ValueError('MACにはSETUP FORMを1つ記載してください。処理だけのマクロはフォームへ変換できません。')
        start=starts[0];tokens=Tokens(self.code[start],start+1)
        tokens.word('SETUP');tokens.word('FORM');name=tokens.pop()
        try:self.form.form_prefix,self.form.name=split_form_reference(name)
        except ValueError as error:raise MacImportError(start+1,str(error)) from error
        self.form.title=self.form.name
        while tokens.more():
            key=tokens.pop().upper()
            if key=='SIZE':self.form.width=tokens.number();self.form.height=tokens.number();self.setup_size=True
            elif key in ('DIALOG','MAIN'):self.form.form_type=key
            elif key=='DOCK':self.form.dock_side=tokens.pop().upper()
            else:raise MacImportError(start+1,'未対応のフォーム指定です: '+key)
        preamble=[]
        preamble_started=False
        for index in range(start):
            line=self.code[index].strip()
            if re.match(r'^VAR\s+!{1,2}'+NAME+r'(?:\s|$)',line,re.I) and not preamble_started:
                tokens=Tokens(line,index+1);tokens.word('VAR');symbol=tokens.pop()
                local=not symbol.startswith('!!');name=symbol[1:] if local else symbol[2:]
                variables=self.form.local_variables if local else self.form.variables
                value=scalar(tokens.pop())
                if not tokens.more() and value and value[1]=='string' and editable_string(value[0]):
                    if name.lower() in {key.lower() for key in variables}:raise MacImportError(index+1,'変数名が重複しています。')
                    variables[name]=value[0]
                    preamble.append(self.comments[index].rstrip())
                    continue
                self.warn('編集用の変数欄へ変換できない初期値は、フォーム定義前の処理として保持しました。')
            if re.fullmatch(r'KILL\s+'+re.escape(self.form.symbol),line,re.I):
                preamble.append(self.comments[index].rstrip());continue
            if self.raw[index].strip().startswith(('-- Generated by','-- Target:')):continue
            if line:preamble_started=True
            preamble.append(self.raw[index])
        self.form.preamble_code='\n'.join(preamble).strip('\n')
        stack=[];layout={};comments=[];assembly=namespace='';members={};member_rows={};imports=[];index=start+1
        bar_entries=[];bar_row=None;explicit_exit=False
        kinds={'BUTTON':'button','PARAGRAPH':'paragraph','PARA':'paragraph','TEXT':'text','TOGGLE':'toggle','OPTION':'option',
               'LIST':'list','LINE':'line','FRAME':'frame','SLIDER':'slider','RTOGGLE':'rtoggle','COMBO':'combo','COMBOBOX':'combo',
               'VIEW':'view','CONTAINER':'container','TEXTPANE':'textpane','TEXTPANEL':'textpane','SELECTOR':'selector'}
        while index<len(self.raw):
            line=self.code[index].strip();row=index+1;index+=1
            if not line:
                raw=self.raw[row-1].strip()
                if raw.startswith(('--','$*')) and not raw.startswith(('-- Auto placement follows','-- Set Control handle')):
                    comments.append(raw[2:].lstrip())
                elif raw:
                    # Preserve complete block-comment fragments as line comments.
                    comments.append(raw)
                continue
            tokens=Tokens(line,row);key=tokens.pop().upper();parent=stack[-1] if stack else ''
            if key=='SHOW':
                if not re.fullmatch(r'SHOW\s+'+re.escape(self.form.symbol)+r'\s*',line,re.I):
                    raise MacImportError(row,'フォーム宣言を終えるSHOWには'+self.form.symbol+'を指定してください。')
                self.warn('SHOW '+self.form.symbol+'をフォーム宣言の終端として読み込み、省略されたフォームのEXITを補いました。')
                if stack:
                    self.warn('SHOWの前で閉じられていないFRAMEを補完しました: '+', '.join(stack))
                # Keep SHOW and its complete comment spans in the program slice.
                index-=1
                break
            if key=='EXIT':
                if tokens.more():raise MacImportError(row,'EXITの後に未対応の指定があります。')
                if stack:stack.pop();continue
                explicit_exit=True
                break
            if key=='TITLE':
                self.form.title=tokens.quoted()
                if tokens.more():raise MacImportError(row,'TITLEの後に未対応の指定があります。')
                continue
            if key in ('PATH','HDIST','HDISTANCE','VDIST','VDISTANCE','HALIGN','VALIGN'):
                field={'PATH':'path','HDIST':'hgap','HDISTANCE':'hgap','VDIST':'vgap','VDISTANCE':'vgap','HALIGN':'halign','VALIGN':'valign'}[key]
                value=tokens.number() if field in ('hgap','vgap') else tokens.pop().upper()
                choices={'path':('DOWN','UP','LEFT','RIGHT'),'halign':('LEFT','CENTRE','RIGHT'),'valign':('TOP','CENTRE','BOTTOM')}
                if field in choices and value not in choices[field]:raise MacImportError(row,'配置方向・整列の指定が不正です: '+str(value))
                if field in ('hgap','vgap') and value<0:raise MacImportError(row,'配置間隔は0以上で指定してください。')
                layout.setdefault(parent,{})[field]=value
                if tokens.more():raise MacImportError(row,'配置指定の後に未対応の指定があります。')
                continue
            if key=='IMPORT':
                assembly=tokens.quoted();imports.append((row,'assembly',assembly))
                if tokens.more():raise MacImportError(row,'IMPORTの後に未対応の指定があります。')
                continue
            if key=='USING':
                tokens.word('NAMESPACE');namespace=tokens.quoted();imports.append((row,'namespace',namespace))
                if tokens.more():raise MacImportError(row,'USINGの後に未対応の指定があります。')
                continue
            if key=='MEMBER':
                member=tokens.pop().lstrip('.');tokens.word('IS');members[member.lower()]=(assembly,namespace,tokens.pop())
                member_rows[member.lower()]=row
                if tokens.more():raise MacImportError(row,'MEMBERの後に未対応の指定があります。')
                continue
            if key=='BAR':
                if stack or bar_row is not None:raise MacImportError(row,'BARはフォーム直下に1つだけ指定してください。')
                if tokens.more():raise MacImportError(row,'BARの後に未対応の指定があります。')
                bar_row=row
                while index<len(self.raw):
                    value=self.code[index].strip();entry_row=index+1
                    if not value:index+=1;continue
                    if not re.match(r'^ADD\b',value,re.I):break
                    index+=1;item=Tokens(value,entry_row);item.word('ADD')
                    label=item.quoted();target=item.pop()
                    if not re.fullmatch(r'\.'+NAME,target):raise MacImportError(entry_row,'BARのADDには.メニュー名を指定してください。')
                    if item.more():raise MacImportError(entry_row,'BARの項目に未対応の指定があります。')
                    if any(name.lower()==target[1:].lower() for _,name,_ in bar_entries):raise MacImportError(entry_row,'同じメニューをBARへ複数回登録できません。')
                    bar_entries.append((label,target[1:],entry_row))
                if not bar_entries:raise MacImportError(row,'BARにはADDでタイトルとメニュー名を指定してください。')
                continue
            if key=='MENU':
                if stack:raise MacImportError(row,'フレーム内でのMENU宣言は未対応です。')
                menu=Menu(name=tokens.pop().lstrip('.'))
                if tokens.more():tokens.word('POPUP');menu.popup=True
                if tokens.more():raise MacImportError(row,'MENUに未対応の指定があります。')
                self.form.menus.append(menu)
                while index<len(self.raw) and self.code[index].strip().upper()!='EXIT':
                    value=self.code[index].strip();menu_row=index+1
                    # MENU items may end at the next independent declaration.
                    # Its EXIT belongs to that declaration, not to this menu.
                    next_key=value.split(maxsplit=1)[0].upper() if value else ''
                    if next_key in set(kinds)|{'MENU','BAR','TITLE','PATH','HDIST','HDISTANCE',
                            'VDIST','VDISTANCE','HALIGN','VALIGN','IMPORT','USING','MEMBER','SHOW','DEFINE'}:break
                    index+=1
                    if not value:continue
                    item=Tokens(value,menu_row);item.word('ADD');menu.items.append(MenuItem(item.quoted(),item.quoted()))
                    if item.more():raise MacImportError(menu_row,'メニュー項目に未対応の指定があります。')
                if index==len(self.raw):raise MacImportError(row,'MENUにEXITがありません。')
                if self.code[index].strip().upper()=='EXIT':index+=1
                else:self.warn('MENUの省略されたEXITを、次の宣言の前で補いました。')
                continue
            if key=='VAR':
                tokens.word('LIST');target=tokens.pop().lstrip('.');tokens.word('PAIRS')
                gadget=self.gadget_named(target)
                if gadget is None or not uses_pairs(gadget):raise MacImportError(row,'VAR LISTの対象OPTIONが見つかりません。')
                while index<len(self.raw) and self.code[index].strip().upper()!='EXIT':
                    value=self.code[index].strip();pair_row=index+1;index+=1
                    if not value:continue
                    item=Tokens(value,pair_row);gadget.items.append(item.quoted());gadget.item_commands.append(item.quoted())
                    if item.more():raise MacImportError(pair_row,'選択肢は表示名とコマンドの2列で指定してください。')
                if index==len(self.raw):raise MacImportError(row,'VAR LISTにEXITがありません。')
                index+=1;continue
            if key not in kinds:raise MacImportError(row,'フォーム内の未対応の宣言です: '+line)
            object_name=tokens.pop()
            if not object_name.startswith(('.','_')):raise MacImportError(row,'部品名を.名前または_名前で指定してください。')
            gadget=Gadget(kind=kinds[key],name=object_name.lstrip('.') if not object_name.startswith('_') else object_name[1:],
                          label='',parent=parent,x=0,y=0)
            if gadget.kind in ('frame','list','view','container','textpane','selector'):gadget.height=5
            if gadget.kind=='option' and object_name.startswith('.'):gadget.option_style='GADGET'
            if gadget.kind=='combo':gadget.combo_keyword=key;gadget.combo_scroll=''
            if gadget.kind=='view':gadget.channels='NONE'
            if gadget.kind=='textpane':gadget.fixed_font=False
            present=set();self.attributes(tokens,gadget,present)
            self.placements[gadget.name]=layout.get(parent,{}).copy()
            for field,value in self.placements[gadget.name].items():setattr(gadget,field,value)
            if not {'x','y'}<=present and gadget.layout_mode!='RELATIVE':
                self.warn('省略されたATの座標は、コンテナごとの現在地とPATHから補いました。キャンバスで配置を確認してください。')
            if gadget.kind=='container' and (gadget.name+'Control').lower() in members:
                gadget.assembly,gadget.namespace,gadget.control_type=members[(gadget.name+'Control').lower()]
            if gadget.kind=='view':
                view_code=[];channels=[]
                while index<len(self.raw) and self.code[index].strip().upper()!='EXIT':
                    value=self.code[index].strip();view_row=index+1;raw=self.raw[index];index+=1
                    if re.match(r'^(WIDTH(?:\.|\s)|HEIGHT\s|ASPECT\s)',value,re.I):
                        self.attributes(Tokens(value,view_row),gadget,present)
                    elif re.match(r'^CHANNEL\s+',value,re.I):channels.append(value.split()[1].upper())
                    else:view_code.append(raw)
                if index==len(self.raw):raise MacImportError(row,'VIEWにEXITがありません。')
                index+=1;gadget.view_code='\n'.join(view_code).strip('\n')
                if channels:gadget.channels='BOTH' if set(channels)=={'REQUESTS','COMMANDS'} else channels[0]
                if gadget.view_type=='ALPHA':gadget.kind='commandline'
            inline=self.comments[row-1].strip()
            if inline:comments.append(inline[2:].lstrip() if inline.startswith(('--','$*')) else inline)
            gadget.comment='\n'.join(comments);comments=[]
            normalize_dimensions(gadget);self.form.gadgets.append(gadget);self.explicit[gadget.name]=present
            if len(self.form.gadgets)>500:raise MacImportError(row,'部品数は500個までです。')
            if gadget.kind=='frame':stack.append(gadget.name)
        else:raise MacImportError(start+1,'フォーム定義にEXITがありません。')
        if comments:self.form.preamble_code+='\n'+'\n'.join('-- '+comment for comment in comments)
        containers=[g for g in self.form.gadgets if g.kind=='container' and g.assembly]
        for member in members:
            if not any(member==(g.name+'Control').lower() for g in containers):
                raise MacImportError(member_rows[member],'CONTAINERの制御用以外のMEMBER宣言は未対応です。')
        for row,field,value in imports:
            if not any(getattr(g,field)==value for g in containers):
                raise MacImportError(row,'CONTAINERの設定用以外のIMPORT／USING宣言は未対応です。')
        if bar_row is not None:
            ordered=[]
            for menu in self.form.menus:menu.on_bar=False
            for label,name,row in bar_entries:
                menu=next((m for m in self.form.menus if m.name.lower()==name.lower()),None)
                if menu is None or menu.popup:raise MacImportError(row,'BARの登録先には定義済みの通常MENUを指定してください: '+name)
                menu.label=label;menu.on_bar=True;ordered.append(menu)
            self.form.menus=ordered+[m for m in self.form.menus if not m.on_bar]
        elif any(not menu.popup for menu in self.form.menus):
            self.warn('BARのない旧形式のMENUは、メニュー名をタイトルとしてBARへ登録しました。')
        for gadget in self.form.gadgets:
            for field in ('xref','yref','width_ref'):
                target=self.gadget_named(getattr(gadget,field))
                if target:setattr(gadget,field,target.name)
        after,index=self.program_slice(index,explicit_exit)
        try:program,methods,method_rows=split_methods(after)
        except MacImportError as error:
            raise MacImportError(index+error.line,str(error).split(': ',1)[-1]) from error
        source_methods={method.name.lower():method for method in methods}
        program_masked=mask_non_code(program).splitlines()
        program_comments=comment_lines(program)
        first=next((row for row,line in enumerate(program_masked) if line.strip()),None)
        if first is not None and re.fullmatch(r'\s*SHOW\s+'+re.escape(self.form.symbol)+r'\s*',program_masked[first],re.I):
            # Only the leading display statement is represented by generated SHOW.
            self.form.after_show_code='\n'.join(
                program_comments[row].rstrip() if row==first else line
                for row,line in enumerate(program.splitlines())).strip('\n')
        else:
            self.form.program_mode='SOURCE'
            self.form.after_show_code=program.strip('\n')
        constructor=source_methods.pop(self.form.name.lower(),None)
        default=source_methods.pop('default',None)
        self.form.auto_default=False
        self.form.keep_default=default is not None
        if default and not empty_signature(default.signature):raise MacImportError(index+method_rows['default'],'DEFAULTの引数には対応していません。')
        before_defaults=copy.deepcopy(self.form)
        defaults_structured=self.read_defaults(default.body) if default else False
        if not defaults_structured:
            self.form=copy.deepcopy(before_defaults)
            self.form.default_mode='SOURCE'
            if default:
                self.form.default_body=default.body
                self.warn('DEFAULTは元コードとして保持しました。初期値は「取り込みコード」のDEFAULT欄で編集してください。')
        if constructor:
            if not empty_signature(constructor.signature):raise MacImportError(index+method_rows[self.form.name.lower()],'フォームのコンストラクタに引数があります。')
            if self.read_constructor(constructor.body,source_methods):
                pass
            else:
                self.form=before_defaults
                self.form.default_mode='SOURCE'
                if default:self.form.default_body=default.body
                self.form.constructor_body=constructor.body;self.form.constructor_mode='SOURCE'
                self.warn('複雑なコンストラクタは元の処理として保持しました。選択肢などの初期化は「取り込みコード」で編集してください。')
        for name,(command,row) in self.callbacks.items():
            gadget=self.form.named(name)
            if uses_pairs(gadget):
                if command.lower()!=('$$'+actual_name(gadget)).lower():raise MacImportError(row,'PAIRS OPTIONのCALLが対象名と一致しません。')
                continue
            match=CALL.fullmatch(command.strip())
            method=source_methods.get(match.group(1).lower()) if match else None
            if match and match.group(1).lower()=='default' and default:
                gadget.callback=default.name
                gadget.callback_expression=command if command!=f'!this.{default.name}()' else ''
                gadget.body=''
                continue
            if gadget.kind in ('button','text','toggle') or (gadget.kind=='option' and gadget.display_mode=='TEXT'):
                if method and empty_signature(method.signature):
                    gadget.callback=method.name;gadget.body=method.body
                    gadget.callback_expression=command if command!=f'!this.{method.name}()' else ''
                else:gadget.command=command
            elif method and empty_signature(method.signature):
                gadget.callback=method.name;gadget.body=method.body
                gadget.callback_expression=command if command!=f'!this.{method.name}()' else ''
            else:raise MacImportError(row,'この部品のCALLを復元できません。引数なしの!this.メソッド()にしてください。')
        linked={g.callback.lower() for g in self.form.gadgets if g.callback}
        callback_counts={}
        for g in self.form.gadgets:
            key=g.callback.lower();callback_counts[key]=callback_counts.get(key,0)+1
        for gadget in self.form.gadgets:
            method=source_methods.get(gadget.callback.lower())
            if gadget.kind!='button' or not method or method.name.lower()!=('macro_'+gadget.name).lower():continue
            if callback_counts[gadget.callback.lower()]!=1:continue
            lines=self.significant(method.body)
            if any(match.group().startswith(('--','$*','$(')) for match in NON_CODE.finditer(method.body)):continue
            macro=re.fullmatch(r'\$M\s+(".*")',lines[-1][1],re.I) if lines else None
            path=scalar(macro.group(1)) if macro else None
            if not path or path[1]!='string' or len(lines)>2 or not macro_path_supported(path[0]):continue
            flag=value=''
            if len(lines)==2:
                assignment=re.fullmatch(r'!!('+NAME+r')\s*=\s*(.*)',lines[0][1])
                literal=scalar(assignment.group(2)) if assignment else None
                if not literal or literal[1]!='string' or not editable_string(literal[0]) or assignment.group(1).lower() not in {key.lower() for key in self.form.variables}:continue
                flag=assignment.group(1);value=literal[0]
            gadget.action_mode='MACRO';gadget.macro_path=path[0];gadget.macro_flag=flag;gadget.macro_value=value;gadget.callback='';gadget.body=''
        self.form.extra_methods=[method for key,method in source_methods.items() if key not in linked]
        if defaults_structured and self.form.default_mode=='GENERATED':
            source_targets=[m.group(1).lower() for _,line in self.significant(default.body)
                            if (m:=PROPERTY.fullmatch(line))]
            generated_targets=[m.group(1).lower() for line in self.form.initial_lines()
                               if (m:=PROPERTY.fullmatch(line.strip()))]
            if source_targets!=generated_targets:
                self.form.default_mode='SOURCE';self.form.default_body=default.body
                if self.form.auto_default:
                    self.form.constructor_body=(self.form.constructor_body+'\n!this.DEFAULT()').strip('\n')
                    self.form.auto_default=False
                self.warn('DEFAULTの代入順や設定対象を維持するため、元コードとして保持しました。')
        self.fit_dimensions()
        self.form.sync_tabs()
        try:self.form.validate()
        except ValueError as error:raise ValueError('MACを設計データへ変換できません: '+str(error)) from error
        return ImportResult(self.form,self.warnings)

    @staticmethod
    def significant(body):
        return [(index,line.strip()) for index,line in enumerate(mask_non_code(body,strings=False).splitlines()) if line.strip()]

    def array_block(self,lines,index):
        start=ARRAY_START.fullmatch(lines[index][1])
        if start:
            variable=start.group(1);cursor=index+1
        else:
            first=CELL.fullmatch(lines[index][1])
            if not first or first.group(2)!='[1]':return None
            variable=first.group(1);cursor=index
        cells={}
        while cursor<len(lines):
            match=CELL.fullmatch(lines[cursor][1])
            if not match or match.group(1).lower()!=variable.lower():break
            indices=tuple(int(n) for n in re.findall(r'\d+',match.group(2)))
            value=scalar(match.group(3))
            if len(indices)!=1 or not value or indices[0]<1 or indices in cells:return None
            cells[indices]=value;cursor+=1
        if set(cells)!={(i,) for i in range(1,len(cells)+1)}:return None
        if cursor>=len(lines):return None
        target=PROPERTY.fullmatch(lines[cursor][1])
        if not target or target.group(3).lower()!='!'+variable.lower():return None
        gadget=self.gadget_named(target.group(1))
        if gadget is None:return None
        return cursor+1,gadget,target.group(2).upper(),[cells[(i,)] for i in range(1,len(cells)+1)]

    def read_defaults(self,body):
        raw=body.splitlines();lines=self.significant(body);removed=set();seen=set();cursor=0;radio_values={}
        while cursor<len(lines):
            block=self.array_block(lines,cursor)
            if block:
                end,gadget,property_name,values=block
                if property_name!='VAL' or gadget.name in seen:break
                local=(ARRAY_START.fullmatch(lines[cursor][1]) or CELL.fullmatch(lines[cursor][1])).group(1)
                references=re.compile(r'!'+re.escape(local)+r'(?![A-Za-z0-9_])',re.I)
                next_reference=next((statement for _,statement in lines[end:] if references.search(statement)),None)
                reset=ARRAY_START.fullmatch(next_reference) if next_reference else None
                if next_reference and not (reset and reset.group(1).lower()==local.lower()):break
                if gadget.kind=='textpane' and all(kind=='string' and editable_string(v) for v,kind in values):gadget.pane_lines=[v for v,_ in values]
                elif gadget.kind=='list' and gadget.selection_mode=='MULTIPLE' and values and all(kind=='number' and float(v).is_integer() and float(v)>0 for v,kind in values):
                    gadget.initial=','.join(str(int(float(v))) for v,_ in values)
                else:break
                removed.update(row for row,_ in lines[cursor:end]);seen.add(gadget.name);cursor=end;continue
            match=PROPERTY.fullmatch(lines[cursor][1]);value=scalar(match.group(3)) if match else None
            gadget=self.gadget_named(match.group(1)) if match else None
            if not gadget or match.group(2).upper()!='VAL' or not value or gadget.name in seen:break
            text,kind=value
            if kind=='string' and not editable_string(text):break
            if gadget.kind=='frame' and kind=='number':
                radios=[g for g in self.form.ordered_children(gadget.name) if g.kind=='rtoggle']
                selected=float(text)
                if not radios or not selected.is_integer() or not 0<=selected<=len(radios):break
                previous=radio_values.setdefault(gadget.name,[])
                if previous and (previous!=[0] or selected==0):break
                previous.append(selected)
                for index,radio in enumerate(radios,1):radio.initial='TRUE' if index==selected else 'FALSE'
                removed.add(lines[cursor][0]);cursor+=1;continue
            if gadget.kind=='slider' and kind=='number':
                if float(text)!=gadget.slider_value:break
            elif gadget.kind=='text' and kind==('number' if gadget.value_type=='REAL' else 'string'):gadget.initial=text
            elif gadget.kind=='paragraph' and gadget.display_mode!='PIXMAP' and kind=='string':gadget.initial=text
            elif gadget.kind in ('option','combo','list') and kind=='number' and float(text).is_integer() and float(text)>0:
                gadget.initial=str(int(float(text)))
            elif gadget.kind=='toggle' and kind=='boolean':gadget.initial=text
            else:break
            seen.add(gadget.name);removed.add(lines[cursor][0]);cursor+=1
        comments=comment_lines(body)
        self.form.default_body='\n'.join(comments[index].rstrip() if index in removed else line for index,line in enumerate(raw))
        return cursor==len(lines)

    def read_table(self,method):
        if any(line.strip() for line in comment_lines(method.body)):return None
        arrays={};head=rows=None;gadget=None
        for _,line in self.significant(method.body):
            start=ARRAY_START.fullmatch(line)
            if start:arrays[start.group(1).lower()]={};continue
            match=CELL.fullmatch(line)
            if match:
                name,indices,value=match.groups();key=name.lower()
                indices=tuple(int(n) for n in re.findall(r'\d+',indices))
                if key not in arrays:
                    if indices!=(1,) or not re.fullmatch(r'(?:OBJECT\s+)?ARRAY\s*\(\s*\)',value,re.I):return None
                    arrays[key]={}
                if any(n<1 for n in indices) or indices in arrays[key]:return None
                item=scalar(value)
                if item and item[1]=='string':
                    if not editable_string(item[0]):return None
                    arrays[key][indices]=item[0]
                elif re.fullmatch(r'(?:OBJECT\s+)?ARRAY\s*\(\s*\)',value,re.I):arrays[key][indices]=None
                else:return None
                continue
            match=re.fullmatch(r'!this\.('+NAME+r')\.(SETHEADINGS|SETROWS)\s*\(\s*!('+NAME+r')\s*\)',line,re.I)
            if not match:return None
            target=self.gadget_named(match.group(1))
            if target is None or target.kind!='list' or (gadget is not None and target is not gadget):return None
            gadget=target;data=arrays.get(match.group(3).lower())
            if data is None:return None
            if match.group(2).upper()=='SETHEADINGS':
                if set(data)!={(i,) for i in range(1,len(data)+1)} or not data:return None
                head=[data[(i,)] for i in range(1,len(data)+1)]
            else:
                cell_data={key:value for key,value in data.items() if len(key)==2}
                if any(value is None for value in cell_data.values()) or any(len(key)>2 for key in data):return None
                count=max((key[0] for key in cell_data),default=0)
                if head is None or count*len(head)!=len(cell_data):return None
                if set(cell_data)!={(r,c) for r in range(1,count+1) for c in range(1,len(head)+1)}:return None
                rows=[[cell_data[(r,c)] for c in range(1,len(head)+1)] for r in range(1,count+1)]
        if gadget is None or head is None or rows is None:return None
        gadget.list_mode='TABLE';gadget.headings=head;gadget.rows=rows;gadget.table_method=method.name
        return gadget

    def read_constructor(self,body,methods):
        lines=self.significant(body);cursor=0;tables=set();table_names={};default_rows=[];raw=body.splitlines()
        calls=[i for i,(_,line) in enumerate(lines) if CALL.fullmatch(line) and CALL.fullmatch(line).group(1).lower()=='default']
        if calls and (len(calls)!=1 or calls[0]!=len(lines)-1):return False
        while cursor<len(lines):
            block=self.array_block(lines,cursor)
            if block:
                end,gadget,property_name,values=block
                if property_name not in ('DTEXT','RTEXT') or gadget.kind not in ('list','option','combo') or not all(kind=='string' for _,kind in values):return False
                image=property_name=='DTEXT' and gadget.kind=='option' and gadget.display_mode=='PIXMAP'
                if not all(editable_string(value,image=image) for value,_ in values):return False
                setattr(gadget,'items' if property_name=='DTEXT' else 'item_values',[v for v,_ in values]);cursor=end;continue
            row,line=lines[cursor];cursor+=1
            call=CALL.fullmatch(line)
            if call:
                name=call.group(1).lower()
                if name=='default':default_rows.append(row);continue
                method=methods.get(name)
                referenced=any(CALL.fullmatch(command.strip()) and CALL.fullmatch(command.strip()).group(1).lower()==name for command,_ in self.callbacks.values())
                if referenced:return False
                table=self.read_table(method) if method and empty_signature(method.signature) else None
                if table:
                    previous=table_names.get(table.name.lower())
                    if previous and previous!=name:return False
                    table_names[table.name.lower()]=name
                    tables.add(name);continue
                return False
            match=re.fullmatch(r'!this\.(INITCALL|OKCALL|CANCELCALL)\s*=\s*(.*)',line,re.I)
            if match:
                value=scalar(match.group(2))
                if not value or value[1]!='string':return False
                setattr(self.form,match.group(1).lower(),value[0]);continue
            match=re.fullmatch(r'!this\.('+NAME+r')\.(ADDPIXMAP|SETPOPUP|ADD)\s*\((.*)\)',line,re.I)
            if match:
                name,operation,arguments=match.groups();operation=operation.upper()
                if operation=='ADD':
                    args=split_arguments(arguments)
                    menu=next((m for m in self.form.menus if m.name.lower()==name.lower() and m.popup),None)
                    if menu is None or len(args)!=3 or args[0].upper()!='CALLBACK':return False
                    menu.items.append(MenuItem(args[1],args[2]));continue
                gadget=self.gadget_named(name)
                if gadget is None:return False
                if operation=='ADDPIXMAP':
                    value=scalar(arguments)
                    if not value or value[1]!='string':return False
                    gadget.pixmap_path=value[0];gadget.display_mode='PIXMAP';continue
                popup=re.fullmatch(r'!this\.('+NAME+r')',arguments.strip(),re.I)
                if not popup:return False
                gadget.popup_menu=popup.group(1);continue
            match=re.fullmatch(r'!this\.('+NAME+r')\.CALLBACK\s*=\s*(.*)',line,re.I)
            if match:
                gadget=self.gadget_named(match.group(1));value=scalar(match.group(2))
                target=re.fullmatch(r'!this\.('+NAME+r')\(',value[0],re.I) if value and value[1]=='string' else None
                method=methods.get(target.group(1).lower()) if target else None
                if not gadget or gadget.kind not in ('slider','combo') or not method or not re.fullmatch(r'\(\s*!gad\s+IS\s+GADGET\s*,\s*!event\s+IS\s+STRING\s*\)',method.signature,re.I):return False
                gadget.callback=method.name;gadget.body=method.body;continue
            if any(g.kind=='container' and g.assembly and (
                re.fullmatch(r'!this\.'+re.escape(g.name)+r'Control\s*=\s*OBJECT\s+'+re.escape(g.control_type)+r'\(\s*\)',line,re.I)
                or re.fullmatch(r'!this\.'+re.escape(g.name)+r'\.Control\s*=\s*!this\.'+re.escape(g.name)+r'Control\.handle\(\s*\)',line,re.I)) for g in self.form.gadgets):continue
            return False
        for name in tables:methods.pop(name)
        if default_rows:
            if len(default_rows)==1 and default_rows[0]==lines[-1][0] and self.form.initial_lines():
                self.form.auto_default=True
            else:self.form.constructor_body='\n'.join(raw[row] for row in default_rows)
        # Retain constructor comments that the structured decoder does not emit.
        comments=[line.rstrip() for line in comment_lines(body) if line.strip()]
        if comments:self.form.constructor_body='\n'.join(comments+[self.form.constructor_body]).strip('\n')
        return True

    def fit_dimensions(self):
        def fit_frame(gadget):
            children=self.form.children(gadget.name);present=self.explicit[gadget.name]
            if 'width' not in present or 'height' not in present:
                self.warn('MACにないフレーム寸法は、部品が収まる大きさに推定しました。キャンバスで確認してください。')
            if gadget.frame_style=='TOOLBAR':
                width=1+sum(display_size(child)[0]+1 for child in children);height=max([2,*[display_size(child)[1]+2 for child in children]])
            else:
                extents=[]
                for child in children:
                    if gadget.frame_style=='TABSET':extents.append((child.width,child.height));continue
                    x,y,w,h=self.form.geometry(child);extents.append((x+w+1,y+h+1))
                width=max([14,*[w for w,_ in extents]]);height=max([5,*[h for _,h in extents]])
            if 'width' not in present:gadget.width=width
            if 'height' not in present:gadget.height=height

        def place_children(parent,trail=()):
            if parent.lower() in trail:raise ValueError('親コンテナの循環を解消してください。')
            children=self.form.children(parent)
            # Fit inner frames first so a following RIGHT/LEFT uses their real edge.
            for child in children:
                if child.kind=='frame':
                    place_children(child.name,(*trail,parent.lower()))
                    fit_frame(child)
            previous=None
            container=self.form.named(parent)
            for child in children:
                settings=self.placements[child.name];present=self.explicit[child.name]
                if child.layout_mode!='RELATIVE' and not (container and container.frame_style in ('TABSET','TOOLBAR')):
                    x=y=0
                    if previous is not None:
                        px,py,pw,ph=self.form.geometry(previous);cw,ch=self.form.geometry(child)[2:]
                        path=settings.get('path','DOWN')
                        x,y=px,py
                        if path in ('DOWN','UP'):
                            x+= {'LEFT':0,'CENTRE':(pw-cw)/2,'RIGHT':pw-cw}[settings.get('halign','LEFT')]
                            step=(ph if path=='DOWN' else ch)+settings['vgap'] if 'vgap' in settings else 1
                            y+=step if path=='DOWN' else -step
                        else:
                            x+=pw+settings.get('hgap',1) if path=='RIGHT' else -cw-settings.get('hgap',1)
                            y+= {'TOP':0,'CENTRE':(ph-ch)/2,'BOTTOM':ph-ch}[settings.get('valign','TOP')]
                    if 'x' not in present:child.x=x
                    if 'y' not in present:child.y=y
                previous=child
        place_children('')
        if not self.setup_size:
            extents=[self.form.geometry(g) for g in self.form.children('')]
            self.form.width=max([70,*[x+w+1 for x,y,w,h in extents]])
            self.form.height=max([22,*[y+h+1 for x,y,w,h in extents]])
            self.warn('MACにないフォームの表示サイズは、部品が収まる大きさに推定しました。')


def split_arguments(text):
    tokens=re.findall(r"""'[^']*'|"[^"]*"|\|[^|]*\||,|[^,\s]+""",text)
    if not tokens or len(tokens)%2==0 or any(token!=',' for token in tokens[1::2]):return []
    values=[scalar(token) for token in tokens[::2]]
    return [value[0] for value in values] if all(value and value[1]=='string' for value in values) else []


def import_mac(text,source_path=None,*,partial=False):
    if len(text)>4*1024*1024 or '\x00' in text:raise ValueError('MACが大きすぎるか、NULを含んでいます。')
    text=text.replace('\r\n','\n').replace('\r','\n').lstrip('\ufeff')
    if partial:
        from .partial_import import recover_mac
        result=recover_mac(text)
    else:result=Importer(text).parse()
    if source_path is not None:result.form.source_mac_path=str(Path(source_path).resolve())
    return result


def read_mac(path,*,partial=False):
    with Path(path).open('rb') as stream:data=stream.read(4*1024*1024+1)
    text,encoding=decode_mac(data)
    result=import_mac(text,path,partial=partial);result.encoding=encoding;return result
