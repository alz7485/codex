"""Canvas zoom and pan change the view, never PML coordinates."""
import math
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QPoint
from PySide6.QtGui import QTransform,QPainter
from PySide6.QtWidgets import QGraphicsView


class CanvasView(QGraphicsView):
    zoomChanged = Signal(float)
    MIN_ZOOM, MAX_ZOOM = 10., 800.

    def __init__(self, scene):
        super().__init__(scene)
        self.zoom_percent = 100.
        self._exact_zoom = 100.
        self._pan_enabled = False
        self._pan_start = None
        self._space_pressed = False
        self._view_center = None
        self._center_on_resize = False
        self._content_rect = QRectF(scene.sceneRect())
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)

    @property
    def panning(self):
        return self._pan_start is not None

    def set_content_rect(self, rect):
        self._content_rect = QRectF(rect)
        if self._pan_enabled:self._reserve_pan_space()

    def _reserve_pan_space(self, target=None):
        # Reserve scrolling space on this view only. The scene and items keep
        # their logical bounds; padding expands only when the camera needs it.
        center = self.mapToScene(self.viewport().rect().center())
        target = target if target is not None else center
        scale = self.transform().m11()
        width = max(1, self.viewport().width()/scale)
        height = max(1, self.viewport().height()/scale)
        area = self._content_rect.united(QRectF(target.x()-width, target.y()-height, width*2, height*2))
        area = area.united(QRectF(center.x()-width, center.y()-height, width*2, height*2))
        if self._view_center is None or not self.sceneRect().contains(area):
            self._view_center = center
            area = area.adjusted(-width, -height, width, height)
            area=area.united(self.sceneRect())
            self.setSceneRect(area)
            self.centerOn(center)

    def _center_view(self, point):
        self._view_center = QPointF(point)
        self.centerOn(point)
        # QGraphicsView rounds its scrollbar positions to integer pixels.
        delta = self.mapFromScene(point)-self.viewport().rect().center()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()+delta.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value()+delta.y())

    def center_content(self, point):
        self._pan_enabled = True
        self._center_on_resize = True
        self._reserve_pan_space(point)
        self._center_view(point)

    def cancel_pan(self):
        if not self.panning:return False
        self._center_view(self._pan_start[1])
        self._finish_pan()
        return True

    def _finish_pan(self):
        self._pan_start = None
        if self._space_pressed:self.viewport().setCursor(Qt.OpenHandCursor)
        else:self.viewport().unsetCursor()

    def mousePressEvent(self, event):
        if self.panning:event.accept();return
        if event.button()==Qt.MiddleButton or (event.button()==Qt.LeftButton and self._space_pressed):
            if self.scene().mouseGrabberItem() is None:
                self._pan_enabled = True
                self._center_on_resize = False
                self._reserve_pan_space()
                self._pan_start = (event.position().toPoint(), self.mapToScene(self.viewport().rect().center()), event.button())
                self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept();return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.panning:
            position, center, _ = self._pan_start
            delta = event.position().toPoint()-position
            scale = self.transform().m11()
            target = center - QPointF(delta)/scale
            self._reserve_pan_space(target)
            self._center_view(target)
            event.accept();return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.panning and event.button()==self._pan_start[2]:
            self._finish_pan();event.accept();return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key()==Qt.Key_Space:
            if self.scene().mouseGrabberItem() is None:
                self._space_pressed = True
                self.viewport().setCursor(Qt.ClosedHandCursor if self.panning else Qt.OpenHandCursor)
            event.accept();return
        if self.panning and event.key()==Qt.Key_Escape:
            self.cancel_pan();event.accept();return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key()==Qt.Key_Space:
            if not event.isAutoRepeat():
                self._space_pressed = False
                if not self.panning:self.viewport().unsetCursor()
            event.accept();return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._space_pressed = False
        self._finish_pan()
        super().focusOutEvent(event)

    def resizeEvent(self, event):
        center = self._view_center
        origin = self.mapToScene(QPoint(0,0))
        super().resizeEvent(event)
        if self._pan_enabled:
            if not self._center_on_resize:
                center=origin+QPointF(self.viewport().rect().center())/self.transform().m11()
            self._reserve_pan_space(center)
            if center is not None:self._center_view(center)

    def set_zoom(self, percent, anchor=None):
        if not math.isfinite(percent):return
        # Keep fractional wheel input until display rounding; splitting a notch
        # into many events must not change its total zoom or introduce drift.
        self._exact_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, percent))
        percent = round(self._exact_zoom, 1)
        if percent == self.zoom_percent:return
        self._center_on_resize = False
        anchor = anchor if anchor is not None else self.viewport().rect().center()
        before = self.mapToScene(anchor)
        self.zoom_percent = percent
        self.setTransform(QTransform.fromScale(percent/100., percent/100.))
        if self._pan_enabled:self._reserve_pan_space(before)
        after = self.mapToScene(anchor)
        self._center_view(self.mapToScene(self.viewport().rect().center()) + before - after)
        self.zoomChanged.emit(percent)

    def wheelEvent(self, event):
        if self.panning:event.accept();return
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()/120. if event.angleDelta().y() else event.pixelDelta().y()/40.
            self.set_zoom(self._exact_zoom + delta*10., event.position().toPoint())
            event.accept()
            return
        super().wheelEvent(event)
