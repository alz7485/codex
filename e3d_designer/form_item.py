"""Selectable form boundary with resize handles; never moves its contents."""
import copy
from PySide6.QtCore import Qt,QRectF,Signal
from PySide6.QtGui import QColor,QPen,QPainterPath
from PySide6.QtWidgets import QGraphicsObject,QGraphicsItem

class FormItem(QGraphicsObject):
    resizing=Signal()
    resized=Signal(object)
    editRequested=Signal()

    def __init__(self,form,sx,sy):
        super().__init__();self.form=form;self.sx=sx;self.sy=sy
        self._width=form.width;self._height=form.height;self._resize=None;self._cancelled=False
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True);self.setZValue(-100000)
        self.setToolTip('フォーム全体：クリックで設定、ダブルクリックで編集。右・下・右下のハンドルでサイズ変更。')
    def body_rect(self):return QRectF(0,0,self._width*self.sx,self._height*self.sy)
    def boundingRect(self):return self.body_rect().adjusted(-2,-25,2,2)
    def shape(self):
        path=QPainterPath();path.addRect(self.boundingRect());return path
    def handles(self):
        if not self.isSelected():return {}
        r=self.body_rect();size=9
        return {'width':QRectF(r.right()-size,r.center().y()-size/2,size,size),
                'height':QRectF(r.center().x()-size/2,r.bottom()-size,size,size),
                'both':QRectF(r.right()-size,r.bottom()-size,size,size)}
    def handle_at(self,pos):return next((name for name,r in reversed(list(self.handles().items())) if r.contains(pos)),None)
    def paint(self,painter,option,widget=None):
        r=self.body_rect();painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor('#2277cc' if self.isSelected() else '#7f91a5'),2,Qt.DashLine if self.isSelected() else Qt.SolidLine))
        painter.drawRect(r.adjusted(1,1,-1,-1))
        painter.setPen(QColor('#314d6b'))
        painter.drawText(QRectF(3,-24,r.width()-6,22),Qt.AlignLeft|Qt.AlignVCenter,f'▣ {self.form.title}  !!{self.form.name}  {self.form.width:.1f} × {self.form.height:.1f}')
        painter.setPen(QPen(QColor('#2277cc'),1));painter.setBrush(QColor('#ffffff'))
        for handle in self.handles().values():painter.drawRect(handle)
    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:event.ignore();return
        self._cancelled=False
        if event.button()==Qt.LeftButton:
            for item in self.scene().selectedItems():
                if item is not self:item.setSelected(False)
            self.setSelected(True)
            handle=self.handle_at(event.pos())
            if handle:
                self._resize=(handle,event.scenePos(),self.form.width,self.form.height,copy.deepcopy(self.form))
                event.accept();return
        super().mousePressEvent(event)
    def cancel_interaction(self):
        if self._resize is None:return False
        _,_,width,height,_=self._resize;self._resize=None;self._cancelled=True
        self.form.width,self.form.height=width,height
        self.prepareGeometryChange();self._width,self._height=width,height;self.update()
        self.resizing.emit();return True

    def resize_to(self,width,height):
        width=max(1,min(300,round(width,1)));height=max(1,min(300,round(height,1)))
        try:
            for g in self.form.gadgets:
                if g.parent:continue
                x,y,w,h=self.form.geometry(g)
                if x<-.001 or y<-.001 or x+w>width+.001 or y+h>height+.001:return False
        except ValueError:return False
        if (width,height)==(self.form.width,self.form.height):return False
        self.form.width,self.form.height=width,height
        self.prepareGeometryChange();self._width,self._height=width,height;self.update()
        self.resizing.emit();return True
    def mouseMoveEvent(self,event):
        if self._cancelled:event.accept();return
        if self._resize:
            handle,origin,width,height,_=self._resize;delta=event.scenePos()-origin
            self.resize_to(width+delta.x()/self.sx if handle in ('width','both') else width,
                           height+delta.y()/self.sy if handle in ('height','both') else height)
            event.accept();return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton:event.ignore();return
        if self._cancelled:
            self._cancelled=False;event.accept();return
        if self._resize:
            _,_,width,height,old=self._resize;self._resize=None
            if (self.form.width,self.form.height)!=(width,height):self.resized.emit(old)
            event.accept();return
        super().mouseReleaseEvent(event)
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:self.editRequested.emit();event.accept();return
        super().mouseDoubleClickEvent(event)
    def hoverMoveEvent(self,event):
        self.setCursor({'width':Qt.SizeHorCursor,'height':Qt.SizeVerCursor,'both':Qt.SizeFDiagCursor}.get(self.handle_at(event.pos()),Qt.ArrowCursor))
        super().hoverMoveEvent(event)
