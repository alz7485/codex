"""Match the main menus and toolbar to the gadget palette."""
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from .palette import BUTTON_BASE_STYLE, BUTTON_STYLE, SPACING
from .palette_icons import palette_icon


ACTION_ICONS = {
    '新規': 'new', '開く': 'open', '保存': 'save',
    'MAC 出力': 'export', '元に戻す': 'undo', 'やり直す': 'redo',
    'コードを表示': 'code', '実機表示（参考）': 'preview',
}


def style_header(toolbar, menu_bar, recent_button):
    toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    toolbar.setIconSize(QSize(18, 18))
    toolbar.setStyleSheet(BUTTON_STYLE + f'''
QToolBar {{ background: #f5f8fc; border: 1px solid #dce4ef;
    padding: 6px; spacing: {SPACING}px; }}
QToolButton {{ padding: 0px 9px; min-height: 33px; }}
QToolButton:checked {{ background: #dcecff; border-color: #608bc2; }}
QToolButton:disabled {{ background: #f5f8fc; color: #8b95a3; border-color: #e2e8f0; }}
QToolButton::menu-indicator {{ subcontrol-origin: padding;
    subcontrol-position: right center; right: 4px; }}
''')
    for action in toolbar.actions():
        kind = ACTION_ICONS.get(action.text())
        if kind:action.setIcon(palette_icon(kind))
    recent_button.setIcon(palette_icon('recent'))
    recent_button.setIconSize(QSize(18, 18))
    recent_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    recent_button.setStyleSheet('QToolButton { padding-right: 20px; }')
    recent_button.setToolTip('最近開いた設計を選んで開きます。')
    menu_bar.setStyleSheet('''
QMenuBar { background: #f5f8fc; color: #273b52; padding: 5px 6px; spacing: 5px; }
QMenuBar::item { background: white; border: 1px solid #d3dce7;
    border-radius: 4px; padding: 7px 12px; font-size: 11px; }
QMenuBar::item:selected { background: #edf5ff; border-color: #8cafdc; }
QMenuBar::item:pressed { background: #dcecff; border-color: #608bc2; }
''')


def style_canvas_controls(controls, buttons):
    """Use smaller palette buttons for view controls above the canvas."""
    controls.setObjectName('canvasControls')
    assets = Path(__file__).parent / 'assets'
    controls.setStyleSheet(BUTTON_BASE_STYLE.replace('QToolButton', 'QPushButton') + '''
QWidget#canvasControls { background: #f5f8fc; border: 1px solid #dce4ef;
    border-radius: 5px; }
QPushButton { padding: 0px 7px; }
QPushButton:disabled { background: #f5f8fc; color: #8b95a3; border-color: #e2e8f0; }
QLabel { color: #273b52; font-size: 11px; }
QLineEdit#canvasZoomPercent, QComboBox, QDoubleSpinBox { background: white; color: #273b52;
    border: 1px solid #d3dce7; border-radius: 4px; padding: 0px 4px; font-size: 11px; }
QLineEdit#canvasZoomPercent:focus, QComboBox:focus, QDoubleSpinBox:focus { border-color: #3566a8; }
QComboBox::drop-down { border: none; width: 16px; }
QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right;
    width: 14px; border-left: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; }
QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right;
    width: 14px; border-left: 1px solid #e2e8f0; }
''' + '\nQComboBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("' +
        (assets / 'control-arrow-down.svg').as_posix() + '"); width: 8px; height: 5px; }' +
        '\nQDoubleSpinBox::up-arrow { image: url("' +
        (assets / 'control-arrow-up.svg').as_posix() + '"); width: 8px; height: 5px; }')
    for button, icon in buttons:
        button.setFixedHeight(28)
        if icon:
            button.setIcon(palette_icon(icon));button.setIconSize(QSize(16, 16))
