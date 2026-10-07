"""Canvas zoom changes the view transform, never PML coordinates."""
import math
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTransform,QPainter
from PySide6.QtWidgets import QGraphicsView


class CanvasView(QGraphicsView):
    zoomChanged = Signal(float)
    MIN_ZOOM, MAX_ZOOM = 10., 800.

    def __init__(self, scene):
        super().__init__(scene)
        self.zoom_percent = 100.
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)

    def set_zoom(self, percent, anchor=None):
        if not math.isfinite(percent):return
        percent = round(max(self.MIN_ZOOM, min(self.MAX_ZOOM, percent)), 1)
        if percent == self.zoom_percent:return
        anchor = anchor if anchor is not None else self.viewport().rect().center()
        before = self.mapToScene(anchor)
        self.zoom_percent = percent
        self.setTransform(QTransform.fromScale(percent/100., percent/100.))
        after = self.mapToScene(anchor)
        self.centerOn(self.mapToScene(self.viewport().rect().center()) + before - after)
        self.zoomChanged.emit(percent)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()/120. if event.angleDelta().y() else event.pixelDelta().y()/40.
            self.set_zoom(self.zoom_percent + delta*10., event.position().toPoint())
            event.accept()
            return
        super().wheelEvent(event)
