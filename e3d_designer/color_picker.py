"""Numbered palette picker for the photographed E3D color chart."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QWidget,QGridLayout,QPushButton,QScrollArea
from .colors import PREVIEW_COLORS,foreground_color


class ColorPicker(QDialog):
    def __init__(self,parent,current=''):
        super().__init__(parent);self.value=current
        self.setWindowTitle('BACKGROUND 色番号');self.resize(650,820)
        layout=QVBoxLayout(self)
        note=QLabel('写真の色味表を参考にした近似色です。正確なRGB値ではありません。\n出力には選んだ色番号を使用します。');note.setWordWrap(True);layout.addWidget(note)
        panel=QWidget();grid=QGridLayout(panel);grid.setSpacing(3);grid.setContentsMargins(2,2,2,2)
        self.buttons={}
        for number,color in PREVIEW_COLORS.items():
            button=QPushButton(str(number));button.setMinimumHeight(23)
            border='2px solid #2277cc' if str(number)==current else '1px solid #8a8a8a'
            button.setStyleSheet(f'background-color:{color};color:{foreground_color(color)};border:{border};padding:2px;')
            button.setToolTip(f'BACKGROUND {number}（近似色）')
            button.clicked.connect(lambda checked=False,n=number:self.choose(str(n)))
            grid.addWidget(button,(number-1)//10,(number-1)%10);self.buttons[number]=button
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel);layout.addWidget(scroll)
        footer=QHBoxLayout();clear=QPushButton('背景色を指定しない');clear.clicked.connect(lambda:self.choose(''));footer.addWidget(clear)
        cancel=QPushButton('キャンセル');cancel.clicked.connect(self.reject);footer.addStretch();footer.addWidget(cancel);layout.addLayout(footer)

    def choose(self,value):
        self.value=value;self.accept()
