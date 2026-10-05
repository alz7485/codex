"""Application-local output folder preferences."""
import json
import os
import sys
import tempfile
from pathlib import Path


def application_directory():
    return Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent


class Settings:
    def __init__(self,path=None):
        self.app_directory=application_directory()
        self.path=Path(path) if path is not None else self.app_directory/'settings.json'
        self.macro_folder=self.app_directory;self.output_folder=self.app_directory;self.recent_files=[];self.error=''
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('version')!=1 or not isinstance(data.get('output_folder'),str):raise ValueError('設定JSONの形式が不正です。')
                folder=Path(data['output_folder'])
                macro=data.get('macro_folder',str(self.app_directory))
                if not isinstance(macro,str):raise ValueError('マクロフォルダの設定が不正です。')
                macro=Path(macro)
                self.macro_folder=macro if macro.is_absolute() else self.app_directory/macro
                recent=data.get('recent_files',[])
                if not isinstance(recent,list) or any(not isinstance(item,str) for item in recent):raise ValueError('最近の設計の設定が不正です。')
                self.output_folder=folder if folder.is_absolute() else self.app_directory/folder
                self.recent_files=recent[:10]
            except (OSError,ValueError,TypeError,AttributeError) as error:self.error=str(error)

    def save_output_folder(self,folder):
        folder=Path(folder).expanduser().resolve()
        if not folder.is_dir():raise ValueError('出力先には存在するフォルダを指定してください。')
        self._write(folder,self.recent_files)
        self.output_folder=folder;self.error=''

    def save_macro_folder(self,folder):
        folder=Path(folder).expanduser().resolve()
        if not folder.is_dir():raise ValueError('マクロフォルダには存在するフォルダを指定してください。')
        self._write(self.output_folder,self.recent_files,folder)
        self.macro_folder=folder;self.error=''

    def remember_design(self,path):
        name=str(Path(path).resolve())
        recent=[name]+[item for item in self.recent_files if os.path.normcase(item)!=os.path.normcase(name)]
        recent=recent[:10]
        self._write(self.output_folder,recent)
        self.recent_files=recent;self.error=''

    def clear_recent(self):
        self._write(self.output_folder,[])
        self.recent_files=[]

    def _write(self,folder,recent,macro_folder=None):
        data=json.dumps({'version':1,'output_folder':str(folder),'recent_files':recent,'macro_folder':str(self.macro_folder if macro_folder is None else macro_folder)},ensure_ascii=False,indent=2)+'\n'
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent,delete=False) as handle:
                temporary=Path(handle.name);handle.write(data.encode('utf-8'))
            os.replace(temporary,self.path)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
