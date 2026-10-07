"""Frame hierarchy explorer with atomic model-owned drag operations."""
from PySide6.QtCore import Qt,Signal,QItemSelectionModel
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QTreeWidget,QTreeWidgetItem,QAbstractItemView

class ObjectExplorer(QTreeWidget):
    currentRowChanged=Signal(int)
    selectionRowsChanged=Signal(object)
    moveRequested=Signal(int,str,int)
    def __init__(self):
        super().__init__();self.nodes={};self.root=None;self._drag_index=-1
        self.setExpandsOnDoubleClick(False)
        self.setHeaderHidden(True);self.setIndentation(16);self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setAutoExpandDelay(500)
        self.setDefaultDropAction(Qt.MoveAction);self.setDragDropOverwriteMode(False);self.setDropIndicatorShown(True)
        self.currentItemChanged.connect(lambda item,previous:self.currentRowChanged.emit(item.data(0,Qt.UserRole) if item and item is not self.root else -1))
        self.itemSelectionChanged.connect(lambda:self.selectionRowsChanged.emit([item.data(0,Qt.UserRole) for item in self.selectedItems()]))
    def rebuild(self,form,title,icon_for=None):
        expanded={item.data(0,Qt.UserRole+1):item.isExpanded() for item in self.nodes.values() if item.childCount()}
        root_expanded=self.root.isExpanded() if self.root else True
        self.clear();self.nodes={}
        self.root=QTreeWidgetItem([f'▣ {form.title}  {form.symbol}']);self.root.setData(0,Qt.UserRole,-1)
        self.root.setFlags(self.root.flags() & ~Qt.ItemIsDragEnabled);self.addTopLevelItem(self.root)
        for index,g in enumerate(form.gadgets):
            icon='🗂️' if g.kind=='frame' and g.frame_style=='TABSET' else '📁' if g.kind=='frame' else icon_for(g) if icon_for else '•'
            suffix=' （非表示）' if g.hidden else ' （非表示：幅参照）' if form.is_hidden(g) else ''
            item=QTreeWidgetItem([f'{icon} {g.label or title(g)}  .{g.name}'+suffix]);item.setData(0,Qt.UserRole,index);item.setData(0,Qt.UserRole+1,g.name)
            if g.kind!='frame':item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)
            self.nodes[index]=item
        lookup={g.name.lower():self.nodes[i] for i,g in enumerate(form.gadgets)}
        for index,g in enumerate(form.gadgets):lookup.get(g.parent.lower(),self.root).addChild(self.nodes[index])
        for index,g in enumerate(form.gadgets):self.nodes[index].setExpanded(expanded.get(g.name,True))
        self.root.setExpanded(root_expanded)
    # Model indices remain stable even when folders are collapsed.
    def item(self,index):return self.nodes.get(index)
    def count(self):return len(self.nodes)
    def currentRow(self):return self.currentItem().data(0,Qt.UserRole) if self.currentItem() else -1
    def setCurrentRow(self,index,reveal=True):
        item=self.nodes.get(index,self.root)
        parent=item.parent() if item else None
        while reveal and parent:parent.setExpanded(True);parent=parent.parent()
        collapsed=[]
        if not reveal:
            parent=item.parent() if item else None
            while parent:
                if not parent.isExpanded():collapsed.append(parent)
                parent=parent.parent()
        self.setCurrentItem(item,0,QItemSelectionModel.ClearAndSelect)
        for parent in collapsed:parent.setExpanded(False)
        if reveal and item:self.scrollToItem(item)
    def setRows(self,indices,reveal=True):
        previous=self.blockSignals(True)
        try:
            self.clearSelection()
            for index in indices:
                item=self.nodes.get(index)
                if not item:continue
                if reveal:
                    parent=item.parent()
                    while parent:parent.setExpanded(True);parent=parent.parent()
                item.setSelected(True)
        finally:self.blockSignals(previous)

    def startDrag(self,actions):
        if len(self.selectedItems())>1:return
        self._drag_index=self.currentRow()
        if self._drag_index<0:return
        # Own the drag so Qt cannot remove tree rows after our model transaction.
        drag=QDrag(self);drag.setMimeData(self.mimeData(self.selectedItems()))
        drag.setPixmap(self.viewport().grab(self.visualItemRect(self.currentItem())))
        try:drag.exec(Qt.MoveAction,Qt.MoveAction)
        finally:self._drag_index=-1
    def move_item(self,index,parent_name,before=-1):self.moveRequested.emit(index,parent_name,before)
    def dropEvent(self,event):
        if event.source() is not self or self._drag_index<0:event.ignore();return
        target=self.itemAt(event.position().toPoint());position=self.dropIndicatorPosition()
        before=-1
        if not target or position==QAbstractItemView.OnViewport:parent=self.root
        elif position==QAbstractItemView.OnItem:parent=target
        else:
            parent=target.parent() or self.root
            if position==QAbstractItemView.AboveItem:before=target.data(0,Qt.UserRole)
            else:
                slot=parent.indexOfChild(target)+1
                if slot<parent.childCount():before=parent.child(slot).data(0,Qt.UserRole)
        parent_name=parent.data(0,Qt.UserRole+1) if parent is not self.root else ''
        self.move_item(self._drag_index,parent_name or '',before)
        event.setDropAction(Qt.MoveAction);event.accept()
