"""실제 검수에서 발견한 기본 툴팁 대비 문제와 같은 출처 화면을 보완합니다."""
from common import *
from pck_tools import read_pack,patch_pack
import re,shutil

old=ROOT/'build_candidate'/GAME/'full_01'
new=ROOT/'build_candidate'/GAME/'full_02'
stage=WORK/'full_02';stage.mkdir(exist_ok=True)
assert not new.exists()
new.mkdir()
for p in old.iterdir():
    if p.name!=PCK:shutil.copy2(p,new/p.name)
changes={};boundaries=[]
for p in RECOVERED.rglob('*.tres'):
    s=p.read_text(encoding='utf8')
    if 'type="Theme"' not in s[:100]:continue
    m=re.search(r'^Label/colors/font_color = Color\(([^)]+)\)',s,re.M)
    if not m or max(float(v) for v in m[1].split(',')[:3])>=.65:continue
    assert 'TooltipLabel/' not in s and 'TooltipPanel/' not in s
    rel=p.relative_to(RECOVERED).as_posix()
    target='KoreanPatch/Resources/'+rel
    added='TooltipLabel/colors/font_color = Color(1, 0.941176, 0.831373, 1)\n'
    edited=s.rstrip()+'\n'+added
    remap=(EXTRACTED/'raw'/(rel+'.remap')).read_text(encoding='utf8')
    changes[target]=edited.encode('utf8')
    changes[rel+'.remap']=re.sub(r'path="res://[^"]+"','path="res://'+target+'"',remap).encode('utf8')
    boundaries.append({'file':rel,'source_sha256':sha(p),'change':added.strip(),'reason':'기본 툴팁의 검은 배경에 상속되는 어두운 Label 글자색 대신 전용 밝은 색 지정'})
assert len(boundaries)==8
patch_pack(old/PCK,new/PCK,changes)
_,_,_,entries=read_pack(new/PCK)
actual={e['name']:e['data'] for e in entries}
for path,value in changes.items():assert actual[path]==value
manifest=read_json(WORK/'full_01/build.json')
manifest.update(candidate=str(new),sha256=sha(new/PCK),inputs_stage='full_01',parent_candidate_sha256=manifest['sha256'],qa='NOT_RUN')
manifest['changes'].update({k:hashlib.sha256(v).hexdigest() for k,v in changes.items()})
write_json(stage/'build.json',manifest)
write_json(stage/'resource_adjustments.json',boundaries)
print(json.dumps({'candidate':str(new),'sha256':manifest['sha256'],'themes':len(boundaries)},ensure_ascii=False))
