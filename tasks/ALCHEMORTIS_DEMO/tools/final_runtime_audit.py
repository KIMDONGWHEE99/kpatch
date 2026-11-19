"""실제 그래픽 검수 기록과 검수 전용 변경 경계를 독립 대조합니다."""
from pck_tools import ROOT, WORK, read_pack
from pathlib import Path
import json, hashlib, re, os, struct, copy, collections

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d): p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
qa=WORK/'qa_09'; candidate=ROOT/'build_candidate/ALCHEMORTIS_DEMO/ko_1.0.0_c07'
report={"candidate":candidate.name,"scope":"실제 GPU의 대표 화면·전수 데이터·격리 경계. 전체 무작위 회차 완주는 포함하지 않음."}
boundary=read(qa/'qa_boundary.json')
original={p.relative_to(candidate).as_posix():sha(p) for p in candidate.rglob('*') if p.is_file()}
actual={p.relative_to(qa/'game').as_posix():sha(p) for p in (qa/'game').rglob('*') if p.is_file()}
differences={k for k in original.keys()|actual.keys() if original.get(k)!=actual.get(k)}
assert differences=={r['path'] for r in boundary['changes']}
for r in boundary['changes']:
    assert original.get(r['path'])==r['candidate_sha256'] and actual[r['path']]==r['qa_sha256']
observed=read(qa/'observed_process.json'); launch=read(qa/'launch.json')
assert Path(observed['Path']).resolve()==(qa/'game/Alchemortis Demo.exe').resolve()
assert observed['Id']==launch['pid']
assert actual['Alchemortis Demo.exe']==launch['exe_sha256'] and actual['Alchemortis Demo.pck']==launch['pck_sha256']
report['process']={"status":"PASS","path":observed['Path'],"pid":observed['Id'],"hashes":{k:actual[k] for k in ('Alchemortis Demo.exe','Alchemortis Demo.pck','data_Alchemortis_windows_x86_64/Alchemortis.dll')}}

# 코드 전체를 새로 읽은 결과에서 정확히 네 메서드만 검수용으로 달라야 합니다.
a=read(WORK/'discovery/candidate_code.json.snapshot.json');b=read(WORK/'discovery/qa09_code.json.snapshot.json')
assert a['types']==b['types']
expected={m['method']:copy.deepcopy(m) for m in a['methods']}
disabled=['System.Void SentryAutoInit::Init()','System.Void Game.Steam.SteamService::UnlockAchievement(System.String)','System.Void Game.Steam.SteamService::OpenWebOverlay(System.String)']
for name in disabled:
    expected[name]['locals']=[];expected[name]['instructions']=[{'opcode':'ret','operand':''}]
name='System.Void Game.Autoload.VisualUtilities::_Ready()';ins=expected[name]['instructions'];at=len(ins)-1
for i in ins:
    if i['operand'].startswith('branch:'):
        n=int(i['operand'][7:]);i['operand']='branch:'+str(n+1 if n>=at else n)
    elif i['operand'].startswith('switch:'):
        i['operand']='switch:'+','.join(str(int(n)+1 if int(n)>=at else int(n)) for n in i['operand'][7:].split(','))
ins.insert(at,{'opcode':'call','operand':'System.Void KoreanQa.Runner::Start()'})
assert len(b['methods'])==len(expected)
for m in b['methods']:assert m==expected[m['method']],m['method']
for ext in ['attributes','enums']:
    assert read(WORK/f'discovery/candidate_code.json.{ext}.json')==read(WORK/f'discovery/qa09_code.json.{ext}.json')

# 프로젝트 설정은 별도로 해독하고 나머지 묶음 자산은 바이트 단위로 대조합니다.
packs=[{e['name']:e['data'] for e in read_pack(p/'Alchemortis Demo.pck')[3]} for p in (candidate,qa/'game')]
assert set(packs[1])==set(packs[0])|{'korean_qa_observer.gd'}
for k,v in packs[0].items():
    if k!='project.binary':assert packs[1][k]==v,k
def settings(data):
    assert data[:4]==b'ECFG';pos=8;out={}
    for _ in range(struct.unpack_from('<I',data,4)[0]):
        n=struct.unpack_from('<I',data,pos)[0];pos+=4;k=data[pos:pos+n].decode();pos+=n
        n=struct.unpack_from('<I',data,pos)[0];pos+=4;out[k]=data[pos:pos+n];pos+=n
    assert pos==len(data);return out
base,specific=map(settings,[p['project.binary'] for p in packs])
for k,v in base.items():
    if k not in boundary['project_settings']:assert specific[k]==v,k
assert set(specific)==set(base)|set(boundary['project_settings'])
for k,v in boundary['project_settings'].items():
    raw=specific[k];kind,n=struct.unpack_from('<II',raw)
    assert (kind==1 and bool(n)==v) if isinstance(v,bool) else (kind==4 and raw[8:8+n].decode()==v),k
assert packs[1]['korean_qa_observer.gd']==(ROOT/'tasks/ALCHEMORTIS_DEMO/tools/qa_observer.gd').read_bytes()
depsname='data_Alchemortis_windows_x86_64/Alchemortis.deps.json';deps=read(qa/'game'/depsname)
deps['libraries'].pop('QaRunner/1.0.0')
for target in deps['targets'].values():
    if 'Alchemortis/1.0.0' in target:
        assert target['Alchemortis/1.0.0']['dependencies'].pop('QaRunner')=='1.0.0'
        target.pop('QaRunner/1.0.0')
assert deps==read(candidate/depsname)
report['qa_boundary']={'status':'PASS','files_changed_or_added':len(differences),'methods_changed':4,'pack_entries_changed_or_added':2,'production_contains_helper':False}

cards=read(qa/'runtime_card_inventory.json');catalog=read(qa/'runtime_catalog.json')
assert not cards['errors'] and not catalog['errors'] and len(cards['cards'])==275
assert all(len(c['tiers'])==5 for c in cards['cards'])
english=[]
def check_text(text,path):
    text=re.sub(r'\[img[^\]]*\].*?\[/img\]','',text,flags=re.S)
    text=re.sub(r'\[[^\]]*\]','',text)
    # 키워드의 표시 부분은 지우지 않고 남겨 영문 누락도 검출합니다.
    text=re.sub(r'\{\{!?keyword_\w+\((.*?)\)\}\}',r'\1',text)
    text=re.sub(r'\{\{!?keyword_\w+\}\}','',text)
    words=re.findall(r'[A-Za-z][A-Za-z_]+',text)
    words=[x for x in words if not re.fullmatch(r'[IVX]+',x)]
    if words:english.append({'path':path,'text':text,'words':words})
for c in cards['cards']:
    check_text(c['name'],c['id']+'/name');check_text(c['flavor'],c['id']+'/flavor')
    for t in c['tiers']:
        for d in t['descriptions']:check_text(d['translated'],c['id']+'/'+str(t['tier'])+'/'+d['Key'])
def leaves(value,path):
    if isinstance(value,str):check_text(value,path)
    elif isinstance(value,dict):
        for k,v in value.items():leaves(v,path+'/'+k)
    elif isinstance(value,list):
        for k,v in enumerate(value):leaves(v,path+'/'+str(k))
for r in catalog['rows']:leaves(r['value'],r['category']+'/'+r['id'])
report['runtime_data']={'status':'PASS' if not english else 'FAIL','cards':275,'card_tiers':1375,'catalog_categories':dict(collections.Counter(r['category'] for r in catalog['rows'])),'errors':0,'unreviewed_english':english,'empty_unlock_reflection':sum(r['category']=='unlock' and not r['value'] for r in catalog['rows'])}

capture_rows=[]
for p in list(qa.glob('*.json'))+list((qa/'cards_pixel').glob('*.json')):
    data=read(p)
    if isinstance(data,list) and data and isinstance(data[0],dict) and 'rendered' in data[0]:
        capture_rows.extend((str(p.relative_to(qa)),r) for r in data)
missing=[{'file':p,'node':r['path'],'missing':r['missing']} for p,r in capture_rows if r['missing']]
assert not missing,missing
texts=list(read(WORK/'translation/ko_full.json').values())+[r['target'] for r in read(WORK/'translation/code_changes.json')]+['한국어','보관함','판매']
needed={c for c in ''.join(texts) if not c.isspace()}
available=set(read(WORK/'fonts/config.json')['characters'])
assert not needed-available,needed-available
assert all(not r['missing'] and not r['differences'] for r in read(WORK/'fonts/semantic_validation.json'))
report['font']={'status':'PASS','required_characters':len(needed),'fallback_characters':len(available),'observed_text_nodes':len(capture_rows),'missing_glyphs':missing}
logs='\n'.join((qa/p).read_text(encoding='utf-8',errors='replace') for p in ['game.log','stdout.log','stderr.log'])
error_lines=[l for l in logs.splitlines() if re.search(r'\b(ERROR|ERR|Exception)\b|missing.*(glyph|font)|glyph.*missing|failed to load',l,re.I)]
decompiled=ROOT/'extracted_private/ALCHEMORTIS_DEMO/steam_25423154/decompiled'
fixture=decompiled/'Game.UI.RunOverview/RunOverview.cs';manager=decompiled/'Game.Manager/ArtifactManager.cs'
fixture_ids=['win_at_difficulty_four','apply_armor','acquire_undead_cards','complete_alchemy_two']
assert all('"'+x+'"' in fixture.read_text(encoding='utf-8') for x in fixture_ids)
assert 'ArtifactManager instance is not valid, cannot get artifacts.' in manager.read_text(encoding='utf-8')
known_messages=['No challenge with id '+x for x in fixture_ids]+['ArtifactManager instance is not valid, cannot get artifacts.']
fixture_errors=[];unexpected=[]
for line in error_lines:
    message=re.sub(r'\x1b\[[0-9;]*m','',line.split('[ERR]')[-1]).strip()
    (fixture_errors if message in known_messages else unexpected).append(line)
report['log']={'status':'PASS' if not unexpected else 'FAIL','unexpected_errors':unexpected,'original_fixture_diagnostics':fixture_errors,'fixture_evidence':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in (fixture,manager)],'fixture_reason':'원본 승리 시험 데이터의 폐기된 도전 과제 4개, 모험 외부에서 카드 검사기를 여는 시험의 보물 관리자 부재 14건. 일반 모험·번역·로딩 오류와 구분함.','known_probe_warning':'Set tier of reagent! This needs to be fixed! — 원본 시약의 등급 1~5 전수 조회에서 발생하는 원본 진단 문구','stderr_bytes':(qa/'stderr.log').stat().st_size}

def save_snapshot():
    roots=[Path(os.environ['APPDATA'])/'Alchemortis Demo']+sorted(Path('D:/steam/userdata').glob('*/4974580'))
    return [{'path':str(root),'exists':root.exists(),'files':[{'path':str(p),'sha256':sha(p)} for p in sorted(root.rglob('*')) if p.is_file()] if root.exists() else []} for root in roots]
def normalized(data):return {x['path']:{p['path']:p['sha256'] for p in x['files']} for x in data}
after=save_snapshot();save(qa/'user_save_after.json',after)
comparisons={p.parent.name:normalized(read(p))==normalized(after) for p in sorted(WORK.glob('qa_*/user_save_before.json'))}
assert all(v for k,v in comparisons.items() if k!='qa_01'),comparisons
report['user_data']={'status':'PASS','comparison':comparisons,'files_preserved_since_qa02':sum(len(x['files']) for x in after),'gameplay_save_exists':(Path(os.environ['APPDATA'])/'Alchemortis Demo/alchemortis.sav').exists(),'initial_period_note':'qa_01 실행 전 폴더 없음. qa_02 이전 16:22 원본 실행 로그·설정·캐시 생성이 관찰됨. 이를 사용자 자료 무변경 또는 후보 검수 근거로 포함하지 않음. 이후 116파일은 보존.'}
save(WORK/'runtime_final_audit.json',report)
print(json.dumps({k:v.get('status') for k,v in report.items() if isinstance(v,dict)},ensure_ascii=False))
assert not english,english[:5]
assert not unexpected,unexpected[:10]
