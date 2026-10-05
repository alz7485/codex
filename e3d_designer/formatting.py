"""Canonical command, identifier and value casing for generated PML."""
import re
from .pml_syntax import KEYWORDS

LITERAL=r"(?:'[^']*'|\"[^\"]*\"|\|[^|]*\|)"
TOKENS=re.compile(r"--[^\n]*|\$\*[^\n]*|"+LITERAL+r"|[!.$]*[A-Za-z_][A-Za-z0-9_]*",re.S)


def canonical_pml(text, external_types=()):
    def replace(match):
        token=match.group()
        if token.startswith(('--','$*')):return token
        if token[0] in "'\"|":
            prefix=text[:match.start()].rsplit('\n',1)[-1]
            inner=token[1:-1]
            if re.search(r'\busing\s+namespace\s*$',prefix,re.I):return token
            command=(re.search(r'\b(?:call|callback)\s*$',prefix,re.I)
                     or re.search(r'\.(?:callback|initcall|okcall|cancelcall)\s*=\s*$',prefix,re.I)
                     or re.fullmatch(r'\s*(?:add\s+)?'+LITERAL+r'\s+',prefix,re.I)
                     or re.search(r"\.add\(\s*'callback'\s*,\s*"+LITERAL+r'\s*,\s*$',prefix,re.I))
            if command:return token[0]+canonical_pml(inner,external_types)+token[-1]
            return token.upper()
        prefix=text[:match.start()].rsplit('\n',1)[-1]
        if token in external_types and (re.search(r'\bmember\s+\.[A-Za-z_][A-Za-z0-9_]*\s+is\s*$',prefix,re.I) or re.search(r'=\s*object\s*$',prefix,re.I)):
            return token
        if token.startswith('$') and token[1:].replace('_','').isalnum():
            return '$'+token[1:].capitalize()
        if token.upper() in KEYWORDS and token.upper() not in ('TRUE','FALSE','UNSET'):
            return token.capitalize()
        prefix=text[:match.start()].rsplit('\n',1)[-1]
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',token) and not prefix.strip() and not text[match.end():].lstrip().startswith(('=', '(')):
            return token.capitalize()
        return token.upper()
    return TOKENS.sub(replace,text)
