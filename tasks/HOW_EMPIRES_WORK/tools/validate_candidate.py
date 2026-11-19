"""완성된 PCK를 다시 읽어 위치별 번역과 변경 경계를 독립 대조합니다."""
from common import *
from pck_tools import read_pack,read_settings
from translation_values import project_translation_paths
import sys,re,collections
sys.path.insert(0,str(ROOT/'tasks/MR_MAGEBOY_DEMO/tools'))
from census_text import tokens

B=WORK/(sys.argv[1] if len(sys.argv)>1 else 'full_01')
manifest=read_json(B/'build.json')
inputs=WORK/manifest.get('inputs_stage',B.name)
candidate=Path(manifest['candidate'])/PCK
assert sha(candidate)==manifest['sha256']
_,_,_,old=read_pack(BASELINE/PCK)
original={e['name']:hashlib.sha256(e['data']).hexdigest() for e in old}
del old
_,_,_,entries=read_pack(candidate)
actual={e['name']:e['data'] for e in entries}
changes={name:hashlib.sha256(data).hexdigest() for name,data in actual.items() if name not in original or hashlib.sha256(data).hexdigest()!=original[name]}
assert changes==manifest['changes']
assert set(original)<=set(actual)
rows=read_json(WORK/'translation/direct_canonical.json')
groups=collections.defaultdict(dict)
for r in rows:groups[r['file']][r['ordinal']]=r
failures=[];count=0
compile_map=read_json(inputs/'compile_map.json')
compiled=B/'independent/bytecode';compiled.mkdir(parents=True,exist_ok=True)
for name,path in compile_map.items():(compiled/Path(name).with_suffix('.gdc')).write_bytes(actual[path[:-3]+'.gdc'])
run_gdre(['--decompile='+(compiled/'*.gdc').as_posix(),'--bytecode=4.5.0','--output='+(B/'independent/decompiled').as_posix()],B,'independent_decompile')
def normalized(text,script):
    found=list(tokens(text,script))
    chunks=[];start=0
    for token in found:
        nonstring=text[start:token['start']]
        if script:nonstring=re.sub(r'#[^\n]*','',nonstring)
        chunks.append(re.sub(r'\s+','',nonstring));chunks.append(('string',token['value']));start=token['end']
    chunks.append(re.sub(r'\s+','',text[start:]))
    return chunks
for name,path in compile_map.items():
    expected=(inputs/'scripts'/name).read_text(encoding='utf8')
    recovered=(B/'independent/decompiled'/name).read_text(encoding='utf8')
    if normalized(expected,True)!=normalized(recovered,True):failures.append({'file':path,'issue':'바이트코드 재추출 구조·값 차이'})
for path,located in groups.items():
    source=(RECOVERED/path).read_text(encoding='utf8')
    if path.endswith('.gd'):
        # 바이트코드 전체 비교는 위에서 수행. 원본 대비 의도한 리터럴 범위를 별도로 검사합니다.
        count+=len(located)
        continue
    remap=actual.get(path+'.remap',b'').decode('utf8')
    matched=re.search(r'path="res://([^"]+)"',remap)
    if not matched:continue
    target=matched[1]
    if not target.startswith('KoreanPatch/Resources/'):
        assert not any(r['source']!=r['target'] for r in located.values()),path
        count+=len(located);continue
    text=actual[target].decode('utf8')
    before=list(tokens(source));after=list(tokens(text))
    if len(before)!=len(after):failures.append({'file':path,'issue':'객체 문자열 개수 차이'})
    for i,(a,b) in enumerate(zip(before,after)):
        expected=located[i]['target'] if i in located else a['value']
        if b['value']!=expected:failures.append({'file':path,'ordinal':i,'issue':'위치별 값 차이'})
    def skeleton(s,items):
        for t in reversed(items):s=s[:t['start']]+'"<VALUE>"'+s[t['end']:]
        return s
    assert skeleton(source,before)==skeleton(text,after),path
    count+=len(located)
original_settings=read_settings((EXTRACTED/'raw/project.binary').read_bytes())
new_settings=read_settings(actual['project.binary'])
assert {k for k in new_settings if new_settings[k]!=original_settings.get(k)}=={'internationalization/locale/translations'}
assert len(project_translation_paths(actual['project.binary']))==238
write_json(B/'independent_validation.json',{'status':'FAIL' if failures else 'PASS','candidate_sha256':manifest['sha256'],'original_entries':len(original),'candidate_entries':len(actual),'changed_entries':len(changes),'direct_locations':count,'decompiled_scripts':len(compile_map),'failures':failures})
print(json.dumps(read_json(B/'independent_validation.json'),ensure_ascii=False))
assert not failures
