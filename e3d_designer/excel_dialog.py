"""Choose the worksheet and mapping before replacing the item editor's draft."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QComboBox,QCheckBox,QLabel,QDialogButtonBox


class ExcelSheetDialog(QDialog):
    def __init__(self,parent,sheets,is_list=False):
        super().__init__(parent);self.setWindowTitle('Excelの読み込み設定');self.setMinimumWidth(360)
        layout=QVBoxLayout(self);fields=QFormLayout();layout.addLayout(fields)
        self.sheet=QComboBox();self.sheet.addItems(sheets);fields.addRow('シート',self.sheet)
        self.format=QComboBox(self);self.format.addItems(['表（複数列）','表示名 / 実値'])
        self.format.setVisible(is_list)
        if is_list:fields.addRow('リスト形式',self.format)
        self.header=QCheckBox('1行目を見出しとして読み込む');self.header.setChecked(is_list)
        fields.addRow('',self.header)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        self.is_list=is_list;self.format.currentIndexChanged.connect(self.update_note);self.update_note()
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def table_mode(self):return self.is_list and self.format.currentIndex()==0

    def update_note(self):
        self.note.setText('A1から表全体を読み込みます。見出しなしの場合は「列1、列2…」を自動設定します。既存の表は置き換わります。' if self.table_mode() else 'A列は表示名、B列は実値または項目編集画面で選んだコマンドです。B列は省略できます。既存の項目は置き換わります。')
