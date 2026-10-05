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
        self.output_folder=self.app_directory;self.error=''
        if self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('version')!=1 or not isinstance(data.get('output_folder'),str):raise ValueError('設定JSONの形式が不正です。')
                folder=Path(data['output_folder'])
                self.output_folder=folder if folder.is_absolute() else self.app_directory/folder
            except (OSError,ValueError,TypeError,AttributeError) as error:self.error=str(error)

    def save_output_folder(self,folder):
        folder=Path(folder).expanduser().resolve()
        if not folder.is_dir():raise ValueError('出力先には存在するフォルダを指定してください。')
        data=json.dumps({'version':1,'output_folder':str(folder)},ensure_ascii=False,indent=2)+'\n'
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent,delete=False) as handle:
                temporary=Path(handle.name);handle.write(data.encode('utf-8'))
            os.replace(temporary,self.path)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
        self.output_folder=folder;self.error=''
