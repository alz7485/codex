"""Compact split buttons: choose a variant once, click again to repeat it."""
from math import ceil
from PySide6.QtCore import QSize,Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget,QToolButton,QMenu,QGridLayout,QLayout,QSizePolicy

GROUPS = (
    ('button',(('button','button',None,'🖱️','ボタン'),)),
    ('option',(('option','option',None,'🔽','プルダウン'),('combo','combo',None,'📝','コンボ'),('image_option','option','PIXMAP','🖼️','画像選択'))),
    ('frame',(('frame','frame',None,'📁','フレーム'),('tabset','frame','TABSET','🗂️','タブ'))),
    ('toggle',(('toggle','toggle',None,'☑️','チェック'),('rtoggle','rtoggle',None,'🔘','ラジオ'))),
    ('line',(('line_horiz','line','HORIZ','📏','横線'),('line_vert','line','VERT','↕️','縦線'))),
    ('menubar',(('menubar',None,None,'📑','メニューバー'),)),
    ('container',(('container','container',None,'🧩','コンテナ'),)),
    ('text',(('text','text',None,'✏️','入力'),)),
    ('paragraph',(('paragraph','paragraph',None,'🏷️','ラベル'),('image','paragraph','PIXMAP','🖼️','画像'))),
    ('list',(('list','list',None,'📋','リスト'),('textpane','textpane',None,'📄','複数行'))),
    ('slider',(('slider_horiz','slider','HORIZONTAL','🎚️','横スライダー'),('slider_vert','slider','VERTICAL','🎚️','縦スライダー'))),
    ('commandline',(('commandline','commandline',None,'⌨️','コマンド'),('view','view',None,'👁️','ビュー'))),
    ('selector',(('selector','selector',None,'🗃️','DBセレクタ'),)),
    ('toolbar',(('toolbar','frame','TOOLBAR','🛠️','ツールバー'),)),
)


class GadgetPalette(QWidget):
    addRequested=Signal(str,object)
    menuRequested=Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.buttons={};self.actions={};self._columns=0
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(4)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        for group,variants in GROUPS:
            button=QToolButton(self);button.setFixedHeight(28)
            button.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            button.setMinimumWidth(0)
            button.setStyleSheet('font-size: 11px; padding: 1px 3px;')
            title=' / '.join(entry[4] for entry in variants)
            button.setAccessibleName(title)
            button.setToolTip(title+'：矢印で種類を選択、ボタン本体で同じ種類を追加' if len(variants)>1 else title+'を編集' if group=='menubar' else title+'を追加')
            menu=QMenu(button) if len(variants)>1 else None
            if menu:
                button.setMenu(menu);button.setPopupMode(QToolButton.MenuButtonPopup)
            for key,kind,direction,icon,label in variants:
                action=QAction(f'{icon} {label}',button);action.setData(key)
                action.setToolTip(title+'：矢印で種類を選択、ボタン本体で同じ種類を追加' if menu else title+'を編集' if group=='menubar' else title+'を追加')
                action.triggered.connect(lambda checked=False,b=button,a=action,k=kind,d=direction:self.activate(b,a,k,d))
                self.actions[key]=action
                if menu:menu.addAction(action)
            button.setDefaultAction(self.actions[variants[0][0]])
            self.buttons[group]=button
        self.reflow(7)
    def activate(self,button,action,kind,direction):
        button.setDefaultAction(action)
        if kind is None:self.menuRequested.emit()
        else:self.addRequested.emit(kind,direction)
    def sizeHint(self):return QSize(724,60)
    def minimumSizeHint(self):return QSize(104,60)
    def resizeEvent(self,event):
        self.reflow(max(1,min(7,(event.size().width()+4)//104)))
        super().resizeEvent(event)
    def reflow(self,columns):
        if columns==self._columns:return
        for index in range(self.grid.count()-1,-1,-1):self.grid.takeAt(index)
        for column in range(max(7,self._columns)):self.grid.setColumnStretch(column,0)
        for index,button in enumerate(self.buttons.values()):self.grid.addWidget(button,index//columns,index%columns)
        for column in range(columns):self.grid.setColumnStretch(column,1)
        self._columns=columns
        self.setFixedHeight(ceil(len(self.buttons)/columns)*32-4)
