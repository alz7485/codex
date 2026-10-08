"""Emit a form's methods before the methods that call them."""
import re
from .pml_syntax import mask_non_code,own_reference_pattern,method_name_pattern,method_declaration_name


def order_methods(blocks, form_name, protected):
    by_name = {}
    for block in blocks:
        name = method_declaration_name(block[0],form_name,protected)
        by_name[name.lower()] = (name,block)
    calls = re.compile(own_reference_pattern(form_name)+r'\.('+method_name_pattern(form_name)+r')\s*\(',re.I)
    dependencies = {}
    for key,(_,block) in by_name.items():
        body = '\n'.join(block[1:])
        for marker,value in protected.items():body = body.replace(marker,value)
        dependencies[key] = list(dict.fromkeys(
            match.group(2).lower() for match in calls.finditer(mask_non_code(body))
            if match.group(2) and match.group(2).lower() in by_name and match.group(2).lower() != key))
    ordered = [];done = set();visiting = []
    def visit(key):
        if key in done:return
        if key in visiting:
            cycle = visiting[visiting.index(key):]+[key]
            names = ' → '.join(by_name[item][0] for item in cycle)
            raise ValueError('メソッドの呼び出しが循環し、定義順序を決められません: '+names)
        visiting.append(key)
        for dependency in dependencies[key]:visit(dependency)
        visiting.pop();done.add(key);ordered.append(by_name[key][1])
    for key in by_name:visit(key)
    return ordered
