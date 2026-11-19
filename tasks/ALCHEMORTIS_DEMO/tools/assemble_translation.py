"""직접 교정한 번역 조각을 합치고 동일 문맥의 중복 문구·제어 표기를 검사한다."""
import json,re,collections,hashlib
from pck_tools import WORK
from po_format import render,parse

folder=WORK/'translation'
rows=json.loads((folder/'source.json').read_text(encoding='utf-8'))
indexed={}
for p in sorted(folder.glob('ko_*.tsv')):
    for line in p.read_text(encoding='utf-8-sig').splitlines():
        if not line:continue
        index,value=line.split('\t',1);index=int(index)
        assert index not in indexed,(p,index)
        indexed[index]=value.replace('\\n','\n')
def source(r):return r['text'] or r['forms']['0']
by_source=collections.defaultdict(set)
for i,text in indexed.items():by_source[source(rows[i])].add(text)
missing=[];targets={};provenance=[];failures=[]
for i,row in enumerate(rows):
    if i==0:continue
    s=source(row)
    if i in indexed:t=indexed[i];reason='개별 문맥 번역'
    elif s=='????':t=s;reason='원본 데모의 가려진 표시 유지; 개별 코드 참조 분류는 후속 조사'
    elif len(by_source[s])==1:t=next(iter(by_source[s]));reason='동일 원문의 검토 번역 재사용'
    else:missing.append((i,row['key'],s));continue
    targets[row['key']]=t
    provenance.append({'index':i,'key':row['key'],'source_sha256':hashlib.sha256(s.encode()).hexdigest(),'target':t,'reason':reason})
    tokens=lambda text:collections.Counter(re.findall(r'(?<!\{)\{\d+(?:[^{}]*)\}(?!\})',text))
    keywords=lambda text:collections.Counter(re.findall(r'\{\{(!?keyword_\w+)(?:\([^{}]*\))?\}\}',text))
    if tokens(s)!=tokens(t):failures.append([i,'자리표시자',list(tokens(s)),list(tokens(t))])
    if keywords(s)!=keywords(t):failures.append([i,'아이콘/용어',list(keywords(s)),list(keywords(t))])
    if s.count('\n')!=t.count('\n'):failures.append([i,'줄바꿈',s.count('\n'),t.count('\n')])
    if not t.strip():failures.append([i,'빈 번역'])
(folder/'ko.json').write_text(json.dumps(targets,ensure_ascii=False,indent=2),encoding='utf-8')
(folder/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
(folder/'missing.json').write_text(json.dumps(missing,ensure_ascii=False,indent=2),encoding='utf-8')
(folder/'format_failures.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2),encoding='utf-8')
print('번역',sum(v!='????' for v in targets.values()),'원본 가림',sum(v=='????' for v in targets.values()),'누락',len(missing),'형식 오류',len(failures))
print(json.dumps(missing,ensure_ascii=False,indent=2));print(json.dumps(failures,ensure_ascii=False,indent=2))
if not missing and not failures:
    text=render(rows,targets)
    assert len(parse(text))==len(rows)
    (folder/'ko.po').write_text(text,encoding='utf-8')
