import copy
import json
import uuid
import sys
from shiboken6 import isValid
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, Signal, QMimeData, QTimer, QEvent
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QKeySequence, QPainterPath, QPixmap, QFont, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QLineEdit, QDoubleSpinBox, QComboBox, QPushButton,
    QPlainTextEdit, QLabel, QSplitter, QGraphicsScene, QGraphicsView,
    QGraphicsObject, QGraphicsItem, QListWidget, QFileDialog, QMessageBox,
    QCheckBox, QMenuBar, QMenu, QGroupBox, QTableWidget, QHeaderView, QAbstractItemView,
    QGridLayout, QTabBar, QDialog, QFrame, QDialogButtonBox, QTabWidget, QInputDialog, QToolButton, QStackedWidget)
from .palette import GadgetPalette
from .explorer import ObjectExplorer
from .form_item import FormItem
from .highlighting import PmlHighlighter,COLORS
from .colors import preview_color,foreground_color
from .model import IDENTIFIER, Form, Gadget, Menu, MenuItem, KINDS, CHAR_WIDTH, LINE_HEIGHT, display_size, native_size, fixed_dimensions, dimension_editable, normalize_dimensions, change_orientation, uses_pairs
from .images import resolve_image_path, sync_image_size
from .symbols import parse_variables,variable_text

LABELS = {'textpane':'複数行テキスト (TEXTPANE)','selector':'DB セレクタ (SELECTOR)','button': 'ボタン', 'paragraph': 'ラベル', 'text': 'テキスト入力',
          'toggle': 'チェックボックス', 'option': 'ドロップダウン', 'list': 'リスト', 'line': '線 (LINE)', 'frame': '枠 (FRAME)', 'slider':'スライダー', 'rtoggle':'ラジオボタン', 'combo':'コンボボックス', 'view':'ビュー', 'commandline':'コマンド欄 (ALPHA)', 'container':'外部部品 (CONTAINER)'}
PALETTE = {
    'button': ('🖱️','ボタン'), 'paragraph': ('🏷️','ラベル'),
    'text': ('✏️','入力'), 'toggle': ('☑️','チェック'),
    'option': ('🔽','プルダウン'), 'list': ('📋','リスト'),
    'line': ('📏','線'), 'frame': ('🖼️','フレーム'),
    'slider': ('🎚️','スライダー'), 'rtoggle': ('🔘','ラジオ'),
    'combo': ('📝','コンボ'), 'view': ('👁️','ビュー'),
    'commandline': ('⌨️','コマンド'), 'container': ('🧩','コンテナ'),
    'textpane': ('📄','複数行入力'),'selector': ('🗃️','DB セレクタ'),
}
# Independent character-width and line-height scales; approximate preview only.
SX, SY = CHAR_WIDTH, LINE_HEIGHT
GADGET_MIME = 'application/x-e3d-designer-gadgets'
PREVIEW_WIDTH_HINT = 'プレビュー用の幅です。現在のTOGGLE／OPTION出力にはWIDTHを指定せず、E3Dの幅には反映されません。'
INSPECTOR_STYLE = '''QTabWidget::pane { border: 1px solid #d6dfeb; background: #ffffff; }
QTabBar::tab { padding: 6px 9px; background: #f2f5f9; color: #46566b; }
QTabBar::tab:selected { background: #eaf3ff; color: #185fa8; border-bottom: 2px solid #2277cc; }
QTabBar::tab:disabled { color: #a5afbb; }'''


def gadget_title(g):
    if g.display_mode=='PIXMAP':return '画像選択' if g.kind=='option' else '画像'
    if g.kind=='frame' and g.frame_style=='TABSET':return 'タブセット'
    if g.kind=='frame' and g.frame_style=='TOOLBAR':return 'ツールバー'
    return LABELS[g.kind]


def preview_geometry(form, gadget):
    try: return form.geometry(gadget)
    except ValueError: return gadget.x, gadget.y, *display_size(gadget)


def free_position(rectangles,width,height,limit_width,limit_height,minimum_y=0,preferred=None):
    xs=sorted({0,*(x+w+1 for x,y,w,h in rectangles)})
    ys=sorted({minimum_y,*(max(minimum_y,y+h+.5) for x,y,w,h in rectangles)})
    positions=([preferred] if preferred is not None else [])+[(x,y) for y in ys for x in xs]
    # Prefer breathing room, then allow exact fits where borders merely touch.
    tight_xs=sorted({0,*(x+w for x,y,w,h in rectangles)})
    tight_ys=sorted({minimum_y,*(max(minimum_y,y+h) for x,y,w,h in rectangles)})
    positions += [(x,y) for y in tight_ys for x in tight_xs]
    return next(((x,y) for x,y in positions if x>=0 and y>=minimum_y and x+width<=limit_width and y+height<=limit_height
                 and all(x+width<=rx or x>=rx+rw or y+height<=ry or y>=ry+rh for rx,ry,rw,rh in rectangles)),None)


class PropertyLayout(QGridLayout):
    """Two-column property cells, with full-width rows for long values."""
    def __init__(self,parent):
        super().__init__(parent)
        self.entries = [];self.setContentsMargins(0,0,0,0)
        self.batching = False;self.pending = False
        self.setHorizontalSpacing(10);self.setVerticalSpacing(6)
        self.setColumnStretch(0,1);self.setColumnStretch(1,1)

    def addRow(self,label,editor=None,pair=None):
        if editor is None: editor,label = label,None
        cell = QWidget();layout = QVBoxLayout(cell)
        layout.setContentsMargins(0,0,0,0);layout.setSpacing(2)
        if label is not None:
            caption = QLabel(label);caption.setWordWrap(True);layout.addWidget(caption)
        layout.addWidget(editor)
        self.entries.append([editor,cell,pair,True]);self.reflow()

    def setRowVisible(self,editor,visible):
        entry = next(entry for entry in self.entries if entry[0] is editor)
        if entry[3] == visible: return
        entry[3] = visible
        if self.batching: self.pending = True
        else: self.reflow()

    def setCaption(self,editor,text):
        entry = next(entry for entry in self.entries if entry[0] is editor)
        caption = entry[1].findChild(QLabel)
        if caption is not None and caption.text() != text: caption.setText(text)

    def reflow(self):
        self.pending = False
        while self.count(): self.takeAt(0)
        visible = [entry for entry in self.entries if entry[3]]
        for _,cell,_,show in self.entries: cell.setVisible(show)
        used = set();row = 0
        for editor,cell,pair,_ in visible:
            if id(editor) in used: continue
            partner = next((entry for entry in visible if pair and entry[2] == pair and entry[0] is not editor),None)
            if partner:
                self.addWidget(cell,row,0);self.addWidget(partner[1],row,1)
                used.add(id(partner[0]))
            else: self.addWidget(cell,row,0,1,2)
            used.add(id(editor));row += 1


class PropertyPages:
    """Keep existing property synchronization shared across compact tab pages."""
    def __init__(self,tabs):
        self.tabs=tabs
        self.pages={};self.owners={};self.current='基本';self.batching=False
        for title in ('基本','配置','内容','動作'):
            page=QWidget();layout=QVBoxLayout(page);content=QWidget()
            grid=PropertyLayout(content);layout.addWidget(content);layout.addStretch()
            tabs.addTab(page,title);self.pages[title]=grid

    def addRow(self,label,editor=None,pair=None):
        actual=editor if editor is not None else label
        grid=self.pages[self.current];self.owners[actual]=grid
        grid.addRow(label,editor,pair)

    def setRowVisible(self,editor,visible):
        grid=self.owners[editor];grid.batching=self.batching;grid.setRowVisible(editor,visible)
        if not self.batching:self.activate_page(grid)
        if not self.batching:self.update_tabs()

    def setCaption(self,editor,text):self.owners[editor].setCaption(editor,text)

    @property
    def pending(self):return any(grid.pending for grid in self.pages.values())

    def reflow(self):
        for grid in self.pages.values():
            grid.batching=False;grid.reflow();self.activate_page(grid)
        self.update_tabs()

    def update_tabs(self):
        current=self.tabs.currentIndex()
        for index,grid in enumerate(self.pages.values()):
            self.tabs.setTabEnabled(index,any(entry[3] for entry in grid.entries))
        if not self.tabs.isTabEnabled(current):self.tabs.setCurrentIndex(0)

    @staticmethod
    def activate_page(grid):
        grid.activate();content=grid.parentWidget();content.updateGeometry()
        page=content.parentWidget();page.layout().activate();page.updateGeometry()


def preview_offset(form, gadget):
    try: return form.offset(gadget)
    except ValueError: return 0, 0


class Item(QGraphicsObject):
    moved = Signal(object,str,float,float)
    groupMoved = Signal(object,object,float,float)
    resizing = Signal()
    resized = Signal(object)
    pageChosen = Signal(str)
    selectionToggled = Signal(str)
    labelEditRequested = Signal(str)

    def __init__(self, gadget, form, image_directories=()):
        super().__init__()
        self.gadget, self.form = gadget, form
        self._resize = None
        self._move_start = None
        self._move_pos = None
        self._move_origin = None
        self._move_children = []
        self._move_names = []
        self._tab_press = None
        self._cancelled = False
        self._sync_geometry = False
        image_path = gadget.pixmap_path if gadget.kind != 'option' else (gadget.items[0] if gadget.items else '')
        if image_path: image_path = resolve_image_path(image_path,image_directories)
        self.pixmap = QPixmap(image_path) if gadget.display_mode == 'PIXMAP' and image_path else QPixmap()
        self.setAcceptHoverEvents(True)
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        parent = form.parent_gadget(gadget)
        if gadget.layout_mode == 'ABSOLUTE' and not (parent and parent.frame_style in ('TOOLBAR','TABSET')): self.setFlag(QGraphicsItem.ItemIsMovable)
        ox, oy = preview_offset(form, gadget)
        x, y, self._width, self._height = preview_geometry(form, gadget)
        self.setPos((x + ox) * SX, (y + oy) * SY)
        self.setZValue(len(form.descendants(gadget.name)) * -1 if gadget.kind == 'frame' else 1)

    def boundingRect(self):
        return QRectF(0, 0, self._width * SX, self._height * SY)

    def shape(self):
        path = QPainterPath(); rect = self.boundingRect()
        parent = self.form.parent_gadget(self.gadget)
        if self.gadget.kind == 'frame' and parent and parent.frame_style == 'TABSET': rect = rect.adjusted(0, 26, 0, 0)
        path.addRect(rect)
        if self.scene():
            # Overlapping children must leave selected resize handles reachable.
            selected_items=self.scene().selectedItems()
            for selected in selected_items if len(selected_items)==1 else ():
                if selected is self or not isinstance(selected,(Item,FormItem)):continue
                for handle in selected.handles().values():
                    hole=QPainterPath();hole.addRect(self.mapRectFromScene(selected.mapRectToScene(handle)))
                    path=path.subtracted(hole)
        return path

    def tab_page_at(self, pos):
        if self.gadget.kind == 'frame' and self.gadget.frame_style == 'TABSET' and 0 <= pos.y() < 26:
            pages = self.form.children(self.gadget.name)
            if pages:
                index = min(len(pages)-1, max(0,int(pos.x() / (self._width * SX / len(pages)))))
                return pages[index]
        return None

    def mousePressEvent(self, event):
        if event.button()!=Qt.LeftButton:event.ignore();return
        self._cancelled=False
        self._tab_press=None
        g = self.gadget
        if event.modifiers() & (Qt.ControlModifier|Qt.ShiftModifier):
            self.selectionToggled.emit(g.name);event.accept();return
        handle = self.handle_at(event.pos())
        if event.button() == Qt.LeftButton and handle:
            self._resize = (handle,event.scenePos(),g.width,g.height,copy.deepcopy(self.form))
            event.accept(); return
        page = self.tab_page_at(event.pos())
        if page:
            self._tab_press=(page.name,event.screenPos())
        scene=self.scene();changed=not self.isSelected();previous=scene.blockSignals(True)
        if changed:
            for item in scene.selectedItems():item.setSelected(False)
        self.setSelected(True);scene.blockSignals(previous)
        if changed and not previous:scene.selectionChanged.emit()
        if self.flags() & QGraphicsItem.ItemIsMovable:
            self._move_start=copy.deepcopy(self.form);self._move_pos=self.pos();self._move_origin=event.scenePos()
            self._move_names=list(self.selected_names())
            moving=set(self._move_names)
            for name in self._move_names:moving.update(self.form.descendants(name))
            self._move_children=[(item,item.pos()) for item in scene.items()
                                 if isinstance(item,Item) and item is not self and item.gadget.name in moving]
        event.accept()

    def cancel_interaction(self):
        if self._resize is not None:
            _,_,width,height,_=self._resize;self._resize=None
            self.gadget.width,self.gadget.height=width,height
            self.resizing.emit()
        elif self._move_start is not None:
            self._sync_geometry=True;self.setPos(self._move_pos);self._sync_geometry=False
            for child,origin in self._move_children:
                child._sync_geometry=True;child.setPos(origin);child._sync_geometry=False
        elif self._tab_press is not None:pass
        else:return False
        self._move_start=None;self._move_children=[];self._tab_press=None;self._cancelled=True
        return True

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:
            self._move_start=None;self._move_children=[];self._tab_press=None
            page = self.tab_page_at(event.pos())
            self.labelEditRequested.emit(page.name if page else self.gadget.name);event.accept();return
        super().mouseDoubleClickEvent(event)

    def selected_names(self):
        scene=self.scene()
        if not scene:return set()
        selected_names=getattr(scene.parent(),'selection_names',None)
        if callable(selected_names):return selected_names()
        return {item.gadget.name for item in scene.selectedItems() if isinstance(item,Item)}

    def handles(self):
        if not self.isSelected() or self.form.is_tab_page(self.gadget): return {}
        if len(self.selected_names())>1:return {}
        if self.gadget.display_mode == 'PIXMAP':return {}
        r = self.boundingRect(); size = 8
        result = {'height':QRectF(r.center().x()-size/2,r.bottom()-size,size,size)} if dimension_editable(self.gadget,'height') else {}
        if dimension_editable(self.gadget,'width'):
            result['width'] = QRectF(r.right()-size,r.center().y()-size/2,size,size)
            if 'height' in result:result['both'] = QRectF(r.right()-size,r.bottom()-size,size,size)
        return result

    def handle_at(self, point):
        return next((name for name,rect in reversed(list(self.handles().items())) if rect.contains(point)),None)

    def hoverMoveEvent(self, event):
        handle = self.handle_at(event.pos())
        self.setToolTip(PREVIEW_WIDTH_HINT if handle=='width' and ((self.gadget.kind=='toggle' and self.gadget.display_mode=='TEXT') or uses_pairs(self.gadget)) else '')
        self.setCursor({'width':Qt.SizeHorCursor,'height':Qt.SizeVerCursor,'both':Qt.SizeFDiagCursor}.get(handle,Qt.ArrowCursor))
        super().hoverMoveEvent(event)

    def mouseMoveEvent(self, event):
        if self._cancelled:event.accept();return
        if self._resize is None:
            if self._move_start is not None:
                if self._tab_press is not None:
                    if (event.screenPos()-self._tab_press[1]).manhattanLength()<QApplication.startDragDistance():
                        event.accept();return
                    self._tab_press=None
                # Move each selected object and descendant once from its original position.
                self.setPos(self._move_pos+event.scenePos()-self._move_origin)
                delta=self.pos()-self._move_pos
                for child,origin in self._move_children:
                    child._sync_geometry=True
                    child.setPos(origin+delta)
                    child._sync_geometry=False
                event.accept();return
            # All movement is model-owned; Qt's fallback can move only the TABSET outline.
            event.accept();return
        handle, origin, width, height, _ = self._resize
        delta = event.scenePos()-origin; g = self.gadget
        old_width, old_height = g.width,g.height
        if g.display_mode != 'PIXMAP':
            if handle in ('width','both') and dimension_editable(g,'width'): g.width = max(1,round((width+delta.x()/SX)*2)/2)
            if handle in ('height','both') and dimension_editable(g,'height'): g.height = max(1,round((height+delta.y()/SY)*2)/2)
        try:
            for candidate in self.form.gadgets:
                x,y,w,h = self.form.geometry(candidate)
                parent = self.form.parent_gadget(candidate)
                pw,ph = self.form.geometry(parent)[2:] if parent else (self.form.width,self.form.height)
                if x < -.001 or y < -.001 or x+w > pw+.001 or y+h > ph+.001:
                    raise ValueError('部品を親の領域内に収めてください。')
        except ValueError:
            g.width,g.height = old_width,old_height
        self.resizing.emit(); event.accept()

    def text_regions(self,metrics):
        rect=self.boundingRect()
        label_width=min(metrics.horizontalAdvance(self.gadget.label)+8,max(0,rect.width()*.45)) if self.gadget.label else 0
        label=QRectF(4,1,max(0,label_width-4),max(0,rect.height()-2))
        entry=rect.adjusted(label_width+4 if label_width else 1,1,-1,-1)
        return label,entry

    def paint(self, painter, option, widget=None):
        r, g = self.boundingRect(), self.gadget
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#7f91a5'), 1))
        background=preview_color(g.background) if g.background and g.kind in ('button','paragraph','list') else None
        painter.setBrush(QColor(background or ('#eff3f8' if g.kind == 'button' else '#ffffff')))
        if g.kind == 'frame':
            parent = self.form.parent_gadget(g)
            painter.setBrush(Qt.NoBrush)
            if not (parent and parent.frame_style == 'TABSET'):
                painter.drawRect(r.adjusted(1, 1, -1, -1))
            if g.frame_style == 'TABSET':
                pages = self.form.children(g.name)
                for i, page in enumerate(pages):
                    tab = QRectF(i*r.width()/len(pages), 0, r.width()/len(pages), 25)
                    painter.setBrush(QColor('#d8eaff' if page.name.lower() == getattr(self, 'active_page', '') else '#edf1f5'))
                    painter.drawRect(tab)
                    painter.drawText(tab.adjusted(6, 0, -6, 0), Qt.AlignVCenter, page.label)
        elif g.kind == 'slider':
            vertical = g.slider_orientation == 'VERTICAL'
            fraction = max(0,min(1,(g.slider_value-g.slider_min)/(g.slider_max-g.slider_min))) if g.slider_max > g.slider_min else 0
            if vertical:
                painter.drawLine(r.center().x(),r.top()+8,r.center().x(),r.bottom()-8)
                knob = QRectF(r.center().x()-6,r.bottom()-8-fraction*max(0,r.height()-16)-5,12,10)
            else:
                painter.drawLine(r.left()+8,r.center().y(),r.right()-8,r.center().y())
                knob = QRectF(r.left()+8+fraction*max(0,r.width()-16)-5,r.center().y()-6,10,12)
            painter.setBrush(QColor('#77a9dd')); painter.drawRoundedRect(knob,2,2)
        elif g.kind in ('view','commandline'):
            painter.setBrush(QColor('#15283b')); painter.drawRect(r.adjusted(1,1,-1,-1))
        elif g.kind == 'container':
            painter.setPen(QPen(QColor('#7f91a5'),1,Qt.DashLine)); painter.drawRect(r.adjusted(1,1,-1,-1))
        elif g.kind == 'line':
            if g.orientation == 'HORIZ':
                painter.drawLine(r.left(), r.center().y(), r.right(), r.center().y())
            else:
                painter.drawLine(r.center().x(), r.top(), r.center().x(), r.bottom())
        elif g.kind=='text':
            _,entry=self.text_regions(painter.fontMetrics())
            painter.drawRect(entry)
        else:
            painter.drawRoundedRect(r.adjusted(1, 1, -1, -1), 3, 3)
        painter.setPen(QColor(foreground_color(background) if background else '#182b40'))
        text = g.label
        if g.display_mode == 'PIXMAP':
            if not self.pixmap.isNull():
                target = QRectF((r.width()-self.pixmap.width())/2,(r.height()-self.pixmap.height())/2,self.pixmap.width(),self.pixmap.height())
                painter.drawPixmap(target,self.pixmap,QRectF(self.pixmap.rect()));text = ''
            else: text = '🖼 PIXMAP\n'+(g.pixmap_path if g.kind != 'option' else (g.items[0] if g.items else '画像未設定'))
        if g.kind == 'textpane':
            if g.fixed_font: painter.setFont(QFont('monospace',10))
            text = '\n'.join(g.pane_lines) or g.label
        if g.kind == 'selector': text = g.label+'\nDATABASE '+g.database+'\n(E3D で取得)'
        if g.kind == 'frame':
            parent = self.form.parent_gadget(g)
            if self.form.children(g.name) and g.frame_style == 'TABSET': text = ''
            if parent and parent.frame_style == 'TABSET': text = ''
        if g.kind == 'paragraph' and g.background: text += f' [BG {g.background}]'
        if g.kind == 'text':
            label,entry=self.text_regions(painter.fontMetrics())
            painter.drawText(label,Qt.AlignLeft|Qt.AlignVCenter,painter.fontMetrics().elidedText(g.label,Qt.ElideRight,max(0,int(label.width()))))
            painter.drawText(entry.adjusted(5,1,-5,-1),Qt.AlignLeft|Qt.AlignVCenter,g.initial)
            text=''
        if g.kind == 'toggle': text = ('☑ ' if g.initial.upper()=='TRUE' else '☐ ') + text
        if g.kind in ('option','combo') and g.display_mode != 'PIXMAP': text += '  ▾'
        if g.kind == 'rtoggle': text = ('● ' if g.initial.upper()=='TRUE' else '○ ')+text
        if g.kind == 'slider': text = ''
        if g.kind in ('view','commandline'):
            painter.setPen(QColor('#d7e7f7'))
            text = ('ALPHA\n> ' if g.kind == 'commandline' or g.view_type == 'ALPHA' else g.view_type+'\n') + g.label
        if g.kind == 'container': text = 'PML.NET\n'+(g.control_type or g.label)
        if g.kind == 'list':
            if g.list_mode == 'TABLE' and g.headings:
                painter.save(); painter.setClipRect(r.adjusted(1,1,-1,-1))
                column_width = r.width()/len(g.headings)
                for row,values in enumerate([g.headings,*g.rows]):
                    if row*SY >= r.height(): break
                    for column,value in enumerate(values):
                        cell = QRectF(column*column_width,row*SY,column_width,SY)
                        painter.setPen(QColor('#9caabd')); painter.setBrush(QColor('#dfeaf5' if row == 0 else (background or '#ffffff')))
                        painter.drawRect(cell); painter.setPen(QColor(foreground_color(background) if background and row != 0 else '#182b40'))
                        painter.drawText(cell.adjusted(4,1,-4,-1),Qt.AlignLeft|Qt.AlignVCenter,value)
                painter.restore(); text = ''
            else: text = '\n'.join(g.items) or g.label
        alignment = Qt.AlignCenter if g.kind == 'button' else Qt.AlignLeft | (Qt.AlignTop if g.kind in ('frame','textpane','selector') else Qt.AlignVCenter)
        painter.drawText(r.adjusted(7, 2, -7, -2), alignment, text)
        if self.isSelected():
            painter.setPen(QPen(QColor('#2277cc'), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            selection_rect=self.shape().boundingRect() if self.form.is_tab_page(g) else r
            painter.drawRect(selection_rect.adjusted(1, 1, -1, -1))
            painter.setPen(QPen(QColor('#2277cc'),1)); painter.setBrush(QColor('#ffffff'))
            for handle in self.handles().values(): painter.drawRect(handle)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() and not self._sync_geometry:
            g = self.gadget
            value.setX(max(0,min(round(value.x()/SX*2)/2,self.form.width-self._width))*SX)
            value.setY(max(0,min(round(value.y()/SY*2)/2,self.form.height-self._height))*SY)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        if event.button()!=Qt.LeftButton:event.ignore();return
        if self._cancelled:
            self._cancelled=False;event.accept();return
        if self._resize is not None:
            _,_,width,height,old = self._resize; self._resize = None
            if (self.gadget.width,self.gadget.height) != (width,height): self.resized.emit(old)
            event.accept(); return
        if self._tab_press is not None:
            name,_=self._tab_press;self._tab_press=None;self._move_start=None;self._move_children=[]
            self.pageChosen.emit(name);event.accept();return
        event.accept()
        old=self._move_start;self._move_start=None
        if old is None or self.pos()==self._move_pos:return
        if len(self._move_names)>1:
            delta=self.pos()-self._move_pos
            self.groupMoved.emit(old,self._move_names,round(delta.x()/SX,2),round(delta.y()/SY,2))
        else:self.moved.emit(old,self.gadget.name,round(self.pos().x()/SX,2),round(self.pos().y()/SY,2))


class TableCell(QLineEdit):
    focused = Signal()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()


class Scene(QGraphicsScene):
    def drawBackground(self, painter, rect):
        painter.fillRect(rect,QColor('#e8edf3'))
        form=self.parent().form
        painter.fillRect(QRectF(0,0,form.width*SX,form.height*SY),QColor('#f8fafc'))
        painter.setPen(QPen(QColor('#d9e2ec'), 1))
        for x in range(0,int(form.width*SX),SX):
            for y in range(0,int(form.height*SY),SY):painter.drawPoint(x,y)


class Window(QMainWindow):
    def __init__(self, settings_path=None):
        super().__init__()
        from .settings import Settings
        self.settings=Settings(settings_path)
        from .recovery import RecoveryStore
        self.recovery=RecoveryStore(self.settings.path.parent/'recovery')
        self.backup_timer=QTimer(self);self.backup_timer.setInterval(30000)
        self.backup_timer.timeout.connect(self.backup_work)
        self.setWindowIcon(QIcon(str(Path(__file__).parent/'assets'/'app-icon.ico')))
        self.form, self.path, self.selected = Form(), None, None
        self._multi_selection=set()
        self.project_key = uuid.uuid4().hex
        self.selected_menu = None
        self.preview_menus = []
        self.history, self.future = [], []
        self.active_pages = {}
        self.dirty, self.loading = False, False
        self.variable_error = False
        self._closing = False
        self.current_workflow='form'
        self.validation_error=''
        self.resize(1380, 880)
        self.setWindowTitle('E3D PML Form Designer — E3D 4.0 想定')
        toolbar = self.addToolBar('ファイル')
        toolbar.setMovable(False)
        file_menu=self.menuBar().addMenu('ファイル');edit_menu=self.menuBar().addMenu('編集')
        for label, fn, shortcut in [('新規', self.new, 'Ctrl+N'), ('開く', self.open, 'Ctrl+O'),
                ('保存', self.save, 'Ctrl+S'), ('名前を付けて保存', self.save_as, 'Ctrl+Shift+S'), ('MAC 出力', self.export, 'Ctrl+E'),
                ('元に戻す', self.undo, 'Ctrl+Z'), ('やり直す', self.redo, 'Ctrl+Shift+Z'),
                ('複製', self.duplicate, 'Ctrl+D'), ('削除', self.delete, None)]:
            a = QAction(label, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut));a.setToolTip(f'{label} ({shortcut})')
            a.triggered.connect(fn)
            if label=='保存':self.save_action=a
            (edit_menu if label in ('元に戻す','やり直す','複製','削除') else file_menu).addAction(a)
            if label not in ('名前を付けて保存','複製','削除'):toolbar.addAction(a)
        self.code_action=QAction('コードを表示',self);self.code_action.setShortcut(QKeySequence('Ctrl+Shift+C'))
        self.code_action.triggered.connect(self.show_code);toolbar.addAction(self.code_action);file_menu.addAction(self.code_action)
        names_action = QAction('変数・名前管理',self)
        names_action.setShortcut(QKeySequence('Ctrl+M'));names_action.triggered.connect(self.manage_names)
        edit_menu.addAction(names_action)
        import_action=file_menu.addAction('MACを読み込む…')
        import_action.triggered.connect(self.open_mac)
        partial_action=file_menu.addAction('MACを部分的に読み込む…')
        partial_action.triggered.connect(self.open_partial_mac)
        source_action=edit_menu.addAction('取り込みコードを編集…')
        source_action.triggered.connect(self.edit_imported_code)
        methods_action=edit_menu.addAction('補助メソッド管理…')
        methods_action.triggered.connect(self.manage_methods)
        self.partial_notice=QPushButton('部分取り込みの省略箇所')
        self.partial_notice.setToolTip('未復元の宣言と元MACを確認します。省略した処理はMACへ出力されません。')
        self.partial_notice.clicked.connect(self.edit_imported_code)
        self.statusBar().addPermanentWidget(self.partial_notice)
        self.partial_notice.hide()
        self.recent_menu=QMenu('最近の設計',self)
        recent_button=QToolButton();recent_button.setText('最近の設計')
        recent_button.setMenu(self.recent_menu);recent_button.setPopupMode(QToolButton.InstantPopup)
        toolbar.addWidget(recent_button)
        file_menu.addMenu(self.recent_menu)
        recovery_action=file_menu.addAction('作業を復元');recovery_action.triggered.connect(self.recover_work)
        self.refresh_recent_menu()
        root = QWidget(); outer = QVBoxLayout(root)
        columns = QSplitter();self.columns=columns
        left = QWidget();self.library_panel=left;ll = QVBoxLayout(left)
        ll.addWidget(QLabel('ツリーエクスプローラ'))
        self.palette_panel=GadgetPalette()
        self.palette_panel.addRequested.connect(self.add)
        self.palette_panel.menuRequested.connect(self.add_palette_menu)
        self.palette_buttons=self.palette_panel.buttons
        self.palette_actions=self.palette_panel.actions
        self.placement_hint=QLabel();self.placement_hint.setWordWrap(True)
        self.placement_hint.setStyleSheet('color: #185fa8; padding: 4px; background: #eaf3ff;')
        self.objects = ObjectExplorer(); self.objects.selectionRowsChanged.connect(self.choose_rows)
        self.objects.setContextMenuPolicy(Qt.CustomContextMenu)
        self.objects.customContextMenuRequested.connect(self.tree_popup)
        self.objects.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.objects.setTextElideMode(Qt.ElideRight)
        self.objects.moveRequested.connect(self.move_tree_gadget);ll.addWidget(self.objects,1);ll.addWidget(self.placement_hint)
        self.objects.itemDoubleClicked.connect(self.edit_tree_item)
        self.objects.setToolTip('フレームをフォルダとして表示。ドラッグで順序や所属フレームを変更できます。')
        left.setMinimumWidth(220); columns.addWidget(left)
        self.scene = Scene(self); self.scene.selectionChanged.connect(self.selection_changed)
        self.view = QGraphicsView(self.scene)
        self.view.installEventFilter(self);self.view.viewport().installEventFilter(self)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.preview_popup)
        self.edit_actions = []
        for widget in (self.view,self.objects):
            for label,key,handler in (('コピー','Ctrl+C',self.copy_gadget),('貼り付け','Ctrl+V',self.paste_gadget),('切り取り','Ctrl+X',self.cut_gadget),('削除','Del',self.delete)):
                action = QAction(label,widget)
                action.setShortcut(QKeySequence(key))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                action.triggered.connect(handler);widget.addAction(action)
                self.edit_actions.append(action)
        self.view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        preview = QWidget();self.canvas_panel=preview
        preview_layout = QVBoxLayout(preview); preview_layout.setContentsMargins(0,0,0,0)
        preview_layout.addWidget(self.palette_panel)
        self.preview_menu_bar = QMenuBar(); self.preview_menu_bar.setNativeMenuBar(False)
        self.preview_menu_frame=QFrame();self.preview_menu_frame.setObjectName("previewMenuFrame")
        self.preview_menu_frame.setStyleSheet("QFrame#previewMenuFrame { border: 1px solid #7f91a5; border-radius: 3px; background: white; }")
        self.preview_menu_frame.setToolTip("フォームのメニューバー：ダブルクリックで編集")
        self.preview_menu_bar.installEventFilter(self);self.preview_menu_frame.installEventFilter(self)
        menu_layout=QVBoxLayout(self.preview_menu_frame);menu_layout.setContentsMargins(3,2,3,2)
        menu_layout.addWidget(self.preview_menu_bar);preview_layout.addWidget(self.preview_menu_frame)
        self.tab_editor=QWidget();tab_layout=QHBoxLayout(self.tab_editor);tab_layout.setContentsMargins(0,0,0,0)
        tab_layout.addWidget(QLabel('編集するタブ'))
        self.tabset_picker=QComboBox();self.tabset_picker.currentIndexChanged.connect(self.change_tabset)
        tab_layout.addWidget(self.tabset_picker)
        self.page_tabs=QTabBar();self.page_tabs.setExpanding(False);self.page_tabs.setMovable(True)
        self.page_tabs.currentChanged.connect(self.change_edit_page);self.page_tabs.tabMoved.connect(self.reorder_pages)
        tab_layout.addWidget(self.page_tabs,1)
        self.add_page_button=QPushButton('＋ タブ');self.add_page_button.clicked.connect(self.add_page)
        tab_layout.addWidget(self.add_page_button)
        self.edit_page_button=QPushButton('タブ設定');self.edit_page_button.clicked.connect(self.edit_page)
        tab_layout.addWidget(self.edit_page_button)
        self.delete_page_button=QPushButton('− タブ');self.delete_page_button.clicked.connect(self.delete_page)
        tab_layout.addWidget(self.delete_page_button)
        preview_layout.addWidget(self.tab_editor);preview_layout.addWidget(self.view)
        columns.addWidget(preview)
        self.code = QPlainTextEdit(); self.code.setReadOnly(True)
        self.code.setStyleSheet('font-family: monospace; font-size: 12px;')
        code_panel=QWidget();code_layout=QVBoxLayout(code_panel);code_layout.setContentsMargins(0,0,0,0);code_layout.setSpacing(3)
        self.output_summary=QLabel();self.output_summary.setWordWrap(True);code_layout.addWidget(self.output_summary)
        self.output_validation=QLabel();self.output_validation.setWordWrap(True);code_layout.addWidget(self.output_validation)
        output_actions=QHBoxLayout()
        save_design=QPushButton('編集用JSONを保存');save_design.clicked.connect(self.save)
        export_mac=QPushButton('MACを出力');export_mac.clicked.connect(self.export)
        output_actions.addWidget(save_design);output_actions.addWidget(export_mac);output_actions.addStretch()
        code_layout.addLayout(output_actions)
        output_row=QHBoxLayout();output_row.addWidget(QLabel('出力先フォルダ'))
        self.output_folder=QLineEdit(str(self.settings.output_folder));self.output_folder.editingFinished.connect(self.save_output_folder)
        self.output_folder.setToolTip('初期値はアプリと同じフォルダ。変更すると settings.json に保存します。')
        output_row.addWidget(self.output_folder,1)
        browse_output=QPushButton('📁');browse_output.setToolTip('出力先フォルダを選択');browse_output.clicked.connect(self.choose_output_folder);output_row.addWidget(browse_output)
        code_layout.addLayout(output_row)
        legend=QLabel('  '.join(f'<span style="color:{COLORS[kind]}">{label}</span>' for kind,label in (('command','コマンド'),('object','オブジェクト'),('variable','変数'),('string','文字列'),('number','数値・論理値'),('method','メソッド'),('comment','コメント'))))
        legend.setWordWrap(True);code_layout.addWidget(legend);code_layout.addWidget(self.code)
        code_layout.addWidget(QLabel('出力形式: .mac / SJIS（CP932）/ CRLF  •  E3Dで読み込みと動作を確認してください。'))
        self.output_dialog=QDialog(self,Qt.Window);self.output_dialog.setWindowTitle('生成コード・MAC出力')
        self.output_dialog.resize(1000,760)
        output_layout=QVBoxLayout(self.output_dialog);output_layout.addWidget(code_panel)
        close_code=QPushButton('閉じる');close_code.clicked.connect(self.output_dialog.close);output_layout.addWidget(close_code)
        right = QTabWidget();self.inspector_tabs=right
        right.setStyleSheet(INSPECTOR_STYLE)
        form_page=QWidget();rl=QVBoxLayout(form_page)
        self.form_fields = QFormLayout()
        self.fname = QLineEdit(); self.ftitle = QLineEdit()
        self.fname.setToolTip('自動設定済みです。管理しやすい名前にしたい場合だけ変更してください。')
        self.fw, self.fh = self.number(1, 300), self.number(1, 300)
        for label, w in [('フォーム名（任意変更）', self.fname), ('タイトル', self.ftitle)]:
            self.form_fields.addRow(label, w); self.connect_field(w, self.update_form)
        form_size=QHBoxLayout();form_size.addWidget(QLabel('幅'));form_size.addWidget(self.fw)
        form_size.addWidget(QLabel('高さ'));form_size.addWidget(self.fh)
        self.form_fields.addRow('サイズ (PML)',form_size)
        self.connect_field(self.fw,self.update_form);self.connect_field(self.fh,self.update_form)
        self.docking = QComboBox()
        for label,value in (('通常ダイアログ','NONE'),('右ドッキング','RIGHT'),('左ドッキング','LEFT'),('上ドッキング','TOP'),('下ドッキング','BOTTOM'),('MAIN フォーム','MAIN')):
            self.docking.addItem(label,value)
        self.docking.currentIndexChanged.connect(self.update_form)
        self.form_fields.addRow('表示形式', self.docking)
        rl.addLayout(self.form_fields)
        rl.addWidget(QLabel('追加の変数（グローバル／ローカル・任意）'))
        self.variables = QPlainTextEdit(); self.variables.setMaximumHeight(90)
        self.variables.setPlaceholderText('projectName=Project A  ← グローバル\n!localName=初期値  ← ローカル')
        self.variables.setToolTip('名前=値 / !!名前=値 はグローバル、!名前=値 はローカルです。\nローカルはフォーム定義前にVAR !名前を出力します。メソッド内では別のスコープになるため、そのメソッドで宣言してください。')
        self.variables.textChanged.connect(self.update_variables)
        rl.addWidget(self.variables)
        self.after_show = QPlainTextEdit(); self.after_show.setFixedHeight(64)
        self.after_show.setPlaceholderText('SHOW の後に出力する任意の PML プログラム')
        self.after_show.textChanged.connect(self.update_after_show)
        self.default_body = QPlainTextEdit(); self.default_body.setFixedHeight(64)
        self.default_body.setPlaceholderText('DEFINE METHOD .DEFAULT() の中に出力する PML')
        self.default_body.textChanged.connect(self.update_default_body)
        lifecycle = QGroupBox('フォームのコールバック');lifecycle_layout = QFormLayout(lifecycle)
        self.form_callbacks = {}
        for event in ('initcall','okcall','cancelcall'):
            editor = QLineEdit();editor.setPlaceholderText('!THIS.メソッド名() または PML コマンド')
            self.form_callbacks[event] = editor;lifecycle_layout.addRow(event.upper(),editor)
            editor.textEdited.connect(lambda text,e=event:self.update_form_callback(e,text))
        rl.addWidget(lifecycle)
        rl.addStretch()
        part_page=QWidget();rl=QVBoxLayout(part_page)
        self.selection_stack=QStackedWidget();self.selection_stack.addWidget(form_page);self.selection_stack.addWidget(part_page)
        multiple_page=QWidget();multiple_page.setStyleSheet('background: #eceff2; color: #8b95a3;')
        multiple_layout=QVBoxLayout(multiple_page);self.multiple_hint=QLabel();self.multiple_hint.setWordWrap(True)
        multiple_layout.addWidget(self.multiple_hint);multiple_layout.addStretch();self.selection_stack.addWidget(multiple_page)
        right.addTab(self.selection_stack,'プロパティ');right.setCurrentIndex(0)
        self.selection_hint=QLabel();self.selection_hint.setWordWrap(True)
        self.selection_hint.setStyleSheet('color: #46566b; padding: 4px;')
        rl.addWidget(self.selection_hint)
        self.props = QTabWidget(); self.prop_layout = PropertyPages(self.props)
        self.fields = {}
        pairs = {}
        for first,second in (('name','label'),('x','y'),('width','height'),('value_type','initial'),('macro_flag','macro_value'),
                ('orientation','background'),('parent','frame_style'),('layout_mode','path'),
                ('halign','valign'),('hgap','vgap'),('xref','yref'),('xedge','yedge'),('xanchor','width_ref'),
                ('xoffset','yoffset'),('selection_mode','list_mode'),('combo_keyword','combo_scroll'),('slider_min','slider_max'),
                ('slider_step','slider_value'),('off_value','on_value'),('view_type','view_aspect'),('display_mode','button_role')):
            pairs[first] = pairs[second] = first
        for key, label in [('name', '部品名'), ('label', '表示文字'), ('x', 'X'), ('y', 'Y'), ('width', '幅'), ('height', '高さ / 行数'), ('value_type', '入力型'), ('initial', '初期値'), ('callback', 'メソッド名'), ('command', 'CALL コマンド'), ('background', 'BACKGROUND (空欄＝背景色)'), ('orientation', 'LINE の向き'), ('frame_style', 'FRAME 形式'), ('parent', '親コンテナ'), ('layout_mode', '配置方式'), ('path', '配置方向'), ('halign', '水平整列'), ('valign', '垂直整列'), ('hgap', '横間隔'), ('vgap', '縦間隔'), ('xref', 'X 基準部品'), ('xedge', 'X 基準辺'), ('xanchor', '自部品の X 辺'), ('xoffset', 'X オフセット'), ('yref', 'Y 基準部品'), ('yedge', 'Y 基準辺'), ('yoffset', 'Y オフセット'), ('width_ref', '幅を揃える部品'),
                ('selection_mode','LIST 選択方式'), ('list_mode','LIST 表示方式'), ('table_method','表の設定メソッド名'), ('combo_keyword','COMBO 定義キーワード'), ('combo_scroll','SCROLL（表示量）'), ('combo_tagwid','TAGWID（表示名の幅）'),
                ('slider_orientation','SLIDER の向き'), ('slider_min','最小値'), ('slider_max','最大値'), ('slider_step','刻み'), ('slider_value','スライダー初期値'),
                ('off_value','ラジオ OFF 実値'), ('on_value','ラジオ ON 実値'),
                ('view_type','VIEW 形式'), ('view_aspect','ASPECT (VIEW)'), ('channels','ALPHA チャンネル'),
                ('assembly','CONTAINER アセンブリ'), ('namespace','名前空間'), ('control_type','コントロール型'),
                ('display_mode','文字 / 画像'),('pixmap_path','画像ファイル (E3D 側のパス)'),('popup_menu','ポップアップメニュー'),
                ('database','DATABASE'),('button_role','ボタン属性'),('action_mode','ボタンの処理方式'),('macro_path','外部マクロのファイル'),('macro_flag','分岐用の変数名'),('macro_value','このボタンの分岐値')]:
            if key in ('slider_min','slider_max','slider_step','slider_value'):
                w = self.number(-1e9, 1e9)
            elif key in ('x','y','width','height','hgap','vgap','xoffset','yoffset'):
                w = self.number(-300 if key in ('xoffset','yoffset') else 0 if key in ('x','y','hgap','vgap') else 1, 300)
            elif key in ('parent','xref','yref','width_ref','popup_menu'):
                w = QComboBox(); w.addItem('(フォーム直下)', '')
            elif key in ('value_type','orientation','frame_style','layout_mode','path','halign','valign','xedge','yedge','xanchor','selection_mode','combo_keyword','slider_orientation','view_type','channels','list_mode','display_mode','database','button_role','action_mode'):
                w = QComboBox()
                w.addItems({'action_mode':['CODE','MACRO'],'display_mode':['TEXT','PIXMAP'],'database':['OWNERS','MEMBERS','AUTO'],'button_role':['NORMAL','OK','APPLY','CANCEL','RESET','HELP'],'value_type': ['STRING', 'REAL'], 'orientation': ['HORIZ', 'VERT'], 'frame_style': ['FRAME','TABSET','TOOLBAR'], 'layout_mode': ['ABSOLUTE','AUTO','RELATIVE'], 'path': ['DOWN','RIGHT','UP','LEFT'], 'halign': ['LEFT','CENTRE','RIGHT'], 'valign': ['TOP','CENTRE','BOTTOM'], 'xedge': ['XMIN','XMAX'], 'yedge': ['YMIN','YMAX'], 'xanchor': ['LEFT','RIGHT'], 'list_mode':['SIMPLE','TABLE'], 'selection_mode':['SINGLE','MULTIPLE'], 'combo_keyword':['COMBO','COMBOBOX'], 'slider_orientation':['HORIZONTAL','VERTICAL'], 'view_type':['ALPHA','AREA','PLOT','VOLUME'], 'channels':['NONE','REQUESTS','COMMANDS','BOTH']}[key])
            else: w = QLineEdit()
            if isinstance(w,QComboBox):
                w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                w.setMinimumContentsLength(8)
            layout_keys={'parent','layout_mode','path','halign','valign','hgap','vgap','xref','xedge','xanchor','xoffset','yref','yedge','yoffset','width_ref'}
            content_keys={'selection_mode','list_mode','table_method','combo_keyword','combo_scroll','combo_tagwid','slider_orientation','slider_min','slider_max','slider_step','slider_value','off_value','on_value','view_type','view_aspect','channels','assembly','namespace','control_type','pixmap_path','database'}
            action_keys={'callback','command','popup_menu','action_mode','macro_path','macro_flag','macro_value'}
            self.prop_layout.current='配置' if key in layout_keys else '内容' if key in content_keys else '動作' if key in action_keys else '基本'
            if key in ('name','callback'):label+='（任意変更）'
            self.fields[key] = w; self.prop_layout.addRow(label, w,pairs.get(key)); self.connect_field(w, self.update_gadget)
            if key in ('name','callback','table_method','macro_flag','macro_value'):
                w.setToolTip('自動設定・自動生成されます。管理用の名前にしたい場合だけ変更してください。')
        self.fields['action_mode'].setItemData(0,'CODE');self.fields['action_mode'].setItemData(1,'MACRO')
        self.initial_choice=QComboBox()
        for value in ('','TRUE','FALSE'):self.initial_choice.addItem(value,value)
        self.initial_choice.currentIndexChanged.connect(self.update_initial_choice)
        self.initial_choice.setToolTip('空欄＝設定しない。TRUE / FALSEを選ぶとDEFAULTへ自動出力します。')
        self.prop_layout.current='基本';self.prop_layout.addRow('初期値',self.initial_choice,'value_type')
        self.fields['action_mode'].setItemText(0,'手入力のコマンド / メソッド')
        self.fields['action_mode'].setItemText(1,'外部マクロを実行')
        self.fields['macro_flag'].setPlaceholderText('例: buttonFlag（!! は不要・空欄ならフラグなし）')
        self.fields['macro_value'].setPlaceholderText('例: A / B')
        self.prop_layout.current='動作'
        self.macro_folder_row=QWidget();macro_layout=QHBoxLayout(self.macro_folder_row);macro_layout.setContentsMargins(0,0,0,0)
        self.macro_folder=QLineEdit(str(self.settings.macro_folder));self.macro_folder.editingFinished.connect(self.save_macro_folder)
        self.macro_folder.setToolTip('呼び出すマクロの選択を開始するフォルダ。settings.json に保存します。')
        macro_layout.addWidget(self.macro_folder,1)
        browse_macro_folder=QPushButton('📁');browse_macro_folder.setToolTip('マクロフォルダを選択');browse_macro_folder.clicked.connect(self.choose_macro_folder);macro_layout.addWidget(browse_macro_folder)
        self.prop_layout.addRow('マクロフォルダ',self.macro_folder_row)
        self.macro_browse=QPushButton('📁 マクロファイルを選択');self.macro_browse.clicked.connect(self.choose_macro)
        self.prop_layout.current='動作'
        self.prop_layout.addRow(self.macro_browse)
        self.macro_template=QPushButton('📄 分岐マクロのひな形を保存');self.macro_template.clicked.connect(self.save_macro_template)
        self.prop_layout.addRow(self.macro_template)
        self.choose_background=QPushButton('🎨 色番号表から選択');self.choose_background.clicked.connect(self.pick_background)
        self.prop_layout.current='基本'
        self.prop_layout.addRow(self.choose_background)
        self.gadget_comment=QPlainTextEdit();self.gadget_comment.setFixedHeight(64)
        self.gadget_comment.setPlaceholderText('部品の用途や注意点。出力時に -- コメントとして付けます。')
        self.gadget_comment.textChanged.connect(self.update_gadget);self.prop_layout.addRow('部品のコメント',self.gadget_comment)
        self.browse_image = QPushButton('📁 画像ファイルを選択');self.browse_image.clicked.connect(self.choose_image)
        self.prop_layout.current='内容'
        self.prop_layout.addRow(self.browse_image)
        self.fixed_font = QCheckBox('FIXCHARS：等幅フォント');self.fixed_font.toggled.connect(self.update_gadget)
        self.prop_layout.addRow(self.fixed_font)
        self.pane_lines = QPlainTextEdit();self.pane_lines.setMaximumHeight(130)
        self.pane_lines.setPlaceholderText('TEXTPANE の初期内容（1行ずつ配列で出力）')
        self.pane_lines.textChanged.connect(self.update_gadget);self.prop_layout.addRow('複数行入力の初期内容',self.pane_lines)
        self.choices = QPlainTextEdit(); self.choices.setMaximumHeight(100)
        self.prop_layout.addRow('選択肢 (1行1項目)', self.choices)
        self.choices.textChanged.connect(self.update_gadget)
        self.choice_commands = QPlainTextEdit(); self.choice_commands.setMaximumHeight(100)
        self.choice_commands.setPlaceholderText('選択肢と同じ行順で実行コマンドを指定')
        self.prop_layout.addRow('OPTION コマンド (1行1項目)', self.choice_commands)
        self.choice_commands.textChanged.connect(self.update_gadget)
        self.item_values = QPlainTextEdit(); self.item_values.setMaximumHeight(100)
        self.item_values.setPlaceholderText('表示名と同じ行順で実値を指定。空欄なら rtext を省略')
        self.prop_layout.addRow('LIST / COMBO 実値 (1行1項目)', self.item_values)
        self.item_values.textChanged.connect(self.update_gadget)
        self.list_table_group = QWidget(); table_layout = QVBoxLayout(self.list_table_group)
        table_layout.setContentsMargins(0,0,0,0)
        table_note = QLabel('複数列 LIST：先頭行が見出しです。各セルに値を入力します。')
        table_note.setWordWrap(True); table_layout.addWidget(table_note)
        self.list_table = QTableWidget(); self.list_table.setMinimumHeight(160); self.list_table.setMaximumHeight(260)
        self.list_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table_layout.addWidget(self.list_table)
        buttons = QHBoxLayout()
        for label, handler in (('+ 列',self.add_table_column),('列削除',self.delete_table_column),('+ 行',self.add_table_row),('行削除',self.delete_table_row)):
            button = QPushButton(label); button.clicked.connect(handler); buttons.addWidget(button)
        table_layout.addLayout(buttons); self.prop_layout.addRow(self.list_table_group)
        self.view_code = QPlainTextEdit(); self.view_code.setMaximumHeight(120)
        self.view_code.setPlaceholderText('LIMITS AUTO など。VIEW の外枠・EXIT は不要')
        self.prop_layout.addRow('VIEW 内の追加 PML', self.view_code)
        self.view_code.textChanged.connect(self.update_gadget)
        self.container_hint = QLabel('外部 DLL が必要です。未設定時は DEFAULT で Control を接続してください。')
        self.container_hint.setWordWrap(True); self.prop_layout.addRow(self.container_hint)
        self.body = QPlainTextEdit(); self.body.setPlaceholderText('メソッド内の PML コード。自動実行はしません。')
        self.body.setFixedHeight(64)
        self.body.textChanged.connect(self.update_gadget)
        self.edit_method_button=QPushButton('処理コードを編集 →')
        self.edit_method_button.clicked.connect(self.show_method_editor)
        self.prop_layout.current='動作';self.prop_layout.addRow(self.edit_method_button)
        rl.addWidget(self.props)
        self.menu_group = QGroupBox('メニューバー'); menu_layout = QVBoxLayout(self.menu_group)
        menu_buttons = QHBoxLayout()
        self.menu_actions = {}
        for label, handler, key in (('+ メニュー',self.add_menu,None),('複製',self.duplicate_menu,'duplicate'),('削除',self.delete_menu,'delete')):
            button = QPushButton(label); button.clicked.connect(handler); menu_buttons.addWidget(button)
            if key: self.menu_actions[key] = button
        menu_layout.addLayout(menu_buttons)
        self.menu_list = QListWidget(); self.menu_list.setMaximumHeight(85)
        self.menu_list.currentRowChanged.connect(self.choose_menu); menu_layout.addWidget(self.menu_list)
        menu_order = QHBoxLayout()
        for label, direction, key in (('← 左へ',-1,'left'),('右へ →',1,'right')):
            button = QPushButton(label); button.clicked.connect(lambda checked=False, d=direction: self.move_menu(d))
            self.menu_actions[key] = button; menu_order.addWidget(button)
        menu_layout.addLayout(menu_order)
        menu_name_layout = QFormLayout(); self.menu_name = QLineEdit()
        self.menu_name.textEdited.connect(self.update_menu_name)
        menu_name_layout.addRow('オブジェクト名',self.menu_name)
        self.menu_label=QLineEdit();self.menu_label.textEdited.connect(self.update_menu_label)
        menu_name_layout.addRow('タイトル表示名',self.menu_label);menu_layout.addLayout(menu_name_layout)
        self.menu_on_bar=QCheckBox('BAR：メニューバーにタイトルを表示する')
        self.menu_on_bar.toggled.connect(self.update_menu_on_bar);menu_layout.addWidget(self.menu_on_bar)
        self.menu_popup = QCheckBox('POPUP：部品の右クリックメニューとして使う')
        self.menu_popup.toggled.connect(self.update_menu_popup);menu_layout.addWidget(self.menu_popup)
        self.menu_items = QTableWidget(0,3); self.menu_items.setHorizontalHeaderLabels(['表示名','コマンド','操作'])
        self.menu_items.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.menu_items.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.menu_items.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.menu_items.setMinimumHeight(120); self.menu_items.setMaximumHeight(220)
        menu_layout.addWidget(self.menu_items)
        self.menu_add_item = QPushButton('+ メニュー項目'); self.menu_add_item.clicked.connect(self.add_menu_item)
        menu_layout.addWidget(self.menu_add_item)
        note = QLabel('BARのADDでタイトルとMENUを関連付け、MENUのADDで項目とコマンドを設定します。項目のコマンドはE3Dで実行されます。')
        note.setWordWrap(True); menu_layout.addWidget(note)
        self.menu_dialog=QDialog(self);self.menu_dialog.setWindowTitle('メニューバーの編集');self.menu_dialog.resize(760,620)
        self.menu_dialog.addAction(self.save_action)
        menu_dialog_layout=QVBoxLayout(self.menu_dialog);menu_dialog_layout.addWidget(self.menu_group)
        close_menu=QPushButton('閉じる');close_menu.clicked.connect(self.menu_dialog.close);menu_dialog_layout.addWidget(close_menu)
        rl.addStretch()
        method_page=QWidget();rl=QVBoxLayout(method_page);right.addTab(method_page,'処理')
        self.program_label=QLabel('表示後のプログラム')
        rl.addWidget(self.program_label); rl.addWidget(self.after_show)
        rl.addWidget(QLabel('DEFAULT メソッドの追加処理（初期値は自動出力）')); rl.addWidget(self.default_body)
        rl.addWidget(QLabel('選択部品のメソッド処理'))
        self.method_target=QLabel();self.method_target.setWordWrap(True);self.method_target.setTextFormat(Qt.PlainText)
        rl.addWidget(self.method_target);rl.addWidget(self.body)
        rl.addStretch()
        right.setMinimumWidth(360)
        columns.addWidget(right); columns.setSizes([220, 780, 380])
        outer.addWidget(columns, 1); self.setCentralWidget(root)
        self.pml_highlighters=[]
        for editor in (self.code,self.after_show,self.default_body,self.body,self.view_code,self.choice_commands):
            editor.setStyleSheet('font-family: monospace; font-size: 12px; background-color: #ffffff; color: #222222;')
            highlighter=PmlHighlighter(editor.document());editor.pml_highlighter=highlighter
            self.pml_highlighters.append(highlighter)
        self.refresh()
        self.set_workflow('form')
        if self.settings.error:self.statusBar().showMessage('設定JSONを読み込めません: '+self.settings.error)
        self.backup_timer.start()

    def show_code(self):
        self.sync_output_summary()
        self.output_dialog.show();self.output_dialog.raise_();self.output_dialog.activateWindow()

    def set_workflow(self,step):
        # Internal focus routing; the canvas and its panels always remain visible.
        if step=='output':self.show_code();return
        self.current_workflow=step
        if step=='form':
            self.choose_row(-1);self.inspector_tabs.setCurrentIndex(0)
        elif step=='layout':self.inspector_tabs.setCurrentIndex(0)
        elif step=='action':
            self.inspector_tabs.setCurrentIndex(0)
            if self.props.isTabEnabled(3):self.props.setCurrentIndex(3)

    def show_method_editor(self):
        if self.selected is None:return
        gadget=self.form.gadgets[self.selected]
        if not gadget.callback:
            if gadget.command or not self.fields['callback'].isEnabled():return
            candidate=copy.deepcopy(self.form);gadget=candidate.gadgets[self.selected]
            gadget.callback=self.automatic_method(candidate,gadget.name)
            if not gadget.body:gadget.body='  -- この部品の処理を必要に応じて追加してください。'
            try:candidate.validate()
            except ValueError as error:self.statusBar().showMessage(str(error));return
            self.checkpoint();self.form=candidate;self.refresh()
        if self.current_workflow!='action':self.set_workflow('action')
        self.inspector_tabs.setCurrentIndex(1);self.body.setFocus()

    def sync_output_summary(self):
        count=sum(not self.form.is_tab_page(g) for g in self.form.gadgets)
        state='未保存の変更あり' if self.dirty else '保存済み' if self.path else '新規設計'
        self.output_summary.setTextFormat(Qt.PlainText);self.output_validation.setTextFormat(Qt.PlainText)
        self.output_summary.setText(f'{self.form.title} / {self.form.symbol}\n部品 {count}個  •  {state}\n設計JSON: {self.path or "保存先は未指定"}')
        error=self.validation_error
        if not error:
            try:self.code.toPlainText().encode('cp932')
            except UnicodeError:error='SJIS（CP932）で出力できない文字があります。表示文字・処理コードを確認してください。'
        if error:
            self.output_validation.setStyleSheet('color: #a12a2a; background: #fff0f0; padding: 8px;')
            self.output_validation.setText('入力を修正してください: '+error)
        else:
            self.output_validation.setStyleSheet('color: #23643c; background: #edf8f0; padding: 8px;')
            self.output_validation.setText('エディタの入力チェック: 問題なし。E3Dでの動作は実機で確認してください。')

    def refresh_recent_menu(self):
        self.recent_menu.clear()
        for name in self.settings.recent_files:
            path=Path(name)
            action=self.recent_menu.addAction(path.name.replace('&','&&'))
            action.setToolTip(str(path));action.setStatusTip(str(path))
            action.triggered.connect(lambda checked=False,p=path:self.open_design(p))
        if not self.settings.recent_files:
            self.recent_menu.addAction('履歴はありません').setEnabled(False)
        else:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction('履歴を消去').triggered.connect(self.clear_recent)

    def remember_project(self):
        try:self.settings.remember_design(self.path)
        except (OSError,ValueError) as error:return '最近の設計を保存できません: '+str(error)
        self.refresh_recent_menu();return ''

    def clear_recent(self):
        try:self.settings.clear_recent()
        except OSError as error:self.statusBar().showMessage('履歴を消去できません: '+str(error));return
        self.refresh_recent_menu()

    def backup_work(self):
        if self.loading or self._closing or not self.dirty:return
        try:self.recovery.write(self.form,self.path,self.variables.toPlainText() if self.variable_error else None)
        except (OSError,ValueError) as error:self.statusBar().showMessage('自動バックアップを保存できません（最後の成功分は保持）: '+str(error))

    def clear_backup(self):
        try:self.recovery.clear()
        except OSError as error:self.statusBar().showMessage('バックアップを削除できません: '+str(error))

    def recovery_options(self):
        options=[]
        try:paths=self.recovery.candidates()
        except OSError as error:self.statusBar().showMessage('復元データを確認できません: '+str(error));return []
        for path in paths:
            try:
                form,data=self.recovery.read(path)
                options.append((path,f"{data.get('saved_at','日時不明')}  {data['source'] or form.title or '未保存の設計'}"))
            except (OSError,ValueError):continue
        return options

    def offer_recovery(self):
        options=self.recovery_options()
        if not options:return
        path,label=options[0]
        answer=QMessageBox.question(self,'未保存作業の復元',f'未保存の作業が見つかりました。復元しますか？\n{label}\n\n「いいえ」でもバックアップは保持し、「作業を復元」から選べます。',QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)
        if answer==QMessageBox.Yes:self.restore_work(path)

    def recover_work(self):
        options=self.recovery_options()
        if not options:self.statusBar().showMessage('復元できる未保存作業はありません。');return
        labels=[f'{index+1}. {label}' for index,(_,label) in enumerate(options)]
        label,accepted=QInputDialog.getItem(self,'作業を復元','復元する作業',labels,0,False)
        if accepted:self.restore_work(options[labels.index(label)][0])

    def restore_work(self,path):
        try:form,data=self.recovery.read(path)
        except (OSError,ValueError) as error:QMessageBox.warning(self,'復元エラー',str(error));return False
        if not self.confirm_discard():return False
        try:claim=self.recovery.claim(path)
        except ValueError as error:QMessageBox.warning(self,'復元エラー',str(error));return False
        self.clear_backup();self.recovery.restored_path=Path(path);self.recovery.restored_lock=claim
        self.project_key=uuid.uuid4().hex;self.form=form
        self.path=Path(data['source']) if data['source'] else None
        self.selected=None;self._multi_selection.clear();self.active_pages.clear();self.history.clear();self.future.clear()
        self.variable_error=False;self.dirty=True;self.refresh()
        self.set_workflow('layout')
        if data['pending_variables'] is not None:self.variables.setPlainText(data['pending_variables'])
        self.statusBar().showMessage('未保存の作業を復元しました。内容を確認して設計を保存してください。');return True

    @staticmethod
    def number(low, high):
        w = QDoubleSpinBox(); w.setRange(low, high); w.setDecimals(1); w.setSingleStep(.1); return w

    @staticmethod
    def load_number(widget, value):
        widget.setValue(value)
        # Qt rounds for display; retain the model's precision until this field changes.
        widget.setProperty('loadedDisplayValue', widget.value())

    @staticmethod
    def edited_number(widget, original):
        value = widget.value()
        return original if value == widget.property('loadedDisplayValue') else value

    @staticmethod
    def connect_field(w, fn):
        if isinstance(w, QLineEdit): w.textEdited.connect(fn)
        elif isinstance(w, QComboBox): w.currentTextChanged.connect(fn)
        else: w.valueChanged.connect(fn)

    def checkpoint(self):
        self.history.append(copy.deepcopy(self.form)); self.history = self.history[-100:]; self.future.clear()
        self.dirty = True

    def manage_names(self):
        if self.variable_error:
            self.statusBar().showMessage('変数欄の入力エラーを修正してから名前管理を開いてください。');return
        from .name_manager import NameManager
        manager = NameManager(self)
        try: manager.exec()
        finally: manager.deleteLater()

    def current_menu(self):
        if self.selected_menu is not None and 0 <= self.selected_menu < len(self.form.menus):
            return self.form.menus[self.selected_menu]
        return None

    def update_form_callback(self,event,text):
        if self.loading: return
        self.checkpoint();setattr(self.form,event,text);self.refresh(rebuild=False)

    def update_menu_popup(self,checked):
        menu = self.current_menu()
        if self.loading or menu is None: return
        self.checkpoint();menu.popup = checked
        if not checked:
            for gadget in self.form.gadgets:
                if gadget.popup_menu.lower() == menu.name.lower(): gadget.popup_menu = ''
        self.refresh(rebuild=False)

    def pick_background(self):
        if self.selected is None:return
        from .color_picker import ColorPicker
        dialog=ColorPicker(self,self.form.gadgets[self.selected].background)
        try:
            if dialog.exec()==ColorPicker.DialogCode.Accepted:
                self.fields['background'].setText(dialog.value);self.update_gadget()
        finally:dialog.deleteLater()

    def save_macro_folder(self):
        text=self.macro_folder.text().strip()
        folder=Path(text).expanduser() if text else self.settings.app_directory
        if not folder.is_absolute():folder=self.settings.app_directory/folder
        try:self.settings.save_macro_folder(folder)
        except (OSError,ValueError) as error:
            self.macro_folder.setText(str(self.settings.macro_folder))
            self.statusBar().showMessage('マクロフォルダを保存できません: '+str(error));return False
        self.macro_folder.setText(str(self.settings.macro_folder))
        self.statusBar().showMessage('マクロフォルダを settings.json に保存しました。');return True

    def choose_macro_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'マクロフォルダを選択',str(self.settings.macro_folder))
        if folder:self.macro_folder.setText(folder);self.save_macro_folder()

    def choose_macro(self):
        filename,_=QFileDialog.getOpenFileName(self,'外部マクロを選択',str(self.settings.macro_folder),'マクロ (*.txt *.mac *.pmlmac);;すべて (*)')
        if filename:
            self.fields['macro_path'].setText(filename);self.update_gadget()

    def save_macro_template(self):
        if self.selected is None:return
        from .macro_actions import branch_template
        try:text=branch_template(self.form,self.form.gadgets[self.selected].macro_path)
        except ValueError as error:self.statusBar().showMessage(str(error));return
        filename,_=QFileDialog.getSaveFileName(self,'分岐マクロのひな形を保存',str(self.settings.output_folder/'CODE1.mac'),'マクロ (*.mac)')
        if not filename:return
        try:
            data=text.replace('\n','\r\n').encode('cp932')
            path=self.mac_output_path(filename)
            if path is None:return
            atomic_write(path,data)
        except (OSError,UnicodeError) as error:self.statusBar().showMessage(str(error));return
        self.statusBar().showMessage('分岐マクロのひな形を保存しました。各分岐の処理をファイルで編集してください。')

    def choose_image(self):
        if self.selected is None: return
        gadget = self.form.gadgets[self.selected]
        if gadget.kind == 'option':
            filenames,_ = QFileDialog.getOpenFileNames(self,'画像の選択肢を追加','','画像 (*.png *.gif *.bmp *.jpg *.jpeg);;すべて (*)')
            if not filenames: return
            self.checkpoint();gadget.items.extend(filenames)
            if gadget.item_values: gadget.item_values.extend(['']*len(filenames))
            self.refresh();return
        filename,_ = QFileDialog.getOpenFileName(self,'画像を選択','','画像 (*.png *.gif *.bmp *.jpg *.jpeg);;すべて (*)')
        if not filename: return
        self.checkpoint();gadget = self.form.gadgets[self.selected]
        gadget.pixmap_path = filename;self.refresh()

    def preview_popup(self,position):
        item = self.view.itemAt(position)
        if not isinstance(item,Item):return
        if item.gadget.kind=='frame':
            self.frame_selection_popup(item.gadget.name,self.view,self.view.viewport().mapToGlobal(position));return
        if not item.gadget.popup_menu:return
        source = next((menu for menu in self.form.menus if menu.popup and menu.name.lower() == item.gadget.popup_menu.lower()),None)
        if source is None: return
        popup = QMenu(self.view)
        for entry in source.items:
            action = popup.addAction(entry.label)
            action.triggered.connect(lambda checked=False,command=entry.command:self.statusBar().showMessage('E3D で実行するコマンド: '+command))
        popup.setAttribute(Qt.WA_DeleteOnClose)
        popup.popup(self.view.viewport().mapToGlobal(position))

    def tree_popup(self,position):
        item=self.objects.itemAt(position)
        index=item.data(0,Qt.UserRole) if item else -1
        if not isinstance(index,int) or not 0<=index<len(self.form.gadgets):return
        gadget=self.form.gadgets[index]
        if gadget.kind=='frame':
            self.frame_selection_popup(gadget.name,self.objects,self.objects.viewport().mapToGlobal(position))

    def frame_selection_popup(self,name,parent,position):
        popup=QMenu(parent)
        action=popup.addAction('子を含めてすべて選択')
        action.triggered.connect(lambda checked=False:self.select_frame_subtree(name))
        popup.setAttribute(Qt.WA_DeleteOnClose);popup.popup(position)

    def select_frame_subtree(self,name):
        index=next((i for i,g in enumerate(self.form.gadgets) if g.name==name and g.kind=='frame'),None)
        if index is None:return
        names={name,*self.form.descendants(name)}
        # Reveal the frame's tab before selecting its descendants, including hidden pages.
        self.choose_row(index)
        self.choose_rows([i for i,g in enumerate(self.form.gadgets) if g.name in names])

    def refresh_menus(self, rebuild=True):
        self.preview_menu_bar.clear()
        for menu in self.preview_menus: menu.deleteLater()
        self.preview_menus = []
        for menu in self.form.menus:
            if menu.popup or not menu.on_bar: continue
            preview = QMenu(menu.display_label,self.preview_menu_bar)
            self.preview_menus.append(preview)
            self.preview_menu_bar.addMenu(preview)
            for item in menu.items: preview.addAction(item.label)
        menu_visible=any(not menu.popup and menu.on_bar for menu in self.form.menus)
        self.preview_menu_bar.setVisible(menu_visible)
        self.preview_menu_frame.setVisible(menu_visible)
        if self.current_menu() is None:
            self.selected_menu = 0 if self.form.menus else None
        self.menu_list.clear()
        self.menu_list.addItems([menu.name for menu in self.form.menus])
        self.menu_list.setCurrentRow(self.selected_menu if self.selected_menu is not None else -1)
        menu = self.current_menu()
        for key in ('duplicate','delete'): self.menu_actions[key].setEnabled(menu is not None)
        self.menu_actions['left'].setEnabled(menu is not None and self.selected_menu > 0)
        self.menu_actions['right'].setEnabled(menu is not None and self.selected_menu < len(self.form.menus)-1)
        self.menu_name.setEnabled(menu is not None); self.menu_items.setEnabled(menu is not None)
        self.menu_popup.setEnabled(menu is not None);self.menu_popup.setChecked(menu.popup if menu else False)
        self.menu_label.setEnabled(menu is not None and not menu.popup)
        self.menu_on_bar.setEnabled(menu is not None and not menu.popup)
        self.menu_on_bar.setChecked(menu.on_bar and not menu.popup if menu else False)
        label=menu.display_label if menu else ''
        if self.menu_label.text()!=label:self.menu_label.setText(label)
        self.menu_add_item.setEnabled(menu is not None)
        name = menu.name if menu else ''
        if self.menu_name.text() != name: self.menu_name.setText(name)
        if not rebuild: return
        self.menu_items.setRowCount(0)
        if menu is None: return
        for row, item in enumerate(menu.items):
            self.menu_items.insertRow(row)
            for column, key in enumerate(('label','command')):
                editor = QLineEdit(getattr(item,key))
                editor.textEdited.connect(lambda text, r=row, k=key: self.update_menu_item(r,k,text))
                self.menu_items.setCellWidget(row,column,editor)
            operations = QPushButton('操作'); popup = QMenu(operations)
            for label, handler, enabled in (
                    ('上へ',lambda checked=False, r=row: self.move_menu_item(r,-1),row > 0),
                    ('下へ',lambda checked=False, r=row: self.move_menu_item(r,1),row < len(menu.items)-1),
                    ('複製',lambda checked=False, r=row: self.duplicate_menu_item(r),True),
                    ('削除',lambda checked=False, r=row: self.delete_menu_item(r),True)):
                action = popup.addAction(label); action.triggered.connect(handler); action.setEnabled(enabled)
            operations.setMenu(popup); self.menu_items.setCellWidget(row,2,operations)

    def choose_menu(self, index):
        if self.loading: return
        self.selected_menu = index if index >= 0 else None
        self.loading = True
        self.refresh_menus()
        self.loading = False

    def add_palette_menu(self):
        if not self.form.menus:self.add_menu()
        self.menu_dialog.show();self.menu_dialog.raise_();self.menu_dialog.activateWindow()
        self.menu_name.setFocus();self.menu_name.selectAll()

    def request_object_label(self,name):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0,lambda:self.edit_object_properties(name))

    def edit_object_properties(self,name):
        from .quick_editor import MiniProperties
        index=next((i for i,g in enumerate(self.form.gadgets) if g.name==name),None)
        if index is None or self._closing:return
        dialog=MiniProperties(self,self.form,index)
        if dialog.exec()==QDialog.Accepted and dialog.result_form is not None:
            if dialog.result_form.dumps()!=self.form.dumps():
                self.checkpoint();self.form=dialog.result_form;self.selected=index;self.refresh()
        dialog.deleteLater()

    def edit_object_label(self,name):
        index=next((i for i,g in enumerate(self.form.gadgets) if g.name==name),None)
        if index is None or self._closing:return
        gadget=self.form.gadgets[index]
        if gadget.kind=='line':
            self.statusBar().showMessage('線には表示名を設定できません。');return
        text,accepted=QInputDialog.getText(self,'表示名の変更','画面に表示する文字',QLineEdit.Normal,gadget.label)
        if not accepted or text==gadget.label:return
        candidate=copy.deepcopy(self.form);candidate.gadgets[index].label=text
        try:candidate.validate()
        except ValueError as error:self.statusBar().showMessage(str(error));return
        self.checkpoint();self.form=candidate;self.selected=index;self.refresh()

    def add_menu(self):
        self.checkpoint()
        used = {g.name.lower() for g in self.form.gadgets} | {menu.name.lower() for menu in self.form.menus}
        index = 1
        while f'menu{index}' in used: index += 1
        self.form.menus.append(Menu(name=f'menu{index}'))
        self.selected_menu = len(self.form.menus)-1
        self.refresh()

    def delete_menu(self):
        if self.current_menu() is None: return
        self.checkpoint();menu = self.form.menus.pop(self.selected_menu)
        for gadget in self.form.gadgets:
            if gadget.popup_menu.lower() == menu.name.lower(): gadget.popup_menu = ''
        self.refresh()

    def duplicate_menu(self):
        menu = self.current_menu()
        if menu is None: return
        self.checkpoint(); duplicate = copy.deepcopy(menu)
        duplicate.name = self.unique_name('menu')
        self.selected_menu += 1
        self.form.menus.insert(self.selected_menu,duplicate); self.refresh()

    def move_menu(self, direction):
        if self.current_menu() is None or direction not in (-1,1): return
        target = self.selected_menu + direction
        if not 0 <= target < len(self.form.menus): return
        self.checkpoint()
        self.form.menus[self.selected_menu], self.form.menus[target] = self.form.menus[target], self.form.menus[self.selected_menu]
        self.selected_menu = target; self.refresh()

    def update_menu_name(self, text):
        menu = self.current_menu()
        if self.loading or menu is None or menu.name==text:return
        from .names import rename
        try:result=rename(self.form,'menu',self.selected_menu,text)
        except ValueError as error:self.statusBar().showMessage(str(error));return
        self.checkpoint();self.form=result;self.refresh()

    def update_menu_label(self,text):
        menu=self.current_menu()
        if self.loading or menu is None or menu.label==text:return
        self.checkpoint();menu.label=text;self.refresh(rebuild=False)

    def update_menu_on_bar(self,checked):
        menu=self.current_menu()
        if self.loading or menu is None or menu.on_bar==checked:return
        self.checkpoint();menu.on_bar=checked;self.refresh()

    def add_menu_item(self):
        menu = self.current_menu()
        if menu is None: return
        self.checkpoint(); menu.items.append(MenuItem()); self.refresh()

    def update_menu_item(self, row, key, text):
        menu = self.current_menu()
        if self.loading or menu is None or not 0 <= row < len(menu.items): return
        self.checkpoint(); setattr(menu.items[row],key,text); self.refresh(rebuild=False)

    def delete_menu_item(self, row):
        menu = self.current_menu()
        if menu is None or not 0 <= row < len(menu.items): return
        self.checkpoint(); menu.items.pop(row); self.refresh()

    def duplicate_menu_item(self, row):
        menu = self.current_menu()
        if menu is None or not 0 <= row < len(menu.items): return
        self.checkpoint(); menu.items.insert(row+1,copy.deepcopy(menu.items[row])); self.refresh()

    def move_menu_item(self, row, direction):
        menu = self.current_menu()
        if menu is None or direction not in (-1,1) or not 0 <= row < len(menu.items): return
        target = row + direction
        if not 0 <= target < len(menu.items): return
        self.checkpoint(); menu.items[row],menu.items[target] = menu.items[target],menu.items[row]; self.refresh()

    def update_variables(self):
        if self.loading: return
        self.dirty = True
        try:values,locals_=parse_variables(self.variables.toPlainText())
        except ValueError as error:
            self.code.setPlainText('-- '+str(error));self.variable_error=True
            self.validation_error=str(error);self.sync_output_summary()
            return
        self.variable_error = False
        if (values,locals_)!=(self.form.variables,self.form.local_variables):
            self.checkpoint();self.form.variables=values;self.form.local_variables=locals_
        self.refresh()

    def update_initial_choice(self):
        if self.loading or self.selected is None:return
        if self.form.gadgets[self.selected].kind not in ('toggle','rtoggle'):return
        self.fields['initial'].setText(self.initial_choice.currentData())
        self.update_gadget()

    def update_default_body(self):
        if self.loading: return
        self.checkpoint(); self.form.default_body = self.default_body.toPlainText()
        for gadget in self.form.gadgets:
            if gadget.callback.lower()=='default':gadget.body=''
        self.refresh()

    def update_after_show(self):
        if self.loading: return
        self.checkpoint(); self.form.after_show_code = self.after_show.toPlainText(); self.refresh()

    def update_form(self):
        if self.loading: return
        from .names import rename
        candidate=copy.deepcopy(self.form)
        candidate.show_form=True
        selection=self.docking.currentData()
        candidate.dock_side='NONE' if selection=='MAIN' else selection
        candidate.dock_right=candidate.dock_side=='RIGHT'
        candidate.form_type='MAIN' if selection=='MAIN' else 'DIALOG'
        candidate.title=self.ftitle.text()
        candidate.width=self.edited_number(self.fw,candidate.width)
        candidate.height=self.edited_number(self.fh,candidate.height)
        if candidate.symbol!=self.fname.text():
            try:candidate=rename(candidate,'form',None,self.fname.text())
            except ValueError as error:self.statusBar().showMessage(str(error));return
        self.checkpoint();self.form=candidate;self.refresh()

    def populate_parents(self, gadget):
        combo = self.fields['parent']; combo.clear(); combo.addItem('(フォーム直下)', '')
        excluded = {gadget.name.lower(), *(name.lower() for name in self.form.descendants(gadget.name))}
        for g in self.form.gadgets:
            if g.kind == 'frame' and g.name.lower() not in excluded:
                if g.frame_style == 'TABSET': continue
                combo.addItem(g.name, g.name)
        if gadget.parent and combo.findData(gadget.parent) < 0: combo.addItem(gadget.parent, gadget.parent)
        combo.setCurrentIndex(max(0, combo.findData(gadget.parent)))
        for key in ('xref','yref','width_ref'):
            widget = self.fields[key]; widget.clear(); widget.addItem('(未指定)', '')
            for g in self.form.children(gadget.parent):
                if g is not gadget: widget.addItem(g.name,g.name)
            value = getattr(gadget,key)
            if value and widget.findData(value) < 0: widget.addItem(value,value)
            widget.setCurrentIndex(max(0,widget.findData(value)))
        widget = self.fields['popup_menu'];widget.clear();widget.addItem('(未指定)','')
        for menu in self.form.menus:
            if menu.popup: widget.addItem(menu.name,menu.name)
        if gadget.popup_menu and widget.findData(gadget.popup_menu) < 0: widget.addItem(gadget.popup_menu,gadget.popup_menu)
        widget.setCurrentIndex(max(0,widget.findData(gadget.popup_menu)))

    def enable_layout_fields(self, gadget):
        mode = gadget.layout_mode
        self.fields['layout_mode'].setEnabled(True)
        for key in ('width','height'):
            pixel = gadget.display_mode == 'PIXMAP'
            self.fields[key].setMaximum(max(8192,getattr(gadget,key)) if pixel else 300)
            self.fields[key].setDecimals(1)
            self.fields[key].setSingleStep(.1)
        for key in ('x','y'): self.fields[key].setEnabled(mode == 'ABSOLUTE')
        for key in ('path','halign','valign','hgap','vgap'): self.fields[key].setEnabled(mode == 'AUTO')
        for key in ('xref','xedge','xanchor','xoffset','yref','yedge','yoffset'): self.fields[key].setEnabled(mode == 'RELATIVE')
        self.fields['width_ref'].setEnabled(gadget.display_mode != 'PIXMAP' and 'width' not in fixed_dimensions(gadget) and gadget.kind not in ('toggle','option','rtoggle'))
        self.fields['width'].setEnabled(dimension_editable(gadget,'width'))
        self.fields['height'].setEnabled(dimension_editable(gadget,'height'))
        hint='元画像のサイズで固定。収まらない場合はフォーム／フレームを広げてください。' if gadget.display_mode == 'PIXMAP' else ''
        self.fields['width'].setToolTip(hint)
        self.fields['height'].setToolTip(hint)
        if ((gadget.kind=='toggle' and gadget.display_mode=='TEXT') or uses_pairs(gadget)):self.fields['width'].setToolTip(PREVIEW_WIDTH_HINT)
        for key,value in fixed_dimensions(gadget).items():
            self.fields[key].setToolTip('高さは1行固定です。' if gadget.kind not in ('line','slider') else f'太さは{value:.1f}固定です。長さだけ変更できます。')
        parent = self.form.parent_gadget(gadget)
        if parent and parent.frame_style == 'TOOLBAR':
            for key in ('x','y','layout_mode','xref','yref','path','width_ref'): self.fields[key].setEnabled(False)

    def enable_gadget_fields(self, gadget):
        # Visibility rules below inspect effective widget enablement.
        # Re-enable page parents before evaluating a different gadget's fields.
        for index in range(self.props.count()):self.props.setTabEnabled(index,True)
        self.prop_layout.batching = True
        self.fields['selection_mode'].setEnabled(gadget.kind in ('list','selector'))
        self.fields['list_mode'].setEnabled(gadget.kind == 'list')
        self.fields['table_method'].setEnabled(gadget.kind == 'list' and gadget.list_mode == 'TABLE')
        self.fields['combo_keyword'].setEnabled(gadget.kind == 'combo')
        self.fields['combo_scroll'].setEnabled(gadget.kind == 'combo')
        self.fields['combo_tagwid'].setEnabled(gadget.kind == 'combo')
        self.fields['combo_tagwid'].setPlaceholderText('0以上 / 空欄なら指定しない')
        self.fields['combo_scroll'].setPlaceholderText('正の整数 / 空欄なら指定しない')
        for key in ('slider_orientation','slider_min','slider_max','slider_step','slider_value'):
            self.fields[key].setEnabled(gadget.kind == 'slider')
        for key in ('off_value','on_value'): self.fields[key].setEnabled(gadget.kind == 'rtoggle')
        self.fields['view_type'].setEnabled(gadget.kind == 'view')
        self.fields['view_aspect'].setEnabled(gadget.kind in ('view','commandline'))
        self.fields['channels'].setEnabled(gadget.kind == 'commandline' or (gadget.kind == 'view' and gadget.view_type == 'ALPHA'))
        for key in ('assembly','namespace','control_type'): self.fields[key].setEnabled(gadget.kind == 'container')
        self.fields['callback'].setEnabled((gadget.kind in ('button','text','toggle','list','combo','slider','selector') or (gadget.kind == 'option' and not uses_pairs(gadget))) and gadget.button_role not in ('OK','CANCEL','HELP'))
        self.item_values.setEnabled(gadget.kind in ('list','combo') or (gadget.kind == 'option' and not uses_pairs(gadget)))
        self.view_code.setEnabled(gadget.kind in ('view','commandline'))
        hint = '空欄＝設定しない。DEFAULT に自動出力'
        if gadget.kind in ('toggle','rtoggle'): hint = 'TRUE / FALSE'
        elif gadget.kind in ('option','combo','list'): hint = '選択行番号（1から）。MULTIPLE は 1,3 のように入力'
        self.fields['initial'].setPlaceholderText(hint)
        self.fields['initial'].setToolTip(hint)
        macro = gadget.kind == 'button' and gadget.action_mode == 'MACRO'
        self.fields['callback'].setEnabled(self.fields['callback'].isEnabled() and not macro)
        self.fields['command'].setEnabled(self.fields['command'].isEnabled() and not macro)
        self.body.setEnabled(bool(gadget.callback) and not macro)
        relevant = {
            'value_type':gadget.kind == 'text', 'initial':gadget.kind in ('text','paragraph','toggle','rtoggle','option','combo','list') and not (gadget.kind == 'paragraph' and gadget.display_mode == 'PIXMAP'),
            'callback':gadget.kind in ('button','text','toggle','list','combo','slider'),
            'command':gadget.kind in ('button','text','toggle'),
            'background':gadget.kind in ('button','paragraph','list'), 'orientation':gadget.kind == 'line',
            'frame_style':gadget.kind == 'frame',
            'display_mode':gadget.kind in ('paragraph','button','toggle','option'),
            'pixmap_path':gadget.kind in ('paragraph','button','toggle') and gadget.display_mode == 'PIXMAP',
            'popup_menu':gadget.kind in ('view','commandline','list','button','toggle','text','combo','slider'),
            'database':gadget.kind == 'selector', 'button_role':gadget.kind == 'button',
            'action_mode':gadget.kind == 'button' and gadget.button_role not in ('OK','CANCEL','HELP'),
            'macro_path':macro,'macro_flag':macro,'macro_value':macro,
            'width_ref':gadget.display_mode != 'PIXMAP' and 'width' not in fixed_dimensions(gadget) and gadget.kind not in ('toggle','option','rtoggle'),
        }
        relevant['callback'] = self.fields['callback'].isEnabled()
        relevant['command'] = (gadget.kind in ('button','text','toggle') or (gadget.kind=='option' and gadget.display_mode=='TEXT' and not uses_pairs(gadget))) and gadget.button_role not in ('OK','CANCEL','HELP') and not macro
        for key in ('path','halign','valign','hgap','vgap'): relevant[key] = gadget.layout_mode == 'AUTO'
        for key in ('xref','xedge','xanchor','xoffset','yref','yedge','yoffset'): relevant[key] = gadget.layout_mode == 'RELATIVE'
        for key in ('selection_mode','list_mode','table_method','combo_keyword','combo_scroll','combo_tagwid','slider_orientation','slider_min','slider_max','slider_step','slider_value','off_value','on_value','view_type','view_aspect','channels','assembly','namespace','control_type'):
            relevant[key] = self.fields[key].isEnabled()
        for key,visible in relevant.items(): self.prop_layout.setRowVisible(self.fields[key],visible)
        boolean=gadget.kind in ('toggle','rtoggle')
        self.prop_layout.setRowVisible(self.fields['initial'],relevant['initial'] and not boolean)
        self.prop_layout.setRowVisible(self.initial_choice,boolean)
        self.initial_choice.setCurrentIndex(max(0,self.initial_choice.findData(gadget.initial.upper())))
        for editor,visible in ((self.choose_background,relevant['background']),(self.macro_folder_row,macro),(self.macro_browse,macro),(self.macro_template,macro),(self.choices,gadget.kind in ('option','combo') or (gadget.kind == 'list' and gadget.list_mode == 'SIMPLE')),
                               (self.choice_commands,uses_pairs(gadget) and not gadget.item_values),
                               (self.item_values,gadget.kind == 'combo' or (gadget.kind == 'option' and not uses_pairs(gadget)) or (gadget.kind == 'list' and gadget.list_mode == 'SIMPLE')),
                               (self.view_code,gadget.kind in ('view','commandline')),
                               (self.container_hint,gadget.kind == 'container'),
                               (self.browse_image,relevant['pixmap_path'] or (gadget.kind == 'option' and gadget.display_mode == 'PIXMAP')),(self.fixed_font,gadget.kind == 'textpane'),(self.pane_lines,gadget.kind == 'textpane')):
            self.prop_layout.setRowVisible(editor,visible)
        self.fields['pixmap_path'].setEnabled(relevant['pixmap_path'])
        self.prop_layout.setRowVisible(self.edit_method_button,self.fields['callback'].isEnabled() and not gadget.command)
        self.fields['display_mode'].setEnabled(relevant['display_mode'])
        self.fields['database'].setEnabled(relevant['database']);self.fields['button_role'].setEnabled(relevant['button_role'])
        self.fields['command'].setEnabled(relevant['command'])
        self.choices.setPlaceholderText('画像のファイルパスを1行1件で指定' if gadget.kind == 'option' and gadget.display_mode == 'PIXMAP' else '選択肢の表示文字を1行1件で指定')
        self.prop_layout.setCaption(self.choices,'画像ファイル (1行1画像)' if gadget.kind == 'option' and gadget.display_mode == 'PIXMAP' else '選択肢 (1行1項目)')
        self.prop_layout.setCaption(self.item_values,'RTEXT 実値 (1行1項目)')
        width_caption = '幅 (px)' if gadget.display_mode == 'PIXMAP' else '幅（プレビューのみ）' if (gadget.kind=='toggle' or uses_pairs(gadget)) else '幅'
        self.prop_layout.setCaption(self.fields['width'],width_caption)
        self.prop_layout.setCaption(self.fields['height'],'高さ (px)' if gadget.display_mode == 'PIXMAP' else '高さ / 行数')
        basis='フレーム基準' if gadget.parent else 'フォーム基準'
        self.prop_layout.setCaption(self.fields['x'],f'X ({basis})')
        self.prop_layout.setCaption(self.fields['y'],f'Y ({basis})')
        for key in ('x','y'):self.fields[key].setToolTip(f'{basis}の座標。フレーム間のドラッグでは位置を保って座標を換算します。')
        self.browse_image.setText('📁 画像ファイルを追加' if gadget.kind == 'option' else '📁 画像ファイルを選択')
        generated=self.form.default_mode=='GENERATED'
        for editor,applicable in ((self.fields['initial'],relevant['initial']),
                                  (self.initial_choice,boolean),(self.pane_lines,gadget.kind=='textpane')):
            editor.setEnabled(generated and applicable)
            if not generated:editor.setToolTip('元コードを保持中です。「取り込みコード」のDEFAULT欄で編集してください。')
        if generated:
            self.initial_choice.setToolTip('空欄＝設定しない。TRUE / FALSEを選ぶとDEFAULTへ自動出力します。')
            self.pane_lines.setToolTip('')
        self.prop_layout.setCaption(self.fields['slider_value'],'宣言時の値' if not generated else '初期値')
        shared=sum(g.callback.lower()==gadget.callback.lower() for g in self.form.gadgets) if gadget.callback else 0
        self.body.setToolTip('同じメソッド名を使うすべての部品に編集を反映します。' if shared>1 else '')
        self.prop_layout.batching = False
        if self.prop_layout.pending: self.prop_layout.reflow()

    def sync_extra_editors(self, gadget, rebuild=True):
        if self.gadget_comment.toPlainText()!=gadget.comment:self.gadget_comment.setPlainText(gadget.comment)
        if rebuild:
            for editor, value in ((self.item_values,'\n'.join(gadget.item_values)), (self.view_code,gadget.view_code)):
                if editor.toPlainText() != value: editor.setPlainText(value)
            if self.pane_lines.toPlainText() != '\n'.join(gadget.pane_lines): self.pane_lines.setPlainText('\n'.join(gadget.pane_lines))
        self.fixed_font.setChecked(gadget.fixed_font)
        self.pane_lines.setFont(QFont('monospace',10) if gadget.fixed_font else QApplication.font())
        self.enable_gadget_fields(gadget)
        self.sync_list_table(gadget,rebuild)

    def current_table(self):
        if self.selected is None: return None
        g = self.form.gadgets[self.selected]
        return g if g.kind == 'list' and g.list_mode == 'TABLE' else None

    def sync_list_table(self, gadget, rebuild=True):
        active = gadget.kind == 'list' and gadget.list_mode == 'TABLE'
        self.prop_layout.setRowVisible(self.list_table_group,active)
        if not active or not rebuild: return
        self.list_table.setRowCount(0); self.list_table.setColumnCount(len(gadget.headings))
        self.list_table.setHorizontalHeaderLabels([f'列{i+1}' for i in range(len(gadget.headings))])
        values = [gadget.headings,*gadget.rows]
        self.list_table.setRowCount(len(values)); self.list_table.setVerticalHeaderLabels(['見出し',*[str(i) for i in range(1,len(values))]])
        for row,cells in enumerate(values):
            for column,value in enumerate(cells):
                editor = TableCell(value)
                if row == 0: editor.setStyleSheet('background: #dfeaf5;')
                editor.focused.connect(lambda r=row,c=column: self.list_table.setCurrentCell(r,c))
                editor.textEdited.connect(lambda text,r=row,c=column: self.update_table_cell(r,c,text))
                self.list_table.setCellWidget(row,column,editor)

    def update_table_cell(self, row, column, text):
        g = self.current_table()
        if self.loading or g is None: return
        self.checkpoint()
        cells = g.headings if row == 0 else g.rows[row-1]
        cells[column] = text; self.refresh(rebuild=False)

    def add_table_column(self):
        g = self.current_table()
        if g is None: return
        self.checkpoint(); g.headings.append(f'見出し{len(g.headings)+1}')
        for row in g.rows: row.append('')
        self.refresh()

    def delete_table_column(self):
        g = self.current_table(); column = self.list_table.currentColumn()
        if g is None or len(g.headings) <= 1 or not 0 <= column < len(g.headings): return
        self.checkpoint(); g.headings.pop(column)
        for row in g.rows: row.pop(column)
        self.refresh()

    def add_table_row(self):
        g = self.current_table()
        if g is None: return
        self.checkpoint(); g.rows.append(['']*len(g.headings)); self.refresh()

    def delete_table_row(self):
        g = self.current_table(); row = self.list_table.currentRow()-1
        if g is None or not 0 <= row < len(g.rows): return
        self.checkpoint(); g.rows.pop(row); self.refresh()

    def apply_page_visibility(self):
        if self.selected is not None and self.selected < len(self.form.gadgets):
            current = self.form.gadgets[self.selected]; seen = set()
            while current and current.name.lower() not in seen:
                seen.add(current.name.lower()); parent = self.form.parent_gadget(current)
                if parent and parent.frame_style == 'TABSET': self.active_pages[parent.name.lower()] = current.name.lower()
                current = parent
        for tabset in self.form.gadgets:
            if tabset.kind == 'frame' and tabset.frame_style == 'TABSET':
                pages = self.form.children(tabset.name)
                valid = {g.name.lower() for g in pages}
                if self.active_pages.get(tabset.name.lower()) not in valid:
                    self.active_pages[tabset.name.lower()] = pages[0].name.lower() if pages else ''
        self.scene.blockSignals(True)
        for item in self.scene.items():
            if not isinstance(item, Item): continue
            visible = True; current = item.gadget; seen = set()
            while current and current.name.lower() not in seen:
                seen.add(current.name.lower()); parent = self.form.parent_gadget(current)
                if parent and parent.frame_style == 'TABSET' and self.active_pages.get(parent.name.lower()) != current.name.lower():
                    visible = False
                current = parent
            item.active_page = self.active_pages.get(item.gadget.name.lower(), '')
            item.setVisible(visible); item.update()
        self.scene.blockSignals(False)
        self.form.sync_tabs()
        visibility={item.data(0):item.isVisible() for item in self.scene.items() if isinstance(item,Item)}
        for index,g in enumerate(self.form.gadgets):
            self.objects.item(index).setHidden(False)
            self.objects.item(index).setForeground(0,QColor('#24354b' if visibility.get(index,True) else '#98a2b3'))
            self.objects.item(index).setToolTip(0,f'{gadget_title(g)}: {g.label}\n.{g.name}'+(f' / 親: .{g.parent}' if g.parent else ' / フォーム直下')+'\nダブルクリックで設定を編集')
        self.sync_tab_editor()
        self.sync_context_hints()

    def sync_context_hints(self):
        g=self.form.gadgets[self.selected] if self.selected is not None and self.selected<len(self.form.gadgets) else None
        if g:
            parent=self.form.parent_gadget(g)
            location=f'{parent.label} (.{parent.name})' if parent else 'フォーム直下'
            self.selection_hint.setText(f'{gadget_title(g)}  .{g.name}\n所属: {location}')
            self.method_target.setText(f'対象: {g.label} (.{g.name})\n処理名: {g.callback or "メソッドなし"}')
        else:
            self.selection_hint.setText('部品を選択してください。\nダブルクリックで設定を編集できます。')
            self.method_target.setText('キャンバスまたは部品一覧で、処理を編集する部品を選択してください。')
        target=g if g and g.kind=='frame' else self.form.parent_gadget(g) if g else None
        if target and target.frame_style=='TABSET':
            target=next((page for page in target.tabs if page.name.lower()==self.active_pages.get(target.name.lower())),None)
        self.placement_hint.setText('追加先: '+(f'{target.label} (.{target.name})' if target else 'フォーム直下'))

    def sync_tab_editor(self):
        tabsets=[g for g in self.form.gadgets if g.kind=='frame' and g.frame_style=='TABSET']
        chosen=self.tabset_picker.currentData()
        current=self.form.gadgets[self.selected] if self.selected is not None and self.selected<len(self.form.gadgets) else None
        if current is not None:chosen=None
        seen=set()
        while current and current.name.lower() not in seen:
            seen.add(current.name.lower())
            if current.kind=='frame' and current.frame_style=='TABSET':
                chosen=current.name;break
            current=self.form.parent_gadget(current)
        self.tabset_picker.blockSignals(True);self.page_tabs.blockSignals(True)
        self.tabset_picker.clear()
        self.tabset_picker.addItem('フォーム直下',None)
        for g in tabsets:self.tabset_picker.addItem(f'{g.label} (.{g.name})',g.name)
        self.tabset_picker.setCurrentIndex(max(0,self.tabset_picker.findData(chosen)))
        while self.page_tabs.count():self.page_tabs.removeTab(0)
        tabset=next((g for g in tabsets if g.name==self.tabset_picker.currentData()),None)
        if tabset:
            for page in self.form.children(tabset.name):
                index=self.page_tabs.addTab(page.label or page.name);self.page_tabs.setTabData(index,page.name)
                self.page_tabs.setTabToolTip(index,f'.{page.name} 内に部品を配置')
            active=self.active_pages.get(tabset.name.lower())
            index=next((i for i in range(self.page_tabs.count()) if self.page_tabs.tabData(i).lower()==active),0)
            self.page_tabs.setCurrentIndex(index)
        self.tabset_picker.blockSignals(False);self.page_tabs.blockSignals(False)
        self.tab_editor.setVisible(bool(tabsets))
        self.add_page_button.setEnabled(tabset is not None)
        self.edit_page_button.setEnabled(self.page_tabs.count()>0)
        self.delete_page_button.setEnabled(self.page_tabs.count()>0)

    def change_tabset(self,index):
        if self.loading:return
        name=self.tabset_picker.itemData(index)
        selected=next((i for i,g in enumerate(self.form.gadgets) if g.name==name),None)
        self.choose_row(selected if selected is not None else -1)

    def change_edit_page(self,index):
        name=self.page_tabs.tabData(index) if index>=0 else None
        selected=next((i for i,g in enumerate(self.form.gadgets) if g.name==name),None)
        if selected is not None:self.choose_row(selected)

    def add_page(self):
        name=self.tabset_picker.currentData()
        index=next((i for i,g in enumerate(self.form.gadgets) if g.name==name),None)
        if index is None:return
        self.selected=index;self.add('frame','PAGE')

    def edit_page(self):
        name=self.page_tabs.tabData(self.page_tabs.currentIndex())
        page=self.form.named(name) if name else None
        if page is None:return
        dialog=QDialog(self);dialog.setWindowTitle('タブ設定')
        layout=QFormLayout(dialog);name_edit=QLineEdit(page.name);label_edit=QLineEdit(page.label)
        layout.addRow('タブのオブジェクト名',name_edit);layout.addRow('タブの表示名',label_edit)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addRow(buttons)
        if dialog.exec()==QDialog.Accepted:
            self.update_page(name,name_edit.text(),label_edit.text())

    def update_page(self,old_name,new_name,label):
        from .names import rename
        from .model import literal
        index=next((i for i,g in enumerate(self.form.gadgets) if g.name==old_name and self.form.is_tab_page(g)),None)
        if index is None:return
        try:
            literal(label);candidate=rename(self.form,'gadget',index,new_name)
            candidate.gadgets[index].label=label;candidate.validate()
        except ValueError as error:self.statusBar().showMessage(str(error));return
        self.checkpoint();self.form=candidate;self.selected=index;self.refresh()

    def reorder_pages(self,source,target):
        if self.loading:return
        names=[self.page_tabs.tabData(i) for i in range(self.page_tabs.count())]
        positions=[i for i,g in enumerate(self.form.gadgets) if g.name in names]
        pages={g.name:g for g in self.form.gadgets if g.name in names}
        if len(positions)!=len(names):return
        selected=self.form.gadgets[self.selected].name if self.selected is not None else None
        self.checkpoint()
        for index,name in zip(positions,names):self.form.gadgets[index]=pages[name]
        self.selected=next((i for i,g in enumerate(self.form.gadgets) if g.name==selected),None)
        self.refresh()

    def delete_page(self):
        name=self.page_tabs.tabData(self.page_tabs.currentIndex())
        page=self.form.named(name) if name else None
        if page is None:return
        if self.form.descendants(name) and QMessageBox.question(self,'タブの削除','このタブ内の部品も削除します。続けますか？',QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        parent=page.parent;removed={name.lower(),*(child.lower() for child in self.form.descendants(name))}
        self.checkpoint();self.form.gadgets=[g for g in self.form.gadgets if g.name.lower() not in removed]
        self.selected=next((i for i,g in enumerate(self.form.gadgets) if g.name==parent),None);self.refresh()

    def choose_page(self, name):
        from PySide6.QtCore import QTimer
        index = next((i for i,g in enumerate(self.form.gadgets) if g.name == name), None)
        if index is not None: QTimer.singleShot(0, lambda: self.choose_row(index))

    def update_gadget(self):
        if self.loading or self.selected is None: return
        previous_history=list(self.history);previous_form=self.form
        previous_future=list(self.future);previous_dirty=self.dirty
        requested_name=self.fields['name'].text()
        self.checkpoint()
        if requested_name!=self.form.gadgets[self.selected].name:self.form=copy.deepcopy(self.form)
        g = self.form.gadgets[self.selected]
        g.comment = self.gadget_comment.toPlainText()
        old_action = g.action_mode
        old_mode = g.list_mode
        old_name = g.name
        old_role = g.button_role
        old_display = g.display_mode
        old_fixed = fixed_dimensions(g)
        direction_key = 'orientation' if g.kind == 'line' else 'slider_orientation' if g.kind == 'slider' else None
        old_direction = getattr(g,direction_key) if direction_key else None
        old_command,old_callback=g.command,g.callback
        from .names import actual_name,code_slots,read_slot,write_slot,rewrite_code
        old_actual = actual_name(g)
        for key, w in self.fields.items():
            if key=='name':continue
            if (old_display == 'PIXMAP' and key in ('width','height','width_ref')) or key in old_fixed:continue
            value = w.currentData() if key in ('parent','xref','yref','width_ref','popup_menu','action_mode') else self.edited_number(w,getattr(g,key)) if isinstance(w, QDoubleSpinBox) else w.currentText() if isinstance(w, QComboBox) else w.text()
            setattr(g, key, value)
        if direction_key and getattr(g,direction_key) != old_direction:
            new_direction = getattr(g,direction_key);setattr(g,direction_key,old_direction)
            change_orientation(g,new_direction,preview_geometry(self.form,g)[2:])
        if g.command and g.command!=old_command:g.callback=''
        elif g.callback and g.callback!=old_callback:g.command=''
        if old_display != g.display_mode:
            if g.display_mode == 'PIXMAP': g.width *= SX;g.height *= SY
            else: g.width = max(1,g.width/SX);g.height = max(1,g.height/SY)
            if g.kind == 'option' and g.display_mode == 'PIXMAP': g.name = g.name.lstrip('_')
        if g.kind == 'option' and g.display_mode == 'PIXMAP':requested_name=requested_name.lstrip('_')
        if g.button_role != old_role and g.button_role in ('OK','CANCEL','HELP'):
            g.callback = '';g.command = '';g.action_mode = 'CODE'
        if g.kind == 'option' and old_display == 'PIXMAP' and g.display_mode == 'TEXT':
            g.callback = '';g.item_values = []
            self.item_values.blockSignals(True);self.item_values.clear();self.item_values.blockSignals(False)
        if g.action_mode == 'MACRO':
            if old_action != 'MACRO':
                if not g.macro_flag:g.macro_flag='buttonFlag'
                if not g.macro_value:g.macro_value=g.name
            g.callback='';g.command=''
            if g.macro_flag and IDENTIFIER.fullmatch(g.macro_flag) and g.macro_flag.lower() not in {name.lower() for name in self.form.variables}:
                self.form.variables[g.macro_flag]=''
        table_changed = old_mode != g.list_mode
        if g.kind == 'list' and g.list_mode == 'TABLE' and not g.headings:
            g.headings = ['見出し1','見出し2']; g.rows = [['','']]
            table_changed = True
        if old_name != g.name:
            for child in self.form.gadgets:
                for key in ('parent','xref','yref','width_ref'):
                    if getattr(child,key).lower() == old_name.lower(): setattr(child,key,g.name)
        if g.layout_mode == 'RELATIVE':
            siblings = [other for other in self.form.children(g.parent) if other is not g]
            if siblings:
                if not g.xref: g.xref = siblings[0].name
                if not g.yref: g.yref = siblings[0].name
        values = self.item_values.toPlainText()
        g.item_values = values.split('\n') if values else []
        g.view_code = self.view_code.toPlainText()
        pane_text = self.pane_lines.toPlainText();g.pane_lines = pane_text.split('\n') if pane_text else []
        g.fixed_font = self.fixed_font.isChecked()
        choices = self.choices.toPlainText()
        g.items = choices.split('\n') if choices else []
        from .callbacks import join_callback,set_callback_body
        if g.callback.lower()!=old_callback.lower():
            join_callback(self.form,g,old_callback)
        else:set_callback_body(self.form,g,self.body.toPlainText())
        if uses_pairs(g) and not g.item_values:
            commands = self.choice_commands.toPlainText().split('\n')
            g.item_commands = (commands if self.choice_commands.toPlainText() else [])
            if len(g.item_commands) < len(g.items): g.item_commands += [''] * (len(g.items) - len(g.item_commands))
        if g.kind=='option' and not uses_pairs(g):g.item_commands=[]
        if g.kind == 'option' and old_display != g.display_mode:
            for _,owner,key in code_slots(self.form):
                write_slot(owner,key,rewrite_code(read_slot(owner,key),self.form,self.form,{old_actual:actual_name(g)}))
        name_changed=requested_name!=g.name
        if name_changed:
            from .names import rename
            try:self.form=rename(self.form,'gadget',self.selected,requested_name)
            except ValueError as error:
                self.form=previous_form;self.history=previous_history
                self.future=previous_future;self.dirty=previous_dirty
                self.statusBar().showMessage(str(error));return
        self.refresh(rebuild=table_changed or name_changed)

    def image_directories(self):
        source = (Path(self.form.source_mac_path).parent,) if self.form.source_mac_path else ()
        return ((self.path.resolve().parent,) if self.path else ()) + source + (self.settings.app_directory,)

    def refresh(self, rebuild=True):
        if self._closing or not isValid(self) or not isValid(self.scene): return
        self.partial_notice.setVisible(bool(self.form.partial_import_source))
        self.partial_notice.setText(f'部分取り込み: {len(self.form.partial_import_notes)}箇所を省略')
        self.loading = True
        image_directories = self.image_directories()
        for gadget in self.form.gadgets:
            if sync_image_size(gadget,image_directories):self.dirty=True
            if normalize_dimensions(gadget):self.dirty=True
        self.inspector_tabs.setEnabled(True)
        if self.selected is not None:self._multi_selection.clear()
        self._multi_selection.intersection_update(g.name for g in self.form.gadgets)
        if len(self._multi_selection)==1:
            name=next(iter(self._multi_selection));self.selected=next(i for i,g in enumerate(self.form.gadgets) if g.name==name)
            self._multi_selection.clear()
        for highlighter in self.pml_highlighters:highlighter.set_symbols(self.form)
        self.refresh_menus(rebuild)
        if not self.variable_error:
            try:current_variables=parse_variables(self.variables.toPlainText())
            except ValueError:current_variables=None
            if current_variables!=(self.form.variables,self.form.local_variables):
                self.variables.setPlainText(variable_text(self.form))
        if self.default_body.toPlainText() != self.form.default_body: self.default_body.setPlainText(self.form.default_body)
        if self.after_show.toPlainText() != self.form.after_show_code: self.after_show.setPlainText(self.form.after_show_code)
        self.program_label.setText('取り込んだ表示プログラム（SHOWを含む）' if self.form.program_mode=='SOURCE' else '表示後のプログラム')
        self.fname.setText(self.form.symbol); self.ftitle.setText(self.form.title)
        self.docking.setCurrentIndex(self.docking.findData('MAIN' if self.form.form_type=='MAIN' else self.form.docking_side()))
        for event,editor in self.form_callbacks.items():
            if editor.text() != getattr(self.form,event): editor.setText(getattr(self.form,event))
        self.load_number(self.fw,self.form.width); self.load_number(self.fh,self.form.height)
        self.objects.rebuild(self.form,gadget_title,lambda g:PALETTE[g.kind][0])
        if self.selected is None and not self._multi_selection:self.objects.setCurrentRow(-1,reveal=False)
        self.scene.blockSignals(True); self.scene.clear()
        self.scene.setSceneRect(-12,-30,self.form.width*SX+24,self.form.height*SY+42)
        self.form_item=FormItem(self.form,SX,SY);self.scene.addItem(self.form_item)
        self.form_item.setSelected(self.selected is None and not self._multi_selection)
        self.form_item.resizing.connect(self.form_resize_preview);self.form_item.resized.connect(self.resize_committed)
        self.form_item.editRequested.connect(lambda:QTimer.singleShot(0,self.edit_form_properties))
        for index, g in enumerate(self.form.gadgets):
            item = Item(g, self.form, image_directories); item.setData(0, index)
            item.pageChosen.connect(self.choose_page)
            item.selectionToggled.connect(self.toggle_selection)
            item.labelEditRequested.connect(self.request_object_label)
            item.resizing.connect(self.resize_preview); item.resized.connect(self.resize_committed)
            item.moved.connect(self.move_committed);item.groupMoved.connect(self.move_multiple_committed); self.scene.addItem(item)
            item.setSelected(index == self.selected or g.name in self._multi_selection)
        self.scene.blockSignals(False)
        self.apply_page_visibility()
        if self.selected is not None and self.selected < len(self.form.gadgets):
            self.objects.setCurrentRow(self.selected,reveal=False); g = self.form.gadgets[self.selected]
            self.populate_parents(g)
            self.enable_layout_fields(g)
            for key, w in self.fields.items():
                if key in ('parent','xref','yref','width_ref','popup_menu'): continue
                value = getattr(g, key)
                if isinstance(w, QDoubleSpinBox): self.load_number(w,value)
                elif key == 'action_mode': w.setCurrentIndex(w.findData(value))
                elif isinstance(w, QComboBox): w.setCurrentText(value)
                else: w.setText(value)
            # Do not reset typing cursor in multi-line editors on every keystroke.
            if rebuild and self.choices.toPlainText() != '\n'.join(g.items): self.choices.setPlainText('\n'.join(g.items))
            if rebuild and self.choice_commands.toPlainText() != '\n'.join(g.item_commands): self.choice_commands.setPlainText('\n'.join(g.item_commands))
            self.choice_commands.setEnabled(g.kind == 'option')
            from .callbacks import callback_body
            body=callback_body(self.form,g)
            if self.body.toPlainText() != body: self.body.setPlainText(body)
            self.props.setEnabled(not self.form.is_tab_page(g))
            self.fields['value_type'].setEnabled(g.kind == 'text'); self.fields['initial'].setEnabled(g.kind in ('text','paragraph','toggle','rtoggle','option','combo','list') and not (g.kind == 'paragraph' and g.display_mode == 'PIXMAP'))
            self.choices.setEnabled(g.kind in ('option', 'list', 'combo'))
            self.fields['label'].setEnabled(g.kind != 'line'); self.fields['orientation'].setEnabled(g.kind == 'line'); self.fields['frame_style'].setEnabled(g.kind == 'frame'); self.fields['callback'].setEnabled(g.kind not in ('paragraph', 'line', 'frame', 'option')); self.fields['command'].setEnabled(g.kind in ('toggle', 'text', 'button')); self.fields['background'].setEnabled(g.kind in ('paragraph', 'button', 'list')); self.body.setEnabled(bool(g.callback))
            self.sync_extra_editors(g, rebuild)
        else: self.selected = None; self.props.setEnabled(False); self.body.setEnabled(False)
        self.selection_stack.setCurrentIndex(1 if self.selected is not None else 0)
        self.props.setVisible(self.selected is not None and not self.form.is_tab_page(self.form.gadgets[self.selected]))
        self.loading = False
        try:
            if self.variable_error: raise ValueError('変数欄の 名前=初期値 の形式を修正してください。')
            self.code.setPlainText(self.form.pml());self.validation_error='';self.statusBar().showMessage('設計を編集できます。PML の実行は E3D 側で行ってください。')
        except ValueError as e:
            self.validation_error=str(e);self.code.setPlainText('-- 出力できません: ' + str(e)); self.statusBar().showMessage(str(e))
        self.sync_output_summary()
        self.edit_method_button.setEnabled(self.selected is not None and self.fields['callback'].isEnabled() and not self.form.gadgets[self.selected].command)
        self.setWindowTitle(('● ' if self.dirty else '') + 'E3D PML Form Designer — ' + (self.path.name if self.path else '新規設計'))
        if self._multi_selection:self.show_multiple_selection(reveal=False)

    def choose_row(self, index):
        if self.loading: return
        self._multi_selection.clear()
        self.selected = index if index >= 0 else None
        # Hidden pages must become visible before Qt can select their outline.
        self.apply_page_visibility()
        self.scene.blockSignals(True)
        for item in self.scene.items():
            if isinstance(item,Item): item.setSelected(item.data(0)==self.selected)
            elif isinstance(item,FormItem):item.setSelected(self.selected is None)
        self.scene.blockSignals(False)
        self.sync_selection()

    def edit_tree_item(self,item,column=0):
        index=item.data(0,Qt.UserRole)
        if index is None or index<0:QTimer.singleShot(0,self.edit_form_properties)
        else:self.request_object_label(self.form.gadgets[index].name)

    def move_tree_gadget(self,index,parent_name,before=-1):
        if self.loading or not 0<=index<len(self.form.gadgets):return
        g=self.form.gadgets[index];parent=self.form.named(parent_name) if parent_name else None
        if parent and parent.frame_style=='TABSET' and not self.form.is_tab_page(g):
            parent=self.current_tab_page(parent)
            if parent is None:
                self.statusBar().showMessage('「＋ タブ」でタブを追加してから部品を配置してください。');return
            parent_name=parent.name;before=-1
        excluded={g.name.lower(),*(name.lower() for name in self.form.descendants(g.name))}
        if parent_name and (parent is None or parent.kind!='frame' or parent.name.lower() in excluded):
            self.statusBar().showMessage('移動先には自分や子孫以外のフレームを指定してください。');return
        same_parent=g.parent.lower()==parent_name.lower()
        if self.form.is_tab_page(g) and not same_parent:
            self.statusBar().showMessage('タブフレームは同じTABSET内で並べ替えてください。');return
        branch=[i for i,item in enumerate(self.form.gadgets) if item.name.lower() in excluded]
        if before in branch:return
        order=[i for i in range(len(self.form.gadgets)) if i not in branch]
        slot=order.index(before) if before in order else len(order)
        order[slot:slot]=branch
        if same_parent:
            siblings=[i for i,item in enumerate(self.form.gadgets) if item.parent.lower()==g.parent.lower()]
            if [i for i in order if i in siblings]==siblings:return
            self.reorder_objects(order,index);return
        draft=copy.deepcopy(self.form);moved=draft.gadgets[index]
        try:
            x,y,width,height=draft.geometry(moved);ox,oy=draft.offset(moved);x+=ox;y+=oy
            moved.parent=parent_name;moved.layout_mode='ABSOLUTE';moved.xref=moved.yref=moved.width_ref=''
            moved.width,moved.height=native_size(moved,width,height)
            ox,oy=draft.offset(moved);pw,ph=draft.geometry(draft.parent_gadget(moved))[2:] if parent else (draft.width,draft.height)
            if width>pw+.001 or height>ph+.001:
                self.statusBar().showMessage('移動先のフレームに部品全体が収まりません。');return
            moved.x=round(max(0,min(x-ox,pw-width)),2);moved.y=round(max(0,min(y-oy,ph-height)),2)
            draft.gadgets=[draft.gadgets[i] for i in order];draft.sync_tabs()
            draft.validate()
        except ValueError as error:self.statusBar().showMessage(str(error));return
        self.checkpoint();self.form=draft;self.selected=order.index(index)
        QTimer.singleShot(0,self.refresh)

    def reorder_objects(self, order, selected):
        if self.loading or sorted(order) != list(range(len(self.form.gadgets))) or order == list(range(len(order))): return
        self.checkpoint(); self.form.gadgets = [self.form.gadgets[index] for index in order]
        self.selected = order.index(selected) if selected in order else None
        self.loading = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0,self.refresh)

    def form_resize_preview(self):
        self.scene.setSceneRect(-12,-30,self.form.width*SX+24,self.form.height*SY+42)
        self.loading=True
        self.load_number(self.fw,self.form.width);self.load_number(self.fh,self.form.height)
        self.loading=False

    def edit_form_properties(self):
        if self._closing:return
        from .quick_editor import FormProperties
        dialog=FormProperties(self,self.form)
        if dialog.exec()==QDialog.Accepted and dialog.result_form is not None:
            if dialog.result_form.dumps()!=self.form.dumps():
                self.checkpoint();self.form=dialog.result_form;self.selected=None;self.refresh()
        dialog.deleteLater()

    def resize_preview(self):
        for item in self.scene.items():
            if not isinstance(item,Item): continue
            x,y,w,h = preview_geometry(self.form,item.gadget); ox,oy = preview_offset(self.form,item.gadget)
            item.prepareGeometryChange(); item._width,item._height = w,h
            item._sync_geometry = True
            item.setPos((x+ox)*SX,(y+oy)*SY); item._sync_geometry = False; item.update()
        if self.selected is not None:
            g = self.form.gadgets[self.selected]; self.loading = True
            self.load_number(self.fields['width'],g.width); self.load_number(self.fields['height'],g.height); self.loading = False

    def resize_committed(self, old):
        self.history.append(old); self.history = self.history[-100:]; self.future.clear(); self.dirty = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0,self.refresh)

    def selection_names(self):
        if self._multi_selection:return set(self._multi_selection)
        return {self.form.gadgets[self.selected].name} if self.selected is not None else set()

    def toggle_selection(self,name):
        names=self.selection_names()
        if name in names:names.remove(name)
        else:names.add(name)
        self.choose_rows([i for i,g in enumerate(self.form.gadgets) if g.name in names])

    def choose_rows(self,indices):
        if self.loading:return
        indices=[index for index in indices if 0<=index<len(self.form.gadgets)]
        if len(indices)<2:
            self.choose_row(indices[0] if indices else -1);return
        self._multi_selection={self.form.gadgets[index].name for index in indices};self.selected=None
        previous=self.scene.blockSignals(True)
        for item in self.scene.items():
            item.setSelected(isinstance(item,Item) and item.gadget.name in self._multi_selection)
        self.scene.blockSignals(previous);self.show_multiple_selection()

    def show_multiple_selection(self,reveal=True):
        self.loading=True
        self.form_item.setSelected(False)
        self.objects.setRows([i for i,g in enumerate(self.form.gadgets) if g.name in self._multi_selection],reveal)
        self.selection_stack.setCurrentIndex(2)
        self.multiple_hint.setText(f'{len(self._multi_selection)} 個の部品を選択中\n個別のプロパティは1個選択すると編集できます。')
        self.inspector_tabs.setEnabled(False);self.sync_context_hints();self.loading=False

    def move_selection(self,dx,dy,names=None,old=None):
        names=set(names) if names is not None else self.selection_names()
        if not names:return False
        candidate=copy.deepcopy(self.form)
        roots=[]
        for g in candidate.gadgets:
            if g.name not in names:continue
            parent=candidate.parent_gadget(g);seen=set();covered=False
            while parent and parent.name not in seen:
                seen.add(parent.name)
                if parent.name in names:covered=True;break
                parent=candidate.parent_gadget(parent)
            if not covered:roots.append(g)
        try:
            for g in roots:
                parent=candidate.parent_gadget(g)
                if g.layout_mode!='ABSOLUTE' or candidate.is_tab_page(g) or (parent and parent.frame_style=='TOOLBAR'):
                    raise ValueError('選択した部品は座標で移動できません。配置方式と所属を確認してください。')
                g.x=round(g.x+dx,2);g.y=round(g.y+dy,2)
            candidate.validate()
        except ValueError as error:
            if old is not None:self.refresh()
            self.statusBar().showMessage(str(error));return False
        if old is None:self.checkpoint()
        else:
            self.history.append(old);self.history=self.history[-100:];self.future.clear();self.dirty=True
        self.form=candidate;self.refresh();return True

    def move_multiple_committed(self,old,names,dx,dy):
        QTimer.singleShot(0,lambda:self.move_selection(dx,dy,names,old))

    def eventFilter(self,watched,event):
        if event.type()==QEvent.MouseButtonDblClick and event.button()==Qt.LeftButton:
            if watched in (self.preview_menu_bar,self.preview_menu_frame):
                for menu in self.preview_menus:menu.close()
                QTimer.singleShot(0,self.add_palette_menu);event.accept();return True
        if event.type()==QEvent.KeyPress and watched in (self.view,self.view.viewport()):
            item=self.scene.mouseGrabberItem()
            if event.key()==Qt.Key_Escape:
                if isinstance(item,(Item,FormItem)) and item.cancel_interaction():
                    self.statusBar().showMessage('操作を取り消しました。');event.accept();return True
            directions={Qt.Key_Left:(-1,0),Qt.Key_Right:(1,0),Qt.Key_Up:(0,-1),Qt.Key_Down:(0,1)}
            if event.key() in directions:
                if not item or not (getattr(item,'_move_start',None) or getattr(item,'_resize',None)):
                    step=.1 if event.modifiers() & Qt.AltModifier else .5
                    x,y=directions[event.key()];self.move_selection(x*step,y*step)
                event.accept();return True
        return super().eventFilter(watched,event)

    def selection_changed(self):
        if self._closing or not isValid(self) or not isValid(self.scene) or self.loading:return
        indices=[item.data(0) for item in self.scene.selectedItems() if isinstance(item,Item)]
        self._multi_selection={self.form.gadgets[index].name for index in indices} if len(indices)>1 else set()
        self.selected=indices[0] if len(indices)==1 else None
        QTimer.singleShot(0,self.sync_selection)

    def sync_selection(self):
        if self._closing or not isValid(self) or not isValid(self.scene): return
        # Property loading only: keep the grabbed graphics item alive while dragging.
        if self._multi_selection:
            self.show_multiple_selection();return
        self.inspector_tabs.setEnabled(True)
        self.loading = True
        self.form_item.setSelected(self.selected is None)
        if self.selected is None:
            self.objects.setCurrentRow(-1);self.inspector_tabs.setCurrentIndex(0)
        if self.selected is not None:
            self.objects.setCurrentRow(self.selected)
            g = self.form.gadgets[self.selected]
            self.populate_parents(g)
            self.enable_layout_fields(g)
            for key, w in self.fields.items():
                if key in ('parent','xref','yref','width_ref','popup_menu'): continue
                v = getattr(g, key)
                if isinstance(w, QDoubleSpinBox): self.load_number(w,v)
                elif key == 'action_mode': w.setCurrentIndex(w.findData(v))
                elif isinstance(w, QComboBox): w.setCurrentText(v)
                else: w.setText(v)
            from .callbacks import callback_body
            self.choices.setPlainText('\n'.join(g.items)); self.body.setPlainText(callback_body(self.form,g))
            self.choice_commands.setPlainText('\n'.join(g.item_commands)); self.choice_commands.setEnabled(g.kind == 'option')
            self.fields['value_type'].setEnabled(g.kind == 'text'); self.fields['initial'].setEnabled(g.kind in ('text','paragraph','toggle','rtoggle','option','combo','list') and not (g.kind == 'paragraph' and g.display_mode == 'PIXMAP'))
            self.choices.setEnabled(g.kind in ('option', 'list', 'combo'))
            self.fields['label'].setEnabled(g.kind != 'line'); self.fields['orientation'].setEnabled(g.kind == 'line'); self.fields['frame_style'].setEnabled(g.kind == 'frame'); self.fields['callback'].setEnabled(g.kind not in ('paragraph', 'line', 'frame', 'option')); self.fields['command'].setEnabled(g.kind in ('toggle', 'text', 'button')); self.fields['background'].setEnabled(g.kind in ('paragraph', 'button', 'list')); self.body.setEnabled(bool(g.callback))
            self.sync_extra_editors(g)
        self.apply_page_visibility()
        self.props.setEnabled(self.selected is not None and not self.form.is_tab_page(self.form.gadgets[self.selected])); self.loading = False
        self.selection_stack.setCurrentIndex(1 if self.selected is not None else 0)
        self.props.setVisible(self.selected is not None and not self.form.is_tab_page(self.form.gadgets[self.selected]))
        if self.selected is not None and self.current_workflow=='form':self.set_workflow('layout')
        elif self.selected is not None and self.current_workflow=='action':
            self.inspector_tabs.setCurrentIndex(0)
            if self.props.isTabEnabled(3):self.props.setCurrentIndex(3)
        self.edit_method_button.setEnabled(self.selected is not None and self.fields['callback'].isEnabled() and not self.form.gadgets[self.selected].command)

    def move_committed(self,old,name,x,y):
        from PySide6.QtCore import QTimer
        index=next((i for i,g in enumerate(self.form.gadgets) if g.name==name),None)
        if index is None:return
        candidate=copy.deepcopy(self.form);g=candidate.gadgets[index]
        try:
            _,_,width,height=candidate.geometry(g)
            excluded={name.lower(),*(child.lower() for child in candidate.descendants(name))}
            visible={item.gadget.name.lower() for item in self.scene.items() if isinstance(item,Item) and item.isVisible()}
            targets=[]
            for frame in candidate.gadgets:
                if frame.kind!='frame' or frame.frame_style!='FRAME' or frame.name.lower() in excluded or frame.name.lower() not in visible:continue
                fx,fy,fw,fh=candidate.geometry(frame);ox,oy=candidate.offset(frame);fx+=ox;fy+=oy
                if x>=fx-.001 and y>=fy-.001 and x+width<=fx+fw+.001 and y+height<=fy+fh+.001:
                    depth=0;parent=candidate.parent_gadget(frame);seen={frame.name.lower()}
                    while parent and parent.name.lower() not in seen:
                        seen.add(parent.name.lower());depth+=1;parent=candidate.parent_gadget(parent)
                    targets.append((depth,-fw*fh,frame.name))
            parent=candidate.named(max(targets)[2]) if targets else None
            if g.kind=='rtoggle' and parent is None:
                message='ラジオボタン全体がFRAME内に収まる位置へ配置してください。'
                QTimer.singleShot(0,lambda:(self.refresh(),self.statusBar().showMessage(message)));return
            changed_parent=g.parent.lower()!=(parent.name.lower() if parent else '')
            g.parent=parent.name if parent else ''
            if changed_parent:
                g.width,g.height=native_size(g,width,height)
                g.xref=g.yref=g.width_ref=''
            ox,oy=candidate.offset(g);g.x=round(x-ox,2);g.y=round(y-oy,2)
            candidate.validate()
        except ValueError as error:
            message=str(error)
            QTimer.singleShot(0,lambda:(self.refresh(),self.statusBar().showMessage(message)));return
        self.form=candidate;self.selected=index
        self.history.append(old);self.history=self.history[-100:];self.future.clear();self.dirty=True
        QTimer.singleShot(0, self.refresh)

    def current_tab_page(self,tabset):
        active=self.active_pages.get(tabset.name.lower())
        return next((page for page in self.form.children(tabset.name) if page.name.lower()==active),None)

    def add(self, kind, direction=None):
        container = self.form.gadgets[self.selected] if self.selected is not None else None
        if container and container.kind != 'frame': container = self.form.parent_gadget(container)
        if direction == 'TOOLBAR':
            if self.form.form_type != 'MAIN':
                self.statusBar().showMessage('表示形式を MAIN フォームに変更してからツールバーを追加してください。');return
            container = None
        if container and container.frame_style == 'TOOLBAR' and kind not in ('button','toggle','option','text','combo','slider'):
            self.statusBar().showMessage('ツールバーにはボタン・チェック・OPTION・入力・COMBO・SLIDER を追加できます。');return
        if self.form.form_type == 'MAIN' and not container and direction != 'TOOLBAR' and kind not in ('button','toggle','option','text','combo','slider'):
            self.statusBar().showMessage('MAIN フォームではツールバー対応部品を追加してください。');return
        if container and container.frame_style == 'TABSET' and direction!='PAGE':
            container=self.current_tab_page(container)
            if container is None:
                self.statusBar().showMessage('「＋ タブ」でタブを追加してから部品を配置してください。');return
        available = None
        if container and container.frame_style == 'TOOLBAR':
            occupied = 1+sum(self.form.geometry(child)[2]+1 for child in self.form.children(container.name))
            available = container.width-occupied
            if available < 1 or container.height < 2:
                self.statusBar().showMessage('ツールバーに空きがありません。幅・高さを広げてください。');return
        draft=copy.deepcopy(self.form)
        if container:container=draft.named(container.name)
        if kind=='rtoggle' and container is None:
            container=Gadget(kind='frame',name=self.unique_name('radioGroup'),label='Radio group',
                             x=0,y=min(len(self.form.gadgets)*1.5,max(0,self.form.height-6)),
                             width=min(30,self.form.width),height=min(6,self.form.height))
            position=free_position([preview_geometry(draft,child) for child in draft.children('')],container.width,container.height,
                                   draft.width,draft.height,preferred=(container.x,container.y))
            if position is None:
                self.statusBar().showMessage('フォームにラジオグループを配置する空きがありません。フォームを広げてください。');return
            container.x,container.y=position
            draft.gadgets.append(container)
        name = self.unique_name(kind)
        width_limit, height_limit = draft.geometry(container)[2:] if container else (self.form.width, self.form.height)
        vertical = (kind == 'line' and direction == 'VERT') or (kind == 'slider' and direction == 'VERTICAL')
        height = min(5 if vertical or direction == 'PIXMAP' or kind in ('list', 'frame', 'view', 'commandline', 'container','textpane','selector') else 1, height_limit)
        if container and container.frame_style=='FRAME':height=min(height,max(1,height_limit-1))
        g = Gadget(kind=kind, name=name, label={'textpane':'Notes','selector':'Owner','button':'Run','paragraph':'Message','text':'Name','toggle':'Enabled','option':'Mode','list':'Results','line':'','frame':'Group','slider':'Level','rtoggle':'Choice','combo':'Choice','view':'Model view','commandline':'Command line','container':'External control'}[kind],
                   orientation=direction if kind == 'line' and direction else 'HORIZ',
                   slider_orientation=direction if kind == 'slider' and direction else 'HORIZONTAL',
                   display_mode='PIXMAP' if direction == 'PIXMAP' else 'TEXT',
                   width=min((1 if kind == 'line' else 3) if vertical else 18,width_limit), height=height,
                   x=0, y=0 if container else min(len(self.form.gadgets) * 1.5, height_limit-height),
                   parent=container.name if container else '')
        if kind == 'line' and direction: g.orientation = direction
        if container and container.frame_style=='TABSET':
            g.width=container.width;g.height=container.height;g.x=g.y=0
            g.label=f'Tab {len(draft.children(container.name))+1}'
        if kind == 'slider' and direction: g.slider_orientation = direction
        if direction == 'PIXMAP': g.display_mode = 'PIXMAP'
        if kind in ('button','text','toggle','list','combo','slider','selector') or (kind=='option' and direction=='PIXMAP'):
            g.callback=self.automatic_method(draft,name);g.body='  -- この部品の処理を必要に応じて追加してください。'
        if direction == 'TOOLBAR':
            g.frame_style = 'TOOLBAR';g.width = self.form.width;g.height = min(4,self.form.height);g.x = 0;g.y = 0
        if direction == 'TABSET':
            g.frame_style='TABSET';g.label='Tabs';g.width=min(40,width_limit)
            g.height=min(12,max(1,height_limit-1) if container else height_limit)
        if container and container.frame_style == 'TOOLBAR':
            g.width = min(g.width,available)
            g.height = min(g.height,container.height-1)
        if kind in ('option', 'list', 'combo'): g.items = ['Item A', 'Item B']
        if direction == 'PIXMAP' and kind == 'option': g.items = []
        if direction == 'PIXMAP': g.width *= SX;g.height *= SY
        normalize_dimensions(g)
        if container is None or container.frame_style=='FRAME':
            rectangles=[preview_geometry(draft,child) for child in draft.children(container.name if container else '')]
            gw,gh=display_size(g)
            position=free_position(rectangles,gw,gh,width_limit,height_limit,minimum_y=1 if container else 0,
                                   preferred=None if container else (g.x,g.y))
            if position is None:
                target=container.label or container.name if container else 'フォーム'
                self.statusBar().showMessage(f'「{target}」に空きがありません。サイズを広げるか、追加先を変更してください。');return
            g.x,g.y=position
        draft.gadgets.append(g)
        selected=len(draft.gadgets)-1
        if direction=='TABSET':
            for index in (1,2):
                base=f'{g.name}_tab{index}';page_name=base;number=1
                while draft.named(page_name):page_name=f'{base}_{number}';number+=1
                draft.gadgets.append(Gadget(kind='frame',name=page_name,label=f'Tab {index}',parent=g.name,x=0,y=0,width=g.width,height=g.height))
        self.checkpoint();self.form=draft;self.selected=selected;self.refresh();self.set_workflow('layout')

    def unique_name(self, base):
        used = self.reserved_names(self.form);i = 1
        while (base + str(i)).lower() in used: i += 1
        return base + str(i)

    @staticmethod
    def automatic_method(form,name):
        base='on_'+name.lstrip('_');method=base;number=2
        used=Window.reserved_names(form)
        while method.lower() in used:method=f'{base}_{number}';number+=1
        return method

    @staticmethod
    def reserved_names(form):
        used={form.name.lower(),'default',*(name.lower() for name in form.variables),*(menu.name.lower() for menu in form.menus)}
        used.update(method.name.lower() for method in form.extra_methods)
        for gadget in form.gadgets:
            used.update((gadget.name.lower(),gadget.callback.lower()))
            if gadget.kind=='list':used.add((gadget.table_method or 'populate_'+gadget.name).lower())
            if gadget.kind=='container':used.add((gadget.name+'Control').lower())
            if gadget.action_mode=='MACRO':used.add(('macro_'+gadget.name).lower())
        return used

    def duplicate(self):
        if self.selected is None: return
        from .clipboard import clone_subtree
        try:
            self.form.validate()
            draft,selected = clone_subtree(self.form,self.form,self.selected)
        except ValueError as error:
            self.statusBar().showMessage(f'複製できません: {error}');return
        self.checkpoint();self.form,self.selected = draft,selected;self.refresh()

    def copy_gadget(self,cut=False):
        if self.selected is None: return False
        try:
            self.form.validate()
            payload = json.dumps({'form':self.form.dumps(),'root':self.selected,'cut':bool(cut),'project':self.project_key},ensure_ascii=False)
        except ValueError as error:
            self.statusBar().showMessage(f'コピーできません: {error}');return False
        data = QMimeData();data.setData(GADGET_MIME,payload.encode('utf-8'))
        QApplication.clipboard().setMimeData(data)
        self.statusBar().showMessage('選択した部品をコピーしました（子部品を含みます）。')
        return True

    def cut_gadget(self):
        if self.copy_gadget(cut=True): self.delete()

    def paste_gadget(self):
        data = QApplication.clipboard().mimeData()
        if not data or not data.hasFormat(GADGET_MIME): return
        try:
            payload = json.loads(bytes(data.data(GADGET_MIME)).decode('utf-8'))
            source = Form.loads(payload['form']);index = payload['root']
            if type(index) is not int or not 0 <= index < len(source.gadgets): raise ValueError('コピー元の部品が不正です。')
            from .clipboard import clone_subtree
            restore = payload.get('cut') is True and payload.get('project') == self.project_key
            draft,selected = clone_subtree(self.form,source,index,restore_names=restore)
        except (ValueError,KeyError,TypeError,UnicodeError) as error:
            self.statusBar().showMessage(f'貼り付けできません: {error}');return
        self.checkpoint();self.form = draft
        self.selected = selected
        self.refresh();self.statusBar().showMessage('部品を貼り付けました。')

    def delete(self):
        names=self.selection_names()
        if not names:return
        removed=set(names)
        for name in names:removed.update(self.form.descendants(name))
        self.checkpoint();self.form.gadgets=[g for g in self.form.gadgets if g.name not in removed]
        self.selected=None;self._multi_selection.clear();self.refresh()

    def undo(self):
        if not self.history: return
        self.future.append(copy.deepcopy(self.form)); self.form = self.history.pop(); self.variable_error = False; self.selected = None; self._multi_selection.clear(); self.dirty = True; self.refresh()

    def redo(self):
        if not self.future: return
        self.history.append(copy.deepcopy(self.form)); self.form = self.future.pop(); self.variable_error = False; self.selected = None; self._multi_selection.clear(); self.dirty = True; self.refresh()

    def confirm_discard(self):
        if not self.dirty: return True
        result = QMessageBox.question(self, '未保存の変更', '変更を保存しますか？', QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if result == QMessageBox.Save: return self.save()
        return result == QMessageBox.Discard

    def new(self):
        if not self.confirm_discard(): return
        self.clear_backup()
        self.project_key = uuid.uuid4().hex
        self.variable_error = False; self.form = Form(); self.path = None; self.selected = None; self._multi_selection.clear(); self.active_pages.clear(); self.history.clear(); self.future.clear(); self.dirty = False; self.refresh()
        self.set_workflow('form')

    def open(self):
        if not self.confirm_discard(): return
        name, _ = QFileDialog.getOpenFileName(self, '設計を開く', '', '設計・MAC (*.json *.mac);;設計 (*.json);;MAC (*.mac)')
        if not name: return
        self.open_design(Path(name),confirmed=True)

    def open_mac(self):
        if not self.confirm_discard():return
        name,_=QFileDialog.getOpenFileName(self,'MACを読み込む','','MAC (*.mac);;すべて (*)')
        if name:self.open_design(Path(name),confirmed=True)

    def open_partial_mac(self):
        if not self.confirm_discard():return
        name,_=QFileDialog.getOpenFileName(self,'MACを部分的に読み込む','','MAC (*.mac);;すべて (*)')
        if name:self.open_design(Path(name),confirmed=True,partial=True)

    def edit_imported_code(self):
        from .import_editor import ImportCodeDialog
        dialog=ImportCodeDialog(self,self.form)
        if dialog.exec()==QDialog.Accepted:
            self.checkpoint();self.form=dialog.result_form;self.refresh()
        dialog.deleteLater()

    def manage_methods(self):
        from .method_manager import MethodManagerDialog
        dialog=MethodManagerDialog(self,self.form)
        if dialog.exec()==QDialog.Accepted:
            self.checkpoint();self.form=dialog.result_form;self.refresh()
        dialog.deleteLater()

    def open_design(self,path,*,confirmed=False,partial=False):
        if not confirmed and not self.confirm_discard():return False
        imported=Path(path).suffix.lower()=='.mac'
        result=None
        try:
            if imported:
                from .mac_import import read_mac
                result=read_mac(path,partial=partial);form=result.form
                form.pml()
            else:
                text = Path(path).read_text(encoding='utf-8')
                form = Form.loads(text)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, '読込エラー', str(e)); return False
        self.clear_backup()
        self.project_key = uuid.uuid4().hex
        self.variable_error = False; self.form = form; self.path = None if imported else Path(path); self.selected = None; self._multi_selection.clear(); self.active_pages.clear(); self.history.clear(); self.future.clear(); self.dirty = imported; self.refresh()
        self.set_workflow('layout')
        if imported:
            mode='部分取り込み' if form.partial_import_source else '読み込み'
            self.statusBar().showMessage(f'MACを{mode}しました: {len(form.gadgets)}部品 / {result.encoding}。設計JSONとして保存してください。')
            if result.warnings:
                QMessageBox.information(self,'MAC取り込み結果','\n'.join(result.warnings))
        else:
            warning=self.remember_project()
            if warning:self.statusBar().showMessage(warning)
        return True

    def save_as(self):
        return self.save(force_dialog=True)

    def save(self, *, force_dialog=False):
        try:
            if self.variable_error: raise ValueError('変数欄を修正してください。')
            data = self.form.dumps()
        except ValueError as e:
            QMessageBox.warning(self, '保存エラー', str(e)); return False
        path = self.path
        if path is None or force_dialog:
            initial = str(path) if path else str(Path(self.form.source_mac_path).with_suffix('.json')) if self.form.source_mac_path else str(self.settings.app_directory/(self.form.name+'.json'))
            name, _ = QFileDialog.getSaveFileName(self, '名前を付けて保存' if force_dialog else '設計を保存', initial, '設計 (*.json)')
            if not name: return False
            path = Path(name)
            if path.suffix.lower() != '.json':
                path = path.with_suffix('.json')
                if path.exists() and QMessageBox.question(self,'上書き確認',f'{path} は存在します。上書きしますか？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:
                    return False
        try: atomic_write(path, data.encode('utf-8'))
        except OSError as e:
            QMessageBox.warning(self, '保存エラー', str(e)); return False
        self.path = path; self.dirty = False; self.refresh()
        self.clear_backup();warning=self.remember_project()
        self.statusBar().showMessage(f'設計を保存しました: {path}'+(' / '+warning if warning else ''));return True

    def mac_output_path(self,filename):
        selected=Path(filename);path=selected.with_suffix('.mac')
        if path!=selected and path.exists():
            answer=QMessageBox.question(self,'上書き確認',f'{path} は存在します。上書きしますか？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if answer!=QMessageBox.Yes:return None
        return path

    def save_output_folder(self):
        text=self.output_folder.text().strip()
        folder=Path(text).expanduser() if text else self.settings.app_directory
        if not folder.is_absolute():folder=self.settings.app_directory/folder
        try:self.settings.save_output_folder(folder)
        except (OSError,ValueError) as error:
            self.statusBar().showMessage('出力先の設定を保存できません: '+str(error));return False
        self.output_folder.setText(str(self.settings.output_folder))
        self.statusBar().showMessage('出力先フォルダを settings.json に保存しました。');return True

    def choose_output_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'出力先フォルダを選択',self.output_folder.text())
        if folder:self.output_folder.setText(folder);self.save_output_folder()

    def export(self):
        try:
            if self.variable_error: raise ValueError('変数欄を修正してください。')
            data = self.form.pml().replace('\n', '\r\n').encode('cp932')
        except (ValueError, UnicodeError) as e:
            QMessageBox.warning(self, '出力エラー', str(e)); return
        folder=Path(self.output_folder.text().strip() or str(self.settings.app_directory)).expanduser()
        if not folder.is_absolute():folder=self.settings.app_directory/folder
        if not folder.is_dir():
            QMessageBox.warning(self,'出力エラー','出力先には存在するフォルダを指定してください。');return
        name, _ = QFileDialog.getSaveFileName(self, 'MAC テキストを出力', str(folder/(self.form.name+'.mac')), 'マクロ (*.mac)')
        if not name: return
        path=self.mac_output_path(name)
        if path is None:return
        try: atomic_write(path, data)
        except OSError as e: QMessageBox.warning(self, '出力エラー', str(e)); return
        self.statusBar().showMessage(f'MAC テキストを出力しました: {path}')

    def closeEvent(self, event):
        if self.confirm_discard():
            self.clear_backup();self.backup_timer.stop()
            self._closing = True
            self.menu_dialog.close();self.output_dialog.close()
            self.scene.blockSignals(True)
            event.accept()
        else: event.ignore()


def atomic_write(path, data):
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        try: f.write(data)
        except BaseException:
            temporary.unlink(missing_ok=True); raise
    try: os.replace(temporary, path)
    finally: temporary.unlink(missing_ok=True)


def main():
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('E3DFormDesigner.Desktop')
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window(); window.show()
    QTimer.singleShot(0,window.offer_recovery)
    return app.exec()
