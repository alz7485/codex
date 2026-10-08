"""Omit empty method definitions and standalone calls to known empty methods."""
import re
from .pml_syntax import has_code,mask_non_code,own_reference_pattern,method_call_sites
from .symbols import FORM_NAME_PATTERN


class OmittedMethodReferenceError(ValueError):
    """The design is editable, but omitting empty methods prevents MAC export."""


def check_editable_code(form):
    """Check output structure, allowing retained calls to be repaired in the editor."""
    try:form.pml()
    except OmittedMethodReferenceError:pass


def prune_empty_calls(text,form,names):
    if not names:return text
    pattern=re.compile(own_reference_pattern(form)+r'\.('+FORM_NAME_PATTERN+r')\s*\(\s*\)',re.I)
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


def validate_omitted_references(form,omitted,fragments):
    """Reject dangling calls without deleting argument evaluation or expressions."""
    referenced={}
    for text in fragments:
        for _,_,name in method_call_sites(text,form):
            if name.lower() in omitted:referenced.setdefault(name.lower(),name)
    if referenced:
        names='、'.join('.'+name for name in referenced.values())
        raise OmittedMethodReferenceError('空メソッド '+names+' を省略すると参照が残ります。'
                                          '呼び出しを編集するか、メソッドに処理を入力してください。')
