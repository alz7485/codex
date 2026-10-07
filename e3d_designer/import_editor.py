"""Edit source that cannot be represented by gadget properties, transactionally."""
import copy
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTabWidget, QPlainTextEdit, QComboBox, QCheckBox, QDialogButtonBox)
from .mac_import import split_methods
from .pml_syntax import has_code
from .method_output import check_editable_code
from .highlighting import PmlHighlighter


class ImportCodeDialog(QDialog):
    def __init__(self, parent, form):
        super().__init__(parent)
        self.draft=copy.deepcopy(form);self.result_form=None
        self.setWindowTitle('取り込みコード');self.resize(780,520)
        layout=QVBoxLayout(self)
        note=QLabel('部品の項目に変換できない処理を保持します。元コード優先では、選択肢などの初期化もこのコードで管理します。')
        note.setWordWrap(True);layout.addWidget(note)
        program_note=QLabel('表示プログラムはSHOWを含め、元の順序で出力します。' if form.program_mode=='SOURCE' else '表示プログラムは、自動生成するSHOWの後へ追加します。')
        program_note.setWordWrap(True);layout.addWidget(program_note)
        controls=QHBoxLayout();self.mode=QComboBox()
        self.mode.addItem('部品から初期化を生成＋追加コード','GENERATED')
        self.mode.addItem('元のコンストラクタを優先','SOURCE')
        self.mode.setCurrentIndex(self.mode.findData(form.constructor_mode))
        controls.addWidget(self.mode)
        self.auto_default=QCheckBox('初期値のDEFAULTを自動呼び出し')
        self.auto_default.setChecked(form.auto_default);controls.addWidget(self.auto_default)
        layout.addLayout(controls);tabs=QTabWidget();layout.addWidget(tabs)
        self.default_mode=QComboBox()
        self.default_mode.addItem('DEFAULT：部品の初期値を生成＋追加コード','GENERATED')
        self.default_mode.addItem('DEFAULT：元コードのみ（初期値はDEFAULT欄で編集）','SOURCE')
        self.default_mode.setCurrentIndex(self.default_mode.findData(form.default_mode))
        layout.insertWidget(2,self.default_mode)
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.default_mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()
        self.editors={};self.highlighters=[]
        extras='\n\n'.join(f'Define Method .{m.name}{m.signature}\n{m.body}\nEndmethod' for m in form.extra_methods)
        for key,title,value in (('preamble_code','フォーム定義前',form.preamble_code),
                                ('constructor_body','コンストラクタ',form.constructor_body),
                                ('default_body','DEFAULT',form.default_body or next((g.body for g in form.gadgets if g.callback.lower()=='default' and g.body),'')),
                                ('after_show_code','表示プログラム',form.after_show_code),
                                ('extra_methods','その他のメソッド',extras)):
            editor=QPlainTextEdit(value);self.editors[key]=editor;tabs.addTab(editor,title)
            editor.setStyleSheet('font-family: monospace; font-size: 12px;')
            highlighter=PmlHighlighter(editor.document());highlighter.set_symbols(form)
            self.highlighters.append(highlighter)
        if form.partial_import_source:
            for title,value in (('省略理由','\n'.join(form.partial_import_notes)),
                                ('元MAC（参照用）',form.partial_import_source)):
                editor=QPlainTextEdit(value);editor.setReadOnly(True);tabs.addTab(editor,title)
                if title.startswith('元MAC'):
                    highlighter=PmlHighlighter(editor.document());self.highlighters.append(highlighter)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def update_mode(self):
        self.auto_default.setEnabled(self.mode.currentData()=='GENERATED' and self.default_mode.currentData()=='GENERATED')
        self.auto_default.setToolTip('元コードを保持中は、コンストラクタ欄の呼び出しを編集してください。' if not self.auto_default.isEnabled() else '')

    def accept(self):
        candidate=copy.deepcopy(self.draft)
        try:
            remaining,methods,_=split_methods(self.editors['extra_methods'].toPlainText())
            if has_code(remaining):raise ValueError('その他のメソッドにはDefine Method〜Endmethodの定義を入力してください。')
            # Keep comments outside methods with the preamble instead of dropping them.
            candidate.preamble_code=self.editors['preamble_code'].toPlainText()
            if remaining.strip():candidate.preamble_code+='\n'+remaining
            candidate.constructor_body=self.editors['constructor_body'].toPlainText()
            candidate.default_body=self.editors['default_body'].toPlainText()
            candidate.after_show_code=self.editors['after_show_code'].toPlainText()
            for gadget in candidate.gadgets:
                if gadget.callback.lower()=='default':gadget.body=''
            candidate.constructor_mode=self.mode.currentData()
            candidate.default_mode=self.default_mode.currentData()
            candidate.auto_default=self.auto_default.isChecked()
            candidate.extra_methods=methods
            candidate.validate();check_editable_code(candidate)
        except ValueError as error:
            self.error.setText(str(error));return
        self.result_form=candidate;super().accept()
