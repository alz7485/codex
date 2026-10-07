"""Name inventory and transactional renaming of project symbols."""
import copy
import re
from .model import IDENTIFIER,uses_pairs
from .pml_syntax import reference_mask,own_reference_pattern
from .symbols import form_reference,SYMBOL_NAME,split_form_reference


def code_slots(form):
    yield 'DEFAULT', form, 'default_body'
    yield '取り込んだ表示プログラム' if form.program_mode=='SOURCE' else '表示後のプログラム', form, 'after_show_code'
    yield 'フォーム定義前の処理',form,'preamble_code'
    yield 'コンストラクタの追加処理',form,'constructor_body'
    for method in form.extra_methods:yield f'追加メソッド {method.name}',method,'body'
    for event in ('initcall','okcall','cancelcall'): yield event.upper(),form,event
    for g in form.gadgets:
        for key in ('command','body','view_code','callback_expression'):
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
    return '_'+g.name.lstrip('_') if uses_pairs(g) else g.name


def rewrite_code(value, source_form, target_form, members, methods=None, *, preserve_literals=False):
    """Replace qualified symbols in one pass, without cascading replacements."""
    members = {key.lower():name for key,name in members.items()}
    methods = {key.lower():name for key,name in (methods or {}).items()}
    pattern = re.compile(own_reference_pattern(source_form)+r'\.([A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_])',re.I)
    masked=reference_mask(value,source_form) if preserve_literals else value
    def replace(match):
        key = match.group(2).lower()
        method_call = masked[match.end():].lstrip().startswith('(')
        target = methods.get(key) if method_call else members.get(key,methods.get(key))
        if target is None: return match.group(0)
        prefix = match.group(1) if match.group(1).lower() == '!this' else form_reference(target_form)
        return prefix+'.'+target
    if not preserve_literals:return pattern.sub(replace,value)
    result=[];cursor=0
    for match in pattern.finditer(masked):
        result.extend((value[cursor:match.start()],replace(match)));cursor=match.end()
    result.append(value[cursor:])
    return ''.join(result)


def reference_pattern(form, kind, name):
    if kind in ('variable','local_variable','form'):
        token=form.symbol if kind=='form' else ('!' if kind=='local_variable' else '!!')+name
        return re.compile(r'(?<![A-Za-z0-9_!.])'+re.escape(token)+r'(?![A-Za-z0-9_])',re.I)
    return re.compile(own_reference_pattern(form)+r'\.'+re.escape(name)+r'(?![A-Za-z0-9_]|\s*\()',re.I)


def reference_locations(form, kind, name):
    pattern = reference_pattern(form,kind,name)
    locations = []
    for label,owner,key in code_slots(form):
        if kind=='local_variable' and not (owner is form and key in ('preamble_code','after_show_code')):continue
        count = len(pattern.findall(read_slot(owner,key)))
        if count: locations.append((label,count))
    if kind == 'gadget':
        stored = next((g.name for g in form.gadgets if actual_name(g).lower()==name.lower()),name)
        for g in form.gadgets:
            for key in ('parent','xref','yref','width_ref'):
                if getattr(g,key).lower() == stored.lower(): locations.append((f'{g.name}: {key}',1))
    if kind == 'variable':
        for g in form.gadgets:
            if g.action_mode == 'MACRO' and g.macro_flag.lower() == name.lower():locations.append((f'{g.name}: 分岐フラグ',1))
    if kind == 'menu':
        for g in form.gadgets:
            if g.popup_menu.lower() == name.lower(): locations.append((f'{g.name}: popup_menu',1))
    return locations


def rename_many(form, changes, update_code=True):
    """Rename symbols simultaneously, including swaps; validate before returning."""
    result = copy.deepcopy(form)
    globals_map, locals_map, gadgets_map, menus_map, members, methods = {}, {}, {}, {}, {}, {}
    selected = set()
    for kind, key, new_name in changes:
        if (kind,key) in selected: raise ValueError('同じ名前が複数回指定されています。')
        selected.add((kind,key))
        if kind in ('variable','local_variable'):
            variables=form.local_variables if kind=='local_variable' else form.variables
            if key not in variables: raise ValueError('変数が見つかりません。')
            old = key
        elif kind == 'form': old = form.name
        elif kind in ('gadget','menu'):
            collection = form.gadgets if kind == 'gadget' else form.menus
            if not isinstance(key,int) or not 0 <= key < len(collection):
                raise ValueError('オブジェクトが見つかりません。')
            old = collection[key].name
        else: raise ValueError('名前の種類が不正です。')
        if kind=='form':
            prefix,new_name=split_form_reference(new_name,form.form_prefix)
            result.form_prefix=prefix
        elif kind=='local_variable' and new_name.startswith('!') and not new_name.startswith('!!'):new_name=new_name[1:]
        elif kind=='variable' and new_name.startswith('!!'):new_name=new_name[2:]
        valid = SYMBOL_NAME.fullmatch(new_name) if kind in ('form','variable','local_variable') else re.fullmatch(r'_?[A-Za-z][A-Za-z0-9_]*',new_name) if kind == 'gadget' and form.gadgets[key].kind == 'option' else IDENTIFIER.fullmatch(new_name)
        if not valid: raise ValueError('名前は英字で始まる英数字・_ にしてください。')
        if kind == 'variable': globals_map[old.lower()] = new_name
        elif kind=='local_variable':locals_map[old.lower()]=new_name
        elif kind == 'form':
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
            if g.action_mode == 'MACRO':methods[('macro_'+old).lower()] = 'macro_'+new_name
            if g.kind == 'list' and g.list_mode == 'TABLE' and not g.table_method:
                methods[('populate_'+old).lower()] = 'populate_'+new_name
    variable_names = [globals_map.get(name.lower(),name) for name in form.variables]
    if len({name.lower() for name in variable_names}) != len(variable_names):
        raise ValueError('変数名が重複しています。')
    result.variables = dict(zip(variable_names,form.variables.values()))
    local_names=[locals_map.get(name.lower(),name) for name in form.local_variables]
    if len({name.lower() for name in local_names})!=len(local_names):raise ValueError('ローカル変数名が重複しています。')
    result.local_variables=dict(zip(local_names,form.local_variables.values()))
    for g in result.gadgets:
        for attribute in ('parent','xref','yref','width_ref'):
            old = getattr(g,attribute)
            setattr(g,attribute,gadgets_map.get(old.lower(),old))
        g.popup_menu = menus_map.get(g.popup_menu.lower(),g.popup_menu)
        g.macro_flag = globals_map.get(g.macro_flag.lower(),g.macro_flag)
    if update_code:
        # Consume qualified references and globals together so swaps cannot cascade.
        pattern = re.compile(r'(?<![A-Za-z0-9_!.])(!this|'+re.escape(form.symbol)+r'(?![A-Za-z0-9_])|!![A-Za-z_][A-Za-z0-9_]*|![A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?',re.I)
        for _,owner,attribute in code_slots(result):
            value = read_slot(owner,attribute)
            def replace(match):
                prefix,member = match.groups()
                own = prefix.lower() in ('!this',form.symbol.lower())
                if prefix.lower()==form.symbol.lower():target_prefix=result.symbol
                elif prefix.startswith('!!'):target_prefix='!!'+globals_map.get(prefix[2:].lower(),prefix[2:])
                elif prefix.startswith('!') and prefix.lower()!='!this' and owner is result and attribute in ('preamble_code','after_show_code'):
                    target_prefix='!'+locals_map.get(prefix[1:].lower(),prefix[1:])
                else:target_prefix=prefix
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
