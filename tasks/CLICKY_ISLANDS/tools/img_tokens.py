"""번역 작업용: 긴 그림 태그([img]res://…[/img])를 짧은 표식(<i:이름>)으로 바꿨다가 되돌립니다.

표식과 원래 태그는 1:1이라 되돌린 결과에서 태그 글자가 하나도 달라지지 않습니다.
"""
import re

TAG = re.compile(r'\[img(=[a-z]+)?\](res://[^\[\]]+?)\[/img\]')
ALIGN = {None: 'i', '=bottom': 'ib', '=center': 'ic', '=top': 'it'}


def token_for(match, table):
    full = match[0]
    if full in table:
        return table[full]
    base = match[2].rsplit('/', 1)[-1]
    for suffix in ('_atlas_texture.tres', '.tres', '.png'):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    name = f'<{ALIGN[match[1]]}:{base}>'
    number = 2
    while name in table.values():
        name = f'<{ALIGN[match[1]]}:{base}{number}>'
        number += 1
    table[full] = name
    return name


def shorten(text, table):
    return TAG.sub(lambda m: token_for(m, table), text)


def restore(text, table):
    reverse = {token: full for full, token in table.items()}
    result = re.sub(r'<i[bct]?:[^<>]+>', lambda m: reverse[m[0]], text)
    return result
