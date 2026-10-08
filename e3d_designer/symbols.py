"""Form references and editable variable declarations; no PML is executed."""
import re

SYMBOL_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
FORM_NAME_PATTERN = r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*'

def validate_form_reference(name, prefix=''):
    # A form reference is imported as data, not an identifier to normalize.
    if (not isinstance(name,str) or not isinstance(prefix,str) or not name.strip()
        or any(c in name+prefix for c in ('\x00','\r','\n'))):
        raise ValueError('フォーム名を空欄にせず、1行で指定してください。')


def split_form_reference(token, default_prefix=''):
    validate_form_reference(token)
    prefix=re.match(r'[!.]*',token).group()
    name=token[len(prefix):]
    if not name:return '',token
    return prefix or default_prefix, name


def form_file_stem(name):
    """Use a filename suggestion without changing the imported form reference."""
    stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip(' .') or 'Form'
    if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',stem.split('.')[0],re.I):stem='Form_'+stem
    return stem


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
