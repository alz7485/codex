import copy
import sys
from shiboken6 import isValid
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QKeySequence, QPainterPath
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QLineEdit, QDoubleSpinBox, QComboBox, QPushButton,
    QPlainTextEdit, QLabel, QSplitter, QGraphicsScene, QGraphicsView,
    QGraphicsObject, QGraphicsItem, QListWidget, QFileDialog, QMessageBox,
    QScrollArea, QCheckBox)
from .model import Form, Gadget, KINDS

LABELS = {'button': 'ボタン', 'paragraph': 'ラベル', 'text': 'テキスト入力',
          'toggle': 'チェックボックス', 'option': 'ドロップダウン', 'list': 'リスト', 'line': '線 (LINE)', 'frame': '枠 (FRAME)'}
# Independent character-width and line-height scales; approximate preview only.
SX, SY = 10, 26


def preview_geometry(form, gadget):
    try: return form.geometry(gadget)
    except ValueError: return gadget.x, gadget.y, gadget.width, gadget.height


def preview_offset(form, gadget):
    try: return form.offset(gadget)
    except ValueError: return 0, 0


class Item(QGraphicsObject):
    moved = Signal()
    pageChosen = Signal(str)

    def __init__(self, gadget, form):
        super().__init__()
        self.gadget, self.form = gadget, form
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        if gadget.layout_mode == 'ABSOLUTE': self.setFlag(QGraphicsItem.ItemIsMovable)
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
        path.addRect(rect); return path

    def mousePressEvent(self, event):
        g = self.gadget
        if g.kind == 'frame' and g.frame_style == 'TABSET' and 0 <= event.pos().y() < 26:
            pages = self.form.children(g.name)
            if pages:
                index = min(len(pages)-1, max(0,int(event.pos().x() / (self._width * SX / len(pages)))))
                self.pageChosen.emit(pages[index].name); event.accept(); return
        super().mousePressEvent(event)

    def paint(self, painter, option, widget=None):
        r, g = self.boundingRect(), self.gadget
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#7f91a5'), 1))
        painter.setBrush(QColor('#eff3f8' if g.kind == 'button' else '#ffffff'))
        if g.kind == 'frame':
            parent = self.form.parent_gadget(g)
            painter.setBrush(Qt.NoBrush)
            if not (parent and parent.frame_style == 'TABSET'):
                painter.drawRect(r.adjusted(1, 8, -1, -1))
            if g.frame_style == 'TABSET':
                pages = self.form.children(g.name)
                for i, page in enumerate(pages):
                    tab = QRectF(i*r.width()/len(pages), 0, r.width()/len(pages), 25)
                    painter.setBrush(QColor('#d8eaff' if page.name.lower() == getattr(self, 'active_page', '') else '#edf1f5'))
                    painter.drawRect(tab)
                    painter.drawText(tab.adjusted(6, 0, -6, 0), Qt.AlignVCenter, page.label)
        elif g.kind == 'line':
            if g.orientation == 'HORIZ':
                painter.drawLine(r.left(), r.center().y(), r.right(), r.center().y())
            else:
                painter.drawLine(r.center().x(), r.top(), r.center().x(), r.bottom())
        else:
            painter.drawRoundedRect(r.adjusted(1, 1, -1, -1), 3, 3)
        painter.setPen(QColor('#182b40'))
        text = g.label
        if g.kind == 'frame':
            parent = self.form.parent_gadget(g)
            if self.form.children(g.name) and g.frame_style == 'TABSET': text = ''
            if parent and parent.frame_style == 'TABSET': text = ''
        if g.kind == 'paragraph' and g.background: text += f' [BG {g.background}]'
        if g.kind == 'text': text += '  [' + g.initial + ']'
        if g.kind == 'toggle': text = '☐ ' + text
        if g.kind == 'option': text += '  ▾'
        if g.kind == 'list': text = '\n'.join(g.items) or g.label
        painter.drawText(r.adjusted(7, 2, -7, -2), Qt.AlignLeft | (Qt.AlignTop if g.kind == 'frame' else Qt.AlignVCenter), text)
        if self.isSelected():
            painter.setPen(QPen(QColor('#2277cc'), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r.adjusted(1, 1, -1, -1))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            g = self.gadget
            ox, oy = preview_offset(self.form, g); parent = self.form.parent_gadget(g)
            width, height = (preview_geometry(self.form,parent)[2], parent.height) if parent else (self.form.width, self.form.height)
            value.setX(ox * SX + max(0, min(round((value.x()/SX - ox)*2)/2, width-self._width))*SX)
            value.setY(oy * SY + max(0, min(round((value.y()/SY - oy)*2)/2, height-g.height))*SY)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.gadget.layout_mode != 'ABSOLUTE': return
        ox, oy = preview_offset(self.form, self.gadget)
        self.gadget.x = round(self.pos().x() / SX - ox, 2)
        self.gadget.y = round(self.pos().y() / SY - oy, 2)
        self.moved.emit()


class Scene(QGraphicsScene):
    def drawBackground(self, painter, rect):
        painter.fillRect(self.sceneRect(), QColor('#f8fafc'))
        painter.setPen(QPen(QColor('#d9e2ec'), 1))
        for x in range(0, int(self.width()), SX):
            for y in range(0, int(self.height()), SY): painter.drawPoint(x, y)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.form, self.path, self.selected = Form(), None, None
        self.history, self.future = [], []
        self.active_pages = {}
        self.dirty, self.loading = False, False
        self.variable_error = False
        self._closing = False
        self.resize(1380, 880)
        self.setWindowTitle('E3D PML Form Designer — E3D 4.0 想定')
        toolbar = self.addToolBar('ファイル')
        for label, fn, shortcut in [('新規', self.new, 'Ctrl+N'), ('開く', self.open, 'Ctrl+O'),
                ('保存', self.save, 'Ctrl+S'), ('PML 出力', self.export, 'Ctrl+E'),
                ('元に戻す', self.undo, 'Ctrl+Z'), ('やり直す', self.redo, 'Ctrl+Shift+Z'),
                ('複製', self.duplicate, 'Ctrl+D'), ('削除', self.delete, None)]:
            a = QAction(label, self)
            if shortcut: a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(fn)
            toolbar.addAction(a)
        root = QWidget(); outer = QVBoxLayout(root)
        outer.addWidget(QLabel('PML フォーム設計  •  プレビューは概略表示 / E3D 4.0 実機互換性は未検証'))
        columns = QSplitter()
        left = QWidget(); ll = QVBoxLayout(left)
        ll.addWidget(QLabel('部品を追加'))
        for kind in KINDS:
            b = QPushButton('+ ' + LABELS[kind]); b.clicked.connect(lambda checked=False, k=kind: self.add(k)); ll.addWidget(b)
        ll.addWidget(QLabel('部品一覧'))
        self.objects = QListWidget(); self.objects.currentRowChanged.connect(self.choose_row); ll.addWidget(self.objects)
        left.setMinimumWidth(180); columns.addWidget(left)
        middle = QSplitter(Qt.Vertical)
        self.scene = Scene(self); self.scene.selectionChanged.connect(self.selection_changed)
        self.view = QGraphicsView(self.scene)
        self.view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        middle.addWidget(self.view)
        self.code = QPlainTextEdit(); self.code.setReadOnly(True)
        self.code.setStyleSheet('font-family: monospace; font-size: 12px;')
        middle.addWidget(self.code); middle.setSizes([550, 230]); columns.addWidget(middle)
        right = QWidget(); rl = QVBoxLayout(right)
        self.form_fields = QFormLayout()
        self.fname = QLineEdit(); self.ftitle = QLineEdit()
        self.fw, self.fh = self.number(1, 300), self.number(1, 300)
        for label, w in [('フォーム名', self.fname), ('タイトル', self.ftitle), ('幅 (PML)', self.fw), ('高さ (PML)', self.fh)]:
            self.form_fields.addRow(label, w); self.connect_field(w, self.update_form)
        self.docking = QComboBox(); self.docking.addItems(['右ドッキング', '通常ダイアログ'])
        self.docking.currentIndexChanged.connect(self.update_form)
        self.form_fields.addRow('表示形式', self.docking)
        rl.addLayout(self.form_fields)
        rl.addWidget(QLabel('グローバル変数 (変数名=初期値、1行1変数)'))
        self.variables = QPlainTextEdit(); self.variables.setMaximumHeight(90)
        self.variables.setPlaceholderText('projectName=Project A\nmode=Default')
        self.variables.textChanged.connect(self.update_variables)
        rl.addWidget(self.variables)
        self.show_form = QCheckBox('末尾で SHOW !!フォーム名 を実行')
        self.show_form.toggled.connect(self.update_form); rl.addWidget(self.show_form)
        self.after_show = QPlainTextEdit(); self.after_show.setMaximumHeight(120)
        self.after_show.setPlaceholderText('SHOW の後に出力する任意の PML プログラム')
        self.after_show.textChanged.connect(self.update_after_show)
        rl.addWidget(QLabel('表示後のプログラム')); rl.addWidget(self.after_show)
        self.default_body = QPlainTextEdit(); self.default_body.setMaximumHeight(120)
        self.default_body.setPlaceholderText('DEFINE METHOD .DEFAULT() の中に出力する PML')
        self.default_body.textChanged.connect(self.update_default_body)
        rl.addWidget(QLabel('DEFAULT メソッドの処理')); rl.addWidget(self.default_body)
        rl.addWidget(QLabel('選択部品のプロパティ'))
        self.props = QWidget(); self.prop_layout = QFormLayout(self.props)
        self.fields = {}
        for key, label in [('name', '部品名'), ('label', '表示文字'), ('x', 'X'), ('y', 'Y'), ('width', '幅'), ('height', '高さ / 行数'), ('value_type', '入力型'), ('initial', '初期値'), ('callback', 'メソッド名'), ('command', 'CALL コマンド'), ('background', 'BACKGROUND (空欄＝背景色)'), ('orientation', 'LINE の向き'), ('frame_style', 'FRAME 形式'), ('parent', '親コンテナ'), ('layout_mode', '配置方式'), ('path', '配置方向'), ('halign', '水平整列'), ('valign', '垂直整列'), ('hgap', '横間隔'), ('vgap', '縦間隔'), ('xref', 'X 基準部品'), ('xedge', 'X 基準辺'), ('xanchor', '自部品の X 辺'), ('xoffset', 'X オフセット'), ('yref', 'Y 基準部品'), ('yedge', 'Y 基準辺'), ('yoffset', 'Y オフセット'), ('width_ref', '幅を揃える部品')]:
            if key in ('x','y','width','height','hgap','vgap','xoffset','yoffset'):
                w = self.number(-300 if key in ('xoffset','yoffset') else 0 if key in ('x','y','hgap','vgap') else 1, 300)
            elif key in ('parent','xref','yref','width_ref'):
                w = QComboBox(); w.addItem('(フォーム直下)', '')
            elif key in ('value_type','orientation','frame_style','layout_mode','path','halign','valign','xedge','yedge','xanchor'):
                w = QComboBox()
                w.addItems({'value_type': ['STRING', 'REAL'], 'orientation': ['HORIZ', 'VERT'], 'frame_style': ['FRAME','TABSET'], 'layout_mode': ['ABSOLUTE','AUTO','RELATIVE'], 'path': ['DOWN','RIGHT','UP','LEFT'], 'halign': ['LEFT','CENTRE','RIGHT'], 'valign': ['TOP','CENTRE','BOTTOM'], 'xedge': ['XMIN','XMAX'], 'yedge': ['YMIN','YMAX'], 'xanchor': ['LEFT','RIGHT']}[key])
            else: w = QLineEdit()
            self.fields[key] = w; self.prop_layout.addRow(label, w); self.connect_field(w, self.update_gadget)
        self.choices = QPlainTextEdit(); self.choices.setMaximumHeight(100)
        self.prop_layout.addRow('選択肢 (1行1項目)', self.choices)
        self.choices.textChanged.connect(self.update_gadget)
        self.choice_commands = QPlainTextEdit(); self.choice_commands.setMaximumHeight(100)
        self.choice_commands.setPlaceholderText('選択肢と同じ行順で実行コマンドを指定')
        self.prop_layout.addRow('OPTION コマンド (1行1項目)', self.choice_commands)
        self.choice_commands.textChanged.connect(self.update_gadget)
        self.body = QPlainTextEdit(); self.body.setPlaceholderText('メソッド内の PML コード。自動実行はしません。')
        self.body.setMinimumHeight(110); self.prop_layout.addRow('処理コード', self.body)
        self.body.textChanged.connect(self.update_gadget)
        rl.addWidget(self.props)
        self.encoding = QComboBox(); self.encoding.addItems(['utf-8', 'cp932'])
        rl.addWidget(QLabel('PML 出力文字コード')); rl.addWidget(self.encoding)
        rl.addWidget(QLabel('text / toggle / option の高さは E3D 側で決まります。\n選択肢は option / list 用です。\n処理コードの構文は E3D で確認してください。'))
        rl.addStretch()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(right); scroll.setMinimumWidth(320)
        columns.addWidget(scroll); columns.setSizes([180, 820, 360])
        outer.addWidget(columns, 1); self.setCentralWidget(root)
        self.refresh()

    @staticmethod
    def number(low, high):
        w = QDoubleSpinBox(); w.setRange(low, high); w.setDecimals(2); w.setSingleStep(.5); return w

    @staticmethod
    def connect_field(w, fn):
        if isinstance(w, QLineEdit): w.textEdited.connect(fn)
        elif isinstance(w, QComboBox): w.currentTextChanged.connect(fn)
        else: w.valueChanged.connect(fn)

    def checkpoint(self):
        self.history.append(copy.deepcopy(self.form)); self.history = self.history[-100:]; self.future.clear()
        self.dirty = True

    def update_variables(self):
        if self.loading: return
        self.dirty = True
        values = {}
        for line in self.variables.toPlainText().splitlines():
            if not line.strip(): continue
            name, sep, value = line.partition('=')
            if not sep or not name.strip() or name.strip().lower() in {n.lower() for n in values}:
                self.code.setPlainText('-- 変数は重複のない 名前=初期値 の形式で指定してください。')
                self.variable_error = True
                return
            values[name.strip()] = value
        self.variable_error = False
        self.checkpoint(); self.form.variables = values; self.refresh()

    def update_default_body(self):
        if self.loading: return
        self.checkpoint(); self.form.default_body = self.default_body.toPlainText(); self.refresh()

    def update_after_show(self):
        if self.loading: return
        self.checkpoint(); self.form.after_show_code = self.after_show.toPlainText(); self.refresh()

    def update_form(self):
        if self.loading: return
        self.checkpoint()
        self.form.show_form = self.show_form.isChecked()
        self.form.dock_right = self.docking.currentIndex() == 0
        self.form.name, self.form.title = self.fname.text(), self.ftitle.text()
        self.form.width, self.form.height = self.fw.value(), self.fh.value()
        self.refresh()

    def populate_parents(self, gadget):
        combo = self.fields['parent']; combo.clear(); combo.addItem('(フォーム直下)', '')
        excluded = {gadget.name.lower(), *(name.lower() for name in self.form.descendants(gadget.name))}
        for g in self.form.gadgets:
            if g.kind == 'frame' and g.name.lower() not in excluded:
                if g.frame_style == 'TABSET' and (gadget.kind != 'frame' or gadget.frame_style != 'FRAME'): continue
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

    def enable_layout_fields(self, gadget):
        mode = gadget.layout_mode
        for key in ('x','y'): self.fields[key].setEnabled(mode == 'ABSOLUTE')
        for key in ('path','halign','valign','hgap','vgap'): self.fields[key].setEnabled(mode == 'AUTO')
        for key in ('xref','xedge','xanchor','xoffset','yref','yedge','yoffset'): self.fields[key].setEnabled(mode == 'RELATIVE')
        self.fields['width_ref'].setEnabled(gadget.kind not in ('toggle','option'))
        self.fields['width'].setEnabled(not gadget.width_ref)

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

    def choose_page(self, name):
        from PySide6.QtCore import QTimer
        index = next((i for i,g in enumerate(self.form.gadgets) if g.name == name), None)
        if index is not None: QTimer.singleShot(0, lambda: self.choose_row(index))

    def update_gadget(self):
        if self.loading or self.selected is None: return
        self.checkpoint(); g = self.form.gadgets[self.selected]
        old_name = g.name
        for key, w in self.fields.items():
            value = w.currentData() if key in ('parent','xref','yref','width_ref') else w.value() if isinstance(w, QDoubleSpinBox) else w.currentText() if isinstance(w, QComboBox) else w.text()
            setattr(g, key, value)
        if old_name != g.name:
            for child in self.form.gadgets:
                for key in ('parent','xref','yref','width_ref'):
                    if getattr(child,key).lower() == old_name.lower(): setattr(child,key,g.name)
        if g.layout_mode == 'RELATIVE':
            siblings = [other for other in self.form.children(g.parent) if other is not g]
            if siblings:
                if not g.xref: g.xref = siblings[0].name
                if not g.yref: g.yref = siblings[0].name
        choices = self.choices.toPlainText()
        g.items = choices.split('\n') if choices else []; g.body = self.body.toPlainText()
        if g.kind == 'option':
            commands = self.choice_commands.toPlainText().split('\n')
            g.item_commands = (commands if self.choice_commands.toPlainText() else [])
            if len(g.item_commands) < len(g.items): g.item_commands += [''] * (len(g.items) - len(g.item_commands))
        self.refresh(rebuild=False)

    def refresh(self, rebuild=True):
        if self._closing or not isValid(self) or not isValid(self.scene): return
        self.loading = True
        variable_text = '\n'.join(f'{k}={v}' for k,v in self.form.variables.items())
        if not self.variable_error and self.variables.toPlainText() != variable_text:
            self.variables.setPlainText(variable_text)
        if self.default_body.toPlainText() != self.form.default_body: self.default_body.setPlainText(self.form.default_body)
        self.show_form.setChecked(self.form.show_form)
        if self.after_show.toPlainText() != self.form.after_show_code: self.after_show.setPlainText(self.form.after_show_code)
        self.fname.setText(self.form.name); self.ftitle.setText(self.form.title)
        self.docking.setCurrentIndex(0 if self.form.dock_right else 1)
        self.fw.setValue(self.form.width); self.fh.setValue(self.form.height)
        self.objects.clear()
        for g in self.form.gadgets: self.objects.addItem(f'{LABELS[g.kind]}  .{g.name}' + (f' → {g.parent}' if g.parent else ''))
        self.scene.blockSignals(True); self.scene.clear()
        self.scene.setSceneRect(0, 0, self.form.width * SX, self.form.height * SY)
        for index, g in enumerate(self.form.gadgets):
            item = Item(g, self.form); item.setData(0, index)
            item.pageChosen.connect(self.choose_page)
            item.moved.connect(self.move_committed); self.scene.addItem(item)
            item.setSelected(index == self.selected)
        self.scene.blockSignals(False)
        self.apply_page_visibility()
        if self.selected is not None and self.selected < len(self.form.gadgets):
            self.objects.setCurrentRow(self.selected); g = self.form.gadgets[self.selected]
            self.populate_parents(g)
            self.enable_layout_fields(g)
            for key, w in self.fields.items():
                if key in ('parent','xref','yref','width_ref'): continue
                value = getattr(g, key)
                if isinstance(w, QDoubleSpinBox): w.setValue(value)
                elif isinstance(w, QComboBox): w.setCurrentText(value)
                else: w.setText(value)
            # Do not reset typing cursor in multi-line editors on every keystroke.
            if rebuild and self.choices.toPlainText() != '\n'.join(g.items): self.choices.setPlainText('\n'.join(g.items))
            if rebuild and self.choice_commands.toPlainText() != '\n'.join(g.item_commands): self.choice_commands.setPlainText('\n'.join(g.item_commands))
            self.choice_commands.setEnabled(g.kind == 'option')
            if self.body.toPlainText() != g.body: self.body.setPlainText(g.body)
            self.props.setEnabled(True)
            self.fields['value_type'].setEnabled(g.kind == 'text'); self.fields['initial'].setEnabled(g.kind == 'text')
            self.choices.setEnabled(g.kind in ('option', 'list'))
            self.fields['label'].setEnabled(g.kind != 'line'); self.fields['orientation'].setEnabled(g.kind == 'line'); self.fields['frame_style'].setEnabled(g.kind == 'frame'); self.fields['callback'].setEnabled(g.kind not in ('paragraph', 'line', 'frame', 'option')); self.fields['command'].setEnabled(g.kind in ('toggle', 'text', 'button')); self.fields['background'].setEnabled(g.kind in ('paragraph', 'button')); self.body.setEnabled(bool(g.callback))
        else: self.selected = None; self.props.setEnabled(False)
        self.loading = False
        try:
            if self.variable_error: raise ValueError('変数欄の 名前=初期値 の形式を修正してください。')
            self.code.setPlainText(self.form.pml()); self.statusBar().showMessage('設計を編集できます。PML の実行は E3D 側で行ってください。')
        except ValueError as e:
            self.code.setPlainText('-- 出力できません: ' + str(e)); self.statusBar().showMessage(str(e))
        self.setWindowTitle(('● ' if self.dirty else '') + 'E3D PML Form Designer — ' + (self.path.name if self.path else '新規設計'))

    def choose_row(self, index):
        if not self.loading:
            self.selected = index if index >= 0 else None; self.refresh()

    def selection_changed(self):
        if self._closing or not isValid(self) or not isValid(self.scene) or self.loading: return
        items = self.scene.selectedItems()
        self.selected = items[0].data(0) if items else None
        # Defer rebuilding the scene until mouse event delivery completes.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.sync_selection)

    def sync_selection(self):
        if self._closing or not isValid(self) or not isValid(self.scene): return
        # Property loading only: keep the grabbed graphics item alive while dragging.
        self.loading = True
        if self.selected is not None:
            self.objects.setCurrentRow(self.selected)
            g = self.form.gadgets[self.selected]
            self.populate_parents(g)
            self.enable_layout_fields(g)
            for key, w in self.fields.items():
                if key in ('parent','xref','yref','width_ref'): continue
                v = getattr(g, key)
                if isinstance(w, QDoubleSpinBox): w.setValue(v)
                elif isinstance(w, QComboBox): w.setCurrentText(v)
                else: w.setText(v)
            self.choices.setPlainText('\n'.join(g.items)); self.body.setPlainText(g.body)
            self.choice_commands.setPlainText('\n'.join(g.item_commands)); self.choice_commands.setEnabled(g.kind == 'option')
            self.fields['value_type'].setEnabled(g.kind == 'text'); self.fields['initial'].setEnabled(g.kind == 'text')
            self.choices.setEnabled(g.kind in ('option', 'list'))
            self.fields['label'].setEnabled(g.kind != 'line'); self.fields['orientation'].setEnabled(g.kind == 'line'); self.fields['frame_style'].setEnabled(g.kind == 'frame'); self.fields['callback'].setEnabled(g.kind not in ('paragraph', 'line', 'frame', 'option')); self.fields['command'].setEnabled(g.kind in ('toggle', 'text', 'button')); self.fields['background'].setEnabled(g.kind in ('paragraph', 'button')); self.body.setEnabled(bool(g.callback))
        self.apply_page_visibility()
        self.props.setEnabled(self.selected is not None); self.loading = False

    def move_committed(self):
        # Items mutate coordinates only on release. Capture previous UI values for undo.
        old = copy.deepcopy(self.form)
        if self.selected is not None:
            g = old.gadgets[self.selected]
            g.x, g.y = self.fields['x'].value(), self.fields['y'].value()
        self.history.append(old); self.future.clear(); self.dirty = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.refresh)

    def add(self, kind):
        container = self.form.gadgets[self.selected] if self.selected is not None else None
        if container and container.kind != 'frame': container = self.form.parent_gadget(container)
        if container and container.frame_style == 'TABSET' and kind != 'frame':
            self.statusBar().showMessage('TABSET 内に FRAME を追加し、その FRAME 内に部品を作成してください。'); return
        self.checkpoint()
        name = self.unique_name(kind)
        width_limit, height_limit = (container.width, container.height) if container else (self.form.width, self.form.height)
        height = min(5 if kind in ('list', 'frame') else 1, height_limit)
        g = Gadget(kind=kind, name=name, label={'button':'Run','paragraph':'Message','text':'Name','toggle':'Enabled','option':'Mode','list':'Results','line':'','frame':'Group'}[kind],
                   width=min(18, width_limit), height=height,
                   x=0, y=0 if container else min(len(self.form.gadgets) * 1.5, height_limit-height),
                   parent=container.name if container else '')
        if kind in ('option', 'list'): g.items = ['Item A', 'Item B']
        self.form.gadgets.append(g); self.selected = len(self.form.gadgets) - 1; self.refresh()

    def unique_name(self, base):
        used = {g.name.lower() for g in self.form.gadgets}; i = 1
        while (base + str(i)).lower() in used: i += 1
        return base + str(i)

    def duplicate(self):
        if self.selected is None: return
        self.checkpoint(); original = self.form.gadgets[self.selected]
        subtree = {original.name.lower(), *(n.lower() for n in self.form.descendants(original.name))}
        copies = [copy.deepcopy(g) for g in self.form.gadgets if g.name.lower() in subtree]
        mapping = {}
        for g in copies:
            old = g.name; g.name = self.unique_name(g.kind); mapping[old.lower()] = g.name
            self.form.gadgets.append(g)
        for g in copies:
            for key in ('parent','xref','yref','width_ref'):
                if getattr(g,key).lower() in mapping: setattr(g,key,mapping[getattr(g,key).lower()])
        self.selected = next(i for i,g in enumerate(self.form.gadgets) if g.name == mapping[original.name.lower()])
        self.refresh()

    def delete(self):
        if self.selected is None: return
        self.checkpoint(); g = self.form.gadgets[self.selected]
        removed = {g.name.lower(), *(n.lower() for n in self.form.descendants(g.name))}
        self.form.gadgets = [g for g in self.form.gadgets if g.name.lower() not in removed]
        self.selected = None; self.refresh()

    def undo(self):
        if not self.history: return
        self.future.append(copy.deepcopy(self.form)); self.form = self.history.pop(); self.variable_error = False; self.selected = None; self.dirty = True; self.refresh()

    def redo(self):
        if not self.future: return
        self.history.append(copy.deepcopy(self.form)); self.form = self.future.pop(); self.variable_error = False; self.selected = None; self.dirty = True; self.refresh()

    def confirm_discard(self):
        if not self.dirty: return True
        result = QMessageBox.question(self, '未保存の変更', '変更を保存しますか？', QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if result == QMessageBox.Save: return self.save()
        return result == QMessageBox.Discard

    def new(self):
        if not self.confirm_discard(): return
        self.variable_error = False; self.form = Form(); self.path = None; self.selected = None; self.history.clear(); self.future.clear(); self.dirty = False; self.refresh()

    def open(self):
        if not self.confirm_discard(): return
        name, _ = QFileDialog.getOpenFileName(self, '設計を開く', '', '設計 (*.json)')
        if not name: return
        try:
            text = Path(name).read_text(encoding='utf-8')
            form = Form.loads(text)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, '読込エラー', str(e)); return
        self.variable_error = False; self.form = form; self.path = Path(name); self.selected = None; self.history.clear(); self.future.clear(); self.dirty = False; self.refresh()

    def save(self):
        try:
            if self.variable_error: raise ValueError('変数欄を修正してください。')
            data = self.form.dumps()
        except ValueError as e:
            QMessageBox.warning(self, '保存エラー', str(e)); return False
        path = self.path
        if path is None:
            name, _ = QFileDialog.getSaveFileName(self, '設計を保存', self.form.name + '.json', '設計 (*.json)')
            if not name: return False
            path = Path(name)
        try: atomic_write(path, data.encode('utf-8'))
        except OSError as e:
            QMessageBox.warning(self, '保存エラー', str(e)); return False
        self.path = path; self.dirty = False; self.refresh(); return True

    def export(self):
        try:
            if self.variable_error: raise ValueError('変数欄を修正してください。')
            data = self.form.pml().replace('\n', '\r\n').encode(self.encoding.currentText())
        except (ValueError, UnicodeError) as e:
            QMessageBox.warning(self, '出力エラー', str(e)); return
        name, _ = QFileDialog.getSaveFileName(self, 'PML を出力', self.form.name.lower() + '.pmlfrm', 'PML form (*.pmlfrm)')
        if not name: return
        try: atomic_write(Path(name), data)
        except OSError as e: QMessageBox.warning(self, '出力エラー', str(e)); return
        self.statusBar().showMessage('PML 出力完了。E3D 4.0 で読み込みと動作を確認してください。')

    def closeEvent(self, event):
        if self.confirm_discard():
            self._closing = True
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
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window(); window.show()
    return app.exec()
