"""복원된 모든 장면·자원 문자열을 원본 위치와 함께 수집한다."""
from pck_tools import WORK,EXTRACTED
import re,json,collections,hashlib
root=EXTRACTED/'recovered';rows=[];fields=collections.Counter()
for path in sorted([*root.rglob('*.tscn'),*root.rglob('*.tres')]):
    text=path.read_text(encoding='utf-8')
    for match in re.finditer(r'^([\w/]+) = "((?:\\.|[^"\\])*)"',text,re.M):
        value=json.loads('"'+match[2]+'"',strict=False)
        fields[match[1]]+=1
        rows.append({'path':path.relative_to(root).as_posix(),'line':text[:match.start()].count('\n')+1,'field':match[1],'source':value,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(WORK/'discovery/resource_strings.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(fields)
for r in rows:
    if r['field'] in ['text','tooltip_text','placeholder_text','title','dialog_text'] and not r['source'].startswith('UI_'):
        print(r['path']+':'+str(r['line'])+' '+r['field']+' '+repr(r['source']))
