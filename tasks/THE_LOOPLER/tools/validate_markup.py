"""태그의 속성·순서·중첩 상태와 자리표시자 문법을 원문과 대조합니다."""
from common import *
from build_candidate import REPORT
import json,re,collections

rows=json.loads((WORK/'translation_canonical.json').read_text('utf-8'))
rows += [{'source':r['before'],'translation':r['after'],'id':r['id']} for r in json.loads((REPORT/'asset_edits.json').read_text('utf-8')) if isinstance(r['before'],str) and isinstance(r['after'],str) and '-korean(' not in r['id']]
rows += [{'source':r['before'],'translation':r['after'],'id':'literal/'+str(r['index'])} for r in json.loads((REPORT/'literal_edits.json').read_text('utf-8'))]
standalone={'sprite','br','space','page','quad','pos'}
def trace(s):
    stack=[];events=[]
    for m in re.finditer(r'<[^>]*>',s):
        tag=m[0];name=re.match(r'</?([^\s=>]+)',tag)
        if not name:continue
        name=name[1].lower()
        if name not in standalone:
            if tag.startswith('</'):
                if stack and stack[-1]==name:stack.pop()
                else:stack.append('unmatched:'+tag)
            elif not tag.endswith('/>'):stack.append(name)
        events.append({'tag':tag,'stack':list(stack)})
    return events
def fields(s):
    tokens=[];i=0
    while i<len(s):
        if s[i:i+2] in ('{{','}}'):tokens.append(s[i:i+2]);i+=2;continue
        if s[i]!='{':i+=1;continue
        start=i;depth=1;i+=1
        while i<len(s) and depth:
            if s[i]=='{':depth+=1
            elif s[i]=='}':depth-=1
            i+=1
        tokens.append(s[start:i])
    return collections.Counter(tokens)
checks=[]
for i,r in enumerate(rows):
    a,b=r['source'],r['translation'];assert trace(a)==trace(b),(i,a,b)
    assert fields(a)==fields(b),(i,a,b)
    checks.append({'id':r.get('id',r.get('index',i)),'status':'PASS','tag_count':len(trace(a)),'placeholder_count':sum(fields(a).values())})
write_json(REPORT/'markup_validation.json',{'status':'PASS','rows':len(rows),'scope':'태그 원시 문자열과 순서/중첩 상태, sprite 속성, 중첩 및 이스케이프 중괄호와 서식 지정자 보존','checks':checks,'input_sha256':{'canonical':sha(WORK/'translation_canonical.json'),'edits':sha(REPORT/'asset_edits.json'),'literals':sha(REPORT/'literal_edits.json')}})
print('MARKUP PASS',len(rows))
