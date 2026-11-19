"""남은 필드·본문·코드 위치를 비공개 검토 자료로 정리합니다."""
from common import *
from collections import Counter,defaultdict
import re

inv=json.loads((EXTRACT/'inventory_fixed.json').read_text(encoding='utf8'))
canon=json.loads((WORK/'canonical_translation.json').read_text(encoding='utf8'))
done={(r['file'],r['path_id'],tuple(r['field'])) for r in canon}
groups=defaultdict(list)
for f in inv['files']:
    for r in f['strings']:
        if (f['relative_path'],r['path_id'],tuple(r['field_path'])) in done:continue
        if r['field_path']==['m_Name']:continue
        groups[(r['class'],'.'.join(str(v) if not isinstance(v,int) else '*' for v in r['field_path']))].append((f['relative_path'],r['path_id'],r['source']))
rows=[]
for (cls,field),values in sorted(groups.items()):
    # 외부 서비스 인증 자료는 값 자체를 출력하지 않습니다.
    hidden=any(v in field.lower() for v in ['token','password','board','apikey'])
    samples=list(dict.fromkeys(v[2] for v in values))
    rows.append(dict(cls=cls,field=field,count=len(values),unique=len(samples),samples=['[비공개 연결 설정]'] if hidden else samples[:8]))
save_json(EXTRACT/'remaining_fields.json',rows)
texts=[dict(file=f['relative_path'],**r) for f in inv['files'] for r in f['text_assets']]
save_json(EXTRACT/'text_assets.json',texts)
print('FIELDS',len(rows));print(json.dumps(rows,ensure_ascii=False,indent=1))
print('TEXTS',json.dumps([dict(file=r['file'],path_id=r['path_id'],name=r['name'],length=len(r['text']),sample=r['text'][:120]) for r in texts],ensure_ascii=False))
