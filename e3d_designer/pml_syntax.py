"""Shared PML vocabulary and comment/string recognition, independent of Qt."""
import re
from .symbols import form_reference,FORM_NAME_PATTERN


NON_CODE_PATTERN = (
    r"--[^\n]*|\$\*[^\n]*|\$\(.*?(?:\$\)|\Z)|"
    r"'[^']*(?:'|\Z)|\"[^\"]*(?:\"|\Z)|\|[^|]*(?:\||\Z)"
)
NON_CODE = re.compile(NON_CODE_PATTERN, re.S)


def mask_non_code(text, strings=True):
    """Mask comments, and optionally strings, without joining code across them."""
    def replace(match):
        token = match.group()
        if not strings and token[0] in "'\"|":return token
        fill = '?' if token[0] in "'\"|" else ' '
        return ''.join('\n' if char == '\n' else fill for char in token)
    return NON_CODE.sub(replace, text)


def has_code(text):
    return bool(mask_non_code(text, strings=False).strip())


def reference_mask(text,form_name):
    """Expose code and known callback assignments, keeping data literals masked."""
    masked=mask_non_code(text)
    callback=re.compile(own_reference_pattern(form_name)+r'\.(?:[A-Za-z_][A-Za-z0-9_]*\.)?'
                        r'(?:CALL|CALLBACK|INITCALL|AUTOCALL|OKCALL|CANCELCALL)\s*=\s*$',re.I)
    result=list(masked)
    for token in NON_CODE.finditer(text):
        if token.group()[0] not in "'\"|":continue
        beginning=text.rfind('\n',0,token.start())+1
        if callback.search(masked[beginning:token.start()]):
            result[token.start()+1:token.end()-1]=reference_mask(token.group()[1:-1],form_name)
    return ''.join(result)


def method_call_sites(text,form_name):
    pattern=re.compile(own_reference_pattern(form_name)+r'\.('+method_name_pattern(form_name)+r')(?=\s*\()',re.I)
    return [(match.start(),match.end(),match.group(2))
            for match in pattern.finditer(reference_mask(text,form_name))]


def method_name_pattern(form):
    name=getattr(form,'name',None)
    return '(?:'+re.escape(name)+'|'+FORM_NAME_PATTERN+')' if name is not None else FORM_NAME_PATTERN


def method_declaration_name(header,form,protected):
    for marker,value in protected.items():header=header.replace(marker,value)
    match=re.match(r'define\s+method\s+\.('+method_name_pattern(form)+r')(?=\s*\()',header,re.I)
    if match is None:raise ValueError('メソッドの宣言を解釈できません: '+header)
    return match.group(1)


def own_reference_pattern(form):
    return r'(?<![\w!.])(!this|'+re.escape(form_reference(form))+r')(?!\w)'


KEYWORDS=set('''VAR LIST PAIRS EXIT KILL SETUP FORM LAYOUT DIALOG MAIN DOCUMENT BLOCKING
DOCK DOCKING LEFT RIGHT TOP BOTTOM FILL NONE ALL RESIZABLE SIZE TITLE
BUTTON PARAGRAPH PARA TEXT TOGGLE RTOGGLE FRAME TABSET TOOLBAR OPTION
COMBO COMBOBOX SLIDER SELECTOR DATABASE CONTAINER PMLNETCONTROL TEXTPANE
VIEW ALPHA AREA PLOT VOLUME LINE HORIZ VERT HORIZONTAL VERTICAL
AT X Y WIDTH HEIGHT BACKGROUND PIXMAP CALL CALLBACK INITCALL AUTOCALL
OKCALL CANCELCALL OK APPLY CANCEL RESET HELP NORMAL
DEFINE METHOD ENDMETHOD SHOW HIDE IS STRING REAL BOOLEAN ARRAY OBJECT
IF THEN ELSE ELSEIF ENDIF DO ENDDO FOR FROM TO BY BREAK RETURN HANDLE ENDHANDLE
AND OR NOT EQ NE GT GE LT LE
SINGLE MULTIPLE MULTI OWNERS MEMBERS AUTO ASPECT FIXCHARS
PATH HDIST HDISTANCE VDIST VDISTANCE HALIGN VALIGN CENTRE CENTER
XMIN XCEN XMAX YMIN YCEN YMAX ANCHOR NOPADDING NOALIGN AUTOALIGN
SCROLL RANGE STEP NDP STATES TAG TAGWIDTH TAGWID CHANNELS REQUESTS
IMPORT USING NAMESPACE MEMBER NOBOX INDENT APPEND DELETE NEW COLLECTION
Q QUERY SAVEWORK CE END MENU BAR ADD LIMITS SELECT REHASH LOOP EVALUATE TRACK RATE CONTENTS COMMANDS'''.split())
