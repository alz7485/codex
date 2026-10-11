"""Compact split buttons: choose a variant once, click again to repeat it."""
from math import ceil
from PySide6.QtCore import Qt,QSize,Signal
from PySide6.QtGui import QAction,QActionGroup
from PySide6.QtWidgets import QWidget,QToolButton,QMenu,QGridLayout,QLayout,QSizePolicy
from .palette_icons import palette_icon

BUTTON_HEIGHT,BUTTON_WIDTH,SPACING,PADDING,MENU_WIDTH,COLUMNS=30,92,2,3,18,9
BUTTON_BASE_STYLE=f'''
QToolButton {{ background: white; color: #273b52; border: 1px solid #d3dce7;
    border-radius: 4px; padding: 1px 2px; font-size: 11px; }}
QToolButton:hover {{ background: #edf5ff; border-color: #8cafdc; }}
QToolButton:pressed {{ background: #dcecff; border-color: #608bc2; }}
QToolButton:focus {{ border-color: #3566a8; }}
'''
BUTTON_STYLE=BUTTON_BASE_STYLE+f'''
QToolButton::menu-button {{ width: {MENU_WIDTH}px; border-left: 1px solid #e2e8f0;
    border-top-right-radius: 4px; border-bottom-right-radius: 4px; }}
QToolButton::menu-button:hover {{ background: #e4effd; }}
QToolButton::menu-button:pressed {{ background: #dcecff; }}
QToolButton::menu-arrow {{ width: 7px; height: 7px; }}
'''

GROUPS = (
    ('paragraph',(('paragraph','paragraph',None,'🏷️','ラベル'),)),
    ('button',(('button','button',None,'🖱️','ボタン'),)),
    ('toggle',(('toggle','toggle',None,'☑️','チェック'),)),
    ('list',(('list','list',None,'📋','リスト'),)),
    ('slider',(('slider_horiz','slider','HORIZONTAL','🎚️','横スライダー'),('slider_vert','slider','VERTICAL','🎚️','縦スライダー'))),
    ('frame',(('frame','frame',None,'📁','フレーム'),('tabset','frame','TABSET','🗂️','タブ'))),
    ('commandline',(('commandline','commandline',None,'⌨️','コマンド'),)),
    ('selector',(('selector','selector',None,'🗃️','DBセレクタ'),)),
    ('menubar',(('menubar',None,None,'📑','メニューバー'),)),
    ('text',(('text','text',None,'✏️','入力'),)),
    ('option',(('option','option',None,'🔽','プルダウン'),('combo','combo',None,'📝','コンボ'))),
    ('rtoggle',(('rtoggle','rtoggle',None,'🔘','ラジオ'),)),
    ('textpane',(('textpane','textpane',None,'📄','複数行'),)),
    ('line',(('line_horiz','line','HORIZ','📏','横線'),('line_vert','line','VERT','↕️','縦線'))),
    ('image',(('image','paragraph','PIXMAP','🖼️','画像'),('image_option','option','PIXMAP','🖼️','画像選択'))),
    ('view',(('view','view',None,'👁️','ビュー'),)),
    ('container',(('container','container',None,'🧩','コンテナ'),)),
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
    netRequested=Signal()
    selectorMethodRequested=Signal()
    toolbarRequested=Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('gadgetPalette')
        self.setStyleSheet('QWidget#gadgetPalette { background: #f5f8fc; border: 1px solid #dce4ef; border-radius: 5px; }')
        self.buttons={};self.actions={};self._columns=0;self.action_groups=[]
        self.grid=QGridLayout(self);self.grid.setContentsMargins(PADDING,PADDING,PADDING,PADDING);self.grid.setSpacing(SPACING)
        self.grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        for group,variants in GROUPS:
            button=PaletteButton(self);button.setFixedHeight(BUTTON_HEIGHT);button.setProperty('paletteGroup',group)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);button.setIconSize(QSize(14,14))
            button.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            button.setFixedWidth(BUTTON_WIDTH)
            button.setStyleSheet(BUTTON_STYLE)
            title=' / '.join(entry[4] for entry in variants)
            button.setAccessibleName(title)
            button.setToolTip(title+'：矢印で種類を選択、ボタン本体で同じ種類を追加' if len(variants)>1 else title+'を編集' if group=='menubar' else title+'を追加')
            menu=QMenu(button) if len(variants)>1 or group in ('selector','container','toolbar') else None
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
            self.describe_choice(button,button.defaultAction(),menu is not None)
            self.buttons[group]=button
        net_action=self.buttons['container'].menu().addAction('.NET部品を簡単作成…')
        net_action.setData('net_components')
        net_action.triggered.connect(self.netRequested.emit)
        selector_action=self.buttons['selector'].menu().addAction('DBセレクタのメソッドを簡単作成…')
        selector_action.setData('db_selector_methods')
        selector_action.triggered.connect(self.selectorMethodRequested.emit)
        toolbar_action=self.buttons['toolbar'].menu().addAction('ツールバーを簡単作成…')
        toolbar_action.setData('toolbar_builder')
        toolbar_action.triggered.connect(self.toolbarRequested.emit)
        self.reflow(COLUMNS)
    def activate(self,button,action,kind,direction):
        button.setDefaultAction(action)
        self.describe_choice(button,action,button.menu() is not None)
        if kind is None:self.menuRequested.emit()
        else:self.addRequested.emit(kind,direction)

    def describe_choice(self,button,action,has_menu):
        # The menu marks the chosen variant; the main button is an add command,
        # rather than a toggle, even though its default QAction is checkable.
        button.setCheckable(False)
        label=action.text()
        group=button.property('paletteGroup')
        if group in ('image','line','slider'):
            button.setText({'image':'画像','line':'線','slider':'スライダー'}[group])
        if group in ('selector','container','toolbar'):
            button.setStyleSheet(BUTTON_STYLE+'QToolButton { padding: 1px 0px; } QToolButton::menu-button { width: 13px; }')
        operation='↓ / Alt＋↓ / F4で種類を選択、ボタン本体で同じ種類を追加' if has_menu else 'メニューバーを編集' if action.data()=='menubar' else 'この部品を追加'
        hint=label+'：'+operation
        button.setAccessibleName(label);button.setAccessibleDescription(operation);button.setToolTip(hint)
    def height_for_columns(self,columns):
        rows=ceil(len(self.buttons)/columns)
        return rows*BUTTON_HEIGHT+(rows-1)*SPACING+2*PADDING
    def sizeHint(self):return QSize(COLUMNS*BUTTON_WIDTH+(COLUMNS-1)*SPACING+2*PADDING,self.height_for_columns(COLUMNS))
    def minimumSizeHint(self):return QSize(BUTTON_WIDTH+2*PADDING,self.height_for_columns(COLUMNS))
    def resizeEvent(self,event):
        self.reflow(max(1,min(COLUMNS,(event.size().width()-2*PADDING+SPACING)//(BUTTON_WIDTH+SPACING))))
        super().resizeEvent(event)
    def reflow(self,columns):
        if columns==self._columns:return
        for index in range(self.grid.count()-1,-1,-1):self.grid.takeAt(index)
        for column in range(max(COLUMNS,self._columns)):self.grid.setColumnStretch(column,0)
        for index,button in enumerate(self.buttons.values()):self.grid.addWidget(button,index//columns,index%columns)
        self._columns=columns
        self.setFixedHeight(self.height_for_columns(columns))
