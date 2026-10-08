"""Shared native control appearance for the editor and the reference window."""
import math

from PySide6.QtCore import Qt,QItemSelectionModel,QSize,QPoint,QRectF
from PySide6.QtGui import QColor,QPalette,QPixmap,QIcon,QFont,QImageReader,QFontDatabase,QPainter,QRegion
from PySide6.QtWidgets import (QApplication,QHBoxLayout,QWidget,
    QLabel,QPushButton,QCheckBox,QRadioButton,QComboBox,QLineEdit,QGroupBox,QTabWidget,
    QFrame,QSlider,QListWidget,QTableWidget,QTableWidgetItem,QPlainTextEdit,
    QAbstractItemView,QStyleFactory,QStyle,QStyleOptionButton,QStyleOptionComboBox,QStyleOptionFrame,QProxyStyle)

from .model import CHAR_WIDTH,LINE_HEIGHT,uses_pairs,uses_auto_width
from .images import resolve_image_path
from .colors import preview_color,foreground_color

FORM_PADDING,FORM_BORDER=8,2
FORM_MARGIN=FORM_PADDING+FORM_BORDER
FORM_BACKGROUND='#f0f0f0'


def slider_fraction(g):
    if g.slider_max<=g.slider_min:return 0
    span=g.slider_max-g.slider_min
    if math.isfinite(span):fraction=(g.slider_value-g.slider_min)/span
    else:fraction=(g.slider_value/2-g.slider_min/2)/(g.slider_max/2-g.slider_min/2)
    return max(0,min(1,fraction))


class FormControlStyle(QProxyStyle):
    def pixelMetric(self,metric,option=None,widget=None):
        # Compact classic buttons: WIDTH 1.2 fits a 2-unit arrow-button pitch.
        if metric==QStyle.PM_ButtonMargin:return 4
        return super().pixelMetric(metric,option,widget)


def default_form_font():
    font=QFont(QApplication.font())
    families=QFontDatabase.families()
    for family in ('MS UI Gothic','MS Gothic','Noto Sans CJK JP'):
        if family in families:font.setFamily(family);break
    font.setPointSizeF(10);font.setWeight(QFont.Medium)
    return font


class NativeControls:
    def init_appearance(self,font=None,char_width=CHAR_WIDTH,line_height=LINE_HEIGHT):
        self.char_width=char_width;self.line_height=line_height
        self.preview_font=QFont(font) if font is not None else default_form_font()

    def style_widget(self,widget):
        # Stylesheet wrappers and deferred deletion must not destroy a style
        # which is still used by another control or the next snapshot.
        base=QStyleFactory.create('Windows')
        if base:
            style=FormControlStyle(base)
            style.setParent(widget);widget._preview_style=style;widget.setStyle(style)
        widget.setFont(self.preview_font);widget.setFocusPolicy(Qt.NoFocus)
        palette=widget.palette()
        palette.setColor(QPalette.Window,QColor(FORM_BACKGROUND));palette.setColor(QPalette.Button,QColor(FORM_BACKGROUND))
        palette.setColor(QPalette.WindowText,QColor('#101010'));palette.setColor(QPalette.ButtonText,QColor('#101010'))
        widget.setPalette(palette)
        return widget

    def tab_header_height(self):
        key=self.preview_font.toString()
        cached=getattr(self,'_tab_header_cache',None)
        if cached and cached[0]==key:return cached[1]
        tabs=self.style_widget(QTabWidget(self))
        try:
            tabs.addTab(QWidget(tabs),'Tab');tabs.ensurePolished()
            height=max(1,tabs.tabBar().sizeHint().height())
            self._tab_header_cache=(key,height)
            return height
        finally:tabs.deleteLater()

    def control_bounds(self,g,width,height):
        # Insets affect drawing only; PML dimensions and drag origins stay intact.
        inset_rows={'button':.05,'paragraph':.1}.get(g.kind,0) if g.display_mode=='TEXT' else 0
        inset=min(inset_rows*self.line_height,max(0,(height-1)/2))
        return QRectF(0,self.pixels(inset),max(1,self.pixels(width)),max(1,self.pixels(height-2*inset)))

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
        automatic=uses_auto_width(g)
        if automatic and g.kind=='paragraph':return max(1,widget.sizeHint().width())
        if automatic and g.kind in ('toggle','rtoggle') and not (g.kind=='rtoggle' and g.combo_tagwid):return max(1,widget.sizeHint().width())
        size=QSize(self.pixels(width),self.pixels(height))
        if g.kind=='button':
            if automatic:size.setWidth(widget.fontMetrics().horizontalAdvance(g.label))
            option=QStyleOptionButton();option.initFrom(widget)
            return widget.style().sizeFromContents(QStyle.CT_PushButton,option,size,widget).width()
        if g.kind=='rtoggle' and g.combo_tagwid:
            option=QStyleOptionButton();widget.initStyleOption(option)
            size.setWidth(self.pixels(float(g.combo_tagwid)*self.char_width))
            return widget.style().sizeFromContents(QStyle.CT_RadioButton,option,size,widget).width()
        if g.kind in ('option','combo','text'):
            if uses_pairs(g) and not g.option_width_explicit:return widget.sizeHint().width()
            entry=widget.entry
            if automatic:
                if g.kind in ('option','combo'):return widget.sizeHint().width()
                size.setWidth(max(entry.fontMetrics().horizontalAdvance(g.initial),entry.fontMetrics().horizontalAdvance('000')))
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

    def tagged_input(self,g,parent,choice=False):
        tag_width=self.pixels(float(g.combo_tagwid)*self.char_width) if g.kind=='combo' and g.combo_tagwid and g.label else None
        scroll=int(g.combo_scroll) if g.kind=='combo' and g.combo_scroll else None
        if scroll is not None and not 1<=scroll<=2147483647:raise ValueError('SCROLLが参考表示で扱える範囲を超えています。MACの値は変更していません。')
        box=self.style_widget(QWidget(parent));layout=QHBoxLayout(box);layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
        if g.label:
            tag=self.style_widget(QLabel(g.label,box));tag.setTextFormat(Qt.PlainText);layout.addWidget(tag)
            if tag_width is not None:tag.setFixedWidth(tag_width)
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
            index=self.choice_index(g)
            entry.setCurrentIndex(0 if not g.initial and g.items else index if 0<=index<len(g.items) else -1)
            if scroll is not None:entry.setMaxVisibleItems(scroll)
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
            else:widget.setContentsMargins(self.pixels(.8*self.char_width),0,0,0)
        elif g.kind=='button':
            widget=QPushButton(g.label,parent);widget.setAutoDefault(False)
            if g.display_mode=='PIXMAP':
                pixmap=self.image(g);widget.setText('');widget.setIcon(QIcon(pixmap));widget.setIconSize(pixmap.size())
        elif g.kind in ('toggle','rtoggle'):
            widget=QCheckBox(g.label,parent) if g.kind=='toggle' else QRadioButton(g.label,parent)
            if g.kind=='rtoggle' and g.combo_tagwid and float(g.combo_tagwid)==0:widget.setText('')
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
            widget.setValue(round(slider_fraction(g)*1000))
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


class EditorAppearance(QWidget,NativeControls):
    def __init__(self,parent=None):
        super().__init__(parent);self.init_appearance();self.hide()

    def snapshot(self,g,width,height,directories=()):
        self.directories=directories
        widget=self.build_gadget(g,self)
        try:
            widget.ensurePolished()
            width=self.control_width(g,widget,width,height)
            widget.resize(self.control_bounds(g,width,height).size().toSize())
            if widget.layout():widget.layout().activate()
            pixmap=QPixmap(widget.size());pixmap.fill(Qt.transparent)
            painter=QPainter(pixmap)
            flags=QWidget.DrawChildren|(QWidget.DrawWindowBackground if widget.autoFillBackground() else QWidget.RenderFlag(0))
            try:widget.render(painter,QPoint(),QRegion(),flags)
            finally:painter.end()
            return pixmap
        finally:widget.deleteLater()
