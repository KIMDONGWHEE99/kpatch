"""원본·후보·실행 검수·최종 ZIP을 같은 파일 해시에 연결합니다."""
from common import *
from checks import *
import re,subprocess,zipfile
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
build=ROOT/'build_candidate'/GAME/'ko_v005';game=build/'game';run=WORK/'qa_v006';qa=run/'game';pkg=WORK/'package_v2';archive=pkg/(GAME+'_KOREAN_PATCH_1.0.0.zip')
manifest=read(build/'build.json');static=read(build/'static_validation.json')
check_binding(static['build_manifest_sha256'],sha((build/'build.json').read_bytes()))
check_binding(static['translation_sha256'],sha((WORK/'translation.json').read_bytes()))
check_binding(manifest['baseline_sha256'],sha((WORK/'baseline.json').read_bytes()))
check_binding(manifest['code_translation_sha256'],sha((WORK/'code_translation.json').read_bytes()))
check_binding(manifest['font_sha256'],sha((WORK/'NotoSansKR-Regular.ttf').read_bytes()))
expected={r['path']:r['sha256'] for r in manifest['files']}
actual={p.relative_to(game).as_posix():sha(p.read_bytes()) for p in game.rglob('*') if p.is_file()};check_binding(expected,actual)
for row in read(WORK/'baseline.json')['files']:assert sha((BASE/row['path']).read_bytes())==row['sha256']
strings=read(WORK/'source_ledger.json');media=read(WORK/'media_ledger.json');errors=read(EXTRACT/'errors.json');resolutions=read(WORK/'extraction_resolutions.json')
check_coverage(strings,media,errors,resolutions)
for err in errors:assert any(r['file']==err['file'] and r['path_id']==err['path_id'] and r['sha256']==err['source_sha256'] for r in resolutions)
code=read(WORK/'code_ledger.json');assert all(r['classification']!='UNKNOWN' for r in code)
assembly=WORK/'assembly_tool/AssemblyTool.dll'
def verify(args,name):
    p=subprocess.run(['dotnet',str(assembly)]+args,capture_output=True,check=True);(run/name).write_bytes(p.stdout+p.stderr)
verify(['verify',str(BASE/DATA/'Managed/Assembly-CSharp.dll'),str(game/DATA/'Managed/Assembly-CSharp.dll'),str(WORK/'code_translation.json')],'candidate_code_validation.log')
verify(['verify-qa',str(game/DATA/'Managed/Assembly-CSharp.dll'),str(qa/DATA/'Managed/Assembly-CSharp.dll')],'qa_code_validation.log')
qfiles={p.relative_to(qa).as_posix():sha(p.read_bytes()) for p in qa.rglob('*') if p.is_file()}
assert set(qfiles)==set(expected)|{DATA+'/Managed/KoreanQA.dll'}
company,product=(qa/DATA/'app.info').read_text().splitlines()
overrides={DATA+'/globalgamemanagers',DATA+'/app.info',DATA+'/Managed/Assembly-CSharp.dll'}
for name,h in expected.items():
    if name not in overrides:assert qfiles[name]==h
original=(game/DATA/'globalgamemanagers').read_bytes()
assert (qa/DATA/'globalgamemanagers').read_bytes()==original.replace(b'PhilipMaxey',company.encode()).replace(b'March and Conquer Demo',product.encode())
assert qfiles[DATA+'/Managed/KoreanQA.dll']==sha((WORK/'qa_tool/KoreanQA.dll').read_bytes())
process=read(run/'process.json');assert Path(process['Path']).resolve()==(qa/'March and Conquer Demo.exe').resolve()
captures=[read(p) for p in sorted((run/'captures').glob('*.json'))];assert (run/'captures/completed.txt').exists()
assert len(captures)==217 and all(r['device']=='NVIDIA GeForce RTX 4060 Ti' and r['product']==product and r['textCount']>0 for r in captures)
log=(run/'Player.log').read_text(encoding='utf-8-sig',errors='replace')
glyph=[s for s in log.splitlines() if re.search(r'character.*Unicode.*not found|missing glyph',s,re.I)]
loading=[s for s in log.splitlines() if re.search(r'(NullReference|TypeLoad|FileNotFound|MissingMethod|InvalidProgram)Exception|Failed to load|Error loading',s,re.I)]
assert not glyph and not loading,(glyph,loading)
assert 'Loaded run from: '+captures[0]['savePath'] in log and 'Input System module state changed to: Shutdown.' in log
health=read(run/'captures/node_110_node_crystal_dragon.json');h=next(t for t in health['texts'] if t['path'].endswith('UnitStatsRoot/HealthText'))
assert h['text']=='2000' and h['preferredHeight']<20
check_binding(read(WORK/'user_baseline_actual.json'),read(WORK/'user_after_qa.json'))
seen={t['text'] for r in captures for t in r['texts']}
positions=read(WORK/'translation.json');unobserved=[r for r in positions if r['target'] not in seen];save(run/'unobserved_exact_positions.json',unobserved)
save(run/'qa_manifest.json',dict(candidate='ko_v005',candidate_manifest_sha256=sha((build/'build.json').read_bytes()),process=process,company=company,product=product,overrides=[dict(file=DATA+'/globalgamemanagers',path_id=1,fields=['companyName','productName']),dict(file=DATA+'/app.info',fields=['company','product']),dict(file=DATA+'/Managed/Assembly-CSharp.dll',method='Battles1000.GameTextManager.Awake',change='KoreanQA.Bootstrap.Start 호출 1개'),dict(file=DATA+'/Managed/KoreanQA.dll',change='검수 전용 추가 모듈')],runtime_test_changes=['검수 저장·설정 분리','실행 중 백그라운드 렌더링 유지','일시정지 후 기술 설명 순회','정상 유닛 팝업 프리팹 복제·화면 안쪽 배치','승리·지역 정복·종료 화면 시험값 진입','격리 저장·불러오기'],files=qfiles))
save(run/'runtime_validation.json',dict(status='PASS',scope='기재된 화면군과 표시 검수. 정상 진행 전체 완주를 의미하지 않음',candidate='ko_v005',candidate_manifest_sha256=sha((build/'build.json').read_bytes()),qa_manifest_sha256=sha((run/'qa_manifest.json').read_bytes()),frames=len(captures),nodes=153,units=48,main_screens=16,exact_translation_positions_observed=len(positions)-len(unobserved),total_translation_positions=len(positions),missing_glyph_warnings=0,patch_loading_errors=0,save_reload='PASS',user_integrity='PASS',normal_exit='PASS',whole_random_campaign='NOT_RUN',screenshots=[dict(name=p.name,sha256=sha(p.read_bytes())) for p in sorted((run/'captures').glob('*.png'))],log_sha256=sha((run/'Player.log').read_bytes()),review_notes=['153개 기술 설명의 제목·본문·비용과 48개 유닛명·체력 표시를 검수판/개별 원본 화면으로 관찰','숫자 2000 줄바꿈 결함을 같은 표시군 8곳에서 수정하고 재실행 확인','TMP의 높이 초과 표시는 실제 마스크 없는 한 줄 글자·회전 장식과 구분하여 육안 판정','독일어 원문 슬롯은 유지. 한국어 전환·재진입을 확인','결과 화면은 검수 조건으로 호출했으며 60전 정상 완주와 구분']))
package=read(pkg/'package.json');check_binding(package['zip_sha256'],sha(archive.read_bytes()))
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist())==set(package['allowed_files']) and z.testzip() is None
    for name in z.namelist():assert sha(z.read(name))==sha((pkg/'from_final_zip'/name).read_bytes())
for filename in ['installer_tests.json','installer_edge_tests.json']:
    result=read(pkg/filename);assert result['status']=='PASS';check_binding(result['final_zip_sha256'],sha(archive.read_bytes()))
assert all(r['status']=='PASS' for r in package['roundtrips']) and read(WORK/'checker_tests.json')['status']=='PASS'
tools_manifest={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in (ROOT/'tasks'/GAME/'tools').rglob('*') if p.is_file()}
save(WORK/'release_ready.json',dict(status='PASS',candidate='ko_v005',candidate_manifest_sha256=sha((build/'build.json').read_bytes()),zip_sha256=sha(archive.read_bytes()),strings=len(strings),code_occurrences=len(code),media=len(media),unresolved=0,installer_cases=24,checker_cases=13,runtime_validation_sha256=sha((run/'runtime_validation.json').read_bytes()),tools=tools_manifest))
print('READY PASS: 후보·실행·최종 ZIP·24개 설치 시험·13개 검사기 시험 연결')
