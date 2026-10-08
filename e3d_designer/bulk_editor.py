"""Transactional gadget spreadsheet with configurable columns and bulk edits."""
import copy
import math

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
    QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
    QPlainTextEdit, QPushButton, QStackedWidget, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QVBoxLayout)

from .callbacks import callback_body, join_callback, set_callback_body
from .model import (IDENTIFIER, KINDS, dimension_editable, literal,
    supports_auto_width, supports_hidden, uses_pairs)


FIELDS = {
    'command': 'コマンド', 'callback': 'メソッド名', 'body': 'メソッド本文',
    'background': '色番号', 'label': '表示名', 'initial': '初期値',
    'width': 'WIDTH', 'height': 'HEIGHT', 'width_explicit': '幅を指定',
    'hidden': '非表示', 'comment': 'コメント', 'value_type': '入力型',
    'button_call': 'OKCALL / CANCELCALL', 'combo_tagwid': 'TAGWID',
    'combo_scroll': 'SCROLL', 'slider_value': 'スライダー値',
    'slider_min': 'スライダー最小値', 'slider_max': 'スライダー最大値',
    'slider_step': 'スライダー増減単位', 'view_code': 'VIEW追加コード',
    'macro_path': 'マクロファイル', 'macro_value': 'マクロ分岐値',
}
MULTILINE = {'body', 'comment', 'view_code'}
NUMBERS = {'width', 'height', 'slider_value', 'slider_min', 'slider_max', 'slider_step'}


def editable_reason(form, g, key):
    """Return why a field cannot be edited; an empty string means applicable."""
    action = g.action_mode == 'CODE' and (g.kind != 'button' or g.button_role not in ('OK', 'CANCEL', 'HELP'))
    callback = g.kind not in ('paragraph', 'line', 'frame', 'rtoggle', 'view', 'commandline', 'container', 'textpane') and not uses_pairs(g)
    command = g.kind in ('button', 'text', 'toggle') or (g.kind == 'option' and g.display_mode == 'TEXT' and not uses_pairs(g))
    if key == 'command' and not (action and command):return 'この部品はCALLコマンドに対応しません。'
    if key in ('callback', 'body'):
        if not (action and callback):return 'この部品はメソッド型の処理に対応しません。'
        if form.constructor_mode == 'SOURCE' and g.kind in ('combo', 'slider'):
            return '元コードのコンストラクタでイベント登録を編集してください。'
        if key == 'body':
            if g.command:return 'コマンドが指定されています。先にメソッド名を設定してください。'
            if g.callback.lower() == 'default' and form.default_mode == 'SOURCE':return '取り込みコードのDEFAULT欄で編集してください。'
    if key == 'background' and g.kind not in ('button', 'paragraph', 'list'):return 'この部品はBACKGROUNDに対応しません。'
    if key == 'label' and (g.kind == 'line' or g.display_mode == 'PIXMAP'):return 'この表示では表示名を使用しません。'
    if key == 'initial':
        if form.default_mode == 'SOURCE':return '取り込みコードのDEFAULT欄で編集してください。'
        if not (g.kind in ('text', 'toggle', 'rtoggle', 'list', 'option', 'combo') or (g.kind == 'paragraph' and g.display_mode == 'TEXT')):
            return 'この部品には初期値欄がありません。'
    if key in ('width', 'height') and (form.is_tab_page(g) or not dimension_editable(g, key)):return '寸法固定・自動幅・幅参照・非表示のため編集できません。'
    if key == 'width_explicit' and (not supports_auto_width(g) or g.width_ref or g.hidden):return 'この部品の幅指定は切り替えできません。'
    if key == 'hidden' and not supports_hidden(g):return 'この部品は幅0の非表示に対応しません。'
    if key == 'value_type' and g.kind != 'text':return 'TEXT専用です。'
    if key == 'button_call' and g.kind != 'button':return 'BUTTON専用です。'
    if key == 'combo_tagwid' and g.kind not in ('combo', 'rtoggle'):return 'COMBO / RTOGGLE専用です。'
    if key == 'combo_scroll' and g.kind != 'combo':return 'COMBO専用です。'
    if key.startswith('slider_') and g.kind != 'slider':return 'SLIDER専用です。'
    if key == 'view_code' and g.kind not in ('view', 'commandline'):return 'VIEW / COMMANDLINE専用です。'
    if key in ('macro_path', 'macro_value') and not (g.kind == 'button' and g.action_mode == 'MACRO'):return '外部マクロ方式のBUTTON専用です。'
    return ''


def field_value(form, g, key):
    if key == 'body':return callback_body(form, g)
    if key == 'width_explicit' and uses_pairs(g):return g.option_width_explicit
    return getattr(g, key)


def choices(form, g, key):
    if key in ('width_explicit', 'hidden'):return ['FALSE', 'TRUE']
    if key == 'initial' and g.kind in ('toggle', 'rtoggle'):return ['', 'TRUE', 'FALSE']
    if key == 'value_type':return ['STRING', 'REAL']
    if key == 'button_call':return ['', 'OKCALL', 'CANCELCALL']
    return None


def apply_values(form, rows, key, text):
    """Apply one value to eligible rows on a copy, or return no mutation on error."""
    if key not in FIELDS:raise ValueError('編集項目が見つかりません。')
    candidate = copy.deepcopy(form)
    selected = list(dict.fromkeys(rows))
    if any(type(row) is not int or not 0 <= row < len(candidate.gadgets) for row in selected):
        raise ValueError('部品が見つかりません。')
    eligible = [row for row in selected if not editable_reason(candidate, candidate.gadgets[row], key)]
    if not eligible:raise ValueError('選択中の部品に、この項目を設定できる部品がありません。')
    for row in eligible:
        g = candidate.gadgets[row]
        if str(field_value(candidate, g, key)) == text and not (key == 'body' and text and not g.callback):continue
        value = text
        options = choices(candidate, g, key)
        if options is not None:
            if text not in options:raise ValueError(f'{g.name}: {FIELDS[key]}は '+', '.join(repr(v) for v in options)+' から選んでください。')
            if key in ('width_explicit', 'hidden'):value = text == 'TRUE'
        if key in NUMBERS:
            try:value = float(text)
            except ValueError:raise ValueError(f'{g.name}: {FIELDS[key]}には数値を入力してください。') from None
            if not math.isfinite(value):raise ValueError(f'{g.name}: 有限の数値を指定してください。')
            if key in ('width', 'height', 'slider_step') and value <= 0:raise ValueError(f'{g.name}: {FIELDS[key]}は0より大きい値にしてください。非表示には「非表示」を使います。')
        if '\x00' in text:raise ValueError(f'{g.name}: NUL文字は使用できません。')
        if key == 'command':
            literal(text, allow_expansion=True, field=f'{g.name}: コマンド')
            if text:
                g.callback = '';g.callback_expression = ''
            g.command = text
        elif key == 'callback':
            if text and (not IDENTIFIER.fullmatch(text) or text.lower() == candidate.name.lower()):
                raise ValueError(f'{g.name}: メソッド名は英字で始まる英数字・_にしてください。フォーム名との重複はできません。')
            previous = g.callback;g.callback = text
            if text:g.command = ''
            join_callback(candidate, g, previous)
        elif key == 'body':
            if text and not g.callback:
                from .app import Window
                g.callback = Window.automatic_method(candidate, g.name)
            set_callback_body(candidate, g, text)
        elif key == 'width_explicit':
            previous_width = candidate.display_width(g)
            if uses_pairs(g):g.option_width_explicit = value
            else:g.width_explicit = value
            if value:g.width = previous_width
        else:
            if key == 'label':literal(text, field=f'{g.name}: 表示名')
            if key == 'background' and text and (not text.isascii() or not text.isdecimal()):
                raise ValueError(f'{g.name}: 色番号は空欄または整数にしてください。')
            if key == 'combo_tagwid' and text:
                try:number = float(text)
                except ValueError:raise ValueError(f'{g.name}: TAGWIDには数値を入力してください。') from None
                if not math.isfinite(number) or number < 0:raise ValueError(f'{g.name}: TAGWIDは0以上の有限数にしてください。')
            if key == 'combo_scroll' and text and (not text.isascii() or not text.isdecimal() or int(text) < 1):
                raise ValueError(f'{g.name}: SCROLLは1以上の整数にしてください。')
            setattr(g, key, value)
            if key in ('width', 'height') and g.kind == 'frame':
                axis = 'W' if key == 'width' else 'H'
                g.frame_size_axes = ''.join(a for a in 'WH' if a in g.frame_size_axes + axis)
    # A shared method has one definition, including unselected callers.
    signatures = {}
    for g in candidate.gadgets:
        if not g.callback:continue
        signature = g.kind in ('combo', 'slider')
        name = g.callback.lower()
        if name in signatures and signatures[name] != signature:
            raise ValueError('COMBO / SLIDERと引数なしの部品ではメソッド名を分けてください。')
        if signature and name == 'default':raise ValueError('COMBO / SLIDERにはDEFAULT以外のメソッド名を指定してください。')
        signatures[name] = signature
    from .draft_validation import validate_draft
    validate_draft(candidate)
    return candidate, len(eligible), len(selected) - len(eligible)


class SpreadsheetDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        dialog = self.parent()
        key = dialog.columns[index.column() - 2]
        g = dialog.draft.gadgets[index.row()]
        options = choices(dialog.draft, g, key)
        if options is not None:
            editor = QComboBox(parent);editor.addItems(options);return editor
        if key in MULTILINE:
            editor = QPlainTextEdit(parent);editor.setMinimumHeight(90)
            editor.setToolTip('改行: Enter / 確定: Ctrl+Enter / 次のセル: Tab')
            if key in ('body', 'view_code'):
                from .highlighting import PmlHighlighter
                editor.highlighter = PmlHighlighter(editor.document());editor.highlighter.set_symbols(dialog.draft)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        value = index.data(Qt.EditRole) or ''
        if isinstance(editor, QComboBox):editor.setCurrentText(value)
        elif isinstance(editor, QPlainTextEdit):editor.setPlainText(value)
        else:super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):value = editor.currentText()
        elif isinstance(editor, QPlainTextEdit):value = editor.toPlainText()
        else:return super().setModelData(editor, model, index)
        model.setData(index, value, Qt.EditRole)

    def eventFilter(self, editor, event):
        if isinstance(editor, QPlainTextEdit) and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ControlModifier:
                    self.commitData.emit(editor);self.closeEditor.emit(editor);return True
                return False
        return super().eventFilter(editor, event)


class BulkPropertiesDialog(QDialog):
    def __init__(self, parent, form, selected_names=()):
        super().__init__(parent)
        self.draft = copy.deepcopy(form);self.result_form = None
        self.columns = ['command', 'callback', 'body', 'background']
        self.loading = False;self.invalid_cells = {}
        self.setWindowTitle('部品の一覧・一括編集');self.resize(1180, 690)
        layout = QVBoxLayout(self)
        note = QLabel('見出しの▼で編集項目を切り替え。セルをダブルクリックして入力、Tabで次へ移動できます。\nCtrl / Shiftで複数行を選び、下の欄で一括設定。メソッド本文の変更は同名メソッドの全呼び出し元へ反映します。')
        note.setWordWrap(True);layout.addWidget(note)
        filters = QHBoxLayout();layout.addLayout(filters)
        filters.addWidget(QLabel('部品タイプ'))
        self.type_filter = QComboBox();self.type_filter.addItem('すべて', '')
        from .app import LABELS
        for kind in KINDS:self.type_filter.addItem(f'{LABELS[kind]} ({kind.upper()})', kind)
        for title, key in [('タブセット', 'TABSET'), ('タブページ', 'PAGE'), ('通常フレーム', 'FRAME'), ('ツールバー', 'TOOLBAR')]:self.type_filter.addItem(title, key)
        filters.addWidget(self.type_filter)
        self.search = QLineEdit();self.search.setPlaceholderText('部品名・表示名・親フレームを検索');filters.addWidget(self.search, 1)
        self.select_all_button = QPushButton('表示行をすべて選択');self.select_all_button.clicked.connect(self.select_visible);filters.addWidget(self.select_all_button)
        self.methods_button = QPushButton('補助メソッド管理…');self.methods_button.clicked.connect(self.manage_helpers);filters.addWidget(self.methods_button)
        self.table = QTableWidget(len(self.draft.gadgets), 6);layout.addWidget(self.table, 1)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setItemDelegate(SpreadsheetDelegate(self))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().sectionClicked.connect(self.choose_column)
        self.table.setColumnWidth(0, 145);self.table.setColumnWidth(1, 130)
        for column in range(2, 6):self.table.setColumnWidth(column, 205)
        self.table.itemChanged.connect(self.cell_changed)
        self.table.itemSelectionChanged.connect(self.update_batch_options)
        batch = QHBoxLayout();layout.addLayout(batch)
        batch.addWidget(QLabel('選択行に一括設定'))
        self.batch_field = QComboBox()
        for key, title in FIELDS.items():self.batch_field.addItem(title, key)
        batch.addWidget(self.batch_field)
        self.batch_stack = QStackedWidget();self.batch_stack.setFixedHeight(96)
        self.batch_text = QPlainTextEdit()
        self.batch_text.setPlaceholderText('設定する値（空欄で消去）。大文字小文字・改行を保持します。')
        self.batch_choices = QComboBox();self.batch_stack.addWidget(self.batch_text);self.batch_stack.addWidget(self.batch_choices)
        batch.addWidget(self.batch_stack, 1)
        self.color_button = QPushButton('色を選ぶ…');self.color_button.clicked.connect(self.choose_color);batch.addWidget(self.color_button)
        self.apply_button = QPushButton('選択行に設定');self.apply_button.clicked.connect(self.apply_batch);batch.addWidget(self.apply_button)
        self.summary = QLabel();layout.addWidget(self.summary)
        self.error = QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.batch_field.currentIndexChanged.connect(self.update_batch_options)
        self.type_filter.currentIndexChanged.connect(self.filter_rows);self.search.textChanged.connect(self.filter_rows)
        self.reload()
        from PySide6.QtCore import QItemSelectionModel
        for row, g in enumerate(self.draft.gadgets):
            if g.name in selected_names:self.table.selectionModel().select(self.table.model().index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self.update_batch_options()

    def selected_rows(self):
        return sorted(index.row() for index in self.table.selectionModel().selectedRows() if not self.table.isRowHidden(index.row()))

    def reload(self):
        self.loading = True
        self.table.setHorizontalHeaderLabels(['オブジェクト名', 'タイプ / 親', *[FIELDS[key]+' ▼' for key in self.columns]])
        for row, g in enumerate(self.draft.gadgets):
            for column in range(6):
                key = self.columns[column - 2] if column >= 2 else None
                reason = editable_reason(self.draft, g, key) if key else '識別用の欄です。名前の変更は「変数・名前管理」で行います。'
                value = field_value(self.draft, g, key) if key else g.name if column == 0 else g.kind.upper()+(' / '+g.parent if g.parent else '')
                if isinstance(value, bool):value = 'TRUE' if value else 'FALSE'
                invalid = self.invalid_cells.get((row, key))
                if invalid:value = invalid[0]
                item = self.table.item(row, column)
                if item is None:item = QTableWidgetItem();self.table.setItem(row, column, item)
                item.setText(str(value))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | (Qt.ItemIsEditable if not reason else Qt.NoItemFlags))
                item.setBackground(QColor('#ffe3e3') if invalid else QColor('#eeeeee') if reason else QColor('white'))
                item.setToolTip(invalid[1] if invalid else reason or (str(value)+'\n\n改行: Enter / 確定: Ctrl+Enter' if key in MULTILINE else str(value)))
        self.loading = False;self.filter_rows()

    def choose_column(self, column):
        if column < 2:return
        self.table.clearFocus()
        menu = QMenu(self)
        for key, title in FIELDS.items():
            action = menu.addAction(title);action.setCheckable(True);action.setChecked(self.columns[column - 2] == key)
            action.triggered.connect(lambda checked=False, k=key:self.set_column(column, k))
        header = self.table.horizontalHeader()
        from PySide6.QtCore import QPoint
        menu.exec(header.mapToGlobal(QPoint(header.sectionViewportPosition(column), header.height())))
        menu.deleteLater()

    def set_column(self, column, key):
        if not 2 <= column < 6 or key not in FIELDS:raise ValueError('編集列が不正です。')
        self.table.clearFocus();self.columns[column - 2] = key;self.reload()

    def filter_rows(self):
        kind = self.type_filter.currentData();text = self.search.text().casefold()
        for row, g in enumerate(self.draft.gadgets):
            type_match = not kind or g.kind == kind or (kind == 'PAGE' and self.draft.is_tab_page(g)) or (kind in ('FRAME', 'TABSET', 'TOOLBAR') and g.kind == 'frame' and g.frame_style == kind and (kind != 'FRAME' or not self.draft.is_tab_page(g)))
            visible = type_match and text in (g.name+' '+g.label+' '+g.parent).casefold()
            self.table.setRowHidden(row, not visible)
        self.update_batch_options()

    def select_visible(self):
        from PySide6.QtCore import QItemSelectionModel
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):self.table.selectionModel().select(self.table.model().index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def update_batch_options(self):
        if not hasattr(self, 'batch_field'):return
        key = self.batch_field.currentData();rows = self.selected_rows()
        eligible = [row for row in rows if not editable_reason(self.draft, self.draft.gadgets[row], key)]
        options = [choices(self.draft, self.draft.gadgets[row], key) for row in eligible]
        selected_options = options[0] if options and all(value == options[0] for value in options) else None
        if selected_options is not None:
            previous = self.batch_choices.currentText()
            self.batch_choices.clear();self.batch_choices.addItems(selected_options)
            if previous in selected_options:self.batch_choices.setCurrentText(previous)
        self.batch_stack.setCurrentIndex(1 if selected_options is not None else 0)
        self.color_button.setVisible(key == 'background');self.apply_button.setEnabled(bool(eligible))
        self.summary.setText(f'表示 {sum(not self.table.isRowHidden(r) for r in range(self.table.rowCount()))} / {self.table.rowCount()}部品　選択 {len(rows)}　設定可能 {len(eligible)}（対象外は変更しません）')

    def apply_change(self, rows, key, value):
        try:candidate, count, skipped = apply_values(self.draft, rows, key, value)
        except ValueError as error:
            if len(rows) == 1 and not editable_reason(self.draft, self.draft.gadgets[rows[0]], key):
                self.invalid_cells[(rows[0], key)] = (value, str(error))
            self.error.setText(str(error));self.reload();return False
        for row in rows:
            if not editable_reason(self.draft, self.draft.gadgets[row], key):self.invalid_cells.pop((row, key), None)
        self.draft = candidate;self.reload()
        self.error.setText(f'{count}部品へ設定しました。対象外 {skipped}部品。OKで設計へ反映します。')
        return True

    def cell_changed(self, item):
        if self.loading or item.column() < 2:return
        self.apply_change([item.row()], self.columns[item.column() - 2], item.text())

    def apply_batch(self):
        self.table.clearFocus()
        value = self.batch_choices.currentText() if self.batch_stack.currentIndex() else self.batch_text.toPlainText()
        self.apply_change(self.selected_rows(), self.batch_field.currentData(), value)

    def choose_color(self):
        from .color_picker import ColorPicker
        dialog = ColorPicker(self, self.batch_text.toPlainText())
        try:
            if dialog.exec() == QDialog.Accepted:self.batch_text.setPlainText(dialog.value)
        finally:dialog.deleteLater()

    def manage_helpers(self):
        from .method_manager import MethodManagerDialog
        self.table.clearFocus()
        if self.invalid_cells:
            self.error.setText('赤いセルの入力を修正してから補助メソッド管理を開いてください。');return
        dialog = MethodManagerDialog(self, self.draft)
        try:
            if dialog.exec() == QDialog.Accepted:self.draft = dialog.result_form;self.reload()
        finally:dialog.deleteLater()

    def accept(self):
        self.table.clearFocus()
        if self.invalid_cells:
            row, key = next(iter(self.invalid_cells))
            self.error.setText(f'{self.draft.gadgets[row].name}: {FIELDS[key]}の赤いセルを修正してください。列を切り替えても入力は保持しています。');return
        candidate = copy.deepcopy(self.draft)
        try:
            candidate.validate()
            from .method_output import check_editable_code
            check_editable_code(candidate)
        except ValueError as error:self.error.setText(str(error));return
        self.result_form = candidate;super().accept()
