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


def rename(form, kind, key, new_name, update_code=True):
    """Return a validated new form; keep the supplied form untouched on failure."""
    result = copy.deepcopy(form)
    if kind == 'variable': old = key
    elif kind == 'form': old = result.name
    elif kind == 'gadget': old = result.gadgets[key].name
    elif kind == 'menu': old = result.menus[key].name
    else: raise ValueError('名前の種類が不正です。')
    valid = re.fullmatch(r'_?[A-Za-z][A-Za-z0-9_]*',new_name) if kind == 'gadget' and result.gadgets[key].kind == 'option' else IDENTIFIER.fullmatch(new_name)
    if not valid: raise ValueError('名前は英字で始まる英数字・_ にしてください。')
    if kind == 'variable':
        if any(name.lower()==new_name.lower() and name!=old for name in result.variables):
            raise ValueError('変数名が重複しています。')
        result.variables = {new_name if name==old else name:value for name,value in result.variables.items()}
    elif kind == 'form': result.name = new_name
    elif kind == 'menu':
        result.menus[key].name = new_name
        for g in result.gadgets:
            if g.popup_menu.lower() == old.lower(): g.popup_menu = new_name
    else:
        result.gadgets[key].name = new_name
        for g in result.gadgets:
            for attribute in ('parent','xref','yref','width_ref'):
                if getattr(g,attribute).lower()==old.lower(): setattr(g,attribute,new_name)
    if update_code:
        replacements = [(old,new_name)]
        if kind == 'gadget':
            old_gadget,new_gadget = form.gadgets[key],result.gadgets[key]
            replacements = [(actual_name(old_gadget),actual_name(new_gadget))]
            if old_gadget.kind == 'container': replacements.append((old+'Control',new_name+'Control'))
        for source,target in replacements:
            pattern = reference_pattern(form,kind,source)
            for _,owner,attribute in code_slots(result):
                write_slot(owner,attribute,pattern.sub(lambda match: match.group(0)[:-len(source)]+target,read_slot(owner,attribute)))
        if kind == 'gadget' and form.gadgets[key].kind == 'list' and form.gadgets[key].list_mode == 'TABLE' and not form.gadgets[key].table_method:
            pattern = re.compile(r'((?:!this|!!'+re.escape(form.name)+r')\.)populate_'+re.escape(old)+r'(?![A-Za-z0-9_])',re.I)
            for _,owner,attribute in code_slots(result):
                write_slot(owner,attribute,pattern.sub(lambda match:match.group(1)+'populate_'+new_name,read_slot(owner,attribute)))
    result.validate()
    return result
