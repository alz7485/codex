"""Format generated PML keywords while preserving identifiers and literals."""
import re
from .pml_syntax import KEYWORDS

LITERAL=r"(?:'[^']*'|\"[^\"]*\"|\|[^|]*\|)"
TOKENS=re.compile(r"--[^\n]*|\$\*[^\n]*|"+LITERAL+r"|[!.$]*[A-Za-z_][A-Za-z0-9_]*",re.S)


def canonical_pml(text, external_types=()):
    def replace(match):
        token=match.group()
        if token.startswith(('--','$*','!','.','_')) or token[0] in "'\"|" or token in external_types:return token
        if token.upper() in KEYWORDS and token.upper() not in ('TRUE','FALSE','UNSET'):
            return token.capitalize()
        return token
    return TOKENS.sub(replace,text)
