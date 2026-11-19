"""진행 식별자 오역을 복원하고 원본 소비 코드와 후보를 독립 대조합니다."""
from common import *
from pck_tools import patch_pack, read_pack
import shutil, re, collections

stage = WORK/'full_05'
stage.mkdir(exist_ok=True)
issue = WORK/'progression_fix'
issue.mkdir(exist_ok=True)
old_rows = read_json(issue/'direct_before.json')
bad = [r for r in old_rows if r['file'].startswith('Data/GameDefines/ThresholdUnlocks/') and r.get('field')=='message']
assert len(bad)==11 and all(r['source']!=r['target'] for r in bad)
classified = {r['id']:r for r in read_json(WORK/'census/classified.json')}
direct = {r['id']:r for r in read_json(WORK/'translation/direct_canonical.json')}
for r in bad:
    assert classified[r['id']]['classification']=='INTERNAL' and r['id'] not in direct
files = sorted({r['file'] for r in bad})
assert len(files)==4
source = ROOT/'build_candidate'/GAME/'full_04'
dest = ROOT/'build_candidate'/GAME/'full_05'
dest.mkdir(exist_ok=True)
changes = {'KoreanPatch/Resources/'+path:(RECOVERED/path).read_bytes() for path in files}
if not (dest/PCK).exists():
    for p in source.iterdir():
        if p.name!=PCK: shutil.copy2(p,dest/p.name)
    patch_pack(source/PCK,dest/PCK,changes)
manifest=read_json(WORK/'full_04/build.json')
manifest.update(candidate=str(dest),sha256=sha(dest/PCK),parent_candidate_sha256=manifest['sha256'],qa='NOT_RUN')
manifest['changes'].update({k:hashlib.sha256(v).hexdigest() for k,v in changes.items()})
write_json(stage/'build.json',manifest)
_,_,_,entries=read_pack(dest/PCK)
actual={e['name']:e['data'] for e in entries}
evidence=[]
for path in files:
    remap=actual[path+'.remap'].decode('utf8')
    target=re.search(r'path="res://([^"]+)"',remap)[1]
    assert target=='KoreanPatch/Resources/'+path
    assert actual[target]==(RECOVERED/path).read_bytes()
    messages=re.findall(r'^message = "([^"]+)"',actual[target].decode('utf8'),re.M)
    for message in messages:
        consumers=[]
        for code in RECOVERED.rglob('*.gd'):
            if 'addons' in code.parts: continue
            content=code.read_text(encoding='utf-8-sig')
            if '"'+message+'"' in content:
                consumers.append({'file':code.relative_to(RECOVERED).as_posix(),'sha256':sha(code)})
        assert consumers or message=='lower_road_threshold', message
        evidence.append({'file':path,'candidate_entry':target,'original_sha256':sha(RECOVERED/path),'message':message,'consumers':consumers,'routing':'원본에도 별도 분기가 없는 기존 이벤트; 이름은 보존' if not consumers else '원본 분기 확인'})
write_json(stage/'progression_identifiers.json',{'status':'PASS','candidate_sha256':manifest['sha256'],'resource_count':len(files),'identifiers':evidence,'restoration':'4개 리소스 전체가 추출 원본 바이트와 동일; 실행 remap 대상 확인'})
print(json.dumps({'candidate':str(dest),'sha256':manifest['sha256'],'restored_identifiers':len(evidence)},ensure_ascii=False))
