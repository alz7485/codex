"""Build DB selector actions without executing database commands."""
import copy
from dataclasses import dataclass
from .model import Gadget, Method, IDENTIFIER, literal, display_size
from .pml_syntax import has_code
from .callbacks import callback_body


RECIPES = (
    ('report', '名前・種類・上位の情報を表示', '選択要素の情報をE3Dのコマンド出力へ表示します。'),
    ('navigate', '選択要素を現在要素（CE）にする', '単一選択の要素へ移動します。処理ボタンから実行します。'),
    ('mydata', '選択要素をMy Dataへ登録', '選択した要素をMy Dataへ登録します。処理ボタンから実行します。'),
    ('custom', '1件ずつ自分の処理を実行', '!element（DBREF）を使って各要素への処理を記述できます。'),
)


def unique_name(form, base, extra=()):
    from .app import Window
    occupied = Window.reserved_names(form)
    i = 1
    while any((base + str(i) + suffix).lower() in occupied for suffix in ('', *extra)):
        i += 1
    return base + str(i)


@dataclass
class SelectorMethodSpec:
    method_name: str = 'processSelector1'
    recipe: str = 'report'
    trigger: str = 'BUTTON'
    button_label: str = 'Process selected'
    refresh: bool = True
    report_name: bool = True
    report_type: bool = True
    report_owner: bool = False
    custom_body: str = ''
    replace_existing: bool = False
    database: str | None = None
    selection_mode: str | None = None

    def build(self, form, selector_index):
        """Return a new form; errors never mutate the input or its history."""
        from .app import Window, free_position, preview_geometry
        if type(selector_index) is not int or not 0 <= selector_index < len(form.gadgets):
            raise ValueError('DBセレクタを選択してください。')
        if form.gadgets[selector_index].kind != 'selector':
            raise ValueError('対象はDBセレクタにしてください。')
        if form.program_mode == 'SOURCE':
            raise ValueError('「取り込みコード」で表示プログラムを自動生成へ変更してから追加してください。')
        draft = copy.deepcopy(form)
        selector = draft.gadgets[selector_index]
        if self.database is not None: selector.database = self.database
        if self.selection_mode is not None: selector.selection_mode = self.selection_mode
        draft.pml()
        if self.recipe not in {key for key, _, _ in RECIPES} or self.trigger not in ('BUTTON', 'SELECTION'):
            raise ValueError('処理または実行方法が不正です。')
        if not IDENTIFIER.fullmatch(self.method_name):
            raise ValueError('メソッド名は英字で始まる英数字・_ にしてください。')
        worker_name = self.method_name + 'Element'
        if any(name.lower() in Window.reserved_names(draft) for name in (self.method_name, worker_name)):
            raise ValueError('メソッド名または生成する1件処理のメソッド名が使用済みです。')
        if self.recipe == 'navigate' and selector.selection_mode != 'SINGLE':
            raise ValueError('現在要素への移動にはSINGLE（単一選択）を使用してください。')
        if self.recipe in ('navigate', 'mydata') and self.trigger != 'BUTTON':
            raise ValueError('現在要素への移動とMy Data登録は処理ボタンから実行してください。')
        if self.trigger == 'SELECTION' and has_code(callback_body(draft, selector)) and not self.replace_existing:
            raise ValueError('既存の選択時処理があります。生成コードを確認し、置き換えのチェックを入れてください。')

        worker = self.worker_body()
        # Snapshot selection before processing: changing CE may refresh the gadget.
        dispatcher = '\n'.join((
            '!selectedNames = object ARRAY()',
            f'do !selected selector !this.{selector.name}',
            '  !selectedNames.append(!selected)', 'enddo',
            'if (!selectedNames.size() eq 0) then',
            '  $p Select at least one database element.', '  return', 'endif',
            '!processedCount = 0', 'do !selected values !selectedNames',
            '  !element = object DBREF(!selected)',
            '  if (BADREF(!element)) then',
            '    $p Invalid database reference: $!selected', '  else',
            f'    !this.{worker_name}(!element)',
            '    !processedCount = !processedCount + 1', '  endif', 'enddo',
            '$p Processed count: $!processedCount'))
        draft.extra_methods.extend((Method(self.method_name, '()', dispatcher),
                                    Method(worker_name, '(!element is DBREF)', worker)))

        def add_button(base, label, body):
            literal(label, field='ボタンの表示名')
            name = unique_name(draft, base, ('Click',))
            parent = draft.parent_gadget(selector)
            if draft.form_type == 'MAIN' or (parent and parent.frame_style != 'FRAME'):
                raise ValueError('処理ボタンはDIALOGフォームの通常フレーム、タブのページ、またはフォーム直下へ追加してください。')
            width, height = draft.geometry(parent)[2:] if parent else ((draft.width, draft.height) if draft.size_explicit else (299, 299))
            button = Gadget(name=name, label=label, callback=name+'Click', body=body,
                            parent=selector.parent, width=18, height=1)
            position = free_position([preview_geometry(draft, g) for g in draft.children(button.parent)],
                                     *display_size(button), width, height, minimum_y=1 if parent else 0)
            if position is None:
                raise ValueError('ボタンを追加する空きがありません。追加先のサイズを広げるか、更新ボタンの追加を外してください。')
            button.x, button.y = position
            draft.gadgets.append(button)

        if self.trigger == 'BUTTON':
            add_button('runSelector', self.button_label, f'!this.{self.method_name}()')
        else:
            old_name = selector.callback
            old_body = callback_body(draft, selector)
            # Preserve the old method for menus and other explicit callers.
            if old_name and old_name.lower() != 'default' and has_code(old_body) and not any(
                    g is not selector and g.callback.lower() == old_name.lower() for g in draft.gadgets):
                draft.extra_methods.append(Method(old_name, '()', old_body))
            selector.callback = unique_name(draft, 'selectSelector')
            selector.callback_expression = ''
            selector.body = f'!this.{self.method_name}()'
        if self.refresh:
            add_button('refreshSelector', 'Refresh list', f'!this.{selector.name}.Refresh()')
        draft.pml()
        return draft

    def worker_body(self):
        if self.recipe == 'report':
            if not any((self.report_name, self.report_type, self.report_owner)):
                raise ValueError('表示する情報を1つ以上選んでください。')
            lines = []
            for enabled, attribute in ((self.report_name, 'name'), (self.report_type, 'type')):
                if enabled:
                    lines.extend((f'!value = !element.{attribute}', f'$p {attribute.capitalize()}: $!value'))
            if self.report_owner:
                lines.extend(('!owner = !element.owner', 'if (BADREF(!owner)) then',
                              '  $p Owner: none', 'else', '  !ownerName = !owner.name',
                              '  $p Owner: $!ownerName', 'endif'))
            return '\n'.join(lines)
        if self.recipe == 'navigate':
            return '\n'.join(('!!CE = !element', '!name = !element.name', '$p Current element: $!name'))
        if self.recipe == 'mydata':
            from .net_components import import_code
            return '\n'.join((import_code('MyDataAddin'),
                "using namespace 'Aveva.Core.Presentation.MyDataAddin'",
                '!myData = object PMLMyData()', '!name = !element.name',
                '!myData.AddElement(!name)', '$p Added to My Data: $!name'))
        if '\x00' in self.custom_body:
            raise ValueError('処理コードにNULを使用できません。')
        from .mac_import import split_methods
        remaining, methods, _ = split_methods('define method .sample(!element is DBREF)\n'+self.custom_body+'\nendmethod')
        if len(methods) != 1 or has_code(remaining):
            raise ValueError('処理コードにはメソッドの本文だけを入力してください。')
        return '\n'.join(('!name = !element.name', '$p Selected element: $!name',
                          self.custom_body or '-- Add processing for !element here'))
