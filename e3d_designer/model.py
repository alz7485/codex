from dataclasses import dataclass, field, asdict
import json
import math
import re
from .pml_syntax import has_code
from .symbols import SYMBOL_NAME

KINDS = ('button', 'paragraph', 'text', 'toggle', 'option', 'list', 'line', 'frame', 'slider', 'rtoggle', 'combo', 'view', 'commandline', 'container', 'textpane', 'selector')
IDENTIFIER = re.compile(r'[A-Za-z][A-Za-z0-9_]*\Z')
CHAR_WIDTH, LINE_HEIGHT = 10, 26


def uses_pairs(gadget):
    return gadget.kind == 'option' and gadget.display_mode == 'TEXT' and gadget.option_style == 'PAIRS'


def supports_hidden(gadget):
    # These declarations emit WIDTH; FRAME zero width means automatic sizing.
    return gadget.kind not in ('frame','line','rtoggle') and not uses_pairs(gadget) and not (gadget.kind=='toggle' and gadget.display_mode=='TEXT')


def fixed_dimensions(gadget):
    if gadget.display_mode == 'PIXMAP':return {}
    if gadget.kind in ('text','paragraph','toggle','option','combo'):return {'height':1}
    if gadget.kind == 'line':
        return {'width':0} if gadget.orientation == 'VERT' else {'height':0}
    if gadget.kind == 'slider':
        return {'width':3} if gadget.slider_orientation == 'VERTICAL' else {'height':1}
    return {}


def dimension_editable(gadget, dimension):
    return gadget.display_mode != 'PIXMAP' and dimension not in fixed_dimensions(gadget) and not (dimension == 'width' and (gadget.width_ref or gadget.hidden))


def normalize_dimensions(gadget):
    before = gadget.width,gadget.height,gadget.width_ref,gadget.hidden
    if type(gadget.width) in (int,float) and gadget.width==0 and supports_hidden(gadget):
        gadget.hidden=True;gadget.width=14
    fixed = fixed_dimensions(gadget)
    for key,value in fixed.items():
        current = getattr(gadget,key)
        if type(current) in (int,float) and math.isfinite(current) and current > 0:
            setattr(gadget,key,value)
    if 'width' in fixed:gadget.width_ref = ''
    return before != (gadget.width,gadget.height,gadget.width_ref,gadget.hidden)


def change_orientation(gadget, direction, resolved_size=None):
    key = 'orientation' if gadget.kind == 'line' else 'slider_orientation'
    if gadget.kind not in ('line','slider') or getattr(gadget,key) == direction:return
    if gadget.hidden and (resolved_size is None or resolved_size[0]==0):
        fixed=fixed_dimensions(gadget);resolved_size=(fixed.get('width',gadget.width),fixed.get('height',gadget.height))
    width,height = resolved_size if resolved_size is not None else display_size(gadget)
    gadget.width,gadget.height = height,width
    gadget.width_ref = ''
    setattr(gadget,key,direction)
    normalize_dimensions(gadget)


def display_size(gadget,*,reveal=False):
    hidden=gadget.hidden and not reveal
    if gadget.display_mode == 'PIXMAP':
        return (0 if hidden else gadget.width/CHAR_WIDTH),gadget.height/LINE_HEIGHT
    fixed = fixed_dimensions(gadget)
    return (0 if hidden else fixed.get('width',gadget.width)),fixed.get('height',gadget.height)


def native_size(gadget,width,height):
    return (width*CHAR_WIDTH,height*LINE_HEIGHT) if gadget.display_mode == 'PIXMAP' else (width,height)


def literal(value, allow_expansion=False, field='表示文字列'):
    # PML expands $ expressions even inside strings. Do not silently emit them.
    forbidden=[]
    if '\r' in value or '\n' in value:forbidden.append('改行')
    if '\x00' in value:forbidden.append('NUL文字（0x00）')
    if '$' in value and not allow_expansion:forbidden.append('$（文字列展開）')
    if forbidden:
        detail=" 空文字列（''）は使用できます。" if '\x00' in value else ''
        raise ValueError(f'{field}には'+'・'.join(forbidden)+'を使用できません。'+detail)
    for delimiter in ("'", '|', '"'):
        if delimiter not in value:
            return delimiter + value + delimiter
    raise ValueError(f'{field}に全種類の引用符があります。引用符を減らしてください。')


def image_path_literal(value,field='画像パス'):
    # UNC shares such as \\server\images$ are filenames, not display labels.
    return literal(value,allow_expansion=True,field=field)


def macro_path_supported(value):
    """Accept static macro filenames, including UNC administrative shares."""
    if not value.strip() or any(ord(c)<32 or c=='"' for c in value):return False
    if '$' not in value:return True
    # The share's trailing $ is part of its name; retain expansion expressions
    # in hand-written CALL/source instead of converting them to a static path.
    return bool(re.fullmatch(r'//[^/$]+/[^/$]+\$(?:/[^$]+)+',value.replace('\\','/')))


@dataclass
class Gadget:
    kind: str = 'button'
    name: str = 'button1'
    label: str = 'Run'
    comment: str = ''
    x: float = 2
    y: float = 1
    width: float = 14
    height: float = 1
    value_type: str = 'STRING'
    initial: str = ''
    items: list[str] = field(default_factory=list)
    item_commands: list[str] = field(default_factory=list)
    callback: str = ''
    command: str = ''
    background: str = ''
    orientation: str = 'HORIZ'
    frame_style: str = 'FRAME'
    parent: str = ''
    body: str = ''
    layout_mode: str = 'ABSOLUTE'
    path_axes: str = ''
    path_row_step: bool = False
    frame_at: bool = False
    frame_size_axes: str = ''
    path: str = 'DOWN'
    halign: str = 'LEFT'
    valign: str = 'TOP'
    hgap: float = 1
    vgap: float = .5
    xref: str = ''
    yref: str = ''
    xedge: str = 'XMIN'
    yedge: str = 'YMAX'
    xanchor: str = 'LEFT'
    xoffset: float = 0
    yoffset: float = .5
    width_ref: str = ''
    item_values: list[str] = field(default_factory=list)
    selection_mode: str = 'SINGLE'
    combo_keyword: str = 'COMBO'
    combo_scroll: str = '20'
    combo_tagwid: str = ''
    option_style: str = 'PAIRS'
    option_width_explicit: bool = False
    slider_orientation: str = 'HORIZONTAL'
    slider_min: float = 0
    slider_max: float = 100
    slider_step: float = 1
    slider_value: float = 50
    off_value: str = ''
    on_value: str = 'ON'
    view_type: str = 'VOLUME'
    view_aspect: str = ''
    channels: str = 'BOTH'
    view_code: str = ''
    assembly: str = ''
    namespace: str = ''
    control_type: str = ''
    list_mode: str = 'SIMPLE'
    table_method: str = ''
    headings: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    display_mode: str = 'TEXT'
    pixmap_path: str = ''
    popup_menu: str = ''
    fixed_font: bool = True
    pane_lines: list[str] = field(default_factory=list)
    database: str = 'OWNERS'
    button_role: str = 'NORMAL'
    action_mode: str = 'CODE'
    macro_path: str = ''
    macro_flag: str = ''
    macro_value: str = ''
    tabs: list['Gadget'] = field(default_factory=list, repr=False)
    callback_expression: str = ''
    hidden: bool = False

    def __post_init__(self):
        if self.selection_mode == 'MULTI': self.selection_mode = 'MULTIPLE'
        normalize_dimensions(self)


@dataclass
class MenuItem:
    label: str = 'Item'
    command: str = ''


@dataclass
class Menu:
    name: str = 'menu1'
    items: list[MenuItem] = field(default_factory=list)
    popup: bool = False
    label: str | None = None
    on_bar: bool = True

    @property
    def display_label(self):
        return self.name if self.label is None else self.label


@dataclass
class Method:
    name: str
    signature: str = '()'
    body: str = ''


@dataclass
class Form:
    name: str = 'userform'
    title: str = 'User Form'
    dock_right: bool = False
    show_form: bool = True
    after_show_code: str = ''
    default_body: str = ''
    width: float = 70
    height: float = 22
    gadgets: list[Gadget] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    menus: list[Menu] = field(default_factory=list)
    form_type: str = 'DIALOG'
    initcall: str = ''
    okcall: str = ''
    cancelcall: str = ''
    dock_side: str = ''  # Empty preserves legacy dock_right projects.
    preamble_code: str = ''
    constructor_body: str = ''
    constructor_mode: str = 'GENERATED'
    extra_methods: list[Method] = field(default_factory=list)
    auto_default: bool = True
    keep_default: bool = False
    default_mode: str = 'GENERATED'
    source_mac_path: str = ''
    program_mode: str = 'GENERATED'
    partial_import_source: str = ''
    partial_import_notes: list[str] = field(default_factory=list)
    local_variables: dict[str, str] = field(default_factory=dict)
    form_prefix: str = '!!'
    size_explicit: bool = True

    @property
    def symbol(self):
        return self.form_prefix+self.name

    def docking_side(self):
        return self.dock_side or ('RIGHT' if self.dock_right else 'NONE')

    def parent_gadget(self, gadget):
        return next((g for g in self.gadgets if g.name.lower() == gadget.parent.lower()), None) if gadget.parent else None

    def __post_init__(self):
        # Materialize tab pages for the existing PML/reference/geometry engine.
        # Persistence keeps those pages inside their owning TABSET.
        pending=list(self.gadgets)
        while pending:
            owner=pending.pop(0)
            if not isinstance(owner,Gadget):continue
            if not isinstance(owner.tabs,list):raise ValueError('タブ情報は配列で指定してください。')
            for page in owner.tabs:
                if not isinstance(page,Gadget) or owner.kind!='frame' or owner.frame_style!='TABSET' or page.kind!='frame' or page.frame_style!='FRAME':
                    raise ValueError('タブ情報は TABSET 内の通常 FRAME で指定してください。')
                if page.parent and page.parent.lower()!=owner.name.lower():raise ValueError('タブの親が TABSET と一致しません。')
                page.parent=owner.name
                if not any(g is page for g in self.gadgets):self.gadgets.append(page);pending.append(page)
        self.sync_tabs()

    def is_tab_page(self,gadget):
        parent=self.parent_gadget(gadget)
        return bool(parent and parent.kind=='frame' and parent.frame_style=='TABSET')

    def sync_tabs(self):
        for g in self.gadgets:
            if isinstance(g,Gadget):g.tabs=self.children(g.name) if g.kind=='frame' and g.frame_style=='TABSET' else []
        done=set()
        def fit_auto_tabs(g,trail=()):
            if g.name.lower() in trail:raise ValueError('親コンテナの循環を解消してください。')
            if g.name.lower() in done:return
            for child in self.children(g.name):
                if child.kind=='frame':fit_auto_tabs(child,(*trail,g.name.lower()))
            if g.frame_style=='TABSET' and type(g.width) in (int,float) and g.width==0:
                widths=[1]
                for page in self.children(g.name):
                    widths.append(page.width)
                    for child in self.children(page.name):
                        x,_,width,_=self.geometry(child);widths.append(x+width+1)
                g.width=max(widths)
            done.add(g.name.lower())
        for g in self.gadgets:
            if isinstance(g,Gadget) and g.kind=='frame' and g.frame_style=='TABSET' and type(g.width) in (int,float) and g.width==0:fit_auto_tabs(g)
        for g in self.gadgets:
            if isinstance(g,Gadget) and self.is_tab_page(g) and type(g.width) in (int,float) and g.width==0:
                g.width=self.geometry(self.parent_gadget(g))[2]

    def named(self, name):
        return next((g for g in self.gadgets if g.name.lower() == name.lower()), None)

    def previous(self, gadget):
        siblings = self.children(gadget.parent)
        index = next(i for i,g in enumerate(siblings) if g is gadget)
        return siblings[index-1] if index else None

    def layout_dependencies(self, gadget,*,reveal=False):
        names = [gadget.width_ref] if gadget.width_ref and (not gadget.hidden or reveal) else []
        if gadget.layout_mode == 'RELATIVE': names += [gadget.xref, gadget.yref]
        if gadget.layout_mode == 'AUTO':
            previous = self.previous(gadget)
            if not previous and not gadget.path_axes: raise ValueError(f'{gadget.name}: 自動配置の前に基準部品を配置してください。')
            if previous:names.append(previous.name)
        result = []
        for name in names:
            target = self.named(name)
            if not target or target.parent.lower() != gadget.parent.lower():
                raise ValueError(f'{gadget.name}: 配置参照は同じ親の部品を指定してください。')
            if target is gadget: raise ValueError('自身を配置参照に指定できません。')
            if target not in result: result.append(target)
        return result

    def ordered_children(self, parent):
        result, visiting, done = [], set(), set()
        def visit(g):
            key = g.name.lower()
            if key in visiting: raise ValueError('配置・幅の循環参照を解消してください。')
            if key in done: return
            visiting.add(key)
            for dependency in self.layout_dependencies(g): visit(dependency)
            visiting.remove(key); done.add(key); result.append(g)
        for g in self.children(parent): visit(g)
        for index, gadget in enumerate(result):
            if gadget.layout_mode == 'AUTO' and self.previous(gadget) is not None and (index == 0 or result[index-1] is not self.previous(gadget)):
                raise ValueError(f'{gadget.name}: 自動配置の直前に基準部品が来るよう部品順と参照を変更してください。')
        return result

    def geometry(self, gadget, trail=None,*,reveal=False):
        trail = set() if trail is None else set(trail)
        key = gadget.name.lower()
        if key in trail: raise ValueError('配置・幅の循環参照を解消してください。')
        trail.add(key)
        parent = self.parent_gadget(gadget)
        if parent and parent.frame_style=='TABSET':
            _,_,width,height=self.geometry(parent,trail,reveal=reveal)
            return 0,0,width,height
        dependencies = {g.name.lower(): self.geometry(g, trail,reveal=reveal) for g in self.layout_dependencies(gadget,reveal=reveal)}
        width,height = display_size(gadget,reveal=reveal)
        if gadget.width_ref and (not gadget.hidden or reveal) and 'width' not in fixed_dimensions(gadget): width = dependencies[gadget.width_ref.lower()][2]
        x, y = gadget.x, gadget.y
        parent = self.parent_gadget(gadget)
        if parent and parent.frame_style == 'TOOLBAR':
            siblings = self.children(parent.name)
            index = next(i for i,g in enumerate(siblings) if g is gadget)
            return 1+sum(display_size(g,reveal=reveal)[0]+1 for g in siblings[:index]),1,width,height
        if gadget.layout_mode == 'RELATIVE':
            xr, yr = dependencies[gadget.xref.lower()], dependencies[gadget.yref.lower()]
            x = xr[0] + (xr[2] if gadget.xedge == 'XMAX' else 0) + gadget.xoffset
            if gadget.xanchor == 'RIGHT': x -= width
            y = yr[1] + (yr[3] if gadget.yedge == 'YMAX' else 0) + gadget.yoffset
        elif gadget.layout_mode == 'AUTO' and self.previous(gadget) is not None:
            previous=self.previous(gadget);prev = dependencies[previous.name.lower()]
            original_x,original_y=x,y
            if gadget.path in ('DOWN', 'UP'):
                x = prev[0] + {'LEFT': 0, 'CENTRE': (prev[2]-width)/2, 'RIGHT': prev[2]-width}[gadget.halign]
                step=prev[3]+gadget.vgap if gadget.path=='DOWN' else height+gadget.vgap
                if gadget.path_row_step:step=prev[3]+1 if gadget.path=='DOWN' and previous.kind=='frame' else 1
                y=prev[1]+step if gadget.path=='DOWN' else prev[1]-step
            else:
                x = prev[0]+prev[2]+gadget.hgap if gadget.path == 'RIGHT' else prev[0]-width-gadget.hgap
                y = prev[1] + {'TOP': 0, 'CENTRE': (prev[3]-height)/2, 'BOTTOM': prev[3]-height}[gadget.valign]
            if gadget.path_axes and 'X' not in gadget.path_axes:x=original_x
            if gadget.path_axes and 'Y' not in gadget.path_axes:y=original_y
        return x, y, width, height

    def change_layout(self,gadget,mode):
        if mode==gadget.layout_mode:return
        x,y,_,_=self.geometry(gadget)
        gadget.layout_mode=mode
        if mode=='ABSOLUTE':
            gadget.x,gadget.y=x,y;gadget.path_axes='';gadget.xref=gadget.yref=''
            if gadget.kind=='frame':gadget.frame_at=True
        elif mode=='AUTO':
            gadget.path_axes='XY';gadget.xref=gadget.yref=''
            if self.previous(gadget) is None:gadget.x=gadget.y=0

    def is_hidden(self,gadget):
        if gadget.hidden:return True
        if supports_hidden(gadget) and gadget.width_ref:
            try:return self.geometry(gadget)[2]==0
            except ValueError:return False
        return False

    def restored_size(self,gadget):
        hidden=self.is_hidden(gadget)
        try:return self.geometry(gadget,reveal=hidden)[2:]
        except ValueError:
            if not hidden:raise
            # A suspended width reference can be missing or cyclic while hidden.
            return display_size(gadget,reveal=True)

    def display_width(self,gadget):
        if self.is_hidden(gadget):return 0
        if gadget.width_ref:
            try:return native_size(gadget,*self.geometry(gadget)[2:])[0]
            except ValueError:pass
        return gadget.width

    def rotate_gadget(self,gadget,direction):
        key='orientation' if gadget.kind=='line' else 'slider_orientation'
        if gadget.kind not in ('line','slider') or getattr(gadget,key)==direction:return
        hidden=self.is_hidden(gadget)
        change_orientation(gadget,direction,self.restored_size(gadget))
        gadget.hidden=hidden

    def offset(self, gadget):
        x = y = 0
        seen = {gadget.name.lower()}
        current = self.parent_gadget(gadget)
        while current is not None and current.name.lower() not in seen:
            seen.add(current.name.lower()); gx, gy, _, _ = self.geometry(current); x += gx; y += gy
            current = self.parent_gadget(current)
        return x, y

    def children(self, name):
        return [g for g in self.gadgets if g.parent.lower() == name.lower()]

    def fit_size(self):
        """Estimate an unsized form from top-level extents, not 70x22."""
        extents=[self.geometry(g) for g in self.children('')]
        self.width=max([1,*[x+width+1 for x,y,width,height in extents]])
        self.height=max([1,*[y+height+1 for x,y,width,height in extents]])

    def descendants(self, name):
        result, pending = [], [name.lower()]
        while pending:
            key = pending.pop()
            for g in self.children(key):
                if g.name.lower() not in {n.lower() for n in result}:
                    result.append(g.name); pending.append(g.name.lower())
        return result

    def validate(self):
        names, callbacks, callback_signatures = set(), {}, {}
        if not isinstance(self.menus,list) or any(not isinstance(menu,Menu) for menu in self.menus):
            raise ValueError('メニューは配列で指定してください。')
        for menu in self.menus:
            if not isinstance(menu.popup,bool): raise ValueError('メニューの POPUP は真偽値で指定してください。')
            if not isinstance(menu.on_bar,bool):raise ValueError('BARへの登録設定は真偽値で指定してください。')
            if menu.label is not None and not isinstance(menu.label,str):raise ValueError('メニューのタイトル表示名は文字列で指定してください。')
            if not isinstance(menu.name,str) or not IDENTIFIER.fullmatch(menu.name):
                raise ValueError('メニュー名は英字で始まる英数字・_ にしてください。')
            literal(menu.display_label,field=f'{menu.name}: メニューのタイトル表示名')
            if menu.name.lower() in names:
                raise ValueError('メニュー名が重複しています。')
            names.add(menu.name.lower())
            if not isinstance(menu.items,list) or any(not isinstance(item,MenuItem) for item in menu.items):
                raise ValueError('メニュー項目は配列で指定してください。')
            for item in menu.items:
                if not isinstance(item.label,str) or not isinstance(item.command,str):
                    raise ValueError('メニュー項目の表示名・コマンドは文字列で指定してください。')
                literal(item.label,field=f'{menu.name}: メニュー項目の表示名')
                literal(item.command,allow_expansion=True,field=f'{menu.name}: メニュー項目のコマンド')
        if any(not menu.popup and menu.on_bar for menu in self.menus):
            if 'bar' in names:raise ValueError('BARはメニューバー用の名前です。メニュー名には別の名前を指定してください。')
            names.add('bar')
        for key in ('name', 'title', 'after_show_code', 'default_body','form_type','initcall','okcall','cancelcall','dock_side','preamble_code','constructor_body','source_mac_path'):
            if not isinstance(getattr(self, key), str): raise ValueError(f'{key} は文字列で指定してください。')
        if not isinstance(self.auto_default,bool):raise ValueError('DEFAULTの自動呼び出し設定は真偽値にしてください。')
        if not isinstance(self.size_explicit,bool):raise ValueError('フォームのサイズ指定設定は真偽値にしてください。')
        if not isinstance(self.keep_default,bool):raise ValueError('取り込んだDEFAULTの保持設定は真偽値にしてください。')
        if self.default_mode not in ('GENERATED','SOURCE'):raise ValueError('DEFAULTの生成形式が不正です。')
        if self.program_mode not in ('GENERATED','SOURCE'):raise ValueError('表示プログラムの生成形式が不正です。')
        if not isinstance(self.partial_import_source,str) or '\x00' in self.partial_import_source:
            raise ValueError('部分取り込みの原文が不正です。')
        if not isinstance(self.partial_import_notes,list) or any(not isinstance(note,str) for note in self.partial_import_notes):
            raise ValueError('部分取り込みの記録は文字列の配列にしてください。')
        if self.constructor_mode not in ('GENERATED','SOURCE'):raise ValueError('コンストラクタの生成形式が不正です。')
        if '\x00' in self.source_mac_path:raise ValueError('取り込み元のパスにNULを使用できません。')
        if not isinstance(self.extra_methods,list) or any(not isinstance(method,Method) for method in self.extra_methods):
            raise ValueError('追加メソッドの形式が不正です。')
        if any(not isinstance(values, dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in values.items())
               for values in (self.variables,self.local_variables)):
            raise ValueError('変数は名前と初期値の文字列を指定してください。')
        if not isinstance(self.gadgets, list) or any(not isinstance(g,Gadget) for g in self.gadgets):
            raise ValueError('部品は配列で指定してください。')
        for g in self.gadgets:
            if not isinstance(g.option_width_explicit,bool):raise ValueError('OPTIONの幅指定設定は真偽値にしてください。')
            if g.frame_size_axes not in ('','W','H','WH'):raise ValueError('FRAMEの寸法指定が不正です。')
            if g.path_axes not in ('','X','Y','XY') or not isinstance(g.path_row_step,bool) or not isinstance(g.frame_at,bool):raise ValueError('PATHの座標軸・縦移動の設定が不正です。')
            if not isinstance(g.hidden,bool):raise ValueError('非表示は真偽値で指定してください。')
            if g.hidden and not supports_hidden(g):raise ValueError(f'{g.name}: この部品はWIDTH 0による非表示に対応していません。')
            for key in ('kind','name','label','value_type','initial','callback','command','background','orientation','frame_style','parent','body','layout_mode','path','halign','valign','xref','yref','xedge','yedge','xanchor','width_ref','selection_mode','combo_keyword','combo_scroll','combo_tagwid','option_style','slider_orientation','off_value','on_value','view_type','channels','view_code','assembly','namespace','control_type','list_mode','table_method','display_mode','pixmap_path','popup_menu','database','button_role','action_mode','macro_path','macro_flag','macro_value','comment'):
                if not isinstance(getattr(g,key),str): raise ValueError(f'部品の {key} は文字列で指定してください。')
            for key in ('items','item_commands','item_values','headings','pane_lines'):
                value = getattr(g,key)
                if not isinstance(value,list) or any(not isinstance(item,str) for item in value):
                    raise ValueError(f'{key} は文字列の配列で指定してください。')
            if not isinstance(g.rows,list) or any(not isinstance(row,list) or any(not isinstance(cell,str) for cell in row) for row in g.rows):
                raise ValueError('LIST の行データは文字列の二次元配列で指定してください。')
            if g.list_mode not in ('SIMPLE','TABLE'):
                raise ValueError('LIST の表示方式は SIMPLE / TABLE を指定してください。')
            if g.list_mode == 'TABLE' and g.kind != 'list':
                raise ValueError('TABLE 表示方式は LIST 用です。')
            for column,value in enumerate(g.headings,1):literal(value,field=f'{g.name}: 見出し{column}')
            for index,row in enumerate(g.rows,1):
                for column,value in enumerate(row,1):literal(value,field=f'{g.name}: リスト{index}行{column}列')
            if g.kind == 'list' and g.list_mode == 'TABLE':
                if not g.headings or any(len(row)!=len(g.headings) for row in g.rows):
                    raise ValueError('複数列 LIST は見出しを設定し、各行の列数を見出しと揃えてください。')
            for key in ('x','y','width','height','hgap','vgap','xoffset','yoffset','slider_min','slider_max','slider_step','slider_value'):
                value = getattr(g,key)
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    raise ValueError('座標とサイズには有限数を指定してください。')
        if not SYMBOL_NAME.fullmatch(self.name) or not isinstance(self.form_prefix,str) or not re.fullmatch(r'[!.]*',self.form_prefix):
            raise ValueError('フォーム名は !!名前 / !名前 / .名前 / _名前 / 名前 で指定してください。')
        if self.form_type not in ('DIALOG','MAIN'): raise ValueError('フォーム形式は DIALOG / MAIN を指定してください。')
        for event in ('initcall','okcall','cancelcall'):
            literal(getattr(self,event),allow_expansion=True,field=f'{self.symbol}: {event}')
        if not isinstance(self.show_form, bool) or not isinstance(self.after_show_code, str):
            raise ValueError('表示後プログラムの形式が不正です。')
        if self.dock_side not in ('','NONE','LEFT','RIGHT','TOP','BOTTOM'):
            raise ValueError('ドッキング方向は NONE / LEFT / RIGHT / TOP / BOTTOM を指定してください。')
        if not isinstance(self.dock_right, bool): raise ValueError('ドッキング設定が不正です。')
        if not isinstance(self.default_body,str): raise ValueError('DEFAULT 処理は文字列で指定してください。')
        if self.name.lower() == 'default': raise ValueError('フォーム名 DEFAULT は DEFAULT メソッドと重複します。')
        literal(self.title,field=f'{self.symbol}: フォームの表示名')
        variable_names = set()
        for name, value in self.variables.items():
            if not SYMBOL_NAME.fullmatch(name) or name.lower() in variable_names or ('!!'+name).lower() == self.symbol.lower():
                raise ValueError('変数名が不正、重複、またはフォーム名と同じです。')
            variable_names.add(name.lower())
            literal(value,field=f'!!{name}: 変数の初期値')
        local_names=set()
        for name,value in self.local_variables.items():
            if not SYMBOL_NAME.fullmatch(name) or name.lower()=='this' or name.lower() in local_names or ('!'+name).lower()==self.symbol.lower():
                raise ValueError('ローカル変数名が不正、重複、またはフォーム名と同じです。')
            local_names.add(name.lower())
            literal(value,field=f'!{name}: 変数の初期値')
        if not self.size_explicit:self.fit_size()
        for value in (self.width, self.height):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 300:
                raise ValueError('フォームサイズは 1〜300 の有限数にしてください。')
        if len(self.gadgets) > 500:
            raise ValueError('部品数は 500 個までです。')
        for g in self.gadgets:
            if not isinstance(g.callback_expression,str):
                raise ValueError('取り込んだCALLの文字列が不正です。')
            literal(g.callback_expression,allow_expansion=True,field=f'{g.name}: 取り込んだCALL')
            if g.layout_mode not in ('ABSOLUTE','AUTO','RELATIVE') or g.path not in ('DOWN','UP','LEFT','RIGHT') or g.halign not in ('LEFT','CENTRE','RIGHT') or g.valign not in ('TOP','CENTRE','BOTTOM') or g.xedge not in ('XMIN','XMAX') or g.yedge not in ('YMIN','YMAX') or g.xanchor not in ('LEFT','RIGHT'):
                raise ValueError('配置方式・整列・参照辺の指定が不正です。')
            if g.hgap < 0 or g.vgap < 0: raise ValueError('配置間隔は0以上で指定してください。')
            if g.width_ref and g.kind in ('toggle','option','rtoggle'):
                raise ValueError('TOGGLE / OPTION / RTOGGLE の幅参照は未対応です。')
            if g.width_ref and 'width' in fixed_dimensions(g):
                raise ValueError(f'{g.name}: 太さが固定の部品には幅参照を指定できません。')
            self.layout_dependencies(g)
            parent = self.parent_gadget(g)
            if g.frame_style == 'TOOLBAR' and (g.kind != 'frame' or self.form_type != 'MAIN' or parent):
                raise ValueError('TOOLBAR は MAIN フォーム直下の FRAME として作成してください。')
            toolbar_kinds = ('button','toggle','option','text','combo','slider')
            if parent and parent.frame_style == 'TOOLBAR' and g.kind not in toolbar_kinds:
                raise ValueError('TOOLBAR に追加できる部品は BUTTON / TOGGLE / OPTION / TEXT / COMBO / SLIDER です。')
            if parent and parent.frame_style == 'TOOLBAR' and (g.layout_mode != 'ABSOLUTE' or g.width_ref):
                raise ValueError('TOOLBAR 内は部品一覧の順で配置します。相対配置・自動配置・幅参照は解除してください。')
            if self.form_type == 'MAIN' and not parent and not (g.kind == 'frame' and g.frame_style == 'TOOLBAR') and g.kind not in toolbar_kinds:
                raise ValueError('MAIN フォームには TOOLBAR またはツールバー対応部品を配置してください。')
            if g.parent and (parent is None or parent.kind != 'frame'):
                raise ValueError(f'{g.name}: 親は存在する FRAME / TABSET を指定してください。')
            if parent and parent.frame_style == 'TABSET' and (g.kind != 'frame' or g.frame_style != 'FRAME'):
                raise ValueError('TABSET の直下には通常の FRAME を作成してください。')
            seen = {g.name.lower()}; ancestor = parent
            while ancestor is not None:
                if ancestor.name.lower() in seen: raise ValueError('親コンテナの循環を解消してください。')
                seen.add(ancestor.name.lower()); ancestor = self.parent_gadget(ancestor)
            if g.kind not in KINDS or not (re.fullmatch(r'_?[A-Za-z][A-Za-z0-9_]*',g.name) if g.kind == 'option' else IDENTIFIER.fullmatch(g.name)):
                raise ValueError('部品の種類または名前が不正です。')
            effective_name = ('_' + g.name.lstrip('_') if uses_pairs(g) else g.name).lower()
            if effective_name in names:
                raise ValueError(f'部品名が重複しています: {g.name}')
            names.add(effective_name)
            for value in (g.x, g.y, g.width, g.height):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError('座標とサイズには有限数を指定してください。')
            x, y, width, height = self.geometry(g)
            parent_width = self.geometry(parent)[2] if parent else self.width
            parent_height = self.geometry(parent)[3] if parent else self.height
            min_width,min_height = (1/CHAR_WIDTH,1/LINE_HEIGHT) if g.display_mode == 'PIXMAP' else (1,1)
            fixed=fixed_dimensions(g)
            if 'width' in fixed and fixed['width']==0:min_width=0
            if 'height' in fixed and fixed['height']==0:min_height=0
            if self.is_hidden(g):min_width=0
            if g.width < (0 if fixed.get('width')==0 else 1) or g.height < (0 if fixed.get('height')==0 else 1) or width < min_width or height < min_height or x + width > parent_width + .001 or y + height > parent_height + .001:
                raise ValueError(f'{g.name}: 部品を親コンテナ内に収めてください。')
            if g.background:
                if g.kind not in ('paragraph', 'button', 'list') or not re.fullmatch(r'[0-9]+', g.background):
                    raise ValueError('BACKGROUND は PARAGRAPH / BUTTON / LIST の非負整数カラー番号を指定してください。')
            if g.frame_style not in ('FRAME', 'TABSET','TOOLBAR'):
                raise ValueError('FRAME 形式は FRAME / TABSET / TOOLBAR を指定してください。')
            if g.frame_style == 'TABSET' and g.kind != 'frame':
                raise ValueError('TABSET は FRAME の形式です。')
            if g.orientation not in ('HORIZ', 'VERT'):
                raise ValueError('LINE の向きは HORIZ / VERT を指定してください。')
            if g.kind == 'line' and g.label:
                raise ValueError('LINE の表示文字は空欄にしてください。')
            literal(g.label,field=f'{g.name}: 表示名')
            if not isinstance(g.fixed_font,bool): raise ValueError('等幅フォント設定は真偽値で指定してください。')
            if g.display_mode not in ('TEXT','PIXMAP'): raise ValueError('表示方式は TEXT / PIXMAP を指定してください。')
            if g.option_style not in ('PAIRS','GADGET'):raise ValueError('OPTIONの宣言形式が不正です。')
            if g.display_mode == 'PIXMAP':
                if g.kind not in ('paragraph','button','toggle','option'): raise ValueError('PIXMAP は PARAGRAPH / BUTTON / TOGGLE / OPTION 用です。')
                if g.kind == 'option' and not IDENTIFIER.fullmatch(g.name): raise ValueError('画像 OPTION の部品名は英字で始めてください。')
            image_path_literal(g.pixmap_path,field=f'{g.name}: 画像パス')
            for index,value in enumerate(g.pane_lines,1):literal(value,field=f'{g.name}: 複数行テキスト{index}行')
            if g.database not in ('OWNERS','MEMBERS','AUTO'): raise ValueError('DATABASE は OWNERS / MEMBERS / AUTO を指定してください。')
            if g.button_role not in ('NORMAL','OK','APPLY','CANCEL','RESET','HELP'): raise ValueError('ボタン属性が不正です。')
            if g.button_role != 'NORMAL' and g.kind != 'button': raise ValueError('ボタン属性は BUTTON 用です。')
            if g.button_role in ('OK','CANCEL','HELP') and (g.callback or g.command): raise ValueError('OK / CANCEL / HELP ボタンの処理はフォームのコールバックに設定してください。')
            if g.popup_menu:
                if g.kind not in ('view','commandline','list','button','toggle','text','combo','slider'): raise ValueError('この部品のポップアップ設定は未対応です。')
                if not any(menu.popup and menu.name.lower() == g.popup_menu.lower() for menu in self.menus): raise ValueError('ポップアップ先には POPUP メニューを指定してください。')
            if g.value_type not in ('STRING', 'REAL'):
                raise ValueError('テキスト型は STRING / REAL を指定してください。')
            if g.kind == 'text' and g.initial:
                if g.value_type == 'REAL':
                    try:
                        if not math.isfinite(float(g.initial)): raise ValueError()
                    except ValueError:
                        raise ValueError(f'{g.name}: REAL の初期値は有限数にしてください。') from None
                else:
                    literal(g.initial,field=f'{g.name}: 初期値')
            if g.kind == 'combo' and g.combo_tagwid and (not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',g.combo_tagwid) or not math.isfinite(float(g.combo_tagwid))):
                raise ValueError('COMBO の TAGWID は0以上の数値、または空欄にしてください。')
            if g.kind == 'combo' and g.combo_scroll and (not re.fullmatch(r'[0-9]+',g.combo_scroll) or int(g.combo_scroll)<1):
                raise ValueError('COMBO の SCROLL は正の整数、または空欄にしてください。')
            if g.selection_mode not in ('SINGLE','MULTIPLE','MULTI') or g.combo_keyword not in ('COMBO','COMBOBOX'):
                raise ValueError('選択方式・コンボ定義キーワードが不正です。')
            if g.slider_orientation not in ('HORIZONTAL','VERTICAL'):
                raise ValueError('SLIDER の向きが不正です。')
            if g.kind == 'slider' and (g.slider_min >= g.slider_max or g.slider_step <= 0 or not g.slider_min <= g.slider_value <= g.slider_max):
                raise ValueError('SLIDER は最小値 < 最大値、刻み > 0、初期値は範囲内にしてください。')
            if g.kind == 'rtoggle':
                if not parent or parent.frame_style != 'FRAME':
                    raise ValueError('RTOGGLE は通常 FRAME 内に配置してください。')
                literal(g.off_value,field=f'{g.name}: OFF値');literal(g.on_value,field=f'{g.name}: ON値')
            if g.view_type not in ('ALPHA','AREA','PLOT','VOLUME') or g.channels not in ('NONE','REQUESTS','COMMANDS','BOTH'):
                raise ValueError('VIEW の形式・チャンネルが不正です。')
            if not isinstance(g.view_aspect,str):
                raise ValueError('VIEW の ASPECT は数値を文字列で指定してください。')
            if g.view_aspect:
                if g.kind not in ('view','commandline'):
                    raise ValueError('ASPECT は VIEW 用です。')
                try:
                    aspect = float(g.view_aspect)
                    if not math.isfinite(aspect) or aspect <= 0: raise ValueError()
                except ValueError:
                    raise ValueError('ASPECT は0より大きい有限数を指定してください。') from None
            if g.kind == 'container':
                settings = (g.assembly,g.namespace,g.control_type)
                if any(settings) and not all(settings):
                    raise ValueError('CONTAINER のアセンブリ・名前空間・型はすべて指定してください。')
                if all(settings):
                    literal(g.assembly,field=f'{g.name}: アセンブリ')
                    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*',g.namespace) or not IDENTIFIER.fullmatch(g.control_type):
                        raise ValueError('CONTAINER の名前空間・型名が不正です。')
                    member = (g.name+'Control').lower()
                    if member in {other.name.lower() for other in self.gadgets} or member in {other.callback.lower() for other in self.gadgets} or member in {menu.name.lower() for menu in self.menus}:
                        raise ValueError('CONTAINER の生成メンバー名が部品名・メソッド名と重複します。')
            for index,item in enumerate(g.items,1):
                image=g.kind=='option' and g.display_mode=='PIXMAP'
                (image_path_literal if image else literal)(item,field=f'{g.name}: 選択肢{index}'+('の画像パス' if image else 'の表示名'))
            for index,item in enumerate(g.item_values,1):literal(item,field=f'{g.name}: 選択肢{index}の実値')
            if g.item_values:
                if g.kind not in ('list','combo','option') or len(g.item_values) != len(g.items):
                    raise ValueError('LIST / COMBO / 画像 OPTION の表示項目と実値の行数を揃えてください。')
            if g.kind == 'option' and g.display_mode == 'TEXT':
                if g.item_values and g.item_commands:raise ValueError('OPTION の実値とコマンドはどちらか一方を指定してください。')
                if g.item_commands and len(g.item_commands) != len(g.items):
                    raise ValueError('OPTION の選択肢とコマンドの行数を揃えてください。')
                for index,command in enumerate(g.item_commands,1):literal(command,allow_expansion=True,field=f'{g.name}: 選択肢{index}のコマンド')
            if g.command:
                if g.kind not in ('toggle', 'text', 'button') and not (g.kind=='option' and g.display_mode=='TEXT' and not uses_pairs(g)): raise ValueError('この部品にはCALLコマンドを指定できません。')
                literal(g.command,allow_expansion=True,field=f'{g.name}: CALLコマンド')
                if g.callback: raise ValueError('メソッド名と CALL コマンドはどちらか一方だけ指定してください。')
            if g.callback:
                if g.kind in ('paragraph', 'line', 'frame', 'rtoggle', 'view', 'commandline', 'container','textpane') or uses_pairs(g):
                    raise ValueError('ラベル・LINE・FRAME・OPTION にはメソッド型コールバックを指定できません。')
                if not IDENTIFIER.fullmatch(g.callback) or g.callback.lower() == self.name.lower():
                    raise ValueError('メソッド名が不正、またはコンストラクタと重複しています。')
                key = g.callback.lower()
                signature = 'OPEN' if g.kind in ('slider','combo') else 'NORMAL'
                if key in callback_signatures and callback_signatures[key] != signature:
                    raise ValueError('SLIDER / COMBO のイベントメソッド名は引数なしの部品と分けてください。')
                if signature == 'OPEN' and key == 'default':
                    raise ValueError('SLIDER / COMBO のイベントメソッドには DEFAULT 以外を指定してください。')
                callback_signatures[key] = signature
                if key in callbacks and callbacks[key] != g.body:
                    raise ValueError('同じメソッド名には同じ処理を指定してください。')
                if key == 'default' and self.default_body and g.body and self.default_body != g.body:
                    raise ValueError('DEFAULT の処理は DEFAULT 欄にまとめてください。')
                callbacks[key] = g.body
        methods = {self.name.lower(),'default',*callbacks}
        for g in self.gadgets:
            if '\x00' in g.comment:raise ValueError('部品コメントに NUL は使用できません。')
            if g.action_mode not in ('CODE','MACRO'):raise ValueError('ボタンの処理方式が不正です。')
            if g.action_mode != 'MACRO':continue
            if g.kind != 'button' or g.button_role not in ('NORMAL','APPLY','RESET'):
                raise ValueError('外部マクロは通常 / APPLY / RESET ボタンで設定してください。')
            if g.callback or g.command:raise ValueError('外部マクロと手入力の CALL は同時に設定できません。')
            if not macro_path_supported(g.macro_path):
                raise ValueError(f'{g.name}: マクロファイルのパスを指定してください。制御文字・二重引用符は使用できません。'
                                 '$はUNC共有名の末尾（//server/share$/file.mac）で使用できます。'
                                 'その他の$を含む呼び出しはCALLコマンドに入力してください。')
            if g.macro_flag:
                if not IDENTIFIER.fullmatch(g.macro_flag) or g.macro_flag.lower() not in {name.lower() for name in self.variables}:
                    raise ValueError(f'{g.name}: フラグには登録済みのグローバル変数名を指定してください。')
                literal(g.macro_value,field=f'{g.name}: マクロのフラグ値')
            method='macro_'+g.name
            if method.lower() in methods:raise ValueError('外部マクロの生成メソッド名が重複しています。')
            methods.add(method.lower())
        for g in self.gadgets:
            if g.kind == 'list' and g.list_mode == 'TABLE':
                method = g.table_method or f'populate_{g.name}'
                if not IDENTIFIER.fullmatch(method) or method.lower() in methods:
                    raise ValueError('複数列 LIST のメソッド名が不正、または他のメソッドと重複しています。')
                methods.add(method.lower())
        for method in self.extra_methods:
            if not isinstance(method.name,str) or not IDENTIFIER.fullmatch(method.name) or method.name.lower() in methods:
                raise ValueError('追加メソッド名が不正、または他のメソッドと重複しています。')
            if not isinstance(method.signature,str) or not re.fullmatch(r'\([^()\r\n]*\)(?:\s+IS\s+[A-Za-z][A-Za-z0-9_.]*)?',method.signature,re.I) or not isinstance(method.body,str):
                raise ValueError('追加メソッドの引数・本文の形式が不正です。')
            methods.add(method.name.lower())
        self.initial_lines()
        self.sync_tabs()

    def dumps(self):
        self.validate()
        raw=asdict(self)
        raw['gadgets']=[value for g,value in zip(self.gadgets,raw['gadgets']) if not self.is_tab_page(g)]
        return json.dumps({'version': 2, 'form': raw, 'gadget_order':[g.name for g in self.gadgets]}, ensure_ascii=False, indent=2)

    @classmethod
    def loads(cls, text):
        try:
            data = json.loads(text)
            if data['version'] not in (1,2): raise ValueError('未対応の設計ファイルです。')
            raw = dict(data['form'])
            if data['version']==1:raw.setdefault('dock_right',True)
            def read_gadget(value):
                record=dict(value)
                tabs=record.get('tabs',[])
                if not isinstance(tabs,list):raise ValueError('タブ情報は配列で指定してください。')
                record['tabs']=[read_gadget(page) for page in tabs]
                return Gadget(**record)
            raw['gadgets'] = [read_gadget(g) for g in raw['gadgets']]
            menus = []
            for value in raw.get('menus',[]):
                menu = dict(value)
                menu['items'] = [MenuItem(**item) for item in menu['items']]
                menus.append(Menu(**menu))
            raw['menus'] = menus
            raw['extra_methods'] = [Method(**method) for method in raw.get('extra_methods',[])]
            result = cls(**raw)
            if 'gadget_order' in data:
                order=data['gadget_order']
                if not isinstance(order,list) or any(not isinstance(name,str) for name in order) or len(order)!=len(result.gadgets) or len(set(order))!=len(order) or set(order)!={g.name for g in result.gadgets}:
                    raise ValueError('部品順の情報が不正です。')
                by_name={g.name:g for g in result.gadgets};result.gadgets=[by_name[name] for name in order]
            result.validate()
            return result
        except (KeyError, TypeError, AttributeError) as e:
            raise ValueError('設計ファイルの形式が不正です。') from e

    def initial_lines(self):
        """Validated initial values emitted only in DEFAULT, after choices are ready."""
        if self.default_mode=='SOURCE':return []
        lines=[];radio_groups=set()
        for g in self.gadgets:
            target='_'+g.name.lstrip('_') if uses_pairs(g) else g.name
            if g.kind == 'slider':
                lines.append(f'  !this.{g.name}.val = {format(g.slider_value,".8g")}')
            elif g.kind == 'textpane':
                lines.append('  !paneLines = ARRAY()')
                for i,value in enumerate(g.pane_lines,1):lines.append(f'  !paneLines[{i}] = {literal(value)}')
                lines.append(f'  !this.{g.name}.val = !paneLines')
            elif g.initial and g.kind in ('text','paragraph','toggle','rtoggle','option','combo','list'):
                if g.kind == 'paragraph' and g.display_mode == 'PIXMAP':continue
                if g.kind in ('toggle','rtoggle'):
                    value=g.initial.upper()
                    if value not in ('TRUE','FALSE'):raise ValueError(f'{g.name}: 初期値は TRUE / FALSE にしてください。')
                    if g.kind == 'rtoggle':
                        parent=self.parent_gadget(g)
                        if parent.name.lower() not in radio_groups:
                            lines.append(f'  !this.{parent.name}.val = 0');radio_groups.add(parent.name.lower())
                        if value == 'TRUE':
                            siblings=[item for item in self.ordered_children(g.parent) if item.kind == 'rtoggle']
                            if sum(item.initial.upper() == 'TRUE' for item in siblings)>1:raise ValueError(f'{parent.name}: ラジオの初期選択は1つにしてください。')
                            lines.append(f'  !this.{parent.name}.val = {siblings.index(g)+1}')
                        continue
                elif g.kind in ('option','combo','list'):
                    multiple=g.kind == 'list' and g.selection_mode == 'MULTIPLE'
                    parts=g.initial.split(',')
                    if not all(re.fullmatch(r'[0-9]+',part.strip()) for part in parts) or (not multiple and len(parts)!=1):
                        raise ValueError(f'{g.name}: 初期選択は行番号を指定してください。')
                    indices=[int(part.strip()) for part in parts]
                    length=len(g.rows) if g.kind == 'list' and g.list_mode == 'TABLE' else len(g.items)
                    if any(index<1 or index>length for index in indices) or len(set(indices))!=len(indices):
                        raise ValueError(f'{g.name}: 初期選択の行番号が範囲外または重複しています。')
                    if multiple:
                        lines.append('  !initialSelection = ARRAY()')
                        for i,index in enumerate(indices,1):lines.append(f'  !initialSelection[{i}] = {index}')
                        value='!initialSelection'
                    else:value=str(indices[0])
                else:value=format(float(g.initial),'.8g') if g.kind == 'text' and g.value_type == 'REAL' else literal(g.initial)
                lines.append(f'  !this.{target}.val = {value}')
        return lines

    def pml(self, normalize=True):
        self.validate()
        from .method_output import empty_method_names,prune_empty_calls,validate_omitted_references
        initial_lines = self.initial_lines()
        default_code = self.default_body or next((g.body for g in self.gadgets if g.callback.lower() == 'default' and g.body), '')
        empty_methods=empty_method_names(self,initial_lines,default_code)
        protected = {}
        code_fragments = []
        def user_code(value):
            value=prune_empty_calls(value,self,empty_methods)
            code_fragments.append(value)
            if not normalize:return value
            import uuid
            marker = '__user_code_'+uuid.uuid4().hex+'__'
            protected[marker]=value
            return marker
        def command_code(value):
            value=prune_empty_calls(value,self,empty_methods)
            code_fragments.append(value)
            return value if has_code(value) else ''
        active_methods = {g.callback.lower() for g in self.gadgets if g.callback and g.callback.lower() not in empty_methods}
        if 'default' not in empty_methods:active_methods.add('default')
        def active_callback(g):return bool(g.callback and g.callback.lower() in active_methods)
        def callback_expression(g):
            if g.callback_expression and re.fullmatch(r'\s*!this\.'+re.escape(g.callback)+r'\s*\(\s*\)\s*',g.callback_expression,re.I):
                return g.callback_expression
            return f'!this.{g.callback}()'
        form_symbol=user_code(self.symbol)
        n = lambda v: format(v, '.8g')
        lines = [f'VAR !!{name} {literal(value)}' for name, value in self.variables.items()]
        lines.extend(f'VAR !{name} {literal(value)}' for name,value in self.local_variables.items())
        if lines:lines.append('')
        if self.preamble_code.strip():lines.extend([user_code(self.preamble_code).rstrip('\n'),''])
        lines += [f'kill {form_symbol}', '',
                 (f'setup form {form_symbol} MAIN' if self.form_type == 'MAIN' else f'setup form {form_symbol} DIALOG DOCK {self.docking_side()}' if self.docking_side() != 'NONE'
                  else f'setup form {form_symbol}'+(f' size {n(self.width)} {n(self.height)}' if self.size_explicit else '')+' DIALOG'),
                 f'  title {literal(self.title)}']
        bar_menus=[menu for menu in self.menus if not menu.popup and menu.on_bar]
        if bar_menus:
            lines.append('  bar')
            lines.extend(f'    add {literal(menu.display_label)} .{menu.name}' for menu in bar_menus)
        for menu in self.menus:
            lines.append(f'  menu .{menu.name}'+(' POPUP' if menu.popup else ''))
            if not menu.popup:
                for item in menu.items:
                    lines.append(f'    add {literal(item.label)} {literal(command_code(item.command),allow_expansion=True)}')
            lines.append('  exit')
        for g in self.gadgets:
            if g.kind == 'container' and g.assembly:
                lines += [f'  import {literal(g.assembly)}', f"  using namespace '{g.namespace}'",
                          f'  member .{g.name}Control is {g.control_type}']
        def member_name(name):
            target=self.named(name)
            return '_'+name.lstrip('_') if uses_pairs(target) else name
        # VDIST stays active for later declarations in the same container.
        # Never drop it to imply the default row step: that changes geometry.
        vdist_scopes=set()
        def render(g, depth):
            indent = '  '*depth
            for comment in g.comment.splitlines():lines.append(indent+'-- '+comment)
            position = f'AT X {n(g.x)} Y {n(g.y)}'
            if g.layout_mode == 'RELATIVE':
                delta = lambda value: ('+' if value > 0 else '') + n(value) if value else ''
                right = '-SIZE' if g.xanchor == 'RIGHT' else ''
                position = f'AT {g.xedge}.{member_name(g.xref)}{right}{delta(g.xoffset)} {g.yedge}.{member_name(g.yref)}{delta(g.yoffset)}'
            elif g.layout_mode == 'AUTO':
                if g.path_row_step and g.parent.lower() in vdist_scopes:
                    raise ValueError(f'{g.name}: 同じコンテナ内でVDIST指定後に1行PATHへ戻す設定は再出力できません。「縦移動：1行ずつ」を外して縦間隔を指定するか、座標指定に変更してください。')
                if not g.path_row_step:vdist_scopes.add(g.parent.lower())
                commands=[f'PATH {g.path}',f'HDIST {n(g.hgap)}',f'HALIGN {g.halign}',f'VALIGN {g.valign}']
                if not g.path_row_step:commands.insert(2,f'VDIST {n(g.vgap)}')
                for command in commands:
                    lines.append(indent+command)
                previous = self.previous(g)
                if previous:lines.append(indent+f'-- Auto placement follows {previous.name}')
                position = f'AT Y {n(g.y)}' if g.path_axes=='X' else f'AT X {n(g.x)}' if g.path_axes=='Y' else ''
            width,height = (g.width,g.height) if g.display_mode == 'PIXMAP' else display_size(g)
            if g.hidden:width=0
            width_clause = f'WIDTH.{member_name(g.width_ref)}' if g.width_ref and not g.hidden else f'WIDTH {n(width)}'
            at = (f'at x{n(g.x)} y{n(g.y)}' if g.layout_mode == 'ABSOLUTE' else position) + ' ' + width_clause
            callback = ' callback '+literal(callback_expression(g),allow_expansion=True) if active_callback(g) else ''
            label = literal(g.label)
            parent = self.parent_gadget(g)
            if parent and parent.frame_style == 'TOOLBAR': position = ''
            if g.kind == 'frame':
                if g.frame_style == 'TOOLBAR':
                    line = f'FRAME .{g.name} TOOLBAR {label}'
                elif g.frame_style == 'TABSET':
                    line = f'FRAME .{g.name} TABSET {position} {label} {width_clause}'
                else:
                    line = f'FRAME .{g.name} {label}'
                    if g.layout_mode != 'ABSOLUTE' or g.frame_at or ((g.x<0 or g.y<0) and not self.is_tab_page(g)): line += ' '+position
                if g.frame_style != 'TABSET' and (g.width_ref or 'W' in g.frame_size_axes):line += ' '+width_clause
                if 'H' in g.frame_size_axes:line += f' HEIGHT {n(g.height)}'
            elif g.kind == 'line':
                line = f"LINE .{g.name} {position} '' {g.orientation} {width_clause} HEIGHT {n(height)}"
            elif g.kind == 'paragraph':
                line = f'PARAGRAPH .{g.name} {position}'
                if g.background: line += f' BACKGROUND {int(g.background)}'
                if g.display_mode == 'PIXMAP' and g.pixmap_path:
                    # Supply the file at declaration time, avoiding an empty-file lookup.
                    line += f' PIXMAP {image_path_literal(g.pixmap_path)} {width_clause} HEIGHT {n(g.height)}'
                elif g.display_mode == 'PIXMAP':
                    line += f" TEXT '' WIDTH {n(display_size(g)[0])}"
                else:
                    line += f' TEXT {label} {width_clause}'
            elif g.kind == 'text':
                line = f'TEXT .{g.name} {position} {label}'
                command = f'!this.macro_{g.name}()' if g.action_mode == 'MACRO' else command_code(g.command) or (callback_expression(g) if active_callback(g) else '')
                if command: line += ' CALL ' + literal(command, allow_expansion=True)
                line += f' {width_clause} IS {g.value_type}'
            elif g.kind == 'option':
                if g.display_mode == 'PIXMAP':
                    line = f'OPTION .{g.name} {position} {label} PIXMAP {width_clause} HEIGHT {n(g.height)}'+callback
                elif not uses_pairs(g):
                    line = f'OPTION .{g.name} {position} {label} {width_clause}'
                    command=command_code(g.command) or (callback_expression(g) if active_callback(g) else '')
                    if command:line += ' CALL '+literal(command,allow_expansion=True)
                else:
                    object_name = '_' + g.name.lstrip('_')
                    line = f"OPTION {object_name} {position} {label}"
                    if not g.item_values:
                        line += f" CALL '$${object_name}'"
                    if g.option_width_explicit:line += ' '+width_clause
                    if not g.item_values:
                        line += f'\n  VAR LIST {object_name} PAIRS'
                        commands = g.item_commands or [''] * len(g.items)
                        for display, command in zip(g.items, commands):
                            line += '\n  ' + literal(display) + ' ' + literal(command_code(command), allow_expansion=True)
                        line += '\nEXIT'
            elif g.kind == 'list':
                selection = 'MULTIPLE' if g.selection_mode == 'MULTI' else g.selection_mode
                background = f'BACKGROUND {int(g.background)} ' if g.background else ''
                line = f'list .{g.name} {background}{position} {label} {selection} {width_clause} HEIGHT {n(g.height)}' + callback
            elif g.kind == 'combo':
                tagwid = f'TAGWID {g.combo_tagwid} ' if g.combo_tagwid else ''
                scroll = f'SCROLL {g.combo_scroll} ' if g.combo_scroll else ''
                line = f'{g.combo_keyword} .{g.name} {tagwid}{label} {position} {scroll}{width_clause}'
            elif g.kind == 'textpane':
                line = f'TEXTPANE .{g.name} {label}'+(' FIXCHARS' if g.fixed_font else '')+f' {position} {width_clause} HEIGHT {n(g.height)}'
            elif g.kind == 'selector':
                line = f'SELECTOR .{g.name} {position} {label} {g.selection_mode} {width_clause} HEIGHT {n(g.height)} DATABASE {g.database}'+callback
            elif g.kind == 'slider':
                line = (f'SLIDER .{g.name} {position} {g.slider_orientation} RANGE {n(g.slider_min)} {n(g.slider_max)} '
                        f'STEP {n(g.slider_step)} VAL {n(g.slider_value)} {width_clause}')
                if g.slider_orientation == 'VERTICAL': line += f' HEIGHT {n(height)}'
            elif g.kind == 'rtoggle':
                line = f'RTOGGLE .{g.name} {label} {position} STATES {literal(g.off_value)} {literal(g.on_value)}'
            elif g.kind in ('view','commandline'):
                view_type = 'ALPHA' if g.kind == 'commandline' else g.view_type
                line = f'VIEW .{g.name} {position} {view_type}\n  {width_clause} HEIGHT {n(g.height)}'
                if g.view_aspect: line += f' ASPECT {n(float(g.view_aspect))}'
                if view_type == 'ALPHA':
                    for channel in ('REQUESTS','COMMANDS'):
                        if g.channels in (channel,'BOTH'): line += '\n  CHANNEL '+channel
                if g.view_code: line += '\n'+user_code('\n'.join('  '+row for row in g.view_code.split('\n')))
                line += '\nEXIT'
            elif g.kind == 'container':
                line = f'CONTAINER .{g.name} {position} PMLNETCONTROL {width_clause} HEIGHT {n(g.height)}'
                if not g.assembly: line += '\n-- Set Control handle in DEFAULT or configure assembly / namespace / type'
            elif g.kind == 'button':
                line = f'BUTTON .{g.name} {position}'
                if g.background: line += f' BACKGROUND {int(g.background)}'
                line += ' PIXMAP' if g.display_mode == 'PIXMAP' else f' {label}'
                if g.button_role != 'NORMAL': line += ' '+g.button_role
                command = f'!this.macro_{g.name}()' if g.action_mode == 'MACRO' else command_code(g.command) or (callback_expression(g) if active_callback(g) else '')
                if command: line += ' CALL ' + literal(command, allow_expansion=True)
                line += f' {width_clause}'
                if g.display_mode == 'PIXMAP': line += f' HEIGHT {n(g.height)}'
            elif g.kind == 'toggle':
                line = f'TOGGLE .{g.name} {position}'+(f' PIXMAP {width_clause} HEIGHT {n(g.height)}' if g.display_mode == 'PIXMAP' else f' {label}')
                command = f'!this.macro_{g.name}()' if g.action_mode == 'MACRO' else command_code(g.command) or (callback_expression(g) if active_callback(g) else '')
                if command: line += ' CALL ' + literal(command, allow_expansion=True)
            else:
                line = f'{g.kind} .{g.name} {label} {at}' + callback
            lines.extend('  ' * depth + part for part in line.split('\n'))
            if g.kind == 'frame':
                for child in self.ordered_children(g.name): render(child, depth + 1)
                lines.append('  ' * depth + 'EXIT')
        for g in self.ordered_children(''): render(g, 1)
        lines.extend(['exit', ''])
        if self.program_mode=='GENERATED':lines += [f'SHOW {form_symbol}', '']
        if self.after_show_code: lines += [user_code(self.after_show_code), '']
        method_start = len(lines)
        method_offsets = [method_start]
        lines.append(f'define method .{self.name}()')
        constructor_start = len(lines)
        constructor_fragments_start = len(code_fragments)
        for menu in self.menus:
            if menu.popup:
                for item in menu.items:
                    lines.append(f"  !this.{menu.name}.Add('CALLBACK', {literal(item.label)}, {literal(command_code(item.command),allow_expansion=True)})")
        for event in ('initcall','okcall','cancelcall'):
            value = command_code(getattr(self,event))
            if value: lines.append(f'  !this.{event} = {literal(value,allow_expansion=True)}')
        for g in self.gadgets:
            if g.display_mode == 'PIXMAP' and g.kind in ('button','toggle') and g.pixmap_path:
                lines.append(f'  !this.{g.name}.AddPixmap({image_path_literal(g.pixmap_path)})')
            if g.popup_menu: lines.append(f'  !this.{g.name}.SetPopup(!this.{g.popup_menu})')
            if g.kind == 'list' and g.list_mode == 'TABLE':
                lines.append(f'  !this.{g.table_method or "populate_"+g.name}()')
            if g.kind in ('slider','combo') and active_callback(g):
                lines.append(f"  !this.{g.name}.callback = '!this.{g.callback}('")
            if g.kind == 'container' and g.assembly:
                lines += [f'  !this.{g.name}Control = object {g.control_type}()',
                          f'  !this.{g.name}.Control = !this.{g.name}Control.handle()']
            if (g.kind in ('list','combo') or (g.kind == 'option' and (not uses_pairs(g) or g.item_values))) and g.items and not (g.kind == 'list' and g.list_mode == 'TABLE'):
                lines.append('  !choices = object ARRAY()')
                for i, item in enumerate(g.items, 1):
                    value=image_path_literal(item) if g.kind=='option' and g.display_mode=='PIXMAP' else literal(item)
                    lines.append(f'  !choices[{i}] = {value}')
                target = '_'+g.name.lstrip('_') if uses_pairs(g) else g.name
                lines.append(f'  !this.{target}.dtext = !choices')
                if g.item_values:
                    lines.append('  !values = object ARRAY()')
                    for i, value in enumerate(g.item_values,1): lines.append(f'  !values[{i}] = {literal(value)}')
                    lines.append(f'  !this.{target}.rtext = !values')
        if self.constructor_mode == 'SOURCE':
            del lines[constructor_start:]
            del code_fragments[constructor_fragments_start:]
        if self.constructor_body:lines.append(user_code(self.constructor_body))
        if initial_lines and self.auto_default and self.constructor_mode == 'GENERATED': lines.append('  !this.DEFAULT()')
        lines.extend(['endmethod', ''])
        for g in self.gadgets:
            if g.kind != 'list' or g.list_mode != 'TABLE': continue
            method_offsets.append(len(lines))
            lines += [f'define method .{g.table_method or "populate_"+g.name}()', '  !HEAD = ARRAY()']
            for column, heading in enumerate(g.headings,1): lines.append(f'  !HEAD[{column}] = {literal(heading)}')
            lines += [f'  !THIS.{g.name}.setheadings(!HEAD)', '  !ROWS = ARRAY()']
            for row, cells in enumerate(g.rows,1):
                lines.append(f'  !ROWS[{row}] = ARRAY()')
                for column, cell in enumerate(cells,1): lines.append(f'  !ROWS[{row}][{column}] = {literal(cell)}')
            lines += [f'  !THIS.{g.name}.setrows(!ROWS)', 'endmethod', '']
        if 'default' in active_methods:
            method_offsets.append(len(lines))
            lines += ['DEFINE METHOD .DEFAULT()', *initial_lines, *([user_code(default_code)] if has_code(default_code) else []), 'ENDMETHOD', '']
        for g in self.gadgets:
            if g.action_mode == 'MACRO':
                method_offsets.append(len(lines))
                lines += [f'define method .macro_{g.name}()']
                if g.macro_flag:lines.append(f'  !!{g.macro_flag} = {literal(g.macro_value)}')
                lines += [f'  $M "{g.macro_path.replace(chr(92), chr(47))}"', 'endmethod', '']
        seen = {'default'}
        for g in self.gadgets:
            if active_callback(g) and g.callback.lower() not in seen:
                seen.add(g.callback.lower())
                signature = '(!gad is GADGET, !event is STRING)' if g.kind in ('slider','combo') else '()'
                method_offsets.append(len(lines))
                lines += [f'define method .{g.callback}{signature}', user_code(g.body), 'endmethod', '']
        for method in self.extra_methods:
            if method.name.lower() in empty_methods:continue
            method_offsets.append(len(lines))
            lines += [f'define method .{method.name} '+user_code(method.signature),user_code(method.body),'endmethod','']
        from .method_order import order_methods
        ends = method_offsets[1:] + [len(lines)]
        blocks = [lines[start:end] for start,end in zip(method_offsets,ends)]
        def nonempty(block):
            body='\n'.join(block[1:-2])
            for marker,value in protected.items():body=body.replace(marker,value)
            return has_code(body)
        blocks=[block for block in blocks[1:]+blocks[:1] if nonempty(block)]
        blocks = order_methods(blocks,self,protected)
        emitted={re.match(r'define\s+method\s+\.([A-Za-z_][A-Za-z0-9_]*)',block[0],re.I).group(1).lower()
                 for block in blocks}
        validate_omitted_references(self,(empty_methods|{self.name.lower()})-emitted,code_fragments)
        lines = lines[:method_start] + [line for block in blocks for line in block]
        from .formatting import canonical_pml
        text='\n'.join(lines)
        if normalize:text=canonical_pml(text,external_types={g.control_type for g in self.gadgets if g.kind=='container' and g.assembly})
        for marker,value in protected.items():text=text.replace(marker,value)
        return text
