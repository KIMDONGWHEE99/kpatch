"""실제 검수 사본을 다시 읽고 배포 후보와의 차이를 11개 허용 수정으로 제한합니다."""
from common import *
from build_candidate import CANDIDATE,REPORT,field_set
import json,copy,collections

qa=WORK/'qa_c04/game';isolation=json.loads((qa.parent/'isolation.json').read_text('utf-8'))
original=bytearray((CANDIDATE/'GameAssembly.dll').read_bytes());actual=bytearray((qa/'GameAssembly.dll').read_bytes())
for r in isolation['overrides']:
    if 'offset' not in r:continue
    i=r['offset'];b=bytes.fromhex(r['before']);a=bytes.fromhex(r['after']);assert original[i:i+len(b)]==b and actual[i:i+len(a)]==a
    actual[i:i+len(b)]=b
assert actual==original
gen=generator();configure_references(gen);relative='The Loopler_Data/data.unity3d'
a=UnityPy.load(str(CANDIDATE/relative));b=UnityPy.load(str(qa/relative));a.typetree_generator=gen;b.typetree_generator=gen
left={(o.assets_file.name,o.path_id,o.type.name):o for o in a.objects};right={(o.assets_file.name,o.path_id,o.type.name):o for o in b.objects};assert left.keys()==right.keys()
allowed=collections.defaultdict(list)
for r in isolation['overrides']:
    if 'asset' in r:allowed[(r['asset'],r['path_id'])].append(r)
for k,o in left.items():
    p=right[k]
    if k[:2] not in allowed:assert o.get_raw_data()==p.get_raw_data(),k;continue
    before=read_tree(o);after=read_tree(p)
    for r in allowed[k[:2]]:field_set(after,r['field'],r['before'])
    assert before==after,k
for f in isolation['files']:
    assert sha(CANDIDATE/f['path'])==f['candidate_sha256']
    assert sha(qa/f['path'])==f['qa_sha256']
    if f['path'] not in ('GameAssembly.dll',relative):assert f['candidate_sha256']==f['qa_sha256']
write_json(qa.parent/'boundary_validation.json',{'status':'PASS','verified_objects':len(left),'verified_files':len(isolation['files']),'allowed_overrides':len(isolation['overrides']),'isolation_sha256':sha(qa.parent/'isolation.json'),'candidate_build_sha256':sha(REPORT/'build.json')})
print('QA BOUNDARY PASS',len(left),'objects',len(isolation['overrides']),'overrides')
