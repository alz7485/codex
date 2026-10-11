"""Configure a PML.NET recipe and review its generated PML before insertion."""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QPlainTextEdit, QLabel, QDoubleSpinBox, QCheckBox, QDialogButtonBox,
    QSplitter, QWidget, QScrollArea)
from .highlighting import PmlHighlighter
from .model import Form
from .net_components import (NetComponentSpec, RECIPES, CONTAINERS,
                             DEFAULT_CONNECTIONS, available_name)


class NetComponentWizard(QDialog):
    def __init__(self, parent, form):
        super().__init__(parent)
        self.form = form
        self.result_gadget = None
        self.loading = False
        self.setWindowTitle('.NET部品を作成 — E3D 4.0向け')
        self.resize(960, 700)
        layout = QVBoxLayout(self)
        note = QLabel('用途を選び、設定を入力して追加します。生成コードを右側で確認できます。\n'
                      'DLLはE3D側に必要です。公開資料の構成を基に生成し、4.0実機での接続は未検証です。')
        note.setWordWrap(True); layout.addWidget(note)
        splitter = QSplitter(); layout.addWidget(splitter, 1)
        panel = QWidget(); fields = QFormLayout(panel)
        self.fields = fields
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(panel)
        splitter.addWidget(scroll)
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True)
        self.highlighter = PmlHighlighter(self.preview.document())
        splitter.addWidget(self.preview); splitter.setSizes([440, 520])
        self.recipe = QComboBox()
        for key, title, _ in RECIPES: self.recipe.addItem(title, key)
        fields.addRow('作るもの', self.recipe)
        self.description = QLabel(); self.description.setWordWrap(True)
        fields.addRow(self.description)
        self.name = QLineEdit(); fields.addRow('部品名', self.name)
        self.label = QLineEdit(); fields.addRow('表示名', self.label)
        self.width = QDoubleSpinBox(); self.width.setRange(1, 300); self.width.setValue(36)
        self.height = QDoubleSpinBox(); self.height.setRange(1, 300); self.height.setValue(9)
        fields.addRow('幅（文字単位）', self.width); fields.addRow('高さ（行単位）', self.height)
        self.assembly = QLineEdit(); fields.addRow('DLL／アセンブリ名', self.assembly)
        self.namespace = QLineEdit(); fields.addRow('名前空間', self.namespace)
        self.control_type = QLineEdit(); fields.addRow('コントロール型', self.control_type)
        self.connection_note = QLabel('E3D側の部品に合わせて変更できます。DLL名は拡張子なし、または読込可能なパスを指定します。')
        self.connection_note.setWordWrap(True); fields.addRow(self.connection_note)
        self.data_source = QComboBox()
        self.data_source.addItem('手入力した行データ', 'ROWS')
        self.data_source.addItem('現在要素の直属の配下（Name／Type）', 'MEMBERS')
        fields.addRow('表のデータ元', self.data_source)
        self.headings = QPlainTextEdit('Name\nType'); self.headings.setMaximumHeight(75)
        fields.addRow('列見出し（1行1列）', self.headings)
        self.rows = QPlainTextEdit('Sample-1\tEQUI\nSample-2\tPIPE')
        self.rows.setPlaceholderText('列はTabで区切り、1行を1件として入力します。空欄なら見出しだけ作ります。')
        self.rows.setMaximumHeight(95); fields.addRow('行データ（Tab区切り）', self.rows)
        self.single = QCheckBox('行の選択を1行に限定する'); fields.addRow(self.single)
        self.mode = QComboBox(); self.mode.addItem('開く', 'OPEN'); self.mode.addItem('保存', 'SAVE')
        fields.addRow('ファイル選択の用途', self.mode)
        self.directory = QLineEdit(); fields.addRow('初期フォルダー', self.directory)
        self.seed = QLineEdit(); fields.addRow('初期ファイル名', self.seed)
        self.file_filter = QLineEdit('All files (*.*)|*.*'); fields.addRow('フィルター', self.file_filter)
        self.setup_code = QPlainTextEdit(); self.setup_code.setMaximumHeight(100)
        self.setup_code.setPlaceholderText('コンテナ接続後に実行するPML。!this.部品名Controlから部品を操作できます。')
        fields.addRow('追加の初期化コード', self.setup_code)
        self.error = QLabel(); self.error.setWordWrap(True); self.error.setStyleSheet('color: #b42318')
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('フォームへ追加')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.recipe.currentIndexChanged.connect(self.select_recipe)
        for editor in (self.name, self.label, self.assembly, self.namespace, self.control_type,
                       self.directory, self.seed, self.file_filter): editor.textChanged.connect(self.update_preview)
        for editor in (self.headings, self.rows, self.setup_code): editor.textChanged.connect(self.update_preview)
        self.mode.currentIndexChanged.connect(self.update_preview)
        self.data_source.currentIndexChanged.connect(self.select_data_source)
        self.single.toggled.connect(self.update_preview)
        self.width.valueChanged.connect(self.update_preview); self.height.valueChanged.connect(self.update_preview)
        self.select_recipe()

    def select_recipe(self, *_):
        self.loading = True
        kind = self.recipe.currentData()
        self.description.setText(next(note for key, _, note in RECIPES if key == kind))
        base = {'grid': 'netGrid', 'file': 'chooseFile', 'mydata': 'addMyData',
                'flexible': 'netTree', 'dimension': 'netDimension', 'custom': 'netControl'}[kind]
        self.name.setText(available_name(self.form, base))
        self.label.setText({'grid': 'Results', 'file': 'Choose file', 'mydata': 'Add to My Data',
                            'flexible': 'Tree', 'dimension': 'Dimensions', 'custom': 'External control'}[kind])
        for editor, value in zip((self.assembly, self.namespace, self.control_type),
                                 DEFAULT_CONNECTIONS.get(kind, ('', '', ''))): editor.setText(value)
        container = kind in CONTAINERS
        self.width.setValue(36 if container else 18); self.height.setValue(9 if container else 1)
        self.setup_code.clear()
        self.fields.setRowVisible(self.height, container)
        for editor in (self.assembly, self.namespace, self.control_type, self.connection_note, self.setup_code):
            self.fields.setRowVisible(editor, container)
        for editor in (self.data_source, self.headings, self.rows, self.single): self.fields.setRowVisible(editor, kind == 'grid')
        for editor in (self.mode, self.directory, self.seed, self.file_filter): self.fields.setRowVisible(editor, kind == 'file')
        self.loading = False
        self.select_data_source()
        self.update_preview()

    def select_data_source(self, *_):
        manual = self.recipe.currentData() == 'grid' and self.data_source.currentData() == 'ROWS'
        for editor in (self.headings, self.rows): self.fields.setRowVisible(editor, manual)
        self.update_preview()

    def spec(self):
        return NetComponentSpec(recipe=self.recipe.currentData(), name=self.name.text().strip(),
            label=self.label.text(), width=self.width.value(), height=self.height.value(),
            assembly=self.assembly.text(), namespace=self.namespace.text(), control_type=self.control_type.text(),
            headings=self.headings.toPlainText().splitlines(),
            rows=[row.split('\t') for row in self.rows.toPlainText().splitlines()], single=self.single.isChecked(),
            data_source=self.data_source.currentData(),
            mode=self.mode.currentData(), directory=self.directory.text(), seed=self.seed.text(),
            file_filter=self.file_filter.text(), setup_code=self.setup_code.toPlainText())

    def candidate(self):
        from .app import Window
        g = self.spec().gadget()
        if any(name.casefold() in Window.reserved_names(self.form)
               for name in (g.name, g.name + ('Control' if g.kind == 'container' else 'Click'))):
            raise ValueError('部品名または生成するメンバー／メソッド名が使用済みです。別の部品名を指定してください。')
        preview = Form(name='netDemo', title='NET component', gadgets=[g],
                       width=min(300, max(70, g.width + 4)), height=min(300, max(22, g.height + 3)))
        from .method_output import check_editable_code
        check_editable_code(preview)
        return g, preview.pml()

    def update_preview(self, *_):
        if self.loading: return
        try:
            _, code = self.candidate()
        except ValueError as error:
            self.error.setText(str(error)); self.preview.clear(); return
        self.error.clear(); self.preview.setPlainText(code)

    def accept(self):
        try: self.result_gadget, _ = self.candidate()
        except ValueError as error: self.error.setText(str(error)); return
        super().accept()
