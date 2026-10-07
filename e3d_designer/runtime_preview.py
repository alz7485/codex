"""Native-widget appearance reference. Never executes PML or changes the design."""
import copy
import math

from PySide6.QtCore import Qt,QItemSelectionModel,QSize
from PySide6.QtGui import QColor,QPalette,QPixmap,QIcon,QFont,QImageReader
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QWidget,
    QLabel,QPushButton,QCheckBox,QRadioButton,QComboBox,QLineEdit,QGroupBox,QTabWidget,
    QFrame,QSlider,QListWidget,QTableWidget,QTableWidgetItem,QPlainTextEdit,QMenuBar,QMenu,
    QAbstractItemView,QStyleFactory,QStyle,QStyleOptionButton,QStyleOptionComboBox,QStyleOptionFrame)

from .model import CHAR_WIDTH,LINE_HEIGHT,uses_pairs
from .images import resolve_image_path
from .colors import preview_color,foreground_color


class RuntimePreview(QDialog):
    def __init__(self,parent=None,char_width=CHAR_WIDTH,line_height=LINE_HEIGHT):
        super().__init__(parent,Qt.Window)
        self.char_width=char_width;self.line_height=line_height
        self.preview_style=QStyleFactory.create('Windows')
        if self.preview_style:self.preview_style.setParent(self)
        else:self.preview_style=QApplication.style()
        self.layout_root=QVBoxLayout(self);self.layout_root.setContentsMargins(0,0,0,0);self.layout_root.setSpacing(0)
        self.surface=None;self.menu_bar=None;self.controls={}

    def style_widget(self,widget):
        widget.setStyle(self.preview_style);widget.setFont(QApplication.font());widget.setFocusPolicy(Qt.NoFocus)
        return widget

    def set_form(self,form,image_directories=(),active_pages=None):
        self.form=copy.deepcopy(form)
        if not self.form.size_explicit:self.form.fit_size()
        self.form.validate();self.directories=image_directories
        self.controls={};self.active_pages=dict(active_pages or {});self.menus=[]
        while self.layout_root.count():
            widget=self.layout_root.takeAt(0).widget()
            if widget:widget.hide();widget.deleteLater()
        self.setWindowTitle(self.form.title)
        self.menu_bar=self.style_widget(QMenuBar(self));self.menu_bar.setNativeMenuBar(False)
        for menu in self.form.menus:
            if menu.popup or not menu.on_bar:continue
            popup=self.style_widget(QMenu(menu.display_label,self.menu_bar))
            self.menus.append(popup);self.menu_bar.addMenu(popup)
            for item in menu.items:popup.addAction(item.label)
        self.menu_bar.setVisible(bool(self.menu_bar.actions()));self.layout_root.addWidget(self.menu_bar)
        self.surface=self.style_widget(QWidget(self));self.surface.setAutoFillBackground(True)
        self.surface.setFixedSize(round(self.form.width*self.char_width),round(self.form.height*self.line_height))
        body=self.style_widget(QWidget(self));body_layout=QVBoxLayout(body)
        body_layout.addWidget(self.surface,0,Qt.AlignLeft|Qt.AlignTop);self.layout_root.addWidget(body,1)
        self.build_children('',self.surface)
        if not self.form.size_explicit:
            roots=[w.geometry() for w in self.controls.values() if w.parent() is self.surface]
            self.surface.setFixedSize(max([round(self.char_width),*[r.x()+r.width() for r in roots]]),
                max([round(self.line_height),*[r.y()+r.height() for r in roots]]))
        self.adjustSize()

    def image(self,g):
        filename=g.items[0] if g.kind=='option' and g.items else g.pixmap_path
        return QPixmap(resolve_image_path(filename,self.directories)) if filename else QPixmap()

    def pixels(self,value,position=False):
        low,high=(-2147483648,2147483647) if position else (0,16777215)
        if not math.isfinite(value) or not low<=round(value)<=high:
            raise ValueError('参考表示で扱える座標・寸法の範囲を超えています。MACの値は変更していません。')
        return round(value)

    def choice_index(self,g):
        try:return int(g.initial)-1 if g.initial else -1
        except ValueError:return -1

    def control_width(self,g,widget,width,height):
        """Reference padding uses Qt metrics; the original PML WIDTH is intact."""
        if g.display_mode=='PIXMAP':return width
        size=QSize(self.pixels(width),self.pixels(height))
        if g.kind=='button':
            option=QStyleOptionButton();option.initFrom(widget)
            return widget.style().sizeFromContents(QStyle.CT_PushButton,option,size,widget).width()
        if g.kind in ('option','combo','text'):
            if uses_pairs(g) and not g.option_width_explicit:return widget.sizeHint().width()
            entry=widget.entry
            if g.kind=='text':
                option=QStyleOptionFrame();option.initFrom(entry)
                option.lineWidth=entry.style().pixelMetric(QStyle.PM_DefaultFrameWidth,option,entry)
                kind=QStyle.CT_LineEdit
            else:
                option=QStyleOptionComboBox();entry.initStyleOption(option);kind=QStyle.CT_ComboBox
            width=entry.style().sizeFromContents(kind,option,size,entry).width()
            if g.label:
                tag=widget.layout().itemAt(0).widget()
                tag_width=tag.minimumWidth() if g.kind=='combo' and g.combo_tagwid else tag.sizeHint().width()
                width+=tag_width+widget.layout().spacing()
        return width

    def select_rows(self,widget,g):
        # Initial selections are static design data; no DEFAULT code is run.
        for value in g.initial.split(','):
            try:index=int(value.strip())-1
            except ValueError:continue
            if isinstance(widget,QTableWidget):
                if 0<=index<widget.rowCount():
                    widget.selectionModel().select(widget.model().index(index,0),
                        QItemSelectionModel.Select|QItemSelectionModel.Rows)
            elif 0<=index<widget.count():widget.item(index).setSelected(True)

    def build_children(self,name,parent):
        for g in self.form.children(name):
            if self.form.is_hidden(g):continue
            widget=self.build_gadget(g,parent);self.controls[g.name]=widget
            x,y,width,height=self.form.geometry(g)
            width,height=(g.width,g.height) if g.display_mode=='PIXMAP' else (width*self.char_width,height*self.line_height)
            width=self.control_width(g,widget,width,height)
            if g.kind=='line':
                width=2 if g.orientation=='VERT' else width;height=2 if g.orientation=='HORIZ' else height
            widget.setGeometry(self.pixels(x*self.char_width,True),self.pixels(y*self.line_height,True),
                max(1,self.pixels(width)),max(1,self.pixels(height)))
            if g.kind=='frame':
                if g.frame_style=='TABSET':
                    pages=self.form.children(g.name)
                    for page in pages:
                        content=self.style_widget(QWidget(widget));widget.addTab(content,page.label)
                        self.controls[page.name]=content;self.build_children(page.name,content)
                    active=self.active_pages.get(g.name.lower())
                    index=next((i for i,page in enumerate(pages) if page.name.lower()==active),0)
                    widget.setCurrentIndex(index)
                else:self.build_children(g.name,widget)

    def tagged_input(self,g,parent,choice=False):
        box=self.style_widget(QWidget(parent));layout=QHBoxLayout(box);layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
        if g.label:
            tag=self.style_widget(QLabel(g.label,box));tag.setTextFormat(Qt.PlainText);layout.addWidget(tag)
            if g.kind=='combo' and g.combo_tagwid:tag.setFixedWidth(self.pixels(float(g.combo_tagwid)*self.char_width))
        if choice:
            entry=self.style_widget(QComboBox(box))
            if g.display_mode=='PIXMAP':
                sizes=[]
                for filename in g.items:
                    path=resolve_image_path(filename,self.directories);entry.addItem(QIcon(path),'')
                    size=QImageReader(path).size()
                    if size.isValid() and not size.isEmpty():sizes.append(size)
                if sizes:entry.setIconSize(QSize(max(size.width() for size in sizes),max(size.height() for size in sizes)))
            else:entry.addItems(g.items)
            entry.setCurrentIndex(max(0,self.choice_index(g)) if g.items else -1)
            if g.kind=='combo' and g.combo_scroll:
                scroll=int(g.combo_scroll)
                if scroll>2147483647:raise ValueError('SCROLLが参考表示で扱える範囲を超えています。MACの値は変更していません。')
                entry.setMaxVisibleItems(scroll)
        else:
            entry=self.style_widget(QLineEdit(g.initial,box));entry.setReadOnly(True)
        layout.addWidget(entry,1);box.entry=entry
        return box

    def build_gadget(self,g,parent):
        if g.kind=='frame':
            widget=QTabWidget(parent) if g.frame_style=='TABSET' else QFrame(parent) if g.frame_style=='TOOLBAR' else QGroupBox(g.label,parent)
        elif g.kind=='paragraph':
            widget=QLabel(g.initial or g.label,parent);widget.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
            widget.setTextFormat(Qt.PlainText)
            if g.display_mode=='PIXMAP':widget.setPixmap(self.image(g));widget.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        elif g.kind=='button':
            widget=QPushButton(g.label,parent);widget.setAutoDefault(False)
            if g.display_mode=='PIXMAP':
                pixmap=self.image(g);widget.setText('');widget.setIcon(QIcon(pixmap));widget.setIconSize(pixmap.size())
        elif g.kind in ('toggle','rtoggle'):
            widget=QCheckBox(g.label,parent) if g.kind=='toggle' else QRadioButton(g.label,parent)
            widget.setChecked(g.initial.upper()=='TRUE')
            if g.display_mode=='PIXMAP':
                pixmap=self.image(g);widget.setText('');widget.setIcon(QIcon(pixmap));widget.setIconSize(pixmap.size())
        elif g.kind in ('option','combo'):return self.tagged_input(g,parent,True)
        elif g.kind=='text':return self.tagged_input(g,parent)
        elif g.kind=='list' and g.list_mode=='TABLE':
            widget=QTableWidget(len(g.rows),len(g.headings),parent);widget.setHorizontalHeaderLabels(g.headings)
            for row,cells in enumerate(g.rows):
                for column,value in enumerate(cells):widget.setItem(row,column,QTableWidgetItem(value))
            widget.verticalHeader().hide();widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
            widget.setSelectionBehavior(QAbstractItemView.SelectRows)
            widget.setSelectionMode(QAbstractItemView.ExtendedSelection if g.selection_mode in ('MULTIPLE','MULTI') else QAbstractItemView.SingleSelection)
            self.select_rows(widget,g)
        elif g.kind in ('list','selector'):
            widget=QListWidget(parent);widget.addItems(g.items)
            widget.setSelectionMode(QAbstractItemView.ExtendedSelection if g.selection_mode in ('MULTIPLE','MULTI') else QAbstractItemView.SingleSelection)
            self.select_rows(widget,g)
        elif g.kind=='slider':
            widget=QSlider(Qt.Vertical if g.slider_orientation=='VERTICAL' else Qt.Horizontal,parent)
            widget.setRange(0,1000)
            fraction=(g.slider_value-g.slider_min)/(g.slider_max-g.slider_min) if g.slider_max>g.slider_min else 0
            widget.setValue(round(max(0,min(1,fraction))*1000))
        elif g.kind=='line':
            widget=QFrame(parent);widget.setFrameShape(QFrame.VLine if g.orientation=='VERT' else QFrame.HLine);widget.setFrameShadow(QFrame.Sunken)
        elif g.kind=='textpane':
            widget=QPlainTextEdit('\n'.join(g.pane_lines),parent);widget.setReadOnly(True)
        elif g.kind in ('view','commandline'):
            widget=QFrame(parent);widget.setFrameShape(QFrame.StyledPanel);widget.setAutoFillBackground(True)
            palette=widget.palette();palette.setColor(QPalette.Window,QColor('#000000'));widget.setPalette(palette)
        else:widget=QWidget(parent)
        self.style_widget(widget)
        if g.kind=='textpane' and g.fixed_font:widget.setFont(QFont('monospace',10))
        color=preview_color(g.background)
        if color:
            palette=widget.palette()
            for role in (QPalette.Window,QPalette.Button,QPalette.Base):palette.setColor(role,QColor(color))
            for role in (QPalette.WindowText,QPalette.ButtonText,QPalette.Text):palette.setColor(role,QColor(foreground_color(color)))
            widget.setPalette(palette);widget.setAutoFillBackground(True)
        return widget
