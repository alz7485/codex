"""Generate external macro branch skeletons from structured button actions."""
from .model import literal


def branch_template(form, path, normalize=True):
    form.validate()
    groups={}
    for gadget in form.gadgets:
        if gadget.action_mode != 'MACRO' or gadget.macro_path.replace('\\','/').lower() != path.replace('\\','/').lower() or not gadget.macro_flag:
            continue
        flag,values=groups.setdefault(gadget.macro_flag.lower(),(gadget.macro_flag,{}))
        values.setdefault(gadget.macro_value.upper() if normalize else gadget.macro_value,gadget.label or gadget.name)
    if not groups:raise ValueError('分岐用の変数名とボタンの分岐値を設定してください。')
    lines=['-- Generated branch skeleton; edit each branch with your E3D logic.']
    for flag,values in groups.values():
        for index,(value,label) in enumerate(values.items()):
            lines += [f'{"IF" if index == 0 else "ELSEIF"} (!!{flag} EQ {literal(value)}) THEN',
                      '  -- Add the operation for this button here.',f'  $P {literal(label)}']
        lines += ['ENDIF','']
    from .formatting import canonical_pml
    text='\n'.join(lines)
    return canonical_pml(text) if normalize else text
