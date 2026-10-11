"""Reviewable recipes for processing existing database selector gadgets."""
from dataclasses import replace
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QPlainTextEdit, QLabel, QCheckBox, QDialogButtonBox,
    QSplitter, QWidget, QScrollArea)
from .highlighting import PmlHighlighter
from .selector_methods import RECIPES, SelectorMethodSpec, unique_name
from .callbacks import callback_body
from .pml_syntax import has_code


class SelectorMethodDialog(QDialog):
    def __init__(self, parent, form, selected=None):
        super().__init__(parent)
        self.form = form
        self.result_form = None
        self.result_selector = None
        self.loading = True
        self.setWindowTitle('DBセレクタのメソッドを簡単作成')
        self.resize(980, 690)
        layout = QVBoxLayout(self)
        note = QLabel('対象と用途を選ぶと、選択要素を処理するPMLメソッドを作ります。\n'
                      '1件処理へ !element（DBREF）を渡します。選択範囲・単一／複数は対象の設定を使います。')
        note.setWordWrap(True); layout.addWidget(note)
        splitter = QSplitter(); layout.addWidget(splitter, 1)
        panel = QWidget(); self.fields = QFormLayout(panel)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(panel); splitter.addWidget(scroll)
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True); splitter.addWidget(self.preview)
        self.highlighter = PmlHighlighter(self.preview.document()); self.highlighter.set_symbols(form)
        splitter.setSizes([410, 570])
        self.target = QComboBox()
        for index, gadget in enumerate(form.gadgets):
            if gadget.kind == 'selector': self.target.addItem(f'{gadget.label} (.{gadget.name})', index)
        self.fields.addRow('対象のDBセレクタ', self.target)
        if selected is not None and self.target.findData(selected) >= 0:
            self.target.setCurrentIndex(self.target.findData(selected))
        self.target_info = QLabel(); self.target_info.setWordWrap(True); self.fields.addRow(self.target_info)
        self.recipe = QComboBox()
        for key, title, _ in RECIPES: self.recipe.addItem(title, key)
        self.fields.addRow('行う処理', self.recipe)
        self.description = QLabel(); self.description.setWordWrap(True); self.fields.addRow(self.description)
        self.method_name = QLineEdit(); self.fields.addRow('処理メソッド名', self.method_name)
        self.trigger = QComboBox()
        self.trigger.addItem('処理ボタンを追加して実行', 'BUTTON')
        self.trigger.addItem('選択が変わったときに実行', 'SELECTION')
        self.fields.addRow('実行方法', self.trigger)
        self.button_label = QLineEdit('Process selected'); self.fields.addRow('処理ボタンの表示名', self.button_label)
        self.refresh = QCheckBox('一覧の更新ボタンも追加する'); self.refresh.setChecked(True); self.fields.addRow(self.refresh)
        self.report_name = QCheckBox('名前（NAME）'); self.report_name.setChecked(True); self.fields.addRow(self.report_name)
        self.report_type = QCheckBox('種類（TYPE）'); self.report_type.setChecked(True); self.fields.addRow(self.report_type)
        self.report_owner = QCheckBox('直属の上位要素（OWNER）'); self.fields.addRow(self.report_owner)
        self.custom_body = QPlainTextEdit(); self.custom_body.setMaximumHeight(220)
        self.custom_body.setPlaceholderText('!element が選択要素のDBREFです。\n例: !owner = !element.owner\n本文だけを入力してください。')
        self.custom_highlighter = PmlHighlighter(self.custom_body.document())
        self.fields.addRow('1件ごとに実行するPML', self.custom_body)
        self.replace_existing = QCheckBox('既存の選択時処理をこの処理に置き換える')
        self.fields.addRow(self.replace_existing)
        self.error = QLabel(); self.error.setWordWrap(True); self.error.setStyleSheet('color: #b42318'); layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('メソッドを追加')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.target.currentIndexChanged.connect(self.select_target)
        self.recipe.currentIndexChanged.connect(self.update_fields)
        self.trigger.currentIndexChanged.connect(self.update_fields)
        for editor in (self.method_name, self.button_label): editor.textChanged.connect(self.update_preview)
        self.custom_body.textChanged.connect(self.update_preview)
        for editor in (self.refresh, self.report_name, self.report_type, self.report_owner, self.replace_existing):
            editor.toggled.connect(self.update_preview)
        self.select_target()
        self.loading = False; self.update_fields()

    def select_target(self, *_):
        previous = self.loading; self.loading = True
        self.method_name.setText(unique_name(self.form, 'processSelector', ('Element',)))
        self.replace_existing.setChecked(False)
        index = self.target.currentData()
        if index is not None:
            gadget = self.form.gadgets[index]
            self.target_info.setText('表示範囲: '+gadget.database+' ／ '+
                ('単一選択（SINGLE）' if gadget.selection_mode == 'SINGLE' else '複数選択（MULTIPLE）'))
        else: self.target_info.setText('先に「その他 → DBセレクタ」で部品を追加してください。')
        self.loading = previous
        if not self.loading: self.update_fields()

    def update_fields(self, *_):
        if self.loading: return
        kind = self.recipe.currentData()
        self.description.setText(next(note for key, _, note in RECIPES if key == kind))
        button = self.trigger.currentData() == 'BUTTON'
        self.fields.setRowVisible(self.button_label, button)
        for editor in (self.report_name, self.report_type, self.report_owner):
            self.fields.setRowVisible(editor, kind == 'report')
        self.fields.setRowVisible(self.custom_body, kind == 'custom')
        index = self.target.currentData()
        existing = index is not None and has_code(callback_body(self.form, self.form.gadgets[index]))
        self.fields.setRowVisible(self.replace_existing, not button and existing)
        self.update_preview()

    def spec(self):
        return SelectorMethodSpec(method_name=self.method_name.text().strip(), recipe=self.recipe.currentData(),
            trigger=self.trigger.currentData(), button_label=self.button_label.text(), refresh=self.refresh.isChecked(),
            report_name=self.report_name.isChecked(), report_type=self.report_type.isChecked(),
            report_owner=self.report_owner.isChecked(), custom_body=self.custom_body.toPlainText(),
            replace_existing=self.replace_existing.isChecked())

    def update_preview(self, *_):
        if self.loading: return
        try:
            spec = self.spec()
            # Display the proposed code before acknowledgement of replacement.
            candidate = replace(spec, replace_existing=True).build(self.form, self.target.currentData())
            self.preview.setPlainText(candidate.pml())
            index = self.target.currentData()
            replacing = (spec.trigger == 'SELECTION' and not spec.replace_existing
                         and has_code(callback_body(self.form, self.form.gadgets[index])))
            self.error.setText('適用するには、生成コードを確認して既存処理の置き換えにチェックを入れてください。' if replacing else '')
        except ValueError as error:
            self.preview.clear(); self.error.setText(str(error))

    def accept(self):
        try: self.result_form = self.spec().build(self.form, self.target.currentData())
        except ValueError as error: self.error.setText(str(error)); return
        self.result_selector = self.target.currentData()
        super().accept()
