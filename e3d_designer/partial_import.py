"""Conservative recovery of declarations; rejected source is retained as data."""
import re
from .mac_import import Importer, MacImportError, comment_lines
from .pml_syntax import mask_non_code
from .method_output import check_editable_code


GADGETS=set('BUTTON PARAGRAPH PARA TEXT TOGGLE RTOGGLE OPTION COMBO COMBOBOX LIST LINE FRAME SLIDER SELECTOR CONTAINER TEXTPANE TEXTPANEL VIEW'.split())
LEAVES={'MENU','VIEW','VAR'}
FORM_DIRECTIVES=set('TITLE PATH HDIST HDISTANCE VDIST VDISTANCE HALIGN VALIGN BAR IMPORT USING MEMBER'.split())


def declaration_spans(text):
    """Locate complete blocks so skipping a bad parent never reparents its children."""
    code=mask_non_code(text,strings=False).splitlines()
    structure=mask_non_code(text).splitlines()
    start=next(i for i,line in enumerate(structure) if re.match(r'^\s*SETUP\s+FORM\b',line,re.I))
    boundary=next((i for i in range(start+1,len(code))
                   if re.match(r'^\s*(?:SHOW|DEFINE\s+METHOD)\b',structure[i],re.I)),len(code))
    keys=[line.strip().split(maxsplit=1)[0].upper() if line.strip() else '' for line in code]
    # An unfamiliar gadget with an extra EXIT is an opaque block, not a FRAME.
    surplus=max(0,sum(key=='EXIT' for key in keys[start+1:boundary])-
                sum(key=='FRAME' or key in LEAVES for key in keys[start+1:boundary])-1)
    spans=[];stack=[];i=start+1
    def opaque_exit(begin):
        """Inspect this declaration, never borrow another unknown object's EXIT."""
        depth=0;cursor=begin+1
        body=False
        while cursor<boundary:
            key=keys[cursor]
            if not key:cursor+=1;continue
            if key in FORM_DIRECTIVES and depth==0:return None,body
            unknown=bool(re.match(r'^\s*\w+\s+[._][A-Za-z_]',code[cursor])) and key not in GADGETS|LEAVES
            if unknown and depth==0:return None,body
            if key in LEAVES:
                cursor+=1
                while cursor<boundary and keys[cursor]!='EXIT':cursor+=1
            elif key=='FRAME':depth+=1
            elif key=='EXIT':
                if depth:depth-=1
                else:return cursor,body
            elif key not in GADGETS and depth==0:body=True
            cursor+=1
        return None,body
    # Reserve EXITs for blocks whose local body establishes their scope, rather
    # than giving a later block's EXIT to an earlier unknown single-line gadget.
    established=sum(1 for row in range(start+1,boundary)
                    if re.match(r'^\s*\w+\s+[._][A-Za-z_]',code[row])
                    and keys[row] not in GADGETS|LEAVES
                    and (scope:=opaque_exit(row))[0] is not None and scope[1])
    surplus=max(0,surplus-established)
    while i<boundary:
        key=keys[i]
        if not key:i+=1;continue
        unknown_object=bool(re.match(r'^\s*\w+\s+[._][A-Za-z_]',code[i])) and key not in GADGETS|LEAVES
        end,body=opaque_exit(i) if unknown_object else (None,False)
        opaque_block=unknown_object and end is not None and (body or surplus)
        if key=='FRAME' or opaque_block:
            stack.append((i,key,unknown_object))
            if unknown_object and not body:surplus=max(0,surplus-1)
        elif key in LEAVES:
            j=i+1
            while j<boundary and keys[j]!='EXIT':
                # Missing leaf EXIT: do not swallow the next independent gadget.
                if keys[j] in GADGETS|{'MENU','BAR'} or (key=='MENU' and keys[j] in FORM_DIRECTIVES):break
                j+=1
            end=j+1 if j<boundary and keys[j]=='EXIT' else j
            kind=key if j<boundary and keys[j]=='EXIT' else key+'（EXITなし）'
            spans.append((i,end,kind));i=end;continue
        elif key=='BAR':
            j=i+1
            while j<boundary and keys[j] in ('','ADD'):j+=1
            spans.append((i,j,key));i=j;continue
        elif key=='EXIT':
            if stack:
                begin,kind,_=stack.pop();spans.append((begin,i+1,kind))
            else:break
        else:spans.append((i,i+1,key))
        i+=1
    spans.extend((begin,boundary,kind) for begin,kind,_ in stack)
    # Methods remain independent of gadgets, even when their linkage is unknown.
    i=boundary
    while i<len(code):
        if re.match(r'^\s*DEFINE\s+METHOD\b',structure[i],re.I):
            j=i+1
            while j<len(code) and not re.match(r'^\s*(?:ENDMETHOD|DEFINE\s+METHOD)\b',structure[j],re.I):j+=1
            end=j+1 if j<len(code) and keys[j]=='ENDMETHOD' else j
            kind='METHOD' if j<len(code) and keys[j]=='ENDMETHOD' else 'METHOD（ENDMETHODなし）'
            spans.append((i,end,kind));i=end
        else:i+=1
    return start,spans


def recover_mac(text):
    starts=[i for i,line in enumerate(mask_non_code(text).splitlines())
            if re.match(r'^\s*SETUP\s+FORM\b',line,re.I)]
    if len(starts)!=1:
        raise ValueError('部分取り込みにもSETUP FORMを1つ含むMACが必要です。')
    original=text;working=text.splitlines();comments=comment_lines(text)
    skipped=set();notes=[]
    # Bound work and retain the normal limits on file size and gadget count.
    for _ in range(101):
        current='\n'.join(working)
        importer=Importer(current)
        try:
            result=importer.parse()
            check_editable_code(result.form)
        except MacImportError as error:
            row=error.line-1
            if row==starts[0] or not 0<=row<len(working) or '500個' in str(error):
                raise ValueError('部分取り込みできません: '+str(error)) from error
            key=mask_non_code(working[row],strings=False).strip().split(maxsplit=1)
            if key and key[0].upper() in ('EXIT','SHOW','SETUP'):
                raise ValueError('フォームの境界を判断できません: '+str(error)) from error
            _,spans=declaration_spans(current)
            unfinished=[span for span in spans if span[1]==row and span[2].endswith('なし）')]
            candidates=unfinished or [span for span in spans if span[0]<=row<span[1]]
            # An invalid FRAME header discards its whole subtree. Other errors
            # discard the smallest complete declaration containing the row.
            span=min(candidates,key=lambda item:item[1]-item[0]) if candidates else (row,row+1,'行')
            begin,end,kind=span
            if not set(range(begin,end))-skipped:
                raise ValueError('部分取り込みを継続できません: '+str(error)) from error
            if len(notes)>=100:raise ValueError('未復元の箇所が100件を超えるため部分取り込みを中止しました。')
            notes.append(f'{begin+1}〜{end}行（{kind}）を省略: '+str(error))
            skipped.update(range(begin,end))
            for i in range(begin,end):working[i]=comments[i]
        except ValueError as error:
            # A discarded gadget can invalidate later relative-placement targets.
            # Discard dependants instead of inventing absolute coordinates.
            names={g.name.lower() for g in importer.form.gadgets}
            dependant=next((g for g in importer.form.gadgets
                            if any(value and value.lower() not in names
                                   for value in (g.parent,g.xref,g.yref,g.width_ref))),None)
            if dependant is not None and len(notes)<100:
                row=next((i for i,line in enumerate(importer.code)
                          if re.match(r'^\s*\w+\s+[._]'+re.escape(dependant.name)+r'(?![A-Za-z0-9_])',line,re.I)),None)
                if row is not None:
                    _,spans=declaration_spans(current)
                    candidates=[span for span in spans if span[0]<=row<span[1]]
                    begin,end,kind=min(candidates,key=lambda item:item[1]-item[0]) if candidates else (row,row+1,'行')
                    notes.append(f'{begin+1}〜{end}行（{kind}）を省略: 配置の参照先が復元できません。')
                    skipped.update(range(begin,end))
                    for i in range(begin,end):working[i]=comments[i]
                    continue
            raise ValueError('残った部品を安全に構築できないため、部分取り込みを中止しました: '+str(error)) from error
        else:
            # A lost block EXIT must not move later declarations into executable
            # program text. Ambiguous recovery leaves the current design intact.
            program=mask_non_code(result.form.after_show_code).splitlines()
            if any(re.match(r'^\s*(?:(?:'+ '|'.join(GADGETS|{'MENU'})+r')\s+[._]|BAR\s*$)',line,re.I)
                   for line in program):
                raise ValueError('フォーム終了後に部品宣言が残るため部分取り込みを中止しました。EXITの所属を確認してください。')
            if notes:
                result.form.partial_import_source=original
                result.form.partial_import_notes=notes
                result.warnings[:0]=[
                    '部分取り込みです。未復元の宣言は出力されません。原文と省略理由は「取り込みコード」で確認できます。',
                    *notes,
                    '処理内の部品・メソッド参照は、未復元の対象がないか確認してください。']
            return result
    raise ValueError('部分取り込みの処理回数が上限を超えました。')
