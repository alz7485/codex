from dataclasses import dataclass, field, asdict
import json
import math
import re
from .pml_syntax import has_code

KINDS = ('button', 'paragraph', 'text', 'toggle', 'option', 'list', 'line', 'frame', 'slider', 'rtoggle', 'combo', 'view', 'commandline', 'container', 'textpane', 'selector')
IDENTIFIER = re.compile(r'[A-Za-z][A-Za-z0-9_]*\Z')
CHAR_WIDTH, LINE_HEIGHT = 10, 26


def uses_pairs(gadget):
    return gadget.kind == 'option' and gadget.display_mode == 'TEXT' and gadget.option_style == 'PAIRS'


def fixed_dimensions(gadget):
    if gadget.display_mode == 'PIXMAP':return {}
    if gadget.kind in ('text','paragraph','toggle','option','combo'):return {'height':1}
    if gadget.kind == 'line':
        return {'width':1} if gadget.orientation == 'VERT' else {'height':1}
    if gadget.kind == 'slider':
        return {'width':3} if gadget.slider_orientation == 'VERTICAL' else {'height':1}
    return {}


def dimension_editable(gadget, dimension):
    return gadget.display_mode != 'PIXMAP' and dimension not in fixed_dimensions(gadget) and not (dimension == 'width' and gadget.width_ref)


def normalize_dimensions(gadget):
    before = gadget.width,gadget.height,gadget.width_ref
    fixed = fixed_dimensions(gadget)
    for key,value in fixed.items():
        current = getattr(gadget,key)
        if type(current) in (int,float) and math.isfinite(current) and current > 0:
            setattr(gadget,key,value)
    if 'width' in fixed:gadget.width_ref = ''
    return before != (gadget.width,gadget.height,gadget.width_ref)


def change_orientation(gadget, direction, resolved_size=None):
    key = 'orientation' if gadget.kind == 'line' else 'slider_orientation'
    if gadget.kind not in ('line','slider') or getattr(gadget,key) == direction:return
    width,height = resolved_size if resolved_size is not None else display_size(gadget)
    gadget.width,gadget.height = height,width
    gadget.width_ref = ''
    setattr(gadget,key,direction)
    normalize_dimensions(gadget)


def display_size(gadget):
    if gadget.display_mode == 'PIXMAP':
        return gadget.width/CHAR_WIDTH,gadget.height/LINE_HEIGHT
    fixed = fixed_dimensions(gadget)
    return fixed.get('width',gadget.width),fixed.get('height',gadget.height)


def native_size(gadget,width,height):
    return (width*CHAR_WIDTH,height*LINE_HEIGHT) if gadget.display_mode == 'PIXMAP' else (width,height)


def literal(value, allow_expansion=False, field='表示文字列'):
    # PML expands $ expressions even inside strings. Do not silently emit them.
    if any(c in value for c in '\r\n\x00') or ('$' in value and not allow_expansion):
        forbidden='改行・NUL' if allow_expansion else '改行・NUL・$'
        raise ValueError(f'{field}には{forbidden} を使用できません。')
    for delimiter in ("'", '|', '"'):
        if delimiter not in value:
            return delimiter + value + delimiter
    raise ValueError(f'{field}に全種類の引用符があります。引用符を減らしてください。')


def image_path_literal(value):
    # UNC shares such as \\server\images$ are filenames, not display labels.
    return literal(value,allow_expansion=True,field='画像パス')


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
    source_mac_path: str = ''

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

    def named(self, name):
        return next((g for g in self.gadgets if g.name.lower() == name.lower()), None)

    def previous(self, gadget):
        siblings = self.children(gadget.parent)
        index = next(i for i,g in enumerate(siblings) if g is gadget)
        return siblings[index-1] if index else None

    def layout_dependencies(self, gadget):
        names = [gadget.width_ref] if gadget.width_ref else []
        if gadget.layout_mode == 'RELATIVE': names += [gadget.xref, gadget.yref]
        if gadget.layout_mode == 'AUTO':
            previous = self.previous(gadget)
            if not previous: raise ValueError(f'{gadget.name}: 自動配置の前に基準部品を配置してください。')
            names.append(previous.name)
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
            if gadget.layout_mode == 'AUTO' and (index == 0 or result[index-1] is not self.previous(gadget)):
                raise ValueError(f'{gadget.name}: 自動配置の直前に基準部品が来るよう部品順と参照を変更してください。')
        return result

    def geometry(self, gadget, trail=None):
        trail = set() if trail is None else set(trail)
        key = gadget.name.lower()
        if key in trail: raise ValueError('配置・幅の循環参照を解消してください。')
        trail.add(key)
        parent = self.parent_gadget(gadget)
        if parent and parent.frame_style=='TABSET':
            _,_,width,height=self.geometry(parent,trail)
            return 0,0,width,height
        dependencies = {g.name.lower(): self.geometry(g, trail) for g in self.layout_dependencies(gadget)}
        width,height = display_size(gadget)
        if gadget.width_ref and 'width' not in fixed_dimensions(gadget): width = dependencies[gadget.width_ref.lower()][2]
        x, y = gadget.x, gadget.y
        parent = self.parent_gadget(gadget)
        if parent and parent.frame_style == 'TOOLBAR':
            siblings = self.children(parent.name)
            index = next(i for i,g in enumerate(siblings) if g is gadget)
            return 1+sum(display_size(g)[0]+1 for g in siblings[:index]),1,width,height
        if gadget.layout_mode == 'RELATIVE':
            xr, yr = dependencies[gadget.xref.lower()], dependencies[gadget.yref.lower()]
            x = xr[0] + (xr[2] if gadget.xedge == 'XMAX' else 0) + gadget.xoffset
            if gadget.xanchor == 'RIGHT': x -= width
            y = yr[1] + (yr[3] if gadget.yedge == 'YMAX' else 0) + gadget.yoffset
        elif gadget.layout_mode == 'AUTO':
            prev = dependencies[self.previous(gadget).name.lower()]
            if gadget.path in ('DOWN', 'UP'):
                x = prev[0] + {'LEFT': 0, 'CENTRE': (prev[2]-width)/2, 'RIGHT': prev[2]-width}[gadget.halign]
                y = prev[1]+prev[3]+gadget.vgap if gadget.path == 'DOWN' else prev[1]-height-gadget.vgap
            else:
                x = prev[0]+prev[2]+gadget.hgap if gadget.path == 'RIGHT' else prev[0]-width-gadget.hgap
                y = prev[1] + {'TOP': 0, 'CENTRE': (prev[3]-height)/2, 'BOTTOM': prev[3]-height}[gadget.valign]
        return x, y, width, height

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
            if not isinstance(menu.name,str) or not IDENTIFIER.fullmatch(menu.name):
                raise ValueError('メニュー名は英字で始まる英数字・_ にしてください。')
            if menu.name.lower() in names:
                raise ValueError('メニュー名が重複しています。')
            names.add(menu.name.lower())
            if not isinstance(menu.items,list) or any(not isinstance(item,MenuItem) for item in menu.items):
                raise ValueError('メニュー項目は配列で指定してください。')
            for item in menu.items:
                if not isinstance(item.label,str) or not isinstance(item.command,str):
                    raise ValueError('メニュー項目の表示名・コマンドは文字列で指定してください。')
                literal(item.label)
                literal(item.command,allow_expansion=True)
        for key in ('name', 'title', 'after_show_code', 'default_body','form_type','initcall','okcall','cancelcall','dock_side','preamble_code','constructor_body','source_mac_path'):
            if not isinstance(getattr(self, key), str): raise ValueError(f'{key} は文字列で指定してください。')
        if not isinstance(self.auto_default,bool):raise ValueError('DEFAULTの自動呼び出し設定は真偽値にしてください。')
        if self.constructor_mode not in ('GENERATED','SOURCE'):raise ValueError('コンストラクタの生成形式が不正です。')
        if '\x00' in self.source_mac_path:raise ValueError('取り込み元のパスにNULを使用できません。')
        if not isinstance(self.extra_methods,list) or any(not isinstance(method,Method) for method in self.extra_methods):
            raise ValueError('追加メソッドの形式が不正です。')
        if not isinstance(self.variables, dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in self.variables.items()):
            raise ValueError('変数は名前と初期値の文字列を指定してください。')
        if not isinstance(self.gadgets, list) or any(not isinstance(g,Gadget) for g in self.gadgets):
            raise ValueError('部品は配列で指定してください。')
        for g in self.gadgets:
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
            for value in g.headings: literal(value)
            for row in g.rows:
                for value in row: literal(value)
            if g.kind == 'list' and g.list_mode == 'TABLE':
                if not g.headings or any(len(row)!=len(g.headings) for row in g.rows):
                    raise ValueError('複数列 LIST は見出しを設定し、各行の列数を見出しと揃えてください。')
            for key in ('x','y','width','height','hgap','vgap','xoffset','yoffset','slider_min','slider_max','slider_step','slider_value'):
                value = getattr(g,key)
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    raise ValueError('座標とサイズには有限数を指定してください。')
        if not IDENTIFIER.fullmatch(self.name):
            raise ValueError('フォーム名は英字で始まる英数字・_ にしてください。')
        if self.form_type not in ('DIALOG','MAIN'): raise ValueError('フォーム形式は DIALOG / MAIN を指定してください。')
        for event in ('initcall','okcall','cancelcall'):
            literal(getattr(self,event),allow_expansion=True)
        if not isinstance(self.show_form, bool) or not isinstance(self.after_show_code, str):
            raise ValueError('表示後プログラムの形式が不正です。')
        if self.dock_side not in ('','NONE','LEFT','RIGHT','TOP','BOTTOM'):
            raise ValueError('ドッキング方向は NONE / LEFT / RIGHT / TOP / BOTTOM を指定してください。')
        if not isinstance(self.dock_right, bool): raise ValueError('ドッキング設定が不正です。')
        if not isinstance(self.default_body,str): raise ValueError('DEFAULT 処理は文字列で指定してください。')
        if self.name.lower() == 'default': raise ValueError('フォーム名 DEFAULT は DEFAULT メソッドと重複します。')
        literal(self.title)
        variable_names = set()
        for name, value in self.variables.items():
            if not IDENTIFIER.fullmatch(name) or name.lower() in variable_names or name.lower() == self.name.lower():
                raise ValueError('変数名が不正、重複、またはフォーム名と同じです。')
            variable_names.add(name.lower())
            literal(value)
        for value in (self.width, self.height):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 300:
                raise ValueError('フォームサイズは 1〜300 の有限数にしてください。')
        if len(self.gadgets) > 500:
            raise ValueError('部品数は 500 個までです。')
        for g in self.gadgets:
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
            if g.width < 1 or g.height < 1 or x < -.001 or y < -.001 or width < min_width or height < min_height or x + width > parent_width + .001 or y + height > parent_height + .001:
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
            literal(g.label)
            if not isinstance(g.fixed_font,bool): raise ValueError('等幅フォント設定は真偽値で指定してください。')
            if g.display_mode not in ('TEXT','PIXMAP'): raise ValueError('表示方式は TEXT / PIXMAP を指定してください。')
            if g.option_style not in ('PAIRS','GADGET'):raise ValueError('OPTIONの宣言形式が不正です。')
            if g.display_mode == 'PIXMAP':
                if g.kind not in ('paragraph','button','toggle','option'): raise ValueError('PIXMAP は PARAGRAPH / BUTTON / TOGGLE / OPTION 用です。')
                if g.kind == 'option' and not IDENTIFIER.fullmatch(g.name): raise ValueError('画像 OPTION の部品名は英字で始めてください。')
            image_path_literal(g.pixmap_path)
            for value in g.pane_lines: literal(value)
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
                    literal(g.initial)
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
                literal(g.off_value); literal(g.on_value)
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
                    literal(g.assembly)
                    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*',g.namespace) or not IDENTIFIER.fullmatch(g.control_type):
                        raise ValueError('CONTAINER の名前空間・型名が不正です。')
                    member = (g.name+'Control').lower()
                    if member in {other.name.lower() for other in self.gadgets} or member in {other.callback.lower() for other in self.gadgets} or member in {menu.name.lower() for menu in self.menus}:
                        raise ValueError('CONTAINER の生成メンバー名が部品名・メソッド名と重複します。')
            for item in g.items:
                (image_path_literal if g.kind=='option' and g.display_mode=='PIXMAP' else literal)(item)
            for item in g.item_values: literal(item)
            if g.item_values:
                if g.kind not in ('list','combo','option') or len(g.item_values) != len(g.items):
                    raise ValueError('LIST / COMBO / 画像 OPTION の表示項目と実値の行数を揃えてください。')
            if g.kind == 'option' and g.display_mode == 'TEXT':
                if g.item_values and g.item_commands:raise ValueError('OPTION の実値とコマンドはどちらか一方を指定してください。')
                if g.item_commands and len(g.item_commands) != len(g.items):
                    raise ValueError('OPTION の選択肢とコマンドの行数を揃えてください。')
                for command in g.item_commands: literal(command, allow_expansion=True)
            if g.command:
                if g.kind not in ('toggle', 'text', 'button') and not (g.kind=='option' and g.display_mode=='TEXT' and not uses_pairs(g)): raise ValueError('この部品にはCALLコマンドを指定できません。')
                literal(g.command, allow_expansion=True)
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
            if not g.macro_path.strip() or any(ord(c)<32 or c in '"$' for c in g.macro_path):
                raise ValueError(f'{g.name}: マクロファイルのパスを指定してください（制御文字・二重引用符・$ は使用できません）。')
            if g.macro_flag:
                if not IDENTIFIER.fullmatch(g.macro_flag) or g.macro_flag.lower() not in {name.lower() for name in self.variables}:
                    raise ValueError(f'{g.name}: フラグには登録済みのグローバル変数名を指定してください。')
                literal(g.macro_value)
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
        protected = {}
        def user_code(value):
            if not normalize:return value
            import uuid
            marker = '__user_code_'+uuid.uuid4().hex+'__'
            protected[marker]=value
            return marker
        initial_lines = self.initial_lines()
        default_code = self.default_body or next((g.body for g in self.gadgets if g.callback.lower() == 'default' and g.body), '')
        active_methods = {g.callback.lower() for g in self.gadgets if g.callback and has_code(g.body) and g.callback.lower() != 'default'}
        if initial_lines or has_code(default_code):active_methods.add('default')
        def active_callback(g):return bool(g.callback and g.callback.lower() in active_methods)
        n = lambda v: format(v, '.8g')
        lines = [f'VAR !!{name} {literal(value)}' for name, value in self.variables.items()]
        if self.preamble_code:lines.extend([user_code(self.preamble_code),''])
        lines += [f'kill !!{self.name}', '-- Generated by E3D PML Form Designer',
                 '-- Target: E3D 4.0 (runtime compatibility not yet verified)',
                 (f'setup form !!{self.name} MAIN' if self.form_type == 'MAIN' else f'setup form !!{self.name} DIALOG DOCK {self.docking_side()}' if self.docking_side() != 'NONE'
                  else f'setup form !!{self.name} size {n(self.width)} {n(self.height)} DIALOG'),
                 f'  title {literal(self.title)}']
        for menu in self.menus:
            lines.append(f'  menu .{menu.name}'+(' POPUP' if menu.popup else ''))
            if not menu.popup:
                for item in menu.items:
                    lines.append(f'    add {literal(item.label)} {literal(item.command,allow_expansion=True)}')
            lines.append('  exit')
        for g in self.gadgets:
            if g.kind == 'container' and g.assembly:
                lines += [f'  import {literal(g.assembly)}', f"  using namespace '{g.namespace}'",
                          f'  member .{g.name}Control is {g.control_type}']
        def render(g, depth):
            indent = '  '*depth
            for comment in g.comment.splitlines():lines.append(indent+'-- '+comment)
            position = f'AT X {n(g.x)} Y {n(g.y)}'
            if g.layout_mode == 'RELATIVE':
                delta = lambda value: ('+' if value > 0 else '') + n(value) if value else ''
                right = '-SIZE' if g.xanchor == 'RIGHT' else ''
                position = f'AT {g.xedge}.{g.xref}{right}{delta(g.xoffset)} {g.yedge}.{g.yref}{delta(g.yoffset)}'
            elif g.layout_mode == 'AUTO':
                for command in (f'PATH {g.path}',f'HDIST {n(g.hgap)}',f'VDIST {n(g.vgap)}',f'HALIGN {g.halign}',f'VALIGN {g.valign}'):
                    lines.append(indent+command)
                previous = self.previous(g)
                lines.append(indent+f'-- Auto placement follows {previous.name}')
                position = ''
            width,height = (g.width,g.height) if g.display_mode == 'PIXMAP' else display_size(g)
            width_clause = f'WIDTH.{g.width_ref}' if g.width_ref else f'WIDTH {n(width)}'
            at = (f'at x{n(g.x)} y{n(g.y)}' if g.layout_mode == 'ABSOLUTE' else position) + ' ' + width_clause
            callback = f" callback '!this.{g.callback}()'" if active_callback(g) else ''
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
                    if g.layout_mode != 'ABSOLUTE': line += ' '+position
                    if g.width_ref: line += ' '+width_clause
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
                command = f'!this.macro_{g.name}()' if g.action_mode == 'MACRO' else g.command or (f'!this.{g.callback}()' if active_callback(g) else '')
                if command: line += ' CALL ' + literal(command, allow_expansion=True)
                line += f' {width_clause} IS {g.value_type}'
            elif g.kind == 'option':
                if g.display_mode == 'PIXMAP':
                    line = f'OPTION .{g.name} {position} {label} PIXMAP {width_clause} HEIGHT {n(g.height)}'+callback
                elif not uses_pairs(g):
                    line = f'OPTION .{g.name} {position} {label} {width_clause}'
                    command=g.command or (f'!this.{g.callback}()' if active_callback(g) else '')
                    if command:line += ' CALL '+literal(command,allow_expansion=True)
                else:
                    object_name = '_' + g.name.lstrip('_')
                    line = f"OPTION {object_name} {position} {label}"
                    if not g.item_values:
                        line += f" CALL '$${object_name}'"
                        line += f'\nVAR LIST {object_name} PAIRS'
                        commands = g.item_commands or [''] * len(g.items)
                        for display, command in zip(g.items, commands):
                            line += '\n' + literal(display) + ' ' + literal(command, allow_expansion=True)
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
                command = f'!this.macro_{g.name}()' if g.action_mode == 'MACRO' else g.command or (f'!this.{g.callback}()' if active_callback(g) else '')
                if command: line += ' CALL ' + literal(command, allow_expansion=True)
                line += f' {width_clause}'
                if g.display_mode == 'PIXMAP': line += f' HEIGHT {n(g.height)}'
            elif g.kind == 'toggle':
                line = f'TOGGLE .{g.name} {position}'+(f' PIXMAP {width_clause} HEIGHT {n(g.height)}' if g.display_mode == 'PIXMAP' else f' {label}')
                command = f'!this.macro_{g.name}()' if g.action_mode == 'MACRO' else g.command or (f'!this.{g.callback}()' if active_callback(g) else '')
                if command: line += ' CALL ' + literal(command, allow_expansion=True)
            else:
                line = f'{g.kind} .{g.name} {label} {at}' + callback
            lines.extend('  ' * depth + part for part in line.split('\n'))
            if g.kind == 'frame':
                for child in self.ordered_children(g.name): render(child, depth + 1)
                lines.append('  ' * depth + 'EXIT')
        for g in self.ordered_children(''): render(g, 1)
        lines.extend(['exit', ''])
        lines += [f'SHOW !!{self.name}', '']
        if self.after_show_code: lines += [user_code(self.after_show_code), '']
        method_start = len(lines)
        method_offsets = [method_start]
        lines.append(f'define method .{self.name}()')
        constructor_start = len(lines)
        for menu in self.menus:
            if menu.popup:
                for item in menu.items:
                    lines.append(f"  !this.{menu.name}.Add('CALLBACK', {literal(item.label)}, {literal(item.command,allow_expansion=True)})")
        for event in ('initcall','okcall','cancelcall'):
            value = getattr(self,event)
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
        if self.constructor_mode == 'SOURCE':del lines[constructor_start:]
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
            method_offsets.append(len(lines))
            lines += [f'define method .{method.name} '+user_code(method.signature),user_code(method.body),'endmethod','']
        from .method_order import order_methods
        ends = method_offsets[1:] + [len(lines)]
        blocks = [lines[start:end] for start,end in zip(method_offsets,ends)]
        blocks = order_methods(blocks[1:]+blocks[:1],self.name,protected)
        lines = lines[:method_start] + [line for block in blocks for line in block]
        from .formatting import canonical_pml
        text='\n'.join(lines)
        if normalize:text=canonical_pml(text,external_types={g.control_type for g in self.gadgets if g.kind=='container' and g.assembly})
        for marker,value in protected.items():text=text.replace(marker,value)
        return text
