"""직접 문구의 번역을 원본 위치와 연결합니다. 미번역을 자동 제외하지 않습니다."""
from common import *
import re, collections
from translation_values import locale_tables, expand

rows=read_json(WORK/'census/classified.json')
_,korean_table,_=locale_tables()
locales=read_json(WORK/'translation/canonical.json')
by_source=collections.defaultdict(set)
by_key={}
for r in locales:
    by_source[r['source'].strip().lower()].add(r['target'].strip())
    by_key.setdefault(r['key'],r['target'])
manual={}
for version in (1,2,3):
    source_path=WORK/f'translation/direct_list_v{version}.json'
    if not source_path.exists(): continue
    sources=read_json(source_path)
    for path in sorted((WORK/'translation').glob(f'direct_v{version}*.tsv')):
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line:continue
            number,target=line.split('\t',1)
            source=sources[int(number)]['source']
            target=target.replace('\\n','\n').replace('\\t','\t')
            if source in manual and manual[source]!=target:raise ValueError(('중복 직접 번역',source))
            manual[source]=target
extra=WORK/'translation/direct_extra.json'
if extra.exists():manual.update(read_json(extra))
missing={};out=[]
for r in rows:
    if r['classification'] not in ('VISIBLE_TRANSLATE','VISIBLE_KEEP'):continue
    s=r['source']; target=None
    if r['classification']=='VISIBLE_KEEP':target=s
    elif s in manual:target=manual[s]
    elif len(by_source[s.strip().lower()])==1:
        target=next(iter(by_source[s.strip().lower()]))
        target=s[:len(s)-len(s.lstrip())]+target+s[len(s.rstrip()):]
    elif 'ADVANCE_'+s.upper() in by_key and re.fullmatch('[a-z_0-9]+',s):
        target=by_key['ADVANCE_'+s.upper()]
    elif re.fullmatch(r'(?:\[/?[^\]]+\]|%[-+0#\d.]*[sdifuxXoegGc%]|[^A-Za-z])*',s):
        target=s
    if s=='Maine' and ('NorthAmerica' in r['file'] or 'America' in r['file']):target='메인'
    if target is not None and '{@' in target:target=expand(target,korean_table)
    item={**r,'target':target,'translation_key':'HEW_DIRECT_'+hashlib.sha256(r['id'].encode()).hexdigest()[:16].upper()}
    out.append(item)
    if target is None:missing.setdefault(s,[]).append({'id':r['id'],'file':r['file'],'line':r['line'],'function':r['function'],'context':r['context']})
write_json(WORK/'translation/direct_canonical.json',out)
new=[{'index':i,'source':s,'locations':loc} for i,(s,loc) in enumerate(missing.items())]
write_json(WORK/'translation/direct_pending.json',new)
print(json.dumps({'locations':len(out),'translated':sum(x['target'] is not None for x in out),'missing_unique':len(new)},ensure_ascii=False))
