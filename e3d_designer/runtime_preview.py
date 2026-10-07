"""Native-widget appearance reference. Never executes PML or changes the design."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QWidget,QLabel,QMenuBar,QMenu,QScrollArea,QFrame
from .model import CHAR_WIDTH,LINE_HEIGHT,supports_hidden
from .appearance import NativeControls,FORM_PADDING,FORM_BORDER,FORM_MARGIN
from .draft_validation import validate_draft


class RuntimePreview(QDialog,NativeControls):
    def __init__(self,parent=None,char_width=CHAR_WIDTH,line_height=LINE_HEIGHT,font=None):
        super().__init__(parent,Qt.Window)
        self.init_appearance(font,char_width,line_height)
        self.layout_root=QVBoxLayout(self);self.layout_root.setContentsMargins(0,0,0,0);self.layout_root.setSpacing(0)
        self.surface=None;self.menu_bar=None;self.controls={};self.preview_warning=''

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
        while self.layout_root.count():
            widget=self.layout_root.takeAt(0).widget()
            if widget:widget.hide();widget.deleteLater()
        self.setWindowTitle(self.form.title)
        if self.preview_warning:
            warning=self.style_widget(QLabel('MAC出力前に修正してください: '+self.preview_warning,self))
            warning.setWordWrap(True);warning.setStyleSheet('background: #fff4d6; padding: 6px;')
            self.layout_root.addWidget(warning)
        self.menu_bar=self.style_widget(QMenuBar(self));self.menu_bar.setNativeMenuBar(False)
        for menu in self.form.menus:
            if menu.popup or not menu.on_bar:continue
            popup=self.style_widget(QMenu(menu.display_label,self.menu_bar))
            self.menus.append(popup);self.menu_bar.addMenu(popup)
            for item in menu.items:popup.addAction(item.label)
        self.menu_bar.setVisible(bool(self.menu_bar.actions()));self.layout_root.addWidget(self.menu_bar)
        self.surface=self.style_widget(QWidget(self));self.surface.setAutoFillBackground(True)
        self.surface.setFixedSize(self.pixels(self.form.width*self.char_width),self.pixels(self.form.height*self.line_height))
        body=self.style_widget(QWidget(self));body_layout=QVBoxLayout(body);body_layout.setContentsMargins(0,0,0,0)
        self.client=self.style_widget(QFrame(body));self.client.setFrameShape(QFrame.WinPanel)
        self.client.setFrameShadow(QFrame.Sunken);self.client.setLineWidth(FORM_BORDER);self.client.setAutoFillBackground(True)
        client_layout=QVBoxLayout(self.client);client_layout.setContentsMargins(FORM_PADDING,FORM_PADDING,FORM_PADDING,FORM_PADDING)
        client_layout.addWidget(self.surface)
        body_layout.addWidget(self.client,0,Qt.AlignLeft|Qt.AlignTop)
        self.scroll=QScrollArea(self);self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True);self.scroll.setWidget(body);self.layout_root.addWidget(self.scroll,1)
        self.build_children('',self.surface,{})
        if not self.form.size_explicit:
            roots=[w.geometry() for w in self.controls.values() if w.parent() is self.surface]
            self.surface.setFixedSize(max([round(self.char_width),*[r.x()+r.width() for r in roots]]),
                max([round(self.line_height),*[r.y()+r.height() for r in roots]]))
        self.client.setFixedSize(self.surface.width()+2*FORM_MARGIN,self.surface.height()+2*FORM_MARGIN)
        self.adjustSize();self.keep_on_screen()

    def keep_on_screen(self):
        screen=self.parentWidget().screen() if self.parentWidget() else self.screen()
        if screen is None:return
        available=screen.availableGeometry()
        self.resize(min(self.width(),max(1,int(available.width()*.9))),
                    min(self.height(),max(1,int(available.height()*.9))))
        rect=self.frameGeometry()
        self.move(max(available.left(),min(rect.left(),available.right()-rect.width()+1)),
                  max(available.top(),min(rect.top(),available.bottom()-rect.height()+1)))

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
            widget.setGeometry(self.pixels(x*self.char_width,True),self.pixels(y*self.line_height,True),
                max(1,self.pixels(width)),max(1,self.pixels(height)))
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
