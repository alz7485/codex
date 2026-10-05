"""Transactional copying of a gadget subtree and its generated symbols."""
import copy
from .model import native_size
from .names import actual_name,code_slots,read_slot,write_slot,rewrite_code


def clone_subtree(target,source,index,restore_names=False):
    if type(index) is not int or not 0 <= index < len(source.gadgets):
        raise ValueError('コピー元の部品が不正です。')
    root = source.gadgets[index]
    subtree = {root.name.lower(),*(name.lower() for name in source.descendants(root.name))}
    originals = [(i,g) for i,g in enumerate(source.gadgets) if g.name.lower() in subtree]
    draft = copy.deepcopy(target)
    occupied = {actual_name(g).lower() for g in draft.gadgets}|{m.name.lower() for m in draft.menus}
    if restore_names and any(actual_name(g).lower() in occupied for _,g in originals): restore_names = False
    reserved = occupied|{draft.name.lower(),'default'}|{g.name.lower() for g in draft.gadgets}
    reserved |= {g.callback.lower() for g in draft.gadgets if g.callback}
    reserved |= {('macro_'+g.name).lower() for g in draft.gadgets if g.action_mode == 'MACRO'}
    reserved |= {(g.table_method or 'populate_'+g.name).lower() for g in draft.gadgets if g.kind == 'list' and g.list_mode == 'TABLE'}
    reserved |= {(g.name+'Control').lower() for g in draft.gadgets if g.kind == 'container' and g.assembly}
    def unique(base,extra=None):
        number = 1
        while (base+str(number)).lower() in reserved or (extra and extra(base+str(number)).lower() in reserved): number += 1
        name = base+str(number);reserved.add(name.lower())
        return name
    mapping = {};members = {};methods = {};copies = []
    for original_index,original in originals:
        gadget = copy.deepcopy(original)
        if not restore_names:
            extra = (lambda name:'macro_'+name) if original.action_mode == 'MACRO' else (lambda name:'_'+name) if original.kind == 'option' and original.display_mode == 'TEXT' else (lambda name:name+'Control') if original.kind == 'container' else (lambda name:'populate_'+name) if original.kind == 'list' and original.list_mode == 'TABLE' else None
            gadget.name = unique(gadget.kind,extra)
        mapping[original.name.lower()] = gadget.name
        members[actual_name(original)] = actual_name(gadget)
        if original.action_mode == 'MACRO':
            methods['macro_'+original.name] = 'macro_'+gadget.name;reserved.add(('macro_'+gadget.name).lower())
            if gadget.macro_flag and gadget.macro_flag.lower() not in {name.lower() for name in draft.variables}:
                source_key=next((name for name in source.variables if name.lower() == gadget.macro_flag.lower()),None)
                if source_key is not None:draft.variables[gadget.macro_flag]=source.variables[source_key]
        if original.kind == 'container':
            members[original.name+'Control'] = gadget.name+'Control';reserved.add((gadget.name+'Control').lower())
        if original.kind == 'list' and original.list_mode == 'TABLE':
            old_method = original.table_method or 'populate_'+original.name
            if not restore_names: gadget.table_method = ''
            new_method = gadget.table_method or 'populate_'+gadget.name
            methods[old_method] = new_method;reserved.add(new_method.lower())
        copies.append((original_index,original,gadget))
    for _,original,gadget in copies:
        if original.callback:
            if original.callback.lower() not in {name.lower() for name in methods}:
                methods[original.callback] = original.callback if restore_names else unique(original.callback+'_copy')
            gadget.callback = next(value for name,value in methods.items() if name.lower() == original.callback.lower())
            if original.callback.lower() == 'default' and not restore_names:
                gadget.body = source.default_body or original.body
    existing = {g.name.lower() for g in draft.gadgets}
    available = existing|{name.lower() for name in mapping.values()}
    for original_index,original,gadget in copies:
        for key in ('parent','xref','yref','width_ref'):
            value = getattr(gadget,key)
            if value.lower() in mapping: setattr(gadget,key,mapping[value.lower()])
        detached = bool(original.parent and original.parent.lower() not in subtree and original.parent.lower() not in existing)
        if detached: gadget.parent = ''
        missing = any(name and name.lower() not in available for name in (gadget.xref,gadget.yref,gadget.width_ref))
        if detached or missing or (gadget.layout_mode == 'AUTO' and not restore_names):
            x,y,width,height = source.geometry(original)
            if detached:
                ox,oy = source.offset(original);x += ox;y += oy
            gadget.x,gadget.y = x,y
            gadget.width,gadget.height = native_size(gadget,width,height)
            gadget.layout_mode = 'ABSOLUTE';gadget.xref = gadget.yref = gadget.width_ref = ''
        if restore_names: draft.gadgets.insert(min(original_index,len(draft.gadgets)),gadget)
        else: draft.gadgets.append(gadget)
    owners = {id(gadget) for _,_,gadget in copies}|{id(gadget.item_commands) for _,_,gadget in copies}
    for _,owner,key in code_slots(draft):
        if id(owner) in owners:
            write_slot(owner,key,rewrite_code(read_slot(owner,key),source.name,draft.name,members,methods))
    draft.validate()
    selected = next(i for i,g in enumerate(draft.gadgets) if g.name == mapping[root.name.lower()])
    return draft,selected
