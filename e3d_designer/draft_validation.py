"""Check that an incomplete design is safe to open, without requiring valid PML."""
import math
import types
from dataclasses import fields,is_dataclass
from functools import lru_cache
from typing import get_args,get_origin,get_type_hints


@lru_cache
def schema(record_type):return get_type_hints(record_type)


def validate_draft(form):
    from .model import Form,IDENTIFIER,KINDS,uses_pairs
    from .symbols import SYMBOL_NAME
    import re
    seen=set()
    def check(value,annotation):
        origin=get_origin(annotation);args=get_args(annotation)
        if origin is types.UnionType:
            if value is None and type(None) in args:return
            return check(value,next(arg for arg in args if arg is not type(None)))
        if origin is list:
            if not isinstance(value,list):raise ValueError('設計の配列の形式が不正です。')
            for item in value:check(item,args[0])
        elif origin is dict:
            if not isinstance(value,dict):raise ValueError('設計の辞書の形式が不正です。')
            for key,item in value.items():check(key,args[0]);check(item,args[1])
        elif annotation is float:
            try:valid=type(value) in (int,float) and math.isfinite(value)
            except OverflowError:valid=False
            if not valid:raise ValueError('座標と数値には有限数を指定してください。')
        elif is_dataclass(annotation):
            if type(value) is not annotation:raise ValueError('設計のレコード形式が不正です。')
            if id(value) in seen:return
            seen.add(id(value))
            for field in fields(value):check(getattr(value,field.name),schema(annotation)[field.name])
        elif type(value) is not annotation:raise ValueError('設計の項目の型が不正です。')
    check(form,Form)
    if not SYMBOL_NAME.fullmatch(form.name) or not re.fullmatch(r'[!.]*',form.form_prefix):raise ValueError('フォーム名が不正です。')
    if not 1<=form.width<=300 or not 1<=form.height<=300:raise ValueError('フォームサイズは1〜300にしてください。')
    if len(form.gadgets)>500:raise ValueError('部品数は500個までです。')
    if form.form_type not in ('DIALOG','MAIN') or form.dock_side not in ('','NONE','LEFT','RIGHT','TOP','BOTTOM'):raise ValueError('フォーム形式が不正です。')
    for mode in (form.default_mode,form.program_mode,form.constructor_mode):
        if mode not in ('GENERATED','SOURCE'):raise ValueError('コードの生成形式が不正です。')
    if '\x00' in form.source_mac_path:raise ValueError('取り込み元のパスが不正です。')
    names=set();stored=set()
    enums={'frame_style':('FRAME','TABSET','TOOLBAR'),'layout_mode':('ABSOLUTE','AUTO','RELATIVE'),
        'path':('DOWN','UP','LEFT','RIGHT'),'halign':('LEFT','CENTRE','RIGHT'),'valign':('TOP','CENTRE','BOTTOM'),
        'xedge':('XMIN','XMAX'),'yedge':('YMIN','YMAX'),'xanchor':('LEFT','RIGHT'),
        'orientation':('HORIZ','VERT'),'slider_orientation':('HORIZONTAL','VERTICAL'),
        'display_mode':('TEXT','PIXMAP'),'list_mode':('SIMPLE','TABLE'),'path_axes':('','X','Y','XY')}
    for g in form.gadgets:
        valid_name=re.fullmatch(r'_?[A-Za-z][A-Za-z0-9_]*',g.name) if g.kind=='option' else IDENTIFIER.fullmatch(g.name)
        if g.kind not in KINDS or not valid_name:raise ValueError('部品の種類または名前が不正です。')
        actual=('_'+g.name.lstrip('_') if uses_pairs(g) else g.name).lower()
        if actual in names or g.name.lower() in stored:raise ValueError('部品名が重複しています。')
        names.add(actual);stored.add(g.name.lower())
        if g.width<0 or g.height<0:raise ValueError('部品寸法は0以上にしてください。')
        if any(getattr(g,key) not in values for key,values in enums.items()):raise ValueError('部品の表示・配置形式が不正です。')
        if g.parent and not form.parent_gadget(g):raise ValueError('親コンテナが見つかりません。')
        parent=form.parent_gadget(g);trail={g.name.lower()}
        while parent:
            if parent.kind!='frame' or parent.name.lower() in trail:raise ValueError('親コンテナの形式または循環が不正です。')
            trail.add(parent.name.lower());parent=form.parent_gadget(parent)
    # Missing layout references, invalid initial values, incomplete callbacks,
    # and out-of-container controls remain editable; export validates them.
