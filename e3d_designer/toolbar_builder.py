"""Build a horizontal action row or a MAIN toolbar as one transaction."""
import copy
import math
from dataclasses import dataclass, field
from .model import Gadget, IDENTIFIER, literal, text_width_hint


ACTIONS = (
    ('custom', '自分の処理', 'PMLメソッドの本文を入力します。あとからボタンの「動作」で編集できます。'),
    ('macro', '外部マクロを実行', '実行する .mac ファイルを指定します。ファイルはこのプロジェクトに同梱されません。'),
    ('info', '現在要素の情報', '現在要素（CE）の名前・種類をコマンド出力へ表示します。'),
    ('owner', '直属の上位へ移動', '現在要素のOWNERへ1階層移動します。上位がない場合は移動しません。'),
    ('members', '直属の配下を表示', '現在要素のMEMBERSを名前・種類の一覧としてコマンド出力へ表示します。'),
)


@dataclass
class ToolbarButtonSpec:
    label: str = 'Run'
    action: str = 'custom'
    width: int = 12
    body: str = '$p Add processing here.'
    macro_path: str = ''

    def action_body(self):
        if self.action == 'custom':
            from .mac_import import split_methods
            from .pml_syntax import has_code
            if '\x00' in self.body:
                raise ValueError('処理コードにNULを使用できません。')
            remaining, methods, _ = split_methods('define method .sample()\n'+self.body+'\nendmethod')
            if len(methods) != 1 or has_code(remaining):
                raise ValueError('処理コードにはメソッドの本文だけを入力してください。')
            if not has_code(self.body):
                raise ValueError('自分の処理の本文を入力してください。')
            return self.body
        guard = ('!element = !!CE', 'if (BADREF(!element)) then',
                 '  $p No valid current element.', '  return', 'endif')
        if self.action == 'info':
            return '\n'.join((*guard, '!name = !element.name', '!type = !element.type',
                              '$p Current element: $!name  Type: $!type'))
        if self.action == 'owner':
            return '\n'.join((*guard, '!owner = !element.owner', 'if (BADREF(!owner)) then',
                '  $p No owner to navigate to.', '  return', 'endif', '!!CE = !owner',
                '!name = !owner.name', '$p Current element: $!name'))
        if self.action == 'members':
            return '\n'.join((*guard, '!members = !element.members',
                'if (!members.size() eq 0) then', '  $p No direct members.', '  return', 'endif',
                'do !member values !members', '  !name = !member.name', '  !type = !member.type',
                '  $p Member: $!name  Type: $!type', 'enddo'))
        return ''


def navigation_buttons():
    return [ToolbarButtonSpec('CE info', 'info'), ToolbarButtonSpec('Up', 'owner', 8),
            ToolbarButtonSpec('Members', 'members')]


def available_name(form, base='tools', prefixes=()):
    from .app import Window
    used = Window.reserved_names(form)
    i = 1
    while any((prefix+base+str(i)).lower() in used for prefix in ('', *prefixes)): i += 1
    return base+str(i)


@dataclass
class ToolbarSpec:
    frame_name: str = 'tools1'
    label: str = 'Tools'
    style: str = 'ROW'
    convert_to_main: bool = False
    buttons: list[ToolbarButtonSpec] = field(default_factory=lambda: [ToolbarButtonSpec()])

    def build(self, form):
        from .app import Window, free_position, preview_geometry
        from .method_output import check_editable_code
        if form.program_mode == 'SOURCE':
            raise ValueError('「取り込みコード」で表示プログラムを自動生成へ変更してから追加してください。')
        draft = copy.deepcopy(form)
        draft.pml()
        if self.style not in ('ROW', 'TOOLBAR'):
            raise ValueError('作成する形式が不正です。')
        if not IDENTIFIER.fullmatch(self.frame_name):
            raise ValueError('部品名は英字で始まる英数字・_ にしてください。')
        if self.frame_name.lower() in Window.reserved_names(draft):
            raise ValueError('部品名が使用済みです。')
        literal(self.label, field='ツールバーの表示名')
        if self.style == 'TOOLBAR' and draft.form_type != 'MAIN':
            if not self.convert_to_main:
                raise ValueError('標準TOOLBARにはMAINへの変更にチェックを入れてください。')
            draft.form_type = 'MAIN'
            draft.dock_right = False
            draft.dock_side = 'NONE'
        if self.style == 'ROW' and draft.form_type == 'MAIN':
            raise ValueError('MAINでは標準TOOLBARを選んでください。')
        if not 1 <= len(self.buttons) <= 16:
            raise ValueError('ボタンは1〜16個にしてください。')
        widths = []
        for button in self.buttons:
            if button.action not in {key for key, _, _ in ACTIONS}:
                raise ValueError('ボタンの処理が不正です。')
            if not button.label.strip():
                raise ValueError('ボタンの表示名を入力してください。')
            literal(button.label, field='ボタンの表示名')
            if type(button.width) is not int or not 4 <= button.width <= 80:
                raise ValueError('ボタンの幅は4〜80にしてください。')
            widths.append(max(button.width, math.ceil(text_width_hint(button.label)+2)))
        width = sum(widths)+len(widths)+1
        limits = (draft.width, draft.height) if draft.size_explicit else (299, 299)
        position = free_position([preview_geometry(draft, g) for g in draft.children('')],
                                 width, 3, *limits, preferred=(0, 0))
        if position is None:
            raise ValueError('横一列のボタンを置く空きがありません。ボタンの幅・個数またはフォームサイズを変更してください。')
        frame = Gadget(kind='frame', name=self.frame_name, label=self.label,
                       frame_style='TOOLBAR' if self.style=='TOOLBAR' else 'FRAME',
                       x=position[0], y=position[1], width=width, height=3)
        draft.gadgets.append(frame)
        root_index = len(draft.gadgets)-1
        x = 1
        for button, button_width in zip(self.buttons, widths):
            name = available_name(draft, self.frame_name+'Button', ('macro_',) if button.action=='macro' else ())
            gadget = Gadget(name=name, label=button.label, parent=frame.name,
                            x=x, y=1, width=button_width, height=1)
            if button.action == 'macro':
                gadget.action_mode = 'MACRO'; gadget.macro_path = button.macro_path.strip()
            else:
                gadget.callback = Window.automatic_method(draft, name)
                gadget.body = button.action_body()
            draft.gadgets.append(gadget)
            x += button_width+1
        draft.validate(); check_editable_code(draft); draft.pml()
        return draft, root_index
