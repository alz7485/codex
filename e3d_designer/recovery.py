"""Per-session recovery snapshots; never overwrite the user's design file."""
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QLockFile
from .model import Form


class RecoveryStore:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.path=self.directory/(uuid.uuid4().hex+'.json')
        self.restored_path=None
        self.lock=self.make_lock(self.path)
        self.restored_lock=None

    @staticmethod
    def make_lock(path):
        lock=QLockFile(str(Path(path).with_suffix('.lock')))
        lock.setStaleLockTime(0)
        return lock

    def claim(self,path):
        lock=self.make_lock(path)
        if not lock.tryLock(0):raise ValueError('この作業は別のアプリで開かれています。')
        return lock

    def write(self,form,source=None,pending_variables=None):
        data={'version':1,'saved_at':datetime.now().astimezone().isoformat(timespec='seconds'),
              'source':str(Path(source).resolve()) if source else None,
              'design':form.dumps(),'pending_variables':pending_variables}
        encoded=json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8')
        self.directory.mkdir(parents=True,exist_ok=True)
        if not self.lock.isLocked() and not self.lock.tryLock(0):raise OSError('バックアップのロックを取得できません。')
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory,delete=False) as handle:
                temporary=Path(handle.name);handle.write(encoded)
            os.replace(temporary,self.path)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)

    def read(self,path):
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('design'),str):raise ValueError('復元データの形式が不正です。')
        if data.get('source') is not None and not isinstance(data['source'],str):raise ValueError('保存先が不正です。')
        if data.get('source') and '\x00' in data['source']:raise ValueError('保存先が不正です。')
        if data.get('pending_variables') is not None and not isinstance(data['pending_variables'],str):raise ValueError('変数欄が不正です。')
        data.setdefault('source',None);data.setdefault('pending_variables',None)
        return Form.loads(data['design']),data

    def candidates(self):
        if not self.directory.exists():return []
        paths=[]
        for path in self.directory.glob('*.json'):
            if path==self.path:continue
            lock=self.make_lock(path)
            if lock.tryLock(0):
                lock.unlock();paths.append(path)
        return sorted(paths,key=lambda path:path.stat().st_mtime,reverse=True)

    def clear(self):
        self.path.unlink(missing_ok=True)
        if self.restored_path is not None:
            self.restored_path.unlink(missing_ok=True);self.restored_path=None
        self.lock.unlock()
        if self.restored_lock is not None:self.restored_lock.unlock();self.restored_lock=None
