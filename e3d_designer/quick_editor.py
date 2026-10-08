"""Transactional compact gadget editor and spreadsheet item editor."""
import copy
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,
    QComboBox,QDoubleSpinBox,QPushButton,QDialogButtonBox,QTableWidget,QTableWidgetItem,QLabel,QCheckBox,QFileDialog)
from .names import rename
from .color_picker import ColorPicker
from .model import dimension_editable,normalize_dimensions,uses_pairs,supports_hidden,fixed_dimensions,supports_auto_width,uses_auto_width


class ItemsDialog(QDialog):
    def __init__(self,parent,gadget,initial_editable=True):
        super().__init__(parent)
        self.gadget=copy.deepcopy(gadget)
        self.setWindowTitle('項目・値の編集');self.resize(570,390)
        layout=QVBoxLayout(self);self.mode=QComboBox()
        if gadget.kind=='list':
            self.mode.addItems(['表示名 / 実値','表（複数列）'])
            self.mode.setCurrentIndex(int(gadget.list_mode=='TABLE'))
        elif uses_pairs(gadget):
            self.mode.addItems(['表示名 / コマンド','表示名 / 実値'])
            self.mode.setCurrentIndex(int(bool(gadget.item_values)))
        else:self.mode.addItems(['表示名 / 実値'])
        layout.addWidget(self.mode)
        self.table=QTableWidget();layout.addWidget(self.table)
        self._tables={};self._loaded_mode=None
        self.mode.currentIndexChanged.connect(self.load_table)
        self.load_table()
        tools=QHBoxLayout()
        for title,handler in [('＋行',self.add_row),('－行',self.remove_row),('＋列',self.add_column),('－列',self.remove_column)]:
            button=QPushButton(title);button.clicked.connect(handler);tools.addWidget(button)
            if '列' in title:button.setVisible(gadget.kind=='list')
        layout.addLayout(tools)
        self.excel_button=QPushButton('📊 Excelから読み込む…');self.excel_button.clicked.connect(self.import_excel)
        self.excel_button.setToolTip('.xlsxのA1から読み込み、確定前にこの表で編集できます。')
        layout.addWidget(self.excel_button)
        form=QFormLayout();self.initial=QLineEdit(gadget.initial)
        self.initial.setPlaceholderText('空欄、または行番号（1から）');form.addRow('初期選択',self.initial)
        self.initial.setEnabled(initial_editable)
        if not initial_editable:self.initial.setToolTip('「取り込みコード」のDEFAULT欄で編集してください。')
        self.selection=QComboBox();self.selection.addItems(['SINGLE','MULTIPLE'])
        self.selection.setCurrentText('MULTIPLE' if gadget.selection_mode=='MULTI' else gadget.selection_mode)
        if gadget.kind=='list':form.addRow('選択方式',self.selection)
        layout.addLayout(form);self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def is_table(self):return self.gadget.kind=='list' and self.mode.currentIndex()==1

    def import_excel(self):
        filename,_=QFileDialog.getOpenFileName(self,'Excelの表を読み込む','','Excel (*.xlsx)')
        if not filename:return
        self.load_excel(filename)

    def load_excel(self,filename):
        from .excel_import import ExcelBook
        from .excel_dialog import ExcelSheetDialog
        try:
            with ExcelBook(filename) as book:
                dialog=ExcelSheetDialog(self,book.sheets,self.gadget.kind=='list')
                try:
                    if dialog.exec()!=QDialog.Accepted:return
                    data=book.read(dialog.sheet.currentText())
                    self.apply_excel_data(data,dialog.table_mode(),dialog.header.isChecked())
                finally:dialog.deleteLater()
        except ValueError as error:self.error.setText(str(error));return
        self.error.setText('Excelの表を読み込みました。内容を確認してOKで確定してください。')

    def apply_excel_data(self,data,table_mode=False,first_row_header=False):
        from .model import literal,image_path_literal
        if not data or not data[0]:raise ValueError('読み込む表に値がありません。')
        columns=max(map(len,data))
        if table_mode and self.gadget.kind!='list':raise ValueError('複数列の表はLISTで指定してください。')
        if not table_mode and columns>2:raise ValueError('表示名／実値・コマンド形式はA・Bの2列までです。LISTでは「表（複数列）」を選んでください。')
        payload=[list(row)+['']*(columns-len(row)) for row in data]
        if table_mode:
            if not first_row_header:payload.insert(0,[f'列{i+1}' for i in range(columns)])
        else:
            if first_row_header:payload=payload[1:]
            payload=[row+['']*(2-len(row)) for row in payload];columns=2
        commands=uses_pairs(self.gadget) and self.mode.currentIndex()==0
        for r,row in enumerate(data,1):
            if first_row_header and not table_mode and r==1:continue
            for c,value in enumerate(row):
                field=f'Excel {chr(65+c) if c<26 else "列"+str(c+1)}{r}'
                image=not table_mode and c==0 and self.gadget.display_mode=='PIXMAP'
                if image:image_path_literal(value,field=field)
                else:literal(value,allow_expansion=not table_mode and c==1 and commands,field=field)
        # All checks finish before replacing the editable draft.
        self.table.clearFocus();self._tables.clear()
        self.mode.blockSignals(True)
        try:
            if self.gadget.kind=='list':self.mode.setCurrentIndex(int(table_mode))
        finally:self.mode.blockSignals(False)
        self._loaded_mode=self.mode.currentIndex()
        self.table.clear();self.table.setColumnCount(columns);self.table.setRowCount(len(payload))
        self.table.setHorizontalHeaderLabels([f'列{i+1}' for i in range(columns)] if table_mode else ['表示名','コマンド' if commands else '実値'])
        self.table.setVerticalHeaderLabels(['見出し',*[str(i+1) for i in range(len(payload)-1)]] if table_mode else [str(i+1) for i in range(len(payload))])
        for r,row in enumerate(payload):
            for c,value in enumerate(row):self.table.setItem(r,c,QTableWidgetItem(value))

    def load_table(self):
        g=self.gadget
        if self._loaded_mode is not None:
            self.table.clearFocus()
            self._tables[self._loaded_mode]=[[self.table.item(r,c).text() if self.table.item(r,c) else '' for c in range(self.table.columnCount())] for r in range(self.table.rowCount())]
        if self.is_table():
            headings=g.headings or ['列1'];rows=g.rows if g.list_mode=='TABLE' else [[v] for v in g.items]
            data=[headings,*rows];headers=[f'列{i+1}' for i in range(len(headings))]
        else:
            values=g.item_commands if uses_pairs(g) and self.mode.currentIndex()==0 else g.item_values
            data=[[v,values[i] if i<len(values) else ''] for i,v in enumerate(g.items)]
            headers=['表示名','コマンド' if uses_pairs(g) and self.mode.currentIndex()==0 else '実値']
        mode=self.mode.currentIndex()
        if mode in self._tables:data=self._tables[mode]
        elif self._loaded_mode is not None:
            previous=self._tables[self._loaded_mode]
            if g.kind=='list':
                if self.is_table():data=[['表示名','実値'],*previous];headers=['列1','列2']
                else:data=[[row[0] if row else '',row[1] if len(row)>1 else ''] for row in previous[1:]]
            else:data=previous
        if self.is_table() and data:headers=[f'列{i+1}' for i in range(len(data[0]))]
        self._loaded_mode=mode
        self.table.clear();self.table.setColumnCount(len(headers));self.table.setRowCount(len(data))
        self.table.setHorizontalHeaderLabels(headers)
        for r,row in enumerate(data):
            for c,value in enumerate(row):self.table.setItem(r,c,QTableWidgetItem(value))
        self.table.setVerticalHeaderLabels(['見出し',*[str(i+1) for i in range(len(data)-1)]] if self.is_table() else [str(i+1) for i in range(len(data))])
        self.table.horizontalHeader().setStretchLastSection(True)

    def add_row(self):self.table.insertRow(self.table.rowCount())
    def remove_row(self):
        row=self.table.currentRow()
        if row>=0 and (not self.is_table() or row>0):self.table.removeRow(row)
    def add_column(self):
        if not self.is_table():
            self.mode.setCurrentIndex(1)
        self.table.insertColumn(self.table.columnCount())
        self.table.setItem(0,self.table.columnCount()-1,QTableWidgetItem(f'列{self.table.columnCount()}'))
    def remove_column(self):
        col=self.table.currentColumn()
        if self.is_table() and col>=0 and self.table.columnCount()>1:self.table.removeColumn(col)
    def accept(self):
        # Commit an active cell editor before reading the spreadsheet.
        self.table.clearFocus()
        data=[[self.table.item(r,c).text() if self.table.item(r,c) else '' for c in range(self.table.columnCount())] for r in range(self.table.rowCount())]
        g=copy.deepcopy(self.gadget);g.initial=self.initial.text()
        if g.kind=='list':g.selection_mode=self.selection.currentText()
        if self.is_table():
            g.list_mode='TABLE';g.headings=data[0] if data else ['列1'];g.rows=data[1:];g.items=[];g.item_values=[]
        else:
            if g.kind=='list':g.list_mode='SIMPLE';g.headings=[];g.rows=[]
            g.items=[row[0] for row in data];values=[row[1] for row in data]
            commands=uses_pairs(g) and self.mode.currentIndex()==0
            g.item_commands=values if commands else []
            g.item_values=[] if commands or not any(values) else values
        self.gadget=g;super().accept()


class MiniProperties(QDialog):
    def __init__(self,parent,form,index):
        super().__init__(parent);self.draft=copy.deepcopy(form);self.index=index
        self.gadget=self.draft.gadgets[index];g=self.gadget;self.fields={};self.result_form=None
        from .images import sync_image_size
        self.image_directories=parent.image_directories() if hasattr(parent,'image_directories') else ()
        sync_image_size(g,self.image_directories)
        normalize_dimensions(g)
        self.setWindowTitle(f'{g.kind.upper()} の設定');self.setMinimumWidth(350)
        layout=QVBoxLayout(self);fields=QFormLayout();layout.addLayout(fields)
        def text(key,title):
            widget=QLineEdit(str(getattr(g,key)));self.fields[key]=widget;fields.addRow(title,widget)
        def number(key,title):
            widget=QDoubleSpinBox();widget.setDecimals(1);widget.setSingleStep(.1);widget.setRange(0 if fixed_dimensions(g).get(key)==0 or (key=='width' and self.draft.is_hidden(g)) else 1,100000) if key in ('width','height') else widget.setRange(-100000,100000)
            widget.setValue(self.draft.display_width(g) if key=='width' else getattr(g,key));widget.setProperty('baseline',widget.value());self.fields[key]=widget;fields.addRow(title,widget)
            if key in ('width','height'):
                widget.setEnabled(dimension_editable(g,key))
                if not dimension_editable(g,key):widget.setToolTip('元画像のサイズ、1行の高さ、または部品の太さで固定されます。')
        text('name','オブジェクト名')
        direction_key='orientation' if g.kind=='line' else 'slider_orientation' if g.kind=='slider' else None
        if direction_key:
            widget=QComboBox()
            for title,value in (('横','HORIZ' if g.kind=='line' else 'HORIZONTAL'),('縦','VERT' if g.kind=='line' else 'VERTICAL')):widget.addItem(title,value)
            widget.setCurrentIndex(widget.findData(getattr(g,direction_key)))
            self.fields[direction_key]=widget;fields.addRow('向き',widget)
        if g.kind in ('combo','rtoggle'):text('combo_tagwid','TAGWID（表示名の幅）')
        self.option_width=None
        if uses_pairs(g):
            self.option_width=QCheckBox('OPTIONの幅をコードへ出力');self.option_width.setChecked(g.option_width_explicit)
            fields.addRow('',self.option_width)
        if g.kind!='line':text('label','表示名')
        if g.kind in ('option','combo','list'):
            button=QPushButton('項目・値を表で編集…');button.clicked.connect(self.edit_items);fields.addRow('値',button)
        elif g.kind in ('toggle','rtoggle'):
            widget=QComboBox();widget.addItems(['','TRUE','FALSE']);widget.setCurrentText(g.initial.upper());self.fields['initial']=widget;fields.addRow('初期値',widget)
        elif g.kind=='slider':number('slider_value','宣言時の値' if form.default_mode=='SOURCE' else '初期値')
        elif g.kind=='text' or (g.kind=='paragraph' and g.display_mode=='TEXT'):text('initial','初期値')
        if 'initial' in self.fields and form.default_mode=='SOURCE':
            self.fields['initial'].setEnabled(False)
            self.fields['initial'].setToolTip('「取り込みコード」のDEFAULT欄で編集してください。')
        if g.display_mode=='PIXMAP' and g.kind in ('button','paragraph','toggle'):text('pixmap_path','画像ファイル')
        if (g.kind in ('button','text','toggle') or (g.kind=='option' and g.display_mode=='TEXT' and not uses_pairs(g))) and g.action_mode=='CODE' and (g.kind!='button' or g.button_role not in ('OK','CANCEL','HELP')):
            self.call_mode=QComboBox();self.call_mode.addItems(['メソッド名','コマンド'])
            self.call_mode.setCurrentIndex(int(bool(g.command)));fields.addRow('処理方式',self.call_mode)
            widget=QLineEdit(g.command or g.callback);self.fields['action']=widget;fields.addRow('処理',widget)
        elif g.callback or g.kind in ('list','combo','slider','selector') or (g.kind=='option' and g.display_mode=='PIXMAP'):text('callback','メソッド名')
        if g.kind=='button':
            widget=QComboBox();widget.addItems(['','OKCALL','CANCELCALL']);widget.setCurrentText(g.button_call)
            widget.setToolTip('空欄なら省略。CALLコマンドの後に付けるフォーム処理です。')
            self.fields['button_call']=widget;fields.addRow('コマンド後のフォーム処理',widget)
        if g.kind in ('button','paragraph','list'):
            row=QHBoxLayout();widget=QLineEdit(g.background);self.fields['background']=widget;row.addWidget(widget)
            button=QPushButton('色を選ぶ');button.clicked.connect(self.choose_color);row.addWidget(button);fields.addRow('色番号',row)
        sized=g.kind not in ('toggle','rtoggle','option','frame') or g.display_mode=='PIXMAP' or g.kind=='option' or (g.kind=='frame' and g.frame_style in ('TABSET','TOOLBAR'))
        if g.kind=='combo':text('combo_scroll','SCROLL（表示量）')
        if sized:number('width','WIDTH')
        if self.option_width is not None:
            self.fields['width'].setEnabled(g.option_width_explicit)
            self.fields['width'].setToolTip('「OPTIONの幅をコードへ出力」がオフなら自動幅、オンなら幅を指定できます。')
            self.option_width.toggled.connect(self.fields['width'].setEnabled)
        self.auto_width=None
        if supports_auto_width(g) and not uses_pairs(g) and 'width' in self.fields:
            self.auto_width=QCheckBox('文字に合わせた自動幅（表示のみ）' if g.kind in ('toggle','rtoggle') else '文字に合わせた自動幅（WIDTH省略）')
            self.auto_width.setChecked(not g.width_explicit)
            self.auto_width.setEnabled(not g.hidden and not g.width_ref)
            fields.addRow('',self.auto_width)
            if 'width' in self.fields:self.auto_width.toggled.connect(lambda checked:self.fields['width'].setEnabled(not checked and not self.gadget.hidden and not self.gadget.width_ref))
        if g.kind in ('line','slider','list','view','alpha','container','textpane','selector') or g.display_mode=='PIXMAP' or (g.kind=='frame' and g.frame_style=='TOOLBAR'):number('height','HEIGHT')
        self.hidden=QCheckBox('非表示（WIDTH 0）',self);self.hidden.setChecked(g.hidden)
        if supports_hidden(g):
            fields.addRow(self.hidden);self.hidden.toggled.connect(self.edit_hidden)
        else:self.hidden.hide()
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        if 'pixmap_path' in self.fields:self.fields['pixmap_path'].textChanged.connect(self.preview_image_dimensions)
        if direction_key:self.fields[direction_key].currentIndexChanged.connect(lambda:self.edit_direction(direction_key))
    def exec(self):
        return super().exec()

    def preview_image_dimensions(self):
        from .images import sync_image_size
        if 'pixmap_path' in self.fields:self.gadget.pixmap_path=self.fields['pixmap_path'].text()
        sync_image_size(self.gadget,self.image_directories)
        for key in ('width','height'):
            if key in self.fields:self.fields[key].setValue(0 if key=='width' and self.gadget.hidden else getattr(self.gadget,key))

    def edit_direction(self,key):
        for dimension in ('width','height'):
            widget=self.fields[dimension]
            if dimension_editable(self.gadget,dimension) and widget.value()!=widget.property('baseline'):
                setattr(self.gadget,dimension,widget.value())
        self.draft.rotate_gadget(self.gadget,self.fields[key].currentData())
        self.hidden.setChecked(self.gadget.hidden)
        for dimension in ('width','height'):
            widget=self.fields[dimension];widget.setMinimum(0 if fixed_dimensions(self.gadget).get(dimension)==0 or (dimension=='width' and self.draft.is_hidden(self.gadget)) else 1)
            widget.setValue(self.draft.display_width(self.gadget) if dimension=='width' else getattr(self.gadget,dimension))
            widget.setProperty('baseline',widget.value());widget.setEnabled(dimension_editable(self.gadget,dimension))
            widget.setToolTip('' if dimension_editable(self.gadget,dimension) else '部品の太さは固定されます。')

    def edit_hidden(self,checked):
        g=self.gadget;widget=self.fields.get('width')
        if widget and dimension_editable(g,'width') and widget.value()!=widget.property('baseline'):g.width=widget.value()
        g.hidden=checked
        if widget:
            hidden=self.draft.is_hidden(g)
            widget.setMinimum(0 if hidden else 1);widget.setValue(self.draft.display_width(g))
            widget.setProperty('baseline',widget.value());widget.setEnabled(dimension_editable(g,'width'))

    def choose_color(self):
        dialog=ColorPicker(self,self.fields['background'].text())
        if dialog.exec()==QDialog.Accepted:self.fields['background'].setText(dialog.value)
        dialog.deleteLater()
    def edit_items(self):
        dialog=ItemsDialog(self,self.gadget,initial_editable=self.draft.default_mode=='GENERATED')
        if dialog.exec()==QDialog.Accepted:
            self.gadget=dialog.gadget;self.draft.gadgets[self.index]=self.gadget
            if self.gadget.display_mode=='PIXMAP':self.preview_image_dimensions()
        dialog.deleteLater()
    def accept(self):
        candidate=copy.deepcopy(self.draft);g=candidate.gadgets[self.index]
        previous_auto=uses_auto_width(g);previous_width=candidate.display_width(g)
        if self.auto_width is not None:g.width_explicit=not self.auto_width.isChecked()
        if previous_auto and not uses_auto_width(g):g.width=previous_width
        if self.option_width is not None:g.option_width_explicit=self.option_width.isChecked()
        previous_callback=g.callback
        for key,widget in self.fields.items():
            if key in ('name','action'):continue
            if key in ('width','height') and not dimension_editable(g,key):continue
            if isinstance(widget,QDoubleSpinBox):
                if widget.value()!=widget.property('baseline'):setattr(g,key,widget.value())
            elif key in ('orientation','slider_orientation'):setattr(g,key,widget.currentData())
            else:setattr(g,key,widget.currentText() if isinstance(widget,QComboBox) else widget.text())
        if 'action' in self.fields:
            g.callback=self.fields['action'].text() if self.call_mode.currentIndex()==0 else ''
            g.command=self.fields['action'].text() if self.call_mode.currentIndex()==1 else ''
        from .callbacks import join_callback
        join_callback(candidate,g,previous_callback)
        try:
            from .images import sync_image_size
            sync_image_size(g,self.image_directories)
            normalize_dimensions(g)
            candidate=rename(candidate,'gadget',self.index,self.fields['name'].text())
            candidate.validate()
        except ValueError as error:self.error.setText(str(error));return
        self.result_form=candidate;super().accept()


class FormProperties(QDialog):
    def __init__(self,parent,form):
        super().__init__(parent);self.draft=copy.deepcopy(form);self.result_form=None
        self.setWindowTitle('フォームの設定');self.setMinimumWidth(350)
        layout=QVBoxLayout(self);fields=QFormLayout();layout.addLayout(fields)
        self.name=QLineEdit(form.symbol);self.title=QLineEdit(form.title)
        fields.addRow('フォーム名',self.name);fields.addRow('表示名',self.title)
        self.width=QDoubleSpinBox();self.height=QDoubleSpinBox()
        for widget,value,label in ((self.width,form.width,'WIDTH'),(self.height,form.height,'HEIGHT')):
            widget.setRange(1,300);widget.setDecimals(1);widget.setSingleStep(.1);widget.setValue(value);widget.setProperty('baseline',widget.value());fields.addRow(label,widget)
        self.auto_size=QCheckBox('部品に合わせて自動サイズ');self.auto_size.setChecked(not form.size_explicit)
        fields.addRow('',self.auto_size)
        self.docking=QComboBox()
        for label,value in (('通常ダイアログ','NONE'),('右ドッキング','RIGHT'),('左ドッキング','LEFT'),('上ドッキング','TOP'),('下ドッキング','BOTTOM'),('MAIN フォーム','MAIN')):self.docking.addItem(label,value)
        self.docking.setCurrentIndex(self.docking.findData('MAIN' if form.form_type=='MAIN' else form.docking_side()))
        fields.addRow('表示形式',self.docking)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def exec(self):return super().exec()
    def accept(self):
        candidate=copy.deepcopy(self.draft);candidate.title=self.title.text()
        candidate.size_explicit=not self.auto_size.isChecked()
        for key in ('width','height'):
            widget=getattr(self,key)
            if widget.value()!=widget.property('baseline'):
                setattr(candidate,key,widget.value());candidate.size_explicit=True
        if not candidate.size_explicit:candidate.fit_size()
        mode=self.docking.currentData();candidate.form_type='MAIN' if mode=='MAIN' else 'DIALOG'
        candidate.dock_side='NONE' if mode=='MAIN' else mode;candidate.dock_right=candidate.dock_side=='RIGHT'
        try:candidate=rename(candidate,'form',None,self.name.text());candidate.validate()
        except ValueError as error:self.error.setText(str(error));return
        self.result_form=candidate;super().accept()
