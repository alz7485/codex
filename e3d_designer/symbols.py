"""Form references and editable variable declarations; no PML is executed."""
import re

SYMBOL_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


def split_form_reference(token, default_prefix=''):
    match = re.fullmatch(r'([!.]*)([A-Za-z_][A-Za-z0-9_]*)', token)
    if not match:
        raise ValueError('フォーム名は !!名前 / !名前 / .名前 / _名前 / 名前 で指定してください。')
    prefix, name = match.groups()
    return prefix or default_prefix, name


def form_reference(value):
    """Legacy helpers accept a bare name; a Form supplies its preserved prefix."""
    return value.symbol if hasattr(value, 'symbol') else '!!'+value


def parse_variables(text):
    globals_, locals_ = {}, {}
    for line in text.splitlines():
        if not line.strip():
            continue
        name, separator, value = line.partition('=')
        name = name.strip()
        local = name.startswith('!') and not name.startswith('!!')
        bare = name[1:] if local else name[2:] if name.startswith('!!') else name
        target = locals_ if local else globals_
        if (not separator or not SYMBOL_NAME.fullmatch(bare)
                or (local and bare.lower() == 'this')
                or bare.lower() in {key.lower() for key in target}):
            raise ValueError('変数は重複のない 名前=初期値 / !!名前=初期値 / !名前=初期値 の形式で指定してください。')
        target[bare] = value
    return globals_, locals_


def variable_text(form):
    return '\n'.join([*(f'{name}={value}' for name,value in form.variables.items()),
                      *(f'!{name}={value}' for name,value in form.local_variables.items())])
