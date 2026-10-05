"""Name inventory and transactional renaming of project symbols."""
import copy
import re
from .model import IDENTIFIER


def code_slots(form):
    yield 'DEFAULT', form, 'default_body'
    yield '表示後のプログラム', form, 'after_show_code'
    for event in ('initcall','okcall','cancelcall'): yield event.upper(),form,event
    for g in form.gadgets:
        for key in ('command','body','view_code'):
            yield f'{g.name}: {key}', g, key
        for index in range(len(g.item_commands)):
            yield f'{g.name}: OPTION {index+1}', g.item_commands, index
    for menu in form.menus:
        for index,item in enumerate(menu.items):
            yield f'{menu.name}: 項目 {index+1}', item, 'command'


def read_slot(owner, key):
    return owner[key] if isinstance(key,int) else getattr(owner,key)


def write_slot(owner, key, value):
    if isinstance(key,int): owner[key] = value
    else: setattr(owner,key,value)


def actual_name(g):
    return '_'+g.name.lstrip('_') if g.kind == 'option' and g.display_mode == 'TEXT' else g.name


def rewrite_code(value, source_form, target_form, members, methods=None):
    """Replace qualified symbols in one pass, without cascading replacements."""
    members = {key.lower():name for key,name in members.items()}
    methods = {key.lower():name for key,name in (methods or {}).items()}
    pattern = re.compile(r'(!this|!!'+re.escape(source_form)+r')\.([A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_])',re.I)
    def replace(match):
        key = match.group(2).lower()
        method_call = value[match.end():].lstrip().startswith('(')
        target = methods.get(key) if method_call else members.get(key,methods.get(key))
        if target is None: return match.group(0)
        prefix = match.group(1) if match.group(1).lower() == '!this' else '!!'+target_form
        return prefix+'.'+target
    return pattern.sub(replace,value)


def reference_pattern(form, kind, name):
    if kind in ('variable','form'):
        return re.compile(r'!!'+re.escape(name)+r'(?![A-Za-z0-9_])',re.I)
    return re.compile(r'(?:!this|!!'+re.escape(form.name)+r')\.'+re.escape(name)+r'(?![A-Za-z0-9_]|\s*\()',re.I)


def reference_locations(form, kind, name):
    pattern = reference_pattern(form,kind,name)
    locations = []
    for label,owner,key in code_slots(form):
        count = len(pattern.findall(read_slot(owner,key)))
        if count: locations.append((label,count))
    if kind == 'gadget':
        stored = next((g.name for g in form.gadgets if actual_name(g).lower()==name.lower()),name)
        for g in form.gadgets:
            for key in ('parent','xref','yref','width_ref'):
                if getattr(g,key).lower() == stored.lower(): locations.append((f'{g.name}: {key}',1))
    if kind == 'menu':
        for g in form.gadgets:
            if g.popup_menu.lower() == name.lower(): locations.append((f'{g.name}: popup_menu',1))
    return locations


def rename_many(form, changes, update_code=True):
    """Rename symbols simultaneously, including swaps; validate before returning."""
    result = copy.deepcopy(form)
    globals_map, gadgets_map, menus_map, members, methods = {}, {}, {}, {}, {}
    selected = set()
    for kind, key, new_name in changes:
        if (kind,key) in selected: raise ValueError('同じ名前が複数回指定されています。')
        selected.add((kind,key))
        if kind == 'variable':
            if key not in form.variables: raise ValueError('変数が見つかりません。')
            old = key
        elif kind == 'form': old = form.name
        elif kind in ('gadget','menu'):
            collection = form.gadgets if kind == 'gadget' else form.menus
            if not isinstance(key,int) or not 0 <= key < len(collection):
                raise ValueError('オブジェクトが見つかりません。')
            old = collection[key].name
        else: raise ValueError('名前の種類が不正です。')
        valid = re.fullmatch(r'_?[A-Za-z][A-Za-z0-9_]*',new_name) if kind == 'gadget' and form.gadgets[key].kind == 'option' else IDENTIFIER.fullmatch(new_name)
        if not valid: raise ValueError('名前は英字で始まる英数字・_ にしてください。')
        if kind == 'variable': globals_map[old.lower()] = new_name
        elif kind == 'form':
            globals_map[old.lower()] = new_name
            result.name = new_name
        elif kind == 'menu':
            result.menus[key].name = new_name
            menus_map[old.lower()] = new_name
            members[old.lower()] = new_name
        else:
            result.gadgets[key].name = new_name
            gadgets_map[old.lower()] = new_name
            members[actual_name(form.gadgets[key]).lower()] = actual_name(result.gadgets[key])
            if form.gadgets[key].kind == 'container': members[(old+'Control').lower()] = new_name+'Control'
            g = form.gadgets[key]
            if g.kind == 'list' and g.list_mode == 'TABLE' and not g.table_method:
                methods[('populate_'+old).lower()] = 'populate_'+new_name
    variable_names = [globals_map.get(name.lower(),name) for name in form.variables]
    if len({name.lower() for name in variable_names}) != len(variable_names):
        raise ValueError('変数名が重複しています。')
    result.variables = dict(zip(variable_names,form.variables.values()))
    for g in result.gadgets:
        for attribute in ('parent','xref','yref','width_ref'):
            old = getattr(g,attribute)
            setattr(g,attribute,gadgets_map.get(old.lower(),old))
        g.popup_menu = menus_map.get(g.popup_menu.lower(),g.popup_menu)
    if update_code:
        # Consume qualified references and globals together so swaps cannot cascade.
        pattern = re.compile(r'(!this|!![A-Za-z][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?',re.I)
        for _,owner,attribute in code_slots(result):
            value = read_slot(owner,attribute)
            def replace(match):
                prefix,member = match.groups()
                own = prefix.lower() in ('!this','!!'+form.name.lower())
                target_prefix = prefix if prefix.lower() == '!this' else '!!'+globals_map.get(prefix[2:].lower(),prefix[2:])
                if member is None: return target_prefix
                target_member = member
                if own:
                    method_call = value[match.end():].lstrip().startswith('(')
                    target_member = methods.get(member.lower(),member) if method_call else members.get(member.lower(),methods.get(member.lower(),member))
                return target_prefix+'.'+target_member
            write_slot(owner,attribute,pattern.sub(replace,value))
    result.validate()
    return result


def rename(form, kind, key, new_name, update_code=True):
    return rename_many(form,[(kind,key,new_name)],update_code)
