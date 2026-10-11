"""A short guided workflow for creating toolbar buttons."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QFormLayout, QComboBox, QLineEdit, QLabel, QCheckBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QPushButton, QSpinBox,
    QPlainTextEdit, QFileDialog)
from .highlighting import PmlHighlighter
from .toolbar_builder import ACTIONS, ToolbarSpec, ToolbarButtonSpec, available_name, navigation_buttons


class ToolbarDialog(QWizard):
    def __init__(self, parent, form):
        super().__init__(parent)
        self.form = form
        self.result_form = None
        self.result_frame = None
        self.loading = False
        self.setWindowTitle('ツールバーを簡単作成')
        self.resize(920, 680)
        self.setWizardStyle(QWizard.ModernStyle)
        for button, text in ((QWizard.BackButton, '戻る'), (QWizard.NextButton, '次へ'),
                             (QWizard.FinishButton, '追加する'), (QWizard.CancelButton, 'キャンセル')):
            self.setButtonText(button, text)

        page = QWizardPage(); page.setTitle('1 / 3　形式を選ぶ')
        page.setSubTitle('ツールバーは、よく使う操作を横一列のボタンにしてすぐ実行するためのものです。')
        layout = QVBoxLayout(page); fields = QFormLayout(); layout.addLayout(fields)
        self.style = QComboBox()
        self.style.addItem('通常フォーム内のボタン列（FRAME）', 'ROW')
        self.style.addItem('MAINフォーム用の標準ツールバー（TOOLBAR）', 'TOOLBAR')
        self.style.setCurrentIndex(self.style.findData('TOOLBAR' if form.form_type=='MAIN' else 'ROW'))
        fields.addRow('作成する形式', self.style)
        self.frame_name = QLineEdit(available_name(form)); fields.addRow('部品名（英数字）', self.frame_name)
        self.label = QLineEdit('Tools'); fields.addRow('表示名', self.label)
        self.convert = QCheckBox('現在のフォームをMAINに変更して追加する')
        fields.addRow(self.convert)
        self.type_note = QLabel(); self.type_note.setWordWrap(True); layout.addWidget(self.type_note)
        guide = QLabel('次の画面でボタンの表示名と処理を設定します。\n'
                       '最後に配置内容と生成コードを確認して追加します。追加全体を1回の取り消しで戻せます。')
        guide.setWordWrap(True); layout.addWidget(guide); layout.addStretch()
        self.type_error = QLabel(); self.type_error.setWordWrap(True)
        self.type_error.setStyleSheet('color: #b42318'); layout.addWidget(self.type_error)
        self.addPage(page)

        page = QWizardPage(); page.setTitle('2 / 3　ボタンを設定する')
        page.setSubTitle('上から順に左→右へ配置します。ボタンを選ぶと、下で処理を編集できます。')
        layout = QVBoxLayout(page)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['ボタンの表示名', '行う処理', '幅'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)
        controls = QHBoxLayout(); layout.addLayout(controls)
        for text, callback in (('ボタンを追加', self.add_button), ('選択行を削除', self.remove_button),
                               ('↑ 上へ', lambda: self.move_button(-1)), ('↓ 下へ', lambda: self.move_button(1)),
                               ('CEナビのサンプルを追加', self.add_navigation)):
            button = QPushButton(text); button.clicked.connect(callback); controls.addWidget(button)
        self.action_note = QLabel(); self.action_note.setWordWrap(True); layout.addWidget(self.action_note)
        self.details = QFormLayout(); layout.addLayout(self.details)
        self.body = QPlainTextEdit(); self.body.setMaximumHeight(145)
        self.body_highlighter = PmlHighlighter(self.body.document())
        self.details.addRow('処理メソッドの本文', self.body)
        self.macro_path = QLineEdit(); self.details.addRow('外部マクロのパス', self.macro_path)
        self.browse = QPushButton('マクロファイルを選ぶ…'); self.browse.clicked.connect(self.choose_macro)
        self.details.addRow(self.browse)
        self.button_error = QLabel(); self.button_error.setWordWrap(True)
        self.button_error.setStyleSheet('color: #b42318'); layout.addWidget(self.button_error)
        self.addPage(page)

        page = QWizardPage(); page.setTitle('3 / 3　確認して追加する')
        page.setSubTitle('生成内容を確認してください。「戻る」で設定を変更できます。')
        layout = QVBoxLayout(page)
        self.summary = QLabel(); self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True); layout.addWidget(self.preview, 1)
        self.highlighter = PmlHighlighter(self.preview.document()); self.highlighter.set_symbols(form)
        self.review_error = QLabel(); self.review_error.setWordWrap(True)
        self.review_error.setStyleSheet('color: #b42318'); layout.addWidget(self.review_error)
        self.addPage(page)

        self.style.currentIndexChanged.connect(self.update_type)
        self.table.currentCellChanged.connect(self.select_button)
        self.body.textChanged.connect(self.save_details)
        self.macro_path.textChanged.connect(self.save_details)
        self.currentIdChanged.connect(self.update_page)
        self.append_button(ToolbarButtonSpec()); self.table.setCurrentCell(0, 0)
        self.update_type()

    def update_type(self, *_):
        toolbar = self.style.currentData() == 'TOOLBAR'
        self.convert.setVisible(toolbar and self.form.form_type != 'MAIN')
        self.type_note.setText(
            '標準TOOLBARはMAIN専用です。E3Dのメニューバーを持つモジュール用で、リボンのタブ式メニューでは使用できません。\n'
            'E3D側でアプリケーションへの登録が必要です。この画面ではフォームと操作メソッドを作成します。\n'
            'MAINへ変更する場合、配置済みの部品が対応しているか確認し、ドッキングを解除します。\n'
            'MACにはSHOWも出力します。実際の表示・登録方法はE3D側のアプリケーションに合わせてください。'
            if toolbar else
            '通常のDIALOGフォームに横一列のボタンを追加します。現在のフォーム形式を保ち、空いている場所へ配置します。\n'
            'E3D 4.0のリボン用ボタンを登録する機能とは別の、フォーム内で使う操作ボタン列です。')
        self.type_error.clear()

    def append_button(self, spec):
        row = self.table.rowCount(); self.table.insertRow(row)
        item = QTableWidgetItem(spec.label)
        item.setData(Qt.UserRole, {'body': spec.body, 'macro_path': spec.macro_path})
        self.table.setItem(row, 0, item)
        action = QComboBox()
        for key, title, _ in ACTIONS: action.addItem(title, key)
        action.setCurrentIndex(action.findData(spec.action)); self.table.setCellWidget(row, 1, action)
        action.currentIndexChanged.connect(self.select_button)
        width = QSpinBox(); width.setRange(4, 80); width.setValue(spec.width)
        self.table.setCellWidget(row, 2, width)

    def buttons(self):
        result = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0); data = item.data(Qt.UserRole)
            result.append(ToolbarButtonSpec(item.text(), self.table.cellWidget(row, 1).currentData(),
                self.table.cellWidget(row, 2).value(), data['body'], data['macro_path']))
        return result

    def add_button(self, *_):
        if self.table.rowCount() >= 16:
            self.button_error.setText('ボタンは16個までです。'); return
        self.append_button(ToolbarButtonSpec()); self.table.setCurrentCell(self.table.rowCount()-1, 0)

    def add_navigation(self, *_):
        if self.table.rowCount()+3 > 16:
            self.button_error.setText('ナビの3ボタンを追加するには空きを3個分用意してください。'); return
        for spec in navigation_buttons(): self.append_button(spec)
        self.table.setCurrentCell(self.table.rowCount()-3, 0)

    def remove_button(self, *_):
        row = self.table.currentRow()
        if row >= 0: self.table.removeRow(row)
        if self.table.rowCount(): self.table.setCurrentCell(min(max(row,0), self.table.rowCount()-1), 0)
        self.select_button()

    def move_button(self, delta):
        row = self.table.currentRow(); target = row+delta
        if not 0 <= row < self.table.rowCount() or not 0 <= target < self.table.rowCount(): return
        specs = self.buttons(); specs[row], specs[target] = specs[target], specs[row]
        self.loading = True; self.table.setRowCount(0)
        for spec in specs: self.append_button(spec)
        self.loading = False; self.table.setCurrentCell(target, 0); self.select_button()

    def select_button(self, *_):
        if self.loading: return
        row = self.table.currentRow(); self.loading = True
        valid = row >= 0 and self.table.item(row, 0) is not None and self.table.cellWidget(row, 1) is not None
        action = self.table.cellWidget(row, 1).currentData() if valid else ''
        data = self.table.item(row, 0).data(Qt.UserRole) if valid else {'body':'', 'macro_path':''}
        self.body.setPlainText(data['body']); self.macro_path.setText(data['macro_path'])
        self.action_note.setText(next((note for key, _, note in ACTIONS if key==action), 'ボタンを追加してください。'))
        self.details.setRowVisible(self.body, action=='custom')
        self.details.setRowVisible(self.macro_path, action=='macro')
        self.details.setRowVisible(self.browse, action=='macro')
        self.button_error.clear(); self.loading = False

    def save_details(self):
        if self.loading: return
        row = self.table.currentRow()
        if row >= 0:
            self.table.item(row, 0).setData(Qt.UserRole,
                {'body': self.body.toPlainText(), 'macro_path': self.macro_path.text()})

    def choose_macro(self):
        filename, _ = QFileDialog.getOpenFileName(self, '実行する外部マクロ', self.macro_path.text(),
                                                'PMLマクロ (*.mac *.MAC);;すべてのファイル (*)')
        if filename: self.macro_path.setText(filename)

    def spec(self):
        return ToolbarSpec(self.frame_name.text().strip(), self.label.text(), self.style.currentData(),
                           self.convert.isChecked(), self.buttons())

    def validateCurrentPage(self):
        if self.currentId() == 0:
            if self.style.currentData() == 'TOOLBAR' and self.form.form_type!='MAIN' and not self.convert.isChecked():
                self.type_error.setText('標準TOOLBARにはMAINへの変更にチェックを入れてください。'); return False
            if self.style.currentData() == 'ROW' and self.form.form_type=='MAIN':
                self.type_error.setText('MAINでは標準TOOLBARを選んでください。'); return False
        elif self.currentId() == 1:
            try: self.spec().build(self.form)
            except ValueError as error: self.button_error.setText(str(error)); return False
        return True

    def update_page(self, page):
        if page != 2: return
        try:
            candidate, index = self.spec().build(self.form)
            labels = ' → '.join(button.label for button in self.buttons())
            converted = '\nフォームをMAINへ変更し、ドッキングを解除します。' if candidate.form_type!=self.form.form_type else ''
            self.summary.setText(f'{candidate.gadgets[index].frame_style} .{candidate.gadgets[index].name} ／ ボタン {len(self.buttons())}個\n'
                + labels + converted + '\n追加後はボタンを選んで「動作」で処理を編集できます。')
            self.preview.setPlainText(candidate.pml()); self.review_error.clear()
        except ValueError as error:
            self.preview.clear(); self.review_error.setText(str(error))

    def accept(self):
        try: self.result_form, self.result_frame = self.spec().build(self.form)
        except ValueError as error: self.review_error.setText(str(error)); return
        super().accept()
