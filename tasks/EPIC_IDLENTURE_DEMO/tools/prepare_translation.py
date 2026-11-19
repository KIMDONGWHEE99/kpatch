"""표시 필드의 위치와 원문을 연결하고 번역 원본 목록을 만듭니다."""
from common import *
import re
rows=json.loads((EXTRACT/'strings.json').read_text(encoding='utf8'))+json.loads((EXTRACT/'resolved_strings.json').read_text(encoding='utf8'))
display={'m_text','m_Text','StatsDisplayName','UpgradesDisplayName','Description','TooltipDescription','DescriptionTemplate','DisplayName','SummaryDescription','ExtraText','Text','_title','_longTitle'}
selected=[]
for r in rows:
    field=r['field'];leaf=field.rsplit('/',1)[-1]
    visible=r['type']=='MonoBehaviour' and (leaf in display or (leaf=='Name' and (field=='/Name' or re.match(r'^/(Armors|Helmets|Gloves|Cloaks|Rings|Weapons|Boots|Amulets)/',field))))
    if visible:selected.append(r)
unique=list(dict.fromkeys(r['source'] for r in selected))
save(WORK/'translation_sources.json',unique)
save(WORK/'translation_occurrences.json',[dict(r,translation_id=unique.index(r['source'])) for r in selected])
(WORK/'translation_review.txt').write_text('\n'.join(f'{i}: {s!r}' for i,s in enumerate(unique)),encoding='utf8')
print('표시 위치',len(selected),'고유 문구',len(unique))
