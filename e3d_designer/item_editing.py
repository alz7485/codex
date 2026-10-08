"""Prevent edits that a retained source constructor would silently ignore."""
from .model import uses_pairs
from .pml_syntax import has_code


def validate_item_change(before,after,constructor_mode):
    keys=('items','item_values','item_commands','headings','rows','list_mode','table_method')
    if constructor_mode!='SOURCE' or all(getattr(before,key)==getattr(after,key) for key in keys):return
    # These definitions are emitted independently of the source constructor.
    if before.kind==after.kind=='list' and before.list_mode==after.list_mode=='TABLE' and before.table_method.lower()==after.table_method.lower():return
    if uses_pairs(before) and uses_pairs(after) and not before.item_values and not after.item_values:return
    raise ValueError('元コード優先のため、この項目変更はMACの初期化へ反映できません。「取り込みコード」で元のコンストラクタを編集するか、初期化の生成方式を変更してください。')


def needs_constructor(gadget):
    return bool((gadget.kind=='list' and gadget.list_mode=='TABLE')
                or ((gadget.kind in ('list','combo') or (gadget.kind=='option' and (not uses_pairs(gadget) or gadget.item_values))) and gadget.items)
                or (gadget.kind in ('slider','combo') and gadget.callback and has_code(gadget.body))
                or gadget.popup_menu
                or (gadget.kind=='container' and gadget.assembly)
                or (gadget.kind in ('button','toggle') and gadget.display_mode=='PIXMAP' and gadget.pixmap_path))
