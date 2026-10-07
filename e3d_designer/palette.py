"""Compact split buttons: choose a variant once, click again to repeat it."""
from math import ceil
from PySide6.QtCore import Qt,QSize,Signal
from PySide6.QtGui import QAction,QActionGroup
from PySide6.QtWidgets import QWidget,QToolButton,QMenu,QGridLayout,QLayout,QSizePolicy
from .palette_icons import palette_icon

BUTTON_HEIGHT,SPACING,PADDING,MENU_WIDTH=35,5,6,22
BUTTON_STYLE=f'''
QToolButton {{ background: white; color: #273b52; border: 1px solid #d3dce7;
    border-radius: 4px; padding: 1px 2px; font-size: 11px; }}
QToolButton:hover {{ background: #edf5ff; border-color: #8cafdc; }}
QToolButton:pressed {{ background: #dcecff; border-color: #608bc2; }}
QToolButton:focus {{ border-color: #3566a8; }}
QToolButton::menu-button {{ width: {MENU_WIDTH}px; border-left: 1px solid #e2e8f0;
    border-top-right-radius: 4px; border-bottom-right-radius: 4px; }}
QToolButton::menu-button:hover {{ background: #e4effd; }}
QToolButton::menu-button:pressed {{ background: #dcecff; }}
QToolButton::menu-arrow {{ width: 7px; height: 7px; }}
'''

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


class PaletteButton(QToolButton):
    def keyPressEvent(self,event):
        menu_key=(event.key()==Qt.Key_Down and event.modifiers() in (Qt.NoModifier,Qt.AltModifier)) or (event.key()==Qt.Key_F4 and event.modifiers()==Qt.NoModifier)
        if self.menu() and menu_key:
            self.showMenu();event.accept();return
        super().keyPressEvent(event)


class GadgetPalette(QWidget):
    addRequested=Signal(str,object)
    menuRequested=Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('gadgetPalette')
        self.setStyleSheet('QWidget#gadgetPalette { background: #f5f8fc; border: 1px solid #dce4ef; border-radius: 5px; }')
        self.buttons={};self.actions={};self._columns=0;self.action_groups=[]
        self.grid=QGridLayout(self);self.grid.setContentsMargins(PADDING,PADDING,PADDING,PADDING);self.grid.setSpacing(SPACING)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        for group,variants in GROUPS:
            button=PaletteButton(self);button.setFixedHeight(BUTTON_HEIGHT)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);button.setIconSize(QSize(18,18))
            button.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            button.setMinimumWidth(0)
            button.setStyleSheet(BUTTON_STYLE)
            title=' / '.join(entry[4] for entry in variants)
            button.setAccessibleName(title)
            button.setToolTip(title+'：矢印で種類を選択、ボタン本体で同じ種類を追加' if len(variants)>1 else title+'を編集' if group=='menubar' else title+'を追加')
            menu=QMenu(button) if len(variants)>1 else None
            if menu:
                button.setMenu(menu);button.setPopupMode(QToolButton.MenuButtonPopup)
                choices=QActionGroup(button);choices.setExclusive(True);self.action_groups.append(choices)
            for key,kind,direction,icon,label in variants:
                action=QAction(palette_icon(key),label,button);action.setData(key)
                action.setToolTip(title+'：矢印で種類を選択、ボタン本体で同じ種類を追加' if menu else title+'を編集' if group=='menubar' else title+'を追加')
                action.triggered.connect(lambda checked=False,b=button,a=action,k=kind,d=direction:self.activate(b,a,k,d))
                self.actions[key]=action
                if menu:
                    action.setCheckable(True);choices.addAction(action);menu.addAction(action)
            button.setDefaultAction(self.actions[variants[0][0]])
            if menu:self.actions[variants[0][0]].setChecked(True)
            if group=='slider':button.setText('スライダー')
            self.describe_choice(button,button.defaultAction(),menu is not None)
            self.buttons[group]=button
        self.reflow(7)
    def activate(self,button,action,kind,direction):
        button.setDefaultAction(action)
        if action.data() in ('slider_horiz','slider_vert'):button.setText('スライダー')
        self.describe_choice(button,action,button.menu() is not None)
        if kind is None:self.menuRequested.emit()
        else:self.addRequested.emit(kind,direction)

    def describe_choice(self,button,action,has_menu):
        # The menu marks the chosen variant; the main button is an add command,
        # rather than a toggle, even though its default QAction is checkable.
        button.setCheckable(False)
        label=action.text()
        operation='↓ / Alt＋↓ / F4で種類を選択、ボタン本体で同じ種類を追加' if has_menu else 'メニューバーを編集' if action.data()=='menubar' else 'この部品を追加'
        hint=label+'：'+operation
        button.setAccessibleName(label);button.setAccessibleDescription(operation);button.setToolTip(hint)
    def sizeHint(self):return QSize(754,2*BUTTON_HEIGHT+SPACING+2*PADDING)
    def minimumSizeHint(self):return QSize(104+2*PADDING,2*BUTTON_HEIGHT+SPACING+2*PADDING)
    def resizeEvent(self,event):
        self.reflow(max(1,min(7,(event.size().width()-2*PADDING+SPACING)//104)))
        super().resizeEvent(event)
    def reflow(self,columns):
        if columns==self._columns:return
        for index in range(self.grid.count()-1,-1,-1):self.grid.takeAt(index)
        for column in range(max(7,self._columns)):self.grid.setColumnStretch(column,0)
        for index,button in enumerate(self.buttons.values()):self.grid.addWidget(button,index//columns,index%columns)
        for column in range(columns):self.grid.setColumnStretch(column,1)
        self._columns=columns
        rows=ceil(len(self.buttons)/columns)
        self.setFixedHeight(rows*BUTTON_HEIGHT+(rows-1)*SPACING+2*PADDING)
