"""Edit independent helper methods without moving gadget commands or defaults."""
import copy
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QListWidget,
    QLabel,QLineEdit,QPlainTextEdit,QPushButton,QDialogButtonBox)
from .model import Method,IDENTIFIER
from .mac_import import split_methods
from .names import code_slots,read_slot,write_slot
from .pml_syntax import has_code,method_call_sites
from .method_output import check_editable_code
from .highlighting import PmlHighlighter


def callers(form,name):
    return [label for label,owner,key in code_slots(form)
            if any(target.lower()==name.lower() for _,_,target in method_call_sites(read_slot(owner,key),form))]


def update_helpers(form,entries):
    """Apply additions, deletions and simultaneous renames transactionally."""
    candidate=copy.deepcopy(form)
    original={method.name.lower() for method in form.extra_methods}
    old_names=[old.lower() for old,_ in entries if old]
    if len(set(old_names))!=len(old_names) or any(name not in original for name in old_names):
        raise ValueError('編集元のメソッドが重複しているか、見つかりません。')
    methods=[copy.deepcopy(method) for _,method in entries]
    for method in methods:
        if not IDENTIFIER.fullmatch(method.name):raise ValueError('メソッド名は英字で始まる英数字・_ にしてください。')
        remaining,parsed,_=split_methods(f'Define Method .{method.name}{method.signature}\n{method.body}\nEndmethod')
        if len(parsed)!=1 or has_code(remaining):raise ValueError('本文に別のメソッド定義を入れないでください。')
    mapping={old:method.name for old,method in entries if old}
    mapping={name.lower():value for name,value in mapping.items()}
    candidate.extra_methods=methods
    for _,owner,key in code_slots(candidate):
        value=read_slot(owner,key)
        for start,end,name in reversed(method_call_sites(value,form)):
            if name.lower() in mapping:
                prefix=value[start:end].rsplit('.',1)[0]
                value=value[:start]+prefix+'.'+mapping[name.lower()]+value[end:]
        write_slot(owner,key,value)
    for removed in original-set(old_names):
        locations=callers(candidate,removed)
        if locations:raise ValueError('呼び出しが残るメソッドは削除できません: '+removed+'（'+', '.join(locations)+'）')
    candidate.validate();check_editable_code(candidate)
    return candidate


class MethodManagerDialog(QDialog):
    def __init__(self,parent,form):
        super().__init__(parent)
        self.form=copy.deepcopy(form);self.result_form=None
        self.entries=[(m.name,copy.deepcopy(m)) for m in form.extra_methods]
        self.loading=False;self.selected=None
        self.setWindowTitle('補助メソッド管理');self.resize(850,550)
        layout=QVBoxLayout(self)
        note=QLabel('初期値と各部品のコマンドは部品側で編集します。ここでは独立した補助メソッドを管理します。')
        note.setWordWrap(True);layout.addWidget(note)
        content=QHBoxLayout();layout.addLayout(content)
        left=QVBoxLayout();content.addLayout(left)
        self.list=QListWidget();self.list.setMaximumWidth(230);left.addWidget(self.list)
        actions=QHBoxLayout();left.addLayout(actions)
        add=QPushButton('追加');remove=QPushButton('削除');actions.addWidget(add);actions.addWidget(remove)
        right=QVBoxLayout();content.addLayout(right,1)
        fields=QFormLayout();right.addLayout(fields)
        self.name=QLineEdit();self.signature=QLineEdit()
        fields.addRow('名前',self.name);fields.addRow('引数・戻り値',self.signature)
        self.references=QLabel();self.references.setWordWrap(True);right.addWidget(self.references)
        self.body=QPlainTextEdit();right.addWidget(self.body)
        self.body.setStyleSheet('font-family: monospace; font-size: 12px;')
        self.highlighter=PmlHighlighter(self.body.document());self.highlighter.set_symbols(form)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);layout.addWidget(buttons)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        self.list.currentRowChanged.connect(self.select)
        self.name.textChanged.connect(self.edited);self.signature.textChanged.connect(self.edited)
        self.body.textChanged.connect(self.edited);add.clicked.connect(self.add);remove.clicked.connect(self.remove)
        self.rebuild()

    def rebuild(self,row=0):
        self.loading=True;self.list.clear()
        self.list.addItems([method.name for _,method in self.entries])
        self.loading=False;self.selected=None
        if self.entries:self.list.setCurrentRow(min(row,len(self.entries)-1))
        else:self.select(-1)

    def select(self,row):
        if self.loading:return
        self.loading=True;self.selected=row if 0<=row<len(self.entries) else None
        method=self.entries[row][1] if self.selected is not None else Method('',body='')
        self.name.setText(method.name);self.signature.setText(method.signature);self.body.setPlainText(method.body)
        for editor in (self.name,self.signature,self.body):editor.setEnabled(self.selected is not None)
        old=self.entries[row][0] if self.selected is not None else ''
        locations=callers(self.form,old) if old else []
        self.references.setText('呼び出しの参照候補: '+', '.join(locations) if locations
                                else '判別できる呼び出しなし（動的な呼び出しは未判定）')
        self.loading=False

    def edited(self):
        if self.loading or self.selected is None:return
        method=self.entries[self.selected][1]
        method.name=self.name.text();method.signature=self.signature.text();method.body=self.body.toPlainText()
        self.list.item(self.selected).setText(method.name)

    def add(self):
        occupied={m.name.lower() for _,m in self.entries}|{g.name.lower() for g in self.form.gadgets}
        occupied|={g.callback.lower() for g in self.form.gadgets}|{self.form.name.lower(),'default'}
        occupied|={m.name.lower() for m in self.form.extra_methods}
        occupied|={(g.table_method or 'populate_'+g.name).lower()
                   for g in self.form.gadgets if g.kind=='list' and g.list_mode=='TABLE'}
        number=1
        while 'helper'+str(number) in occupied:number+=1
        self.entries.append(('',Method('helper'+str(number))));self.rebuild(len(self.entries)-1)

    def remove(self):
        if self.selected is None:return
        row=self.selected;self.entries.pop(row);self.rebuild(row)

    def accept(self):
        try:self.result_form=update_helpers(self.form,self.entries)
        except ValueError as error:self.error.setText(str(error));return
        super().accept()
