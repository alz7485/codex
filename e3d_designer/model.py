from dataclasses import dataclass, field, asdict
import json
import math
import re

KINDS = ('button', 'paragraph', 'text', 'toggle', 'option', 'list', 'line', 'frame', 'slider', 'rtoggle', 'combo', 'view', 'commandline', 'container')
IDENTIFIER = re.compile(r'[A-Za-z][A-Za-z0-9_]*\Z')


def literal(value, allow_expansion=False):
    # PML expands $ expressions even inside strings. Do not silently emit them.
    if any(c in value for c in '\r\n\x00') or ('$' in value and not allow_expansion):
        raise ValueError('表示文字列には改行・NUL・$ を使用できません。')
    for delimiter in ("'", '|', '"'):
        if delimiter not in value:
            return delimiter + value + delimiter
    raise ValueError('表示文字列に全種類の引用符があります。引用符を減らしてください。')


@dataclass
class Gadget:
    kind: str = 'button'
    name: str = 'button1'
    label: str = 'Run'
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
    slider_orientation: str = 'HORIZONTAL'
    slider_min: float = 0
    slider_max: float = 100
    slider_step: float = 1
    slider_value: float = 50
    off_value: str = ''
    on_value: str = 'ON'
    view_type: str = 'VOLUME'
    channels: str = 'BOTH'
    view_code: str = ''
    assembly: str = ''
    namespace: str = ''
    control_type: str = ''


@dataclass
class MenuItem:
    label: str = 'Item'
    command: str = ''


@dataclass
class Menu:
    name: str = 'menu1'
    items: list[MenuItem] = field(default_factory=list)


@dataclass
class Form:
    name: str = 'userform'
    title: str = 'User Form'
    dock_right: bool = True
    show_form: bool = True
    after_show_code: str = ''
    default_body: str = ''
    width: float = 70
    height: float = 22
    gadgets: list[Gadget] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    menus: list[Menu] = field(default_factory=list)

    def parent_gadget(self, gadget):
        return next((g for g in self.gadgets if g.name.lower() == gadget.parent.lower()), None) if gadget.parent else None

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
        dependencies = {g.name.lower(): self.geometry(g, trail) for g in self.layout_dependencies(gadget)}
        width = dependencies[gadget.width_ref.lower()][2] if gadget.width_ref else gadget.width
        height = gadget.height
        x, y = gadget.x, gadget.y
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
        for key in ('name', 'title', 'after_show_code', 'default_body'):
            if not isinstance(getattr(self, key), str): raise ValueError(f'{key} は文字列で指定してください。')
        if not isinstance(self.variables, dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in self.variables.items()):
            raise ValueError('変数は名前と初期値の文字列を指定してください。')
        if not isinstance(self.gadgets, list) or any(not isinstance(g,Gadget) for g in self.gadgets):
            raise ValueError('部品は配列で指定してください。')
        for g in self.gadgets:
            for key in ('kind','name','label','value_type','initial','callback','command','background','orientation','frame_style','parent','body','layout_mode','path','halign','valign','xref','yref','xedge','yedge','xanchor','width_ref','selection_mode','combo_keyword','slider_orientation','off_value','on_value','view_type','channels','view_code','assembly','namespace','control_type'):
                if not isinstance(getattr(g,key),str): raise ValueError(f'部品の {key} は文字列で指定してください。')
            for key in ('items','item_commands','item_values'):
                value = getattr(g,key)
                if not isinstance(value,list) or any(not isinstance(item,str) for item in value):
                    raise ValueError(f'{key} は文字列の配列で指定してください。')
            for key in ('x','y','width','height','hgap','vgap','xoffset','yoffset','slider_min','slider_max','slider_step','slider_value'):
                value = getattr(g,key)
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    raise ValueError('座標とサイズには有限数を指定してください。')
        if not IDENTIFIER.fullmatch(self.name):
            raise ValueError('フォーム名は英字で始まる英数字・_ にしてください。')
        if not isinstance(self.show_form, bool) or not isinstance(self.after_show_code, str):
            raise ValueError('表示後プログラムの形式が不正です。')
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
            self.layout_dependencies(g)
            parent = self.parent_gadget(g)
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
            effective_name = ('_' + g.name.lstrip('_') if g.kind == 'option' else g.name).lower()
            if effective_name in names:
                raise ValueError(f'部品名が重複しています: {g.name}')
            names.add(effective_name)
            for value in (g.x, g.y, g.width, g.height):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError('座標とサイズには有限数を指定してください。')
            x, y, width, height = self.geometry(g)
            parent_width = self.geometry(parent)[2] if parent else self.width
            parent_height = parent.height if parent else self.height
            if x < -.001 or y < -.001 or width < 1 or height < 1 or x + width > parent_width + .001 or y + height > parent_height + .001:
                raise ValueError(f'{g.name}: 部品を親コンテナ内に収めてください。')
            if g.background:
                if g.kind not in ('paragraph', 'button') or not re.fullmatch(r'[0-9]+', g.background):
                    raise ValueError('BACKGROUND は PARAGRAPH / BUTTON の非負整数カラー番号を指定してください。')
            if g.frame_style not in ('FRAME', 'TABSET'):
                raise ValueError('FRAME 形式は FRAME / TABSET を指定してください。')
            if g.frame_style == 'TABSET' and g.kind != 'frame':
                raise ValueError('TABSET は FRAME の形式です。')
            if g.orientation not in ('HORIZ', 'VERT'):
                raise ValueError('LINE の向きは HORIZ / VERT を指定してください。')
            if g.kind == 'line' and g.label:
                raise ValueError('LINE の表示文字は空欄にしてください。')
            literal(g.label)
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
            if g.selection_mode not in ('SINGLE','MULTI') or g.combo_keyword not in ('COMBO','COMBOBOX'):
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
            for item in g.items: literal(item)
            for item in g.item_values: literal(item)
            if g.item_values:
                if g.kind not in ('list','combo') or len(g.item_values) != len(g.items):
                    raise ValueError('LIST / COMBO の表示名と実値の行数を揃えてください。')
            if g.kind == 'option':
                if g.item_commands and len(g.item_commands) != len(g.items):
                    raise ValueError('OPTION の選択肢とコマンドの行数を揃えてください。')
                for command in g.item_commands: literal(command, allow_expansion=True)
            if g.command:
                if g.kind not in ('toggle', 'text', 'button'): raise ValueError('CALL コマンド欄は TOGGLE / TEXT / BUTTON 用です。')
                literal(g.command, allow_expansion=True)
                if g.callback: raise ValueError('メソッド名と CALL コマンドはどちらか一方だけ指定してください。')
            if g.callback:
                if g.kind in ('paragraph', 'line', 'frame', 'option', 'rtoggle', 'view', 'commandline', 'container'):
                    raise ValueError('ラベル・LINE・FRAME・OPTION にはメソッド型コールバックを指定できません。')
                if not IDENTIFIER.fullmatch(g.callback) or g.callback.lower() == self.name.lower():
                    raise ValueError('メソッド名が不正、またはコンストラクタと重複しています。')
                key = g.callback.lower()
                signature = 'OPEN' if g.kind == 'slider' else 'NORMAL'
                if key in callback_signatures and callback_signatures[key] != signature:
                    raise ValueError('SLIDER のイベントメソッド名は他の部品と分けてください。')
                if signature == 'OPEN' and key == 'default':
                    raise ValueError('SLIDER のイベントメソッドには DEFAULT 以外を指定してください。')
                callback_signatures[key] = signature
                if key in callbacks and callbacks[key] != g.body:
                    raise ValueError('同じメソッド名には同じ処理を指定してください。')
                if key == 'default' and self.default_body and g.body and self.default_body != g.body:
                    raise ValueError('DEFAULT の処理は DEFAULT 欄にまとめてください。')
                callbacks[key] = g.body

    def dumps(self):
        self.validate()
        return json.dumps({'version': 1, 'form': asdict(self)}, ensure_ascii=False, indent=2)

    @classmethod
    def loads(cls, text):
        try:
            data = json.loads(text)
            if data['version'] != 1: raise ValueError('未対応の設計ファイルです。')
            raw = dict(data['form'])
            raw['gadgets'] = [Gadget(**g) for g in raw['gadgets']]
            menus = []
            for value in raw.get('menus',[]):
                menu = dict(value)
                menu['items'] = [MenuItem(**item) for item in menu['items']]
                menus.append(Menu(**menu))
            raw['menus'] = menus
            result = cls(**raw)
            result.validate()
            return result
        except (KeyError, TypeError, AttributeError) as e:
            raise ValueError('設計ファイルの形式が不正です。') from e

    def pml(self):
        self.validate()
        n = lambda v: format(v, '.8g')
        lines = [f'VAR !!{name} {literal(value)}' for name, value in self.variables.items()]
        lines += [f'kill !!{self.name}', '-- Generated by E3D PML Form Designer',
                 '-- Target: E3D 4.0 (runtime compatibility not yet verified)',
                 (f'setup form !!{self.name} DIALOG DOCK RIGHT' if self.dock_right
                  else f'setup form !!{self.name} size {n(self.width)} {n(self.height)} DIALOG'),
                 f'  title {literal(self.title)}']
        for menu in self.menus:
            lines.append(f'  menu .{menu.name}')
            for item in menu.items:
                lines.append(f'    add {literal(item.label)} {literal(item.command,allow_expansion=True)}')
            lines.append('  exit')
        for g in self.gadgets:
            if g.kind == 'container' and g.assembly:
                lines += [f'  import {literal(g.assembly)}', f"  using namespace '{g.namespace}'",
                          f'  member .{g.name}Control is {g.control_type}']
        def render(g, depth):
            indent = '  '*depth
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
            width_clause = f'WIDTH.{g.width_ref}' if g.width_ref else f'WIDTH {n(g.width)}'
            at = (f'at x{n(g.x)} y{n(g.y)}' if g.layout_mode == 'ABSOLUTE' else position) + ' ' + width_clause
            callback = f" callback '!this.{g.callback}()'" if g.callback else ''
            label = literal(g.label)
            if g.kind == 'frame':
                if g.frame_style == 'TABSET':
                    line = f'FRAME .{g.name} TABSET {position} {label} {width_clause}'
                else:
                    line = f'FRAME .{g.name} {label}'
                    if g.layout_mode != 'ABSOLUTE': line += ' '+position
                    if g.width_ref: line += ' '+width_clause
            elif g.kind == 'line':
                line = f"LINE .{g.name} {position} '' {g.orientation} {width_clause} HEIGHT {n(g.height)}"
            elif g.kind == 'paragraph':
                line = f'PARAGRAPH .{g.name} {position}'
                if g.background: line += f' BACKGROUND {int(g.background)}'
                line += f' TEXT {label} {width_clause}'
            elif g.kind == 'text':
                line = f'TEXT .{g.name} {position} {label}'
                command = g.command or (f'!this.{g.callback}()' if g.callback else '')
                if command: line += ' CALL ' + literal(command, allow_expansion=True)
                line += f' {width_clause} IS {g.value_type}'
            elif g.kind == 'option':
                object_name = '_' + g.name.lstrip('_')
                line = f"OPTION {object_name} {position} {label} CALL '$${object_name}'"
                line += f'\nVAR LIST {object_name} PAIRS'
                commands = g.item_commands or [''] * len(g.items)
                for display, command in zip(g.items, commands):
                    line += '\n' + literal(display) + ' ' + literal(command, allow_expansion=True)
                line += '\nEXIT'
            elif g.kind == 'list':
                line = f'list .{g.name} {position} {label} {g.selection_mode} {width_clause} lines {max(1, round(g.height))}' + callback
            elif g.kind == 'combo':
                line = f'{g.combo_keyword} .{g.name} {label} {position} {width_clause}' + callback
            elif g.kind == 'slider':
                line = (f'SLIDER .{g.name} {position} {g.slider_orientation} RANGE {n(g.slider_min)} {n(g.slider_max)} '
                        f'STEP {n(g.slider_step)} VAL {n(g.slider_value)} {width_clause}')
                if g.slider_orientation == 'VERTICAL': line += f' HEIGHT {n(g.height)}'
            elif g.kind == 'rtoggle':
                line = f'RTOGGLE .{g.name} {label} {position} STATES {literal(g.off_value)} {literal(g.on_value)}'
            elif g.kind in ('view','commandline'):
                view_type = 'ALPHA' if g.kind == 'commandline' else g.view_type
                line = f'VIEW .{g.name} {position} {view_type}\n  {width_clause} HEIGHT {n(g.height)}'
                if view_type == 'ALPHA':
                    for channel in ('REQUESTS','COMMANDS'):
                        if g.channels in (channel,'BOTH'): line += '\n  CHANNEL '+channel
                if g.view_code: line += '\n'+'\n'.join('  '+row for row in g.view_code.split('\n'))
                line += '\nEXIT'
            elif g.kind == 'container':
                line = f'CONTAINER .{g.name} {position} PMLNETCONTROL {width_clause} HEIGHT {n(g.height)}'
                if not g.assembly: line += '\n-- Set Control handle in DEFAULT or configure assembly / namespace / type'
            elif g.kind == 'button':
                line = f'BUTTON .{g.name} {position}'
                if g.background: line += f' BACKGROUND {int(g.background)}'
                line += f' {label}'
                command = g.command or (f'!this.{g.callback}()' if g.callback else '')
                if command: line += ' CALL ' + literal(command, allow_expansion=True)
                line += f' {width_clause}'
            elif g.kind == 'toggle':
                line = f'TOGGLE .{g.name} {position} {label}'
                command = g.command or (f'!this.{g.callback}()' if g.callback else '')
                if command: line += ' CALL ' + literal(command, allow_expansion=True)
            else:
                line = f'{g.kind} .{g.name} {label} {at}' + callback
            lines.extend('  ' * depth + part for part in line.split('\n'))
            if g.kind == 'frame':
                for child in self.ordered_children(g.name): render(child, depth + 1)
                lines.append('  ' * depth + 'EXIT')
        for g in self.ordered_children(''): render(g, 1)
        lines.extend(['exit', ''])
        if self.show_form: lines += [f'SHOW !!{self.name}', '']
        if self.after_show_code: lines += [self.after_show_code, '']
        lines.append(f'define method .{self.name}()')
        for g in self.gadgets:
            if g.kind == 'text' and g.initial:
                value = n(float(g.initial)) if g.value_type == 'REAL' else literal(g.initial)
                lines.append(f'  !this.{g.name}.val = {value}')
            if g.kind == 'slider' and g.callback:
                lines.append(f"  !this.{g.name}.callback = '!this.{g.callback}('")
            if g.kind == 'container' and g.assembly:
                lines += [f'  !this.{g.name}Control = object {g.control_type}()',
                          f'  !this.{g.name}.Control = !this.{g.name}Control.handle()']
            if g.kind in ('list','combo') and g.items:
                lines.append('  !choices = object ARRAY()')
                for i, item in enumerate(g.items, 1):
                    lines.append(f'  !choices[{i}] = {literal(item)}')
                lines.append(f'  !this.{g.name}.dtext = !choices')
                if g.item_values:
                    lines.append('  !values = object ARRAY()')
                    for i, value in enumerate(g.item_values,1): lines.append(f'  !values[{i}] = {literal(value)}')
                    lines.append(f'  !this.{g.name}.rtext = !values')
        lines.extend(['endmethod', ''])
        default_code = self.default_body or next((g.body for g in self.gadgets if g.callback.lower() == 'default' and g.body), '')
        lines += ['DEFINE METHOD .DEFAULT()', default_code or '  -- TODO: add default logic', 'ENDMETHOD', '']
        seen = {'default'}
        for g in self.gadgets:
            if g.callback and g.callback.lower() not in seen:
                seen.add(g.callback.lower())
                signature = '(!gad is GADGET, !event is STRING)' if g.kind == 'slider' else '()'
                lines += [f'define method .{g.callback}{signature}', g.body or '  -- TODO: add PML logic', 'endmethod', '']
        return '\n'.join(lines)
