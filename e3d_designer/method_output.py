"""Omit empty method definitions and standalone calls to known empty methods."""
import re
from .pml_syntax import has_code,mask_non_code,own_reference_pattern


def prune_empty_calls(text,form,names):
    if not names:return text
    pattern=re.compile(own_reference_pattern(form)+r'\.([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)',re.I)
    raw=list(text);masked=mask_non_code(text);offset=0
    for line in masked.splitlines(keepends=True):
        match=pattern.fullmatch(line.strip())
        if match and match.group(2).lower() in names:
            # Erase only executable characters; preserve inline/block comments.
            for index in range(offset,offset+len(line)):
                if not masked[index].isspace():raw[index]=' '
        offset+=len(line)
    return ''.join(raw)


def empty_method_names(form,initial_lines,default_code):
    bodies={method.name.lower():method.body for method in form.extra_methods}
    bodies.update((g.callback.lower(),g.body) for g in form.gadgets if g.callback and g.callback.lower()!='default')
    bodies['default']='\n'.join([*initial_lines,default_code])
    empty=set()
    while True:
        updated={name for name,body in bodies.items()
                 if not has_code(prune_empty_calls(body,form,empty))}
        if updated==empty:return empty
        empty=updated
