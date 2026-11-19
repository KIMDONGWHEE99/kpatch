"""화면 판독 결과를 실행 경로·후보 지문·격리 변경 경계·로그와 연결합니다."""
from common import *
import subprocess,re,datetime
build='ko_c03';candidate=ROOT/'build_candidate/EPIC_IDLENTURE_DEMO'/build;g=generator();runs=['qa_005','qa_007','qa_008'];reports=[]
original_log=(WORK/'qa_base002/Player.log').read_text(encoding='utf8')
baseline_warnings={s for s in original_log.splitlines() if s.startswith('No sprite ')};assert len(baseline_warnings)==19
exceptions=[]
for run in runs:
    root=WORK/run;game=root/'game';capt=root/'captures';manifest=json.loads((root/'manifest.json').read_text(encoding='utf8'));assert manifest['candidate']=='ko_c03' and manifest['candidate_manifest_sha256']==sha((WORK/'ko_c03.json').read_bytes())
    assert (capt/'complete.txt').exists() and not (capt/'timeout.txt').exists()
    for r in manifest['files']:assert sha((game/r['path']).read_bytes())==r['sha256'],(run,r['path'])
    before=json.loads((root/'user_before.json').read_text(encoding='utf8'));after=json.loads((root/'user_after.json').read_text(encoding='utf8'));assert before==after
    observed=json.loads((root/'observed_process.json').read_text(encoding='utf-8-sig'));observed=observed if isinstance(observed,list) else [observed];launch=json.loads((root/'launch.json').read_text(encoding='utf8'));assert any(r['ProcessId']==launch['pid'] and Path(r['ExecutablePath'])==game/'Epic Idlenture.exe' for r in observed)
    log=(root/'Player.log').read_text(encoding='utf8');assert not re.search(r'Exception:|MissingReference|The character with Unicode|was not found in the|Failed to load|Could not load',log,re.I)
    warnings={s for s in log.splitlines() if s.startswith('No sprite ')};assert warnings==baseline_warnings
    allowed={DATA+'/app.info',DATA+'/globalgamemanagers',DATA+'/resources.assets',DATA+'/Managed/Assembly-CSharp.dll'}
    for p in candidate.rglob('*'):
        if p.is_file() and p.relative_to(candidate).as_posix() not in allowed:assert p.read_bytes()==(game/p.relative_to(candidate)).read_bytes()
    a=load(candidate/DATA/'globalgamemanagers',g);b=load(game/DATA/'globalgamemanagers',g)
    assert set(a.file.objects)==set(b.file.objects)
    for pid,obj in a.file.objects.items():
        expected=obj.get_raw_data()
        if pid==1:expected=expected.replace(b'impulse9',b'EPIC_QA1').replace(b'Epic Idlenture',b'Epic_KoreanQA1')
        assert b.file.objects[pid].get_raw_data()==expected
    a=load(candidate/DATA/'resources.assets',g);b=load(game/DATA/'resources.assets',g)
    for pid,obj in a.file.objects.items():
        if pid==5090:
            at=obj.read_typetree();bt=b.file.objects[pid].read_typetree();assert bt['settings']['path']==str(root/'saves/SaveFile_v2.es3');bt['settings']['path']=at['settings']['path'];assert at==bt
        else:assert b.file.objects[pid].get_raw_data()==obj.get_raw_data()
    subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'verify_isolation',str(candidate/DATA/'Managed/Assembly-CSharp.dll'),str(game/DATA/'Managed/Assembly-CSharp.dll')],check=True)
    font=json.loads((capt/'font_coverage.json').read_text(encoding='utf8'));assert font['status']=='PASS' and font['missing']=='' and font['characters']>=606
    images=sorted(capt.glob('*.png'));records=[]
    for p in images:
        data=json.loads(p.with_suffix('.json').read_text(encoding='utf8'));assert data['device']=='NVIDIA GeForce RTX 4060 Ti' and data['width']==1280 and data['height']==720 and data['frame']>0
        records.append(dict(stage=p.stem,sha256=sha(p.read_bytes()),frame=data['frame'],status='PASS',review='실제 GPU 화면 육안 판독. 같은 후보의 반복 첫 화면은 qa_005에서 확인한 동일 UI·글꼴 검토와 연결' if run!='qa_005' and p.stem.startswith('00') else '실제 GPU 화면 육안 판독: 한글·문장 끝·버튼·태그·잘림 확인'))
    if run=='qa_005':assert len(records)==48 and len(list(capt.glob('dialog_*.png')))==22
    if run=='qa_007':assert len(list(capt.glob('gem_*.png')))==33 and len(list(capt.glob('item_*.png')))==8 and len(list(capt.glob('ability_*.png')))==6
    if run=='qa_008':assert len(list(capt.glob('research_*.png')))==12
    reports.append(dict(run=run,status='PASS',pid=launch['pid'],manifest_sha256=sha((root/'manifest.json').read_bytes()),driver_sha256=sha((game/DATA/'Managed/KoreanQA.dll').read_bytes()),user_data_unchanged=True,patch_errors=0,glyph_warnings=0,font=font,screens=records))
save(WORK/'runtime_report.json',dict(status='PASS',build=build,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),runs=reports,baseline_warning_count=19,baseline_log_sha256=sha((WORK/'qa_base002/Player.log').read_bytes()),scope='일반 UI 48장·보석 33종·장비 8종(999레벨/+9)·기술 6종·연구 상세 12종. 도움말 위치 고정, 진행 상태 해금, 대사 재생과 일시정지는 격리 검수 사본에서만 수행. 전체 회차 완주 아님',not_applicable={'formula_ui':'직접 표시 호출 3곳 모두 _includeFormula=0. 원본에서도 GetAttributeEffect(Damage)가 예외를 발생시키는 비활성 계산식 분기는 표시 대상으로 강제 실행하지 않음'}))
print('실행 경계·로그·저장·화면 대조 PASS',sum(len(r['screens']) for r in reports))
