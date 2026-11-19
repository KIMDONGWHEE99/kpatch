"""서식의 순서·중첩·아이콘 속성·제어 문자를 비교합니다."""
from common import *
import re, collections
from translation_values import locale_tables, expand

PRINTF = re.compile(r'%(?:[-+0#]*\d*(?:\.\d+)?[sdifuxXoegGc]|%)')
BRACE = re.compile(r'\{(?:@?[A-Za-z_0-9.]+)\}')
TAG = re.compile(r'\[(/?)(b|i|u|s|color|font|font_size|outline_size|outline_color|url|img|center|left|right|fill|table|cell|wave|shake|rainbow|pulse|indent|code|bgcolor|fgcolor)([^\]]*)\]')

def tags(value):
    stack=[]; errors=[]; order=[]
    for m in TAG.finditer(value):
        closing,name,attrs=m.groups()
        order.append(m[0])
        if closing:
            if not stack or stack[-1]!=name: errors.append(('close',m[0],list(stack)))
            else:stack.pop()
        else:stack.append(name)
    return order,errors,stack

rows=read_json(WORK/'translation/canonical.json')+read_json(WORK/'translation/direct_canonical.json')
english,korean,_=locale_tables()
diffs=[]
for r in rows:
    s,t=r['source'],r['target']
    if t is None:raise ValueError(r['id'])
    if '.translation::' in r['id']:
        s,t=expand(s,english),expand(t,korean)
    failures=[]
    if PRINTF.findall(s)!=PRINTF.findall(t):failures.append('printf_order')
    if collections.Counter(BRACE.findall(s))!=collections.Counter(BRACE.findall(t)):failures.append('brace_tokens')
    if [c for c in s if c in '\n\r\t']!=[c for c in t if c in '\n\r\t']:failures.append('control_order')
    a,b=tags(s),tags(t)
    if a[0]!=b[0]:failures.append('tag_order')
    if (b[1] or b[2]) and a!=b:failures.append('tag_balance_changed')
    if re.findall(r'\[img[^\]]*\].*?\[/img\]',s)!=re.findall(r'\[img[^\]]*\].*?\[/img\]',t):failures.append('icon_attributes_or_path')
    if failures:diffs.append({'id':r['id'],'file':r['file'],'source':s,'target':t,'failures':failures,'source_tags':a,'target_tags':b})
write_json(WORK/'translation/format_differences.json',diffs)
print(json.dumps({'rows':len(rows),'differences':len(diffs),'kinds':dict(collections.Counter(k for r in diffs for k in r['failures']))}))
for r in diffs:
    print(r['id'],r['failures'],repr(r['source'])[:230],repr(r['target'])[:230])
