"""번역표와 직접 문구의 원본 위치를 연결하고 미확인 항목을 보존합니다."""
from common import *
import csv, re, sys, collections, bisect
sys.path.insert(0,str(ROOT/'tasks/MR_MAGEBOY_DEMO/tools'))
from census_text import tokens

inventory = {r['path']:r for r in read_json(WORK/'pck_inventory.json')}
locale_rows = []
for path in sorted((RECOVERED/'Data/Localization').rglob('*.csv')):
    original = path.relative_to(RECOVERED).with_suffix('.en.translation').as_posix()
    for row in csv.DictReader(path.open(encoding='utf-8-sig',newline='')):
        locale_rows.append({'id':original+'::'+row['key'],'file':original,'file_sha256':inventory[original]['sha256'],
            'key':row['key'],'source':row['en'],'source_sha256':hashlib.sha256(row['en'].encode()).hexdigest(),
            'category':path.parent.name,'classification':'UNKNOWN','target':None})
write_json(WORK/'translation/locale_inventory.json',locale_rows)
write_json(WORK/'translation/source_by_key.json',{r['key']:r['source'] for r in locale_rows})
duplicate_counts = collections.Counter(r['key'] for r in locale_rows)
write_json(WORK/'translation/duplicate_keys.json',[r for r in locale_rows if duplicate_counts[r['key']]>1])
keys = {r['key'] for r in locale_rows}
records, errors = [], []
for path in sorted(RECOVERED.rglob('*')):
    rel = path.relative_to(RECOVERED).as_posix()
    if path.suffix not in ('.gd','.tscn','.tres','.godot','.json','.gdshader') or rel.startswith('.godot/'):
        continue
    if path.suffix == '.gd':
        original = rel[:-3]+'.gdc'
    elif rel+'.remap' in inventory:
        match = re.search(r'path="res://([^"]+)"',(EXTRACTED/'raw'/(rel+'.remap')).read_text(encoding='utf-8'))
        original = match[1].replace("\\'", "'").replace('\\"', '"') if match else None
    elif rel == 'project.godot':
        original = 'project.binary'
    else:
        original = rel
    original_info = inventory.get(original,{})
    try:
        text = path.read_text(encoding='utf-8-sig')
        recovered_hash = sha(path)
        scan_text = text
        if path.suffix == '.gdshader':
            # 셰이더의 C 형식 주석을 같은 길이 공백으로 바꿔 원본 위치를 보존합니다.
            scan_text = re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: re.sub(r'[^\n]', ' ', m[0]), text, flags=re.S)
        newlines = [m.start() for m in re.finditer('\n', text)]
        for ordinal, token in enumerate(tokens(scan_text, path.suffix == '.gd',path.suffix=='.godot')):
            line_start = text.rfind('\n',0,token['start'])+1
            line_end = text.find('\n',token['end'])
            context = text[line_start:line_end if line_end>=0 else len(text)].strip()
            prefix = text[line_start:token['start']]
            value = token['value']
            status, reason = 'UNKNOWN','표시 소비 위치 확인 필요'
            if value in keys:
                status,reason='INTERNAL','원본 영어 언어표에 대응하는 번역 식별자; 값은 해당 언어표에서 번역'
            elif value.startswith(('res://','uid://','user://')):
                status,reason='INTERNAL','자산·노드·사용자 저장 경로'
            elif path.suffix in ('.tscn','.tres') and (context.startswith('[') or re.search(r'(ExtResource|SubResource|NodePath)\([^)]*$',prefix)):
                status,reason='INTERNAL','Godot 장면/리소스의 선언·참조 문법'
            elif path.suffix=='.gd' and token['start']>0 and text[token['start']-1] in ('&','$','^'):
                status,reason='INTERNAL','Godot 노드 경로·StringName 식별자 문법'
            records.append({'id':rel+'::'+str(ordinal),'file':rel,'original_file':original,
                'original_sha256':original_info.get('sha256'),'recovered_sha256':recovered_hash,
                'line':bisect.bisect_left(newlines,token['start'])+1,'ordinal':ordinal,
                'source':value,'source_sha256':hashlib.sha256(value.encode()).hexdigest(),
                'start':token['start'],'end':token['end'],'quote':token['quote'],
                'context':context,'prefix':prefix.strip(),'classification':status,'evidence':reason})
    except Exception as error:
        errors.append({'file':rel,'original_file':original,'original_sha256':original_info.get('sha256'),'error':str(error),'status':'UNKNOWN'})
write_json(WORK/'census/strings.json',records)
write_json(WORK/'census/extraction_errors.json',errors)
summary={'locale_rows':len(locale_rows),'strings':len(records),'classifications':dict(collections.Counter(r['classification'] for r in records)),
         'errors':errors,'unknown_dirs':collections.Counter(r['file'].split('/')[0] for r in records if r['classification']=='UNKNOWN')}
write_json(WORK/'census/summary.json',summary)
print(json.dumps(summary,ensure_ascii=False))
