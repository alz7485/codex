"""Native-widget appearance reference. Never executes PML or changes the design."""
import copy
from PySide6.QtCore import Qt,QPoint,QSize,QRectF
from PySide6.QtGui import QTransform,QPainter,QColor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QWidget,QLabel,QMenuBar,QMenu,QFrame,QGraphicsView,QGraphicsScene
from .model import CHAR_WIDTH,LINE_HEIGHT,supports_hidden
from .appearance import NativeControls,FORM_PADDING,FORM_BORDER,FORM_MARGIN,FORM_BACKGROUND
from .draft_validation import validate_draft


class FitFormView(QGraphicsView):
    """Scale the native form as a whole; its widget geometry stays at 100%."""
    def __init__(self,parent):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self));self.form_widget=None;self.display_scale=1.
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.TextAntialiasing|QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor(FORM_BACKGROUND))

    def set_form_widget(self,widget):
        self.form_widget=widget
        self.proxy=self.scene().addWidget(widget)
        self.setSceneRect(QRectF(widget.rect()))
        self.fit_form()

    def fit_form(self):
        if self.form_widget is None:return
        rect=self.sceneRect()
        self.display_scale=min(1.,max(1,self.viewport().width()-2)/rect.width(),
                               max(1,self.viewport().height()-2)/rect.height())
        self.setTransform(QTransform.fromScale(self.display_scale,self.display_scale))
        self.centerOn(rect.center())
        self.setToolTip(f'全体表示 {self.display_scale*100:.1f}%（部品の寸法・座標は変更しません）')

    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_form()


class RuntimePreview(QDialog,NativeControls):
    def __init__(self,parent=None,char_width=CHAR_WIDTH,line_height=LINE_HEIGHT,font=None):
        super().__init__(parent,Qt.Window)
        self.init_appearance(font,char_width,line_height)
        self.layout_root=QVBoxLayout(self);self.layout_root.setContentsMargins(0,0,0,0);self.layout_root.setSpacing(0)
        self.surface=None;self.menu_bar=None;self.controls={};self.preview_warning=''
        self.form_view=FitFormView(self);self.layout_root.addWidget(self.form_view)

    def validate_display(self):
        self.preview_warning=''
        try:self.form.validate()
        except ValueError as error:
            validate_draft(self.form)
            # Code and initial-value errors do not prevent a static reference.
            # Missing/cyclic geometry and overflow remain errors.
            memo={}
            for g in self.form.gadgets:
                x,y,width,height=self.form.geometry(g,_memo=memo)
                parent=self.form.parent_gadget(g)
                pw,ph=self.form.geometry(parent,_memo=memo)[2:] if parent else (self.form.width,self.form.height)
                if x+width>pw+.001 or y+height>ph+.001:raise error
            self.preview_warning=str(error)

    def set_form(self,form,image_directories=(),active_pages=None):
        self.form=copy.deepcopy(form)
        self.validate_display();self.directories=image_directories
        self.controls={};self.active_pages=dict(active_pages or {});self.menus=[]
        self.form_view.form_widget=None;self.form_view.scene().clear()
        self.form_root=self.style_widget(QWidget())
        form_layout=QVBoxLayout(self.form_root);form_layout.setContentsMargins(0,0,0,0);form_layout.setSpacing(0)
        self.setWindowTitle(self.form.title)
        warning=None
        if self.preview_warning:
            warning=self.style_widget(QLabel('MAC出力前に修正してください: '+self.preview_warning,self.form_root))
            warning.setWordWrap(True);warning.setStyleSheet('background: #fff4d6; padding: 6px;')
            form_layout.addWidget(warning)
        self.menu_bar=self.style_widget(QMenuBar(self.form_root));self.menu_bar.setNativeMenuBar(False)
        for menu in self.form.menus:
            if menu.popup or not menu.on_bar:continue
            popup=self.style_widget(QMenu(menu.display_label,self.menu_bar))
            self.menus.append(popup);self.menu_bar.addMenu(popup)
            for item in menu.items:popup.addAction(item.label)
        self.menu_bar.setVisible(bool(self.menu_bar.actions()));form_layout.addWidget(self.menu_bar)
        self.surface=self.style_widget(QWidget(self.form_root));self.surface.setAutoFillBackground(True)
        # Padding is inside the drawable surface so negative AT coordinates can
        # use it. The source origin stays unchanged, including in child frames.
        self.layout_origin=QPoint(FORM_PADDING,FORM_PADDING)
        self.content_size=QSize(self.pixels(self.form.width*self.char_width),self.pixels(self.form.height*self.line_height))
        self.surface.setFixedSize(self.content_size+QSize(2*FORM_PADDING,2*FORM_PADDING))
        self.client=self.style_widget(QFrame(self.form_root));self.client.setFrameShape(QFrame.WinPanel)
        self.client.setFrameShadow(QFrame.Sunken);self.client.setLineWidth(FORM_BORDER);self.client.setAutoFillBackground(True)
        client_layout=QVBoxLayout(self.client);client_layout.setContentsMargins(0,0,0,0)
        client_layout.addWidget(self.surface)
        form_layout.addWidget(self.client)
        self.build_children('',self.surface,{})
        if not self.form.size_explicit:
            roots=[w.geometry() for w in self.controls.values() if w.parent() is self.surface]
            self.content_size=QSize(max([round(self.char_width),*[r.x()+r.width()-self.layout_origin.x() for r in roots]]),
                max([round(self.line_height),*[r.y()+r.height()-self.layout_origin.y() for r in roots]]))
            self.surface.setFixedSize(self.content_size+QSize(2*FORM_PADDING,2*FORM_PADDING))
        self.client.setFixedSize(self.content_size+QSize(2*FORM_MARGIN,2*FORM_MARGIN))
        width=self.client.width()
        extra=(self.menu_bar.sizeHint().height() if self.menu_bar.actions() else 0)
        if warning:extra+=max(warning.sizeHint().height(),warning.heightForWidth(width))
        self.form_root.setFixedSize(width,self.client.height()+extra)
        form_layout.activate()
        self.form_view.set_form_widget(self.form_root)
        self.resize(self.form_root.size()+QSize(2,2));self.keep_on_screen()

    def keep_on_screen(self):
        screen=self.parentWidget().screen() if self.parentWidget() else self.screen()
        if screen is None:return
        available=screen.availableGeometry()
        frame=self.frameGeometry().size()-self.size()
        self.resize(min(self.width(),max(1,available.width()-max(24,frame.width()+12))),
                    min(self.height(),max(1,available.height()-max(48,frame.height()+12))))
        rect=self.frameGeometry()
        self.move(max(available.left(),min(rect.left(),available.right()-rect.width()+1)),
                  max(available.top(),min(rect.top(),available.bottom()-rect.height()+1)))
        self.layout_root.activate();self.form_view.fit_form()

    def showEvent(self,event):
        super().showEvent(event);self.keep_on_screen()

    def build_children(self,name,parent,geometry_memo):
        for g in self.form.children(name):
            if g.hidden:continue
            x,y,width,height=self.form.geometry(g,_memo=geometry_memo)
            if width==0 and supports_hidden(g):continue
            widget=self.build_gadget(g,parent);self.controls[g.name]=widget
            width,height=(g.width,g.height) if g.display_mode=='PIXMAP' else (width*self.char_width,height*self.line_height)
            width=self.control_width(g,widget,width,height)
            if g.kind=='line':
                width=2 if g.orientation=='VERT' else width;height=2 if g.orientation=='HORIZ' else height
            bounds=self.control_bounds(g,width,height)
            origin=self.layout_origin if parent is self.surface else QPoint()
            widget.setGeometry(self.pixels(x*self.char_width+origin.x()+bounds.x(),True),self.pixels(y*self.line_height+origin.y()+bounds.y(),True),
                int(bounds.width()),int(bounds.height()))
            if g.kind=='frame':
                if g.frame_style=='TABSET':
                    pages=self.form.children(g.name)
                    for page in pages:
                        content=self.style_widget(QWidget(widget));widget.addTab(content,page.label)
                        self.controls[page.name]=content;self.build_children(page.name,content,geometry_memo)
                    active=self.active_pages.get(g.name.lower())
                    index=next((i for i,page in enumerate(pages) if page.name.lower()==active),0)
                    widget.setCurrentIndex(index)
                else:self.build_children(g.name,widget,geometry_memo)
