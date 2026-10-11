"""Consistent blue outline icons for editor actions and gadget variants."""
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QPixmap,QPainter,QPen,QColor,QIcon,QPolygonF


def palette_icon(kind):
    pm=QPixmap(56,56);pm.setDevicePixelRatio(2);pm.fill(Qt.transparent);p=QPainter(pm);p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor('#3566a8'),1.8));p.setBrush(Qt.NoBrush)
    if kind in ('line_vert','slider_vert'):
        p.translate(28,0);p.rotate(90)
    kind={'line_horiz':'line','line_vert':'line','slider_horiz':'slider','slider_vert':'slider','combo':'option'}.get(kind,kind)
    if kind=='new':
        p.drawPolyline(QPolygonF([QPointF(18,3),QPointF(5,3),QPointF(5,25),QPointF(23,25),QPointF(23,8),QPointF(18,3),QPointF(18,8),QPointF(23,8)]))
        p.drawLine(10,16,18,16);p.drawLine(14,12,14,20)
    elif kind=='open':
        p.drawPolyline(QPolygonF([QPointF(3,21),QPointF(3,6),QPointF(11,6),QPointF(14,9),QPointF(24,9),QPointF(24,12)]))
        p.drawPolygon(QPolygonF([QPointF(3,23),QPointF(7,12),QPointF(26,12),QPointF(22,23)]))
    elif kind=='save':
        p.drawPolygon(QPolygonF([QPointF(4,3),QPointF(21,3),QPointF(25,7),QPointF(25,25),QPointF(4,25)]))
        p.drawRect(QRectF(9,3,10,8));p.drawRect(QRectF(9,17,11,8));p.drawLine(16,5,16,9)
    elif kind=='export':
        p.drawPolyline(QPolygonF([QPointF(12,4),QPointF(5,4),QPointF(5,24),QPointF(22,24),QPointF(22,18)]))
        p.drawLine(12,14,24,4);p.drawPolyline(QPolygonF([QPointF(17,4),QPointF(24,4),QPointF(24,11)]))
    elif kind in ('undo','redo'):
        if kind=='redo':p.translate(28,0);p.scale(-1,1)
        p.drawPolyline(QPolygonF([QPointF(10,5),QPointF(4,11),QPointF(10,17)]))
        p.drawLine(4,11,17,11);p.drawArc(QRectF(12,11,12,12),-90*16,180*16)
        p.drawLine(12,23,18,23)
    elif kind=='code':
        p.drawPolyline(QPolygonF([QPointF(9,7),QPointF(3,14),QPointF(9,21)]))
        p.drawPolyline(QPolygonF([QPointF(19,7),QPointF(25,14),QPointF(19,21)]))
        p.drawLine(16,5,12,23)
    elif kind=='preview':
        p.drawRoundedRect(QRectF(3,4,22,16),2,2);p.drawLine(14,20,14,24);p.drawLine(8,24,20,24)
        p.drawPolygon(QPolygonF([QPointF(11,8),QPointF(18,12),QPointF(11,16)]))
    elif kind=='more':
        p.setBrush(QColor('#3566a8'))
        for x in (5,12,19):p.drawEllipse(QRectF(x,12,4,4))
    elif kind=='center':
        p.drawEllipse(QRectF(8,8,12,12))
        p.drawLine(14,3,14,10);p.drawLine(14,18,14,25)
        p.drawLine(3,14,10,14);p.drawLine(18,14,25,14)
    elif kind=='recent':
        p.drawEllipse(QRectF(4,4,20,20));p.drawLine(14,7,14,14);p.drawLine(14,14,19,17)
    elif kind in ('image','image_option'):
        p.drawRect(QRectF(3,4,22,20));p.drawEllipse(QRectF(17,7,4,4))
        p.drawPolyline(QPolygonF([QPointF(5,21),QPointF(11,13),QPointF(16,18),QPointF(20,15),QPointF(24,21)]))
    elif kind=='rtoggle':
        p.drawEllipse(QRectF(4,4,20,20));p.setBrush(QColor('#3566a8'));p.drawEllipse(QRectF(10,10,8,8))
    elif kind=='tabset':
        p.drawRect(QRectF(3,8,22,16));p.drawRect(QRectF(3,4,8,4));p.drawRect(QRectF(11,4,8,4))
    elif kind=='textpane':
        p.drawRect(QRectF(3,4,22,20))
        for y in (9,14,19):p.drawLine(7,y,21,y)
    elif kind=='view':
        p.drawRect(QRectF(3,4,22,20));p.drawRect(QRectF(9,10,10,10));p.drawLine(9,10,14,6);p.drawLine(19,10,23,7);p.drawLine(14,6,23,7)
    elif kind=='button':
        p.drawRoundedRect(QRectF(3,7,22,14),3,3);p.drawLine(9,14,19,14)
    elif kind=='option':
        p.drawRoundedRect(QRectF(3,6,22,16),2,2);p.drawLine(19,6,19,22)
        p.drawPolyline(QPolygonF([QPointF(21,12),QPointF(22.5,15),QPointF(24,12)]))
    elif kind=='frame':
        p.drawRoundedRect(QRectF(3,6,22,18),2,2);p.fillRect(QRectF(7,4,8,4),QColor('white'));p.drawLine(7,6,14,6)
    elif kind=='toggle':
        p.drawRoundedRect(QRectF(4,5,20,19),2,2);p.drawPolyline(QPolygonF([QPointF(8,14),QPointF(12,18),QPointF(21,9)]))
    elif kind=='line':p.drawLine(3,14,25,14)
    elif kind=='menubar':
        p.drawRect(QRectF(3,7,22,14));p.drawLine(3,12,25,12);p.drawLine(10,7,10,12);p.drawLine(17,7,17,12)
    elif kind=='container':
        for x,y in ((4,4),(16,4),(4,16),(16,16)):p.drawRect(QRectF(x,y,8,8))
    elif kind=='text':
        p.drawRect(QRectF(2,7,24,14));p.drawLine(7,11,7,17);p.drawLine(5,11,9,11);p.drawLine(5,17,9,17)
    elif kind=='paragraph':
        p.drawLine(8,5,20,5);p.drawLine(14,5,14,23);p.drawLine(8,23,20,23)
    elif kind=='list':
        p.drawRect(QRectF(3,4,22,20))
        for y in (9,14,19):p.drawLine(3,y,25,y)
        p.drawLine(10,4,10,24)
    elif kind=='slider':
        p.drawLine(3,14,25,14);p.setBrush(QColor('white'));p.drawRoundedRect(QRectF(10,7,7,14),2,2)
    elif kind=='commandline':
        p.drawRoundedRect(QRectF(2,5,24,18),2,2);p.drawPolyline(QPolygonF([QPointF(7,10),QPointF(11,14),QPointF(7,18)]));p.drawLine(15,18,21,18)
    elif kind=='selector':
        p.drawEllipse(QRectF(5,4,18,7));p.drawLine(5,7,5,21);p.drawLine(23,7,23,21);p.drawArc(QRectF(5,17,18,7),180*16,180*16)
    else:
        p.drawRect(QRectF(2,7,24,14))
        for x in (5,12,19):p.drawRect(QRectF(x,10,4,8))
    p.end();return QIcon(pm)
