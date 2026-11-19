"""복구 뒤에도 이진 형식으로 남은 자원을 텍스트로 변환하여 빠짐없이 조사합니다."""
from common import *
import sys,re,collections
sys.path.insert(0,str(ROOT/'tasks/MR_MAGEBOY_DEMO/tools'))
from census_text import tokens
stage=WORK/'census/extra_text';stage.mkdir(exist_ok=True)
missing=read_json(WORK/'census/zero_or_unscanned_files.json')
binary=[r for r in missing if Path(r['path']).suffix in ('.res','.scn')]
assert len({Path(r['path']).name for r in binary})==len(binary)
for i in range(0,len(binary),30):
    group=binary[i:i+30]
    absent=[r for r in group if not (stage/Path(r['path']).name).exists()]
    if absent:
        run_gdre(['--bin-to-txt='+(RECOVERED/r['path']).as_posix() for r in absent]+['--output='+stage.as_posix()],stage,'convert_'+str(i))
    print('converted',min(i+30,len(binary)),flush=True)
rows=[];files=[]
for r in missing:
    rel=r['path'];ext=Path(rel).suffix
    p=stage/Path(rel).name if ext in ('.res','.scn') else RECOVERED/str(Path(rel).with_suffix('.gd') if ext=='.gdc' else rel)
    text=p.read_text(encoding='utf8')
    recovered_hash=sha(p)
    scan_text=re.sub(r'/\*.*?\*/|//[^\n]*',lambda m:re.sub(r'[^\n]',' ',m[0]),text,flags=re.S) if ext=='.gdshader' else text
    try:found=list(tokens(scan_text,ext=='.gdc'))
    except Exception as error:raise ValueError((rel,str(error))) from error
    files.append({'file':rel,'original_sha256':r['sha256'],'recovered':str(p.relative_to(WORK)) if p.is_relative_to(WORK) else str(p.relative_to(RECOVERED)),'recovered_sha256':sha(p),'strings':len(found)})
    for i,t in enumerate(found):
        start=text.rfind('\n',0,t['start'])+1;end=text.find('\n',t['end'])
        context=text[start:min(end if end>=0 else len(text),start+1000)]
        value=t['value'];prefix=text[max(start,t['start']-150):t['start']]
        status='UNKNOWN';reason='추가 자원 검토 대기'
        if value.startswith(('res://','uid://')):
            status='INTERNAL';reason='외부 자산 경로·UID'
        elif context.startswith('[') or re.search(r'(ExtResource|SubResource|NodePath)\([^)]*$',prefix):
            status='INTERNAL';reason='자원 선언·참조·노드 속성 경로'
        elif ext=='.gdshader':
            status='INTERNAL';reason='셰이더 선언·속성으로 화면 문구 소비 없음'
        rows.append({'id':rel+'::'+str(i),'file':rel,'original_sha256':r['sha256'],'recovered_sha256':recovered_hash,'source':value,'source_sha256':hashlib.sha256(value.encode()).hexdigest(),'context':context[:1000],'prefix':prefix[-150:],'classification':status,'evidence':reason})
write_json(WORK/'census/extra_files.json',files)
write_json(WORK/'census/extra_strings.json',rows)
pending=[r for r in rows if r['classification']=='UNKNOWN']
write_json(WORK/'census/extra_pending.json',pending)
print('files',len(files),'strings',len(rows),'pending',len(pending))
print(collections.Counter(r['file'].split('/')[0] for r in pending))
unique={r['source']:r for r in pending}
for r in list(unique.values())[:75]:print(r['file'],repr(r['source'])[:130],r['prefix'][:80])
