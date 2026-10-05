"""Project variable and object name editor."""
import copy
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QTabWidget,
    QTableWidget,QTableWidgetItem,QHeaderView,QPushButton,QCheckBox,QInputDialog)
from .names import actual_name,reference_locations,rename


class ValueEditor(QLineEdit):
    focused = Signal()

    def focusInEvent(self,event):
        super().focusInEvent(event);self.focused.emit()


class NameManager(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner; self.draft = copy.deepcopy(owner.form)
        self.setWindowTitle('変数・オブジェクト名管理'); self.resize(900,620)
        layout = QVBoxLayout(self)
        self.search = QLineEdit();self.search.setPlaceholderText('名前・種類・親・参照先で検索')
        self.search.textChanged.connect(self.filter_rows);layout.addWidget(self.search)
        self.tabs = QTabWidget();layout.addWidget(self.tabs)
        self.variables = self.make_table(['変数名','初期値','参照箇所'])
        self.objects = self.make_table(['種類','オブジェクト名','PML名','親','参照箇所'])
        self.tabs.addTab(self.variables,'グローバル変数');self.tabs.addTab(self.objects,'オブジェクト')
        buttons = QHBoxLayout()
        for text,handler in (('+ 変数',self.add_variable),('変数削除',self.delete_variable),('名前変更',self.rename_selected)):
            button=QPushButton(text);button.clicked.connect(handler);buttons.addWidget(button)
        layout.addLayout(buttons)
        self.update_code=QCheckBox('コード内の !!変数 / !!フォーム / !THIS.部品 の参照も更新')
        self.update_code.setChecked(True);layout.addWidget(self.update_code)
        note=QLabel('親・相対配置・幅参照は常に更新します。コード内の置換は既知の参照表記に限定します。\n入力した変更は「適用」で反映します。適用後はメイン画面でUndoできます。')
        note.setWordWrap(True);layout.addWidget(note)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        footer=QHBoxLayout();footer.addStretch()
        apply=QPushButton('適用');apply.clicked.connect(self.apply_changes);footer.addWidget(apply)
        close=QPushButton('閉じる');close.clicked.connect(self.reject);footer.addWidget(close)
        layout.addLayout(footer);self.rebuild()

    def make_table(self, headers):
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    def locations(self, kind, name):
        values=reference_locations(self.draft,kind,name)
        return ' / '.join(f'{label} ({count})' for label,count in values) or 'なし'

    def item(self, text):
        item=QTableWidgetItem(text);item.setToolTip(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable);return item

    def rebuild(self):
        self.variables.setRowCount(0)
        for row,(name,value) in enumerate(self.draft.variables.items()):
            self.variables.insertRow(row);self.variables.setItem(row,0,self.item(name))
            editor=ValueEditor(value);editor.textEdited.connect(lambda text,n=name:self.set_value(n,text))
            editor.focused.connect(lambda r=row:self.variables.setCurrentCell(r,1))
            self.variables.setCellWidget(row,1,editor)
            self.variables.setItem(row,2,self.item(self.locations('variable',name)))
        self.object_keys=[('form',None),*[('gadget',i) for i in range(len(self.draft.gadgets))],*[('menu',i) for i in range(len(self.draft.menus))]]
        self.objects.setRowCount(len(self.object_keys))
        for row,(kind,key) in enumerate(self.object_keys):
            if kind=='form': name=self.draft.name;token='!!'+name;parent='';label='FORM'
            elif kind=='menu': name=self.draft.menus[key].name;token='.'+name;parent=self.draft.name;label='MENU'
            else:
                g=self.draft.gadgets[key];name=g.name;token=('.' if g.kind!='option' else '')+actual_name(g)
                parent=g.parent or self.draft.name;label=g.kind.upper()
            for column,value in enumerate((label,name,token,parent,self.locations(kind,actual_name(self.draft.gadgets[key]) if kind=='gadget' else name))):
                self.objects.setItem(row,column,self.item(value))
        self.filter_rows()

    def filter_rows(self, *args):
        query=self.search.text().lower()
        for table in (self.variables,self.objects):
            for row in range(table.rowCount()):
                values=[table.item(row,col).text() for col in range(table.columnCount()) if table.item(row,col)]
                if table is self.variables: values.append(table.cellWidget(row,1).text())
                table.setRowHidden(row,bool(query) and query not in ' '.join(values).lower())

    def set_value(self, name, text):
        self.draft.variables[name]=text

    def add_variable(self):
        used={name.lower() for name in self.draft.variables}|{self.draft.name.lower()};index=1
        while f'var{index}' in used:index+=1
        self.draft.variables[f'var{index}']='';self.tabs.setCurrentIndex(0);self.search.clear();self.rebuild()
        self.variables.setCurrentCell(self.variables.rowCount()-1,0)

    def delete_variable(self):
        row=self.variables.currentRow()
        if self.tabs.currentIndex()!=0 or row<0 or self.variables.isRowHidden(row):return
        name=self.variables.item(row,0).text()
        if reference_locations(self.draft,'variable',name):
            self.status.setText('使用中の変数です。コードの参照を削除してから変数を削除してください。');return
        del self.draft.variables[name];self.rebuild();self.status.clear()

    def rename_selected(self):
        if self.tabs.currentIndex()==0:
            row=self.variables.currentRow()
            if row<0 or self.variables.isRowHidden(row):return
            kind='variable';key=self.variables.item(row,0).text();old=key
        else:
            row=self.objects.currentRow()
            if row<0 or self.objects.isRowHidden(row):return
            kind,key=self.object_keys[row];old=self.objects.item(row,1).text()
        name,ok=QInputDialog.getText(self,'名前変更','新しい名前',text=old)
        if ok:self.rename_entry(kind,key,name)

    def rename_entry(self, kind, key, name):
        try:self.draft=rename(self.draft,kind,key,name,self.update_code.isChecked())
        except ValueError as error:self.status.setText(str(error));return False
        self.rebuild();self.status.setText('名前と参照を更新しました。「適用」で反映します。');return True

    def apply_changes(self):
        try:self.draft.validate()
        except ValueError as error:self.status.setText(str(error));return False
        if self.owner.form!=self.draft:
            self.owner.checkpoint();self.owner.form=copy.deepcopy(self.draft);self.owner.refresh()
        self.status.setText('適用しました。保存はメイン画面の「保存」で行います。');return True
