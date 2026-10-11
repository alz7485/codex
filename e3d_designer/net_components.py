"""PML.NET creation recipes. No DLLs or E3D APIs run in the designer."""
from dataclasses import dataclass, field
from .model import Gadget, Form, IDENTIFIER, literal


RECIPES = (
    ('grid', '表（Grid Control）', '列見出しと行データから、読み取り専用の表を作ります。'),
    ('file', 'ファイルを開く／保存', 'ファイル選択ボタンを作り、選択したパスをメソッドで取得します。'),
    ('mydata', 'My Dataへ現在要素を登録', 'ボタンを押したとき、現在要素をMy Dataへ追加します。'),
    ('flexible', 'ツリー（Flexible Explorer接続）', 'PML.NET対応ラッパーDLLが必要です。既存アドインを直接コンテナへ載せることはできません。表示定義や初期化はその部品のAPIに合わせて追加します。'),
    ('dimension', 'サポート寸法部品の接続', '専用DLL・寸法設定が必要です。表示内容は部品側の設定と初期化コードで指定します。'),
    ('custom', '自作／外部.NET部品の接続', 'PML.NET対応DLLを指定すると、メンバー宣言・生成・コンテナ接続を作ります。'),
)
CONTAINERS = {'grid', 'flexible', 'dimension', 'custom'}
DEFAULT_CONNECTIONS = {
    'grid': ('GridControl', 'Aveva.Core.Presentation', 'NetGridControl'),
    'dimension': ('Aveva.Presentation.Supports.DimensionControl',
                  'Aveva.Presentation.Supports.DimensionControl', 'SupportDimensionControl'),
}


def import_code(assembly):
    return '\n'.join((f'import {literal(assembly, field="DLL名")}', 'handle (1000,0)',
                      '  -- Assembly already loaded', 'endhandle'))


@dataclass
class NetComponentSpec:
    recipe: str = 'grid'
    name: str = 'netGrid1'
    label: str = 'Results'
    assembly: str = 'GridControl'
    namespace: str = 'Aveva.Core.Presentation'
    control_type: str = 'NetGridControl'
    width: float = 36
    height: float = 9
    headings: list[str] = field(default_factory=lambda: ['Name', 'Type'])
    rows: list[list[str]] = field(default_factory=lambda: [['Sample-1', 'EQUI']])
    single: bool = False
    data_source: str = 'ROWS'
    mode: str = 'OPEN'
    directory: str = ''
    seed: str = ''
    file_filter: str = 'All files (*.*)|*.*'
    setup_code: str = ''

    def gadget(self):
        if self.recipe not in {key for key, _, _ in RECIPES}:
            raise ValueError('部品の種類が不正です。')
        if not IDENTIFIER.fullmatch(self.name):
            raise ValueError('部品名は英字で始まる英数字・_ にしてください。')
        literal(self.label)
        if self.recipe in CONTAINERS:
            g = Gadget(kind='container', name=self.name, label=self.label,
                       width=self.width, height=self.height, assembly=self.assembly.strip(),
                       namespace=self.namespace.strip(), control_type=self.control_type.strip())
            if not all((g.assembly, g.namespace, g.control_type)):
                raise ValueError('DLL名・名前空間・コントロール型を指定してください。')
            setup = []
            if self.recipe == 'grid':
                if self.data_source not in ('ROWS', 'MEMBERS'):
                    raise ValueError('表のデータ元が不正です。')
                if g.control_type.lower() != 'netgridcontrol':
                    raise ValueError('表の型はNetGridControlを指定してください。別の部品は「自作／外部」を使用してください。')
                headings = self.headings if self.data_source == 'ROWS' else ['Name', 'Type']
                if not headings or any(not title.strip() for title in headings):
                    raise ValueError('表には空欄でない列見出しを指定してください。')
                if len({title.casefold() for title in headings}) != len(headings):
                    raise ValueError('列見出しが重複しています。')
                if self.data_source == 'ROWS' and any(len(row) != len(headings) for row in self.rows):
                    raise ValueError('行データの列数を見出しの列数に合わせてください。')
                ctrl = f'!this.{g.name}Control'
                setup = ['!netHeadings = object ARRAY()']
                for i, title in enumerate(headings, 1):
                    setup.append(f'!netHeadings[{i}] = {literal(title)}')
                setup.append('!netRows = object ARRAY()')
                for i, row in enumerate(self.rows if self.data_source == 'ROWS' else [], 1):
                    setup.append(f'!netRows[{i}] = object ARRAY()')
                    for j, cell in enumerate(row, 1):
                        setup.append(f'!netRows[{i}][{j}] = {literal(cell)}')
                if self.data_source == 'MEMBERS':
                    setup += ['if (BADREF(!!CE)) then', '  $p Select a database element first.',
                              'else', '  do !netElement values !!CE.members',
                              '    !netRow = object ARRAY()', '    !netRow[1] = !netElement.name',
                              '    !netRow[2] = !netElement.type', '    !netRows.append(!netRow)',
                              '  enddo', 'endif']
                setup += [f'!netSource = object NetDataSource({literal(g.name)}, !netHeadings, !netRows)',
                          f'{ctrl}.BindToDataSource(!netSource)', f'{ctrl}.EditableGrid(FALSE)',
                          f'{ctrl}.SingleRowSelection({"TRUE" if self.single else "FALSE"})']
            if self.setup_code.strip():
                setup.append(self.setup_code)
            g.net_setup = '\n'.join(setup)
        else:
            g = Gadget(name=self.name, label=self.label, width=self.width, height=1,
                       callback=self.name + 'Click')
            if self.recipe == 'file':
                if self.mode not in ('OPEN', 'SAVE'):
                    raise ValueError('ファイル選択はOPENまたはSAVEを指定してください。')
                parts = self.file_filter.split('|')
                if len(parts) < 2 or len(parts) % 2 or any(not part.strip() for part in parts):
                    raise ValueError('フィルターは「表示名|*.拡張子」の組で指定してください。')
                args = [literal(self.directory), literal(self.seed), literal(self.label),
                        'TRUE' if self.mode == 'OPEN' else 'FALSE', literal(self.file_filter), '1']
                g.body = '\n'.join((import_code('PMLFileBrowser'),
                    "using namespace 'Aveva.Core.Presentation'",
                    f'!browser = object PMLFileBrowser({literal(self.mode)})',
                    f'!browser.show({", ".join(args)})', '!selectedFile = !browser.file()',
                    "if (!selectedFile eq '') then", '  return', 'endif',
                    '$p Selected file: $!selectedFile', '-- Add processing for !selectedFile here'))
            else:
                g.body = '\n'.join((import_code('MyDataAddin'),
                    "using namespace 'Aveva.Core.Presentation.MyDataAddin'",
                    'if (BADREF(!!CE)) then', '  $p Select a database element first.',
                    '  return', 'endif', '!myData = object PMLMyData()',
                    '!elementName = !!CE.name', '!myData.AddElement(!elementName)',
                    '$p Added to My Data: $!elementName'))
        g.x = g.y = 0
        Form(gadgets=[g], width=max(70, g.width), height=max(22, g.height)).validate()
        return g


def available_name(form, base):
    from .app import Window
    reserved = Window.reserved_names(form)
    i = 1
    while any(name.casefold() in reserved for name in (f'{base}{i}', f'{base}{i}Control', f'{base}{i}Click')):
        i += 1
    return f'{base}{i}'
