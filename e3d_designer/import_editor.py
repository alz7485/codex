"""Edit source that cannot be represented by gadget properties, transactionally."""
import copy
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTabWidget, QPlainTextEdit, QComboBox, QCheckBox, QDialogButtonBox)
from .mac_import import split_methods
from .pml_syntax import has_code
from .highlighting import PmlHighlighter


class ImportCodeDialog(QDialog):
    def __init__(self, parent, form):
        super().__init__(parent)
        self.draft=copy.deepcopy(form);self.result_form=None
        self.setWindowTitle('取り込みコード');self.resize(780,520)
        layout=QVBoxLayout(self)
        note=QLabel('部品の項目に変換できない処理を保持します。元コード優先では、選択肢などの初期化もこのコードで管理します。')
        note.setWordWrap(True);layout.addWidget(note)
        controls=QHBoxLayout();self.mode=QComboBox()
        self.mode.addItem('部品から初期化を生成＋追加コード','GENERATED')
        self.mode.addItem('元のコンストラクタを優先','SOURCE')
        self.mode.setCurrentIndex(self.mode.findData(form.constructor_mode))
        controls.addWidget(self.mode)
        self.auto_default=QCheckBox('初期値のDEFAULTを自動呼び出し')
        self.auto_default.setChecked(form.auto_default);controls.addWidget(self.auto_default)
        layout.addLayout(controls);tabs=QTabWidget();layout.addWidget(tabs)
        self.editors={};self.highlighters=[]
        extras='\n\n'.join(f'Define Method .{m.name}{m.signature}\n{m.body}\nEndmethod' for m in form.extra_methods)
        for key,title,value in (('preamble_code','フォーム定義前',form.preamble_code),
                                ('constructor_body','コンストラクタ',form.constructor_body),
                                ('extra_methods','その他のメソッド',extras)):
            editor=QPlainTextEdit(value);self.editors[key]=editor;tabs.addTab(editor,title)
            editor.setStyleSheet('font-family: monospace; font-size: 12px;')
            highlighter=PmlHighlighter(editor.document());highlighter.set_symbols(form)
            self.highlighters.append(highlighter)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def accept(self):
        candidate=copy.deepcopy(self.draft)
        try:
            remaining,methods,_=split_methods(self.editors['extra_methods'].toPlainText())
            if has_code(remaining):raise ValueError('その他のメソッドにはDefine Method〜Endmethodの定義を入力してください。')
            # Keep comments outside methods with the preamble instead of dropping them.
            candidate.preamble_code=self.editors['preamble_code'].toPlainText()
            if remaining.strip():candidate.preamble_code+='\n'+remaining
            candidate.constructor_body=self.editors['constructor_body'].toPlainText()
            candidate.constructor_mode=self.mode.currentData()
            candidate.auto_default=self.auto_default.isChecked()
            candidate.extra_methods=methods
            candidate.validate();candidate.pml()
        except ValueError as error:
            self.error.setText(str(error));return
        self.result_form=candidate;super().accept()
