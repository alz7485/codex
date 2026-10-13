"""Build the controlled Markdown manual as offline HTML and optional PDF.

Run: python scripts/build_manual.py --pdf
HTML uses the standard library. PDF uses the app's installed PySide6.
Only the Markdown constructs used by MANUAL.md are supported.
"""
import argparse
import base64
import html
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'MANUAL.md'
DESTINATION = ROOT / 'docs/manual'


def blocks(source):
    lines = source.splitlines(); i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip(): i += 1; continue
        if line.startswith('```'):
            language = line[3:]; i += 1; body = []
            while i < len(lines) and not lines[i].startswith('```'):
                body.append(lines[i]); i += 1
            if i == len(lines): raise ValueError('Unclosed code block')
            yield 'code', (language, '\n'.join(body)); i += 1; continue
        anchor = re.fullmatch(r'<a id="([a-z0-9-]+)"></a>', line)
        if anchor: yield 'anchor', anchor[1]; i += 1; continue
        heading = re.match(r'^(#{1,3}) (.+)$', line)
        if heading: yield 'heading', (len(heading[1]), heading[2]); i += 1; continue
        picture = re.fullmatch(r'!\[([^]]*)\]\(([^)]+)\)', line)
        if picture: yield 'image', (picture[1], picture[2]); i += 1; continue
        if line.startswith('|'):
            table = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [cell.strip() for cell in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell) for cell in cells): table.append(cells)
                i += 1
            if any(len(row) != len(table[0]) for row in table): raise ValueError('Table width mismatch')
            yield 'table', table; continue
        listed = re.match(r'^(?:(\d+)\. |[-*] )(.+)$', line)
        if listed:
            ordered = listed[1] is not None; start = listed[1]; items = []
            while i < len(lines):
                item = re.match(r'^(?:(\d+)\. |[-*] )(.+)$', lines[i])
                if item is None or (item[1] is not None) != ordered: break
                items.append(item[2]); i += 1
            yield 'list', (ordered, start, items); continue
        paragraph = [line]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r'^(?:#|```|\||<a id=|!\[|\d+\. |[-*] )', lines[i]):
            paragraph.append(lines[i]); i += 1
        yield 'paragraph', ''.join(paragraph)


def link_url(value, pdf=False):
    if value.startswith('#') or '://' in value: return value
    return '../../'+value


def inline(text, pdf=False):
    token = re.compile(r'(`[^`]+`|\*\*.+?\*\*|\[[^]]+\]\([^)]+\))')
    result = []; end = 0
    for match in token.finditer(text):
        result.append(html.escape(text[end:match.start()])); item = match[0]
        if item.startswith('`'):
            style = ' style="font-family: DejaVu Sans Mono; font-size: 9pt"' if pdf else ''
            result.append(f'<code{style}>{html.escape(item[1:-1])}</code>')
        elif item.startswith('**'): result.append('<b>'+html.escape(item[2:-2])+'</b>')
        else:
            label, url = re.fullmatch(r'\[([^]]+)\]\(([^)]+)\)', item).groups()
            result.append(f'<a href="{html.escape(link_url(url,pdf),quote=True)}">{html.escape(label)}</a>')
        end = match.end()
    result.append(html.escape(text[end:])); return ''.join(result)


def content(parsed, pdf=False, image_width=620):
    output = []; chapter = False
    for kind, value in parsed:
        if kind == 'anchor':
            output.append(f'<a name="{value}" id="{value}"></a>'); chapter = True
        elif kind == 'heading':
            level, title = value
            style = ' style="color: #164c78"' if pdf and level==2 and chapter else ''
            output.append(f'<h{level}{style}>{html.escape(title)}</h{level}>'); chapter = False
        elif kind == 'paragraph': output.append('<p>'+inline(value,pdf)+'</p>')
        elif kind == 'code':
            language, body = value
            style = ' style="font-family: DejaVu Sans Mono; font-size: 8pt; background-color: #f1f5f9"' if pdf else ''
            output.append(f'<pre{style}>{html.escape(body)}</pre>')
        elif kind == 'image':
            label, filename = value; path = ROOT/filename
            if not path.is_file(): raise ValueError('Missing image: '+filename)
            if pdf:
                from PySide6.QtGui import QImage
                picture = QImage(str(path)); width = min(image_width, picture.width())
                height = round(width*picture.height()/picture.width())
                page_break=' style="page-break-before: always"' if height>200 else ''
                output.append(f'<p{page_break}><img src="{path.as_uri()}" width="{width}" height="{height}"><br>{html.escape(label)}</p>')
            else:
                encoded = base64.b64encode(path.read_bytes()).decode()
                output.append(f'<figure><img src="data:image/png;base64,{encoded}" alt="{html.escape(label,quote=True)}"><figcaption>{html.escape(label)}</figcaption></figure>')
        elif kind == 'table':
            attributes = ' border="1" cellpadding="5" cellspacing="0" width="100%"' if pdf else ''
            output.append('<table'+attributes+'><thead><tr>')
            output.extend('<th>'+inline(cell,pdf)+'</th>' for cell in value[0])
            output.append('</tr></thead><tbody>')
            for row in value[1:]:
                output.append('<tr>'+''.join('<td>'+inline(cell,pdf)+'</td>' for cell in row)+'</tr>')
            output.append('</tbody></table>')
        elif kind == 'list':
            ordered, start, items = value; tag = 'ol' if ordered else 'ul'
            attribute = f' start="{start}"' if ordered else ''
            output.append('<'+tag+attribute+'>')
            output.extend('<li>'+inline(item,pdf)+'</li>' for item in items)
            output.append('</'+tag+'>')
    return '\n'.join(output)


def build_html(parsed):
    toc = []; anchor = None
    for kind,value in parsed:
        if kind=='anchor': anchor=value
        if kind=='heading' and value[0]==2 and anchor:
            toc.append(f'<a href="#{anchor}">{html.escape(value[1])}</a>'); anchor=None
    css = '''
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f6fa;color:#23344b;font:16px/1.85 "Noto Sans CJK JP","Yu Gothic",Meiryo,sans-serif}
aside{position:fixed;inset:0 auto 0 0;width:285px;background:white;border-right:1px solid #d7e1ed;padding:24px;overflow:auto}
aside a{display:block;padding:5px 0;font-size:14px;text-decoration:none}aside a[hidden]{display:none}main{margin:28px 32px 50px 315px;background:white;border:1px solid #d7e1ed;border-radius:10px;padding:36px;max-width:1080px}
h1{font-size:29px;color:#164c78}h2{font-size:25px;border-bottom:2px solid #dce8f4;padding-top:28px;scroll-margin-top:15px}h3{font-size:19px;color:#164c78;margin-top:27px}
a{color:#175f9c}p{margin:14px 0}table{width:100%;border-collapse:collapse;font-size:14px;margin:20px 0}th,td{border:1px solid #ccd9e6;padding:9px 11px;text-align:left;vertical-align:top}th{background:#edf4fb}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f9;border:1px solid #d7e1ed;border-radius:6px;padding:16px;font:13px/1.65 Consolas,monospace}code{background:#edf2f7;padding:1px 4px;border-radius:3px}pre code{padding:0}
figure{margin:20px 0}img{max-width:100%;height:auto;border:1px solid #d7e1ed}figcaption{font-size:13px;color:#52677d}input{width:100%;padding:8px;border:1px solid #bacbdd;border-radius:4px;font:inherit}button{padding:8px 14px;background:#edf4fb;border:1px solid #bacbdd;border-radius:5px;color:#164c78;cursor:pointer}
@media(max-width:900px){aside{position:static;width:auto;max-height:260px}main{margin:15px;padding:20px}}
@media print{aside,.controls{display:none}body{background:white;font-size:10pt}main{margin:0;padding:0;border:0}h2{break-before:page}h3{break-after:avoid}pre,figure,tr{break-inside:avoid}a{color:inherit}table{font-size:9pt}}
'''
    source = '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    source += '<title>FormDesigner 詳細操作マニュアル</title><style>'+css+'</style></head><body>'
    source += '<aside aria-label="目次"><b>FormDesigner マニュアル</b><p><input id="filter" placeholder="目次を絞り込む" aria-label="目次検索"></p><nav>'+''.join(toc)+'</nav></aside>'
    source += '<main><p class="controls"><button type="button" onclick="window.print()">印刷／PDFに保存</button>　本文の検索は Ctrl+F</p>'+content(parsed)+'</main>'
    source += '''<script>document.getElementById('filter').addEventListener('input',function(){const q=this.value.toLowerCase();document.querySelectorAll('nav a').forEach(a=>{a.hidden=!a.textContent.toLowerCase().includes(q);});});</script></body></html>'''
    (DESTINATION/'index.html').write_text(source,encoding='utf-8')


def build_pdf(parsed):
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QFont,QPageSize,QPageLayout,QTextDocument
    from PySide6.QtPrintSupport import QPrinter
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    printer = QPrinter(QPrinter.HighResolution); printer.setResolution(96)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(DESTINATION/'FormDesigner-Manual.pdf'))
    printer.setDocName('FormDesigner 詳細操作マニュアル')
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4),QPageLayout.Portrait,QMarginsF(14,14,14,14),QPageLayout.Millimeter))
    document = QTextDocument(); document.setDefaultFont(QFont('DejaVu Sans',10))
    page = printer.pageRect(QPrinter.DevicePixel)
    document.setPageSize(page.size())
    width = int(page.width())-16
    body = content(parsed,pdf=True,image_width=width)
    document.setHtml('<html><head><style>body{font-family:"DejaVu Sans";font-size:10pt}h1{font-size:22pt;color:#164c78}h2{font-size:17pt}h3{font-size:12pt;color:#164c78}td{font-size:9pt}th{font-size:9pt;background-color:#edf4fb}p{margin-top:9px;margin-bottom:9px}</style></head><body>'+body+'</body></html>')
    document.print_(printer)
    if (DESTINATION/'FormDesigner-Manual.pdf').stat().st_size==0: raise ValueError('Empty PDF')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pdf',action='store_true')
    args=parser.parse_args();DESTINATION.mkdir(parents=True,exist_ok=True)
    parsed=list(blocks(SOURCE.read_text(encoding='utf-8')))
    build_html(parsed)
    if args.pdf: build_pdf(parsed)
    print('Built manual:',len(parsed),'blocks; HTML'+(' and PDF' if args.pdf else ''))


if __name__=='__main__':main()
