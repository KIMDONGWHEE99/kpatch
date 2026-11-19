"""검증된 최종 ZIP으로 교체하고 지문이 맞는 초기 저장만 원자적으로 복구합니다."""
from common import *
import shutil,datetime,copy
stage=WORK/'progression_fix'
game=Path('D:/steam/steamapps/common/How Empires Work')
user=Path('C:/Users/PC/AppData/Roaming/Godot/app_userdata/How Empires Work')
local=Path('C:/Users/PC/AppData/Local')
shell=Path('C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')
package=WORK/'package_1.0.1_r2'
report=read_json(package/'package.json')
tests=read_json(package/'installer_tests.json')
assert tests['status']=='PASS' and tests['zip_sha256']==report['zip_sha256']
assert sha(Path(report['archive']))==report['zip_sha256']
assert read_json(stage/'release_readiness.json')['status']=='PASS'
plan=read_json(stage/'save_repair_plan.json');assert plan['status']=='PASS'
manifest=read_json(package/'from_final_zip/manifest.json')
assert sha(package/'from_final_zip/manifest.json')==report['manifest_sha256']
for item in manifest['payload']:assert sha(package/'from_final_zip'/item['path'])==item['sha256']
old_hash=read_json(WORK/'full_04/build.json')['sha256'];new_hash=read_json(WORK/'full_06/build.json')['sha256']
assert new_hash==manifest['changes'][0]['patched_sha256']==plan['candidate_sha256']
original_hash=manifest['changes'][0]['original_sha256']
assert sha(game/PCK) in (old_hash,new_hash,original_hash)
for record in manifest['baseline']:
    if record['path']!=PCK:assert sha(game/record['path'])==record['sha256']
running=subprocess.run([str(shell),'-NoProfile','-Command',"Get-Process -Name HowEmpiresWork -ErrorAction SilentlyContinue | Select-Object Id,Path | ConvertTo-Json"],capture_output=True,check=False)
text=running.stdout.decode('utf-8-sig',errors='replace').strip()
if text:
    processes=json.loads(text);processes=processes if isinstance(processes,list) else [processes]
    assert all(p.get('Path') and Path(p['Path']).resolve()!= (game/'HowEmpiresWork.exe').resolve() for p in processes),'설치본 실행 중'

def snapshot():
    roots=[user]+[p/'4663730' for p in Path('D:/steam/userdata').iterdir() if p.is_dir()]
    return {str(root):{p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()} for root in roots if root.exists()}

backup=local/'HowEmpiresWorkKoreanPatch/working_private/7A2EF6E46A4A4B0C/build_26482667/save_repair_1.0.1'
backup.mkdir(exist_ok=True)
def replace(target,source,expected):
    assert sha(source)==expected
    temporary=target.with_name(target.name+'.hew-repair-new')
    assert not temporary.exists()
    try:
        with source.open('rb') as inp,temporary.open('xb') as out:
            shutil.copyfileobj(inp,out);out.flush();os.fsync(out.fileno())
        assert sha(temporary)==expected
        os.replace(temporary,target)
    finally:
        if temporary.exists():temporary.unlink()

def durable_journal(value):
    pending=journal_path.with_suffix('.json.new')
    with pending.open('w',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    os.replace(pending,journal_path)

# 강제 종료 뒤 같은 도구를 다시 실행하면 기록된 이전 저장으로 먼저 복원합니다.
journal_path=backup/'transaction.json'
if journal_path.exists():
    previous=read_json(journal_path)
    assert previous['records']==plan['records']
    if previous['phase']=='APPLYING':
        for row in plan['records']:
            target=Path(row['path']).resolve();assert target.parent==(user/'saves').resolve()
            assert sha(target) in (row['sha256'],row['repaired_sha256'])
            assert sha(backup/target.name)==row['sha256']
        for row in plan['records']:
            target=Path(row['path']);temporary=target.with_name(target.name+'.hew-repair-new')
            if temporary.exists():temporary.unlink()
            if sha(target)!=row['sha256']:replace(target,backup/target.name,row['sha256'])
        previous['phase']='ROLLED_BACK';durable_journal(previous)
    elif previous['phase']=='COMPLETE':
        assert sha(game/PCK)==new_hash
        assert all(sha(Path(row['path']))==row['repaired_sha256'] for row in plan['records'])
        print('이미 적용된 수정본과 복구 저장의 지문을 확인했습니다.')
        raise SystemExit(0)
before=snapshot();write_json(stage/'application_user_before.json',before)
for row in plan['records']:
    target=Path(row['path']).resolve();assert target.parent==(user/'saves').resolve()
    original=Path(row['backup']).resolve();original.relative_to(stage.resolve())
    repaired=Path(row['repaired']).resolve();repaired.relative_to((stage/'repaired').resolve())
    assert sha(target)==sha(original)==row['sha256']
    assert sha(repaired)==row['repaired_sha256']
    out=backup/target.name
    if not out.exists():shutil.copy2(original,out)
    assert sha(out)==row['sha256']
write_json(backup/'repair_plan.json',plan)
env=dict(os.environ);env['LOCALAPPDATA']=str(local)
env['PSModulePath']=str(shell.parent/'Modules')+r';C:\Program Files\WindowsPowerShell\Modules'
operations=[] if sha(game/PCK)==new_hash else [('remove_1.0.0',WORK/'package_1.0.0_r2/from_final_zip','Uninstall'),('install_1.0.1',package/'from_final_zip','Install')]
if sha(game/PCK)==original_hash:operations=operations[-1:]
for name,pkg,mode in operations:
    result=subprocess.run([str(shell),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(pkg/'Patch.ps1'),'-Mode',mode,'-GameDirectory',str(game)],env=env,capture_output=True,timeout=180)
    (stage/(name+'.stdout')).write_bytes(result.stdout);(stage/(name+'.stderr')).write_bytes(result.stderr)
    assert result.returncode==0,(name,result.stderr.decode('utf8',errors='replace'))
    print(name,'PASS',flush=True)
assert sha(game/PCK)==new_hash

journal={'phase':'APPLYING','records':plan['records'],'backup_directory':str(backup)}
durable_journal(journal)
changed=[]
try:
    for row in plan['records']:
        target=Path(row['path']);assert sha(target)==row['sha256'],'사용자 저장이 준비 후 바뀜'
        replace(target,Path(row['repaired']),row['repaired_sha256']);changed.append(row)
    after=snapshot();write_json(stage/'application_user_after.json',after)
    expected=copy.deepcopy(before)
    for row in plan['records']:expected[str(user)]['saves/'+Path(row['path']).name]=row['repaired_sha256']
    assert after==expected,'허용된 4개 저장 외 사용자 파일 변경'
    for record in manifest['baseline']:
        assert sha(game/record['path'])==(new_hash if record['path']==PCK else record['sha256'])
    assert sha(backup.parent/'cache/0/original')==manifest['changes'][0]['original_sha256']
    journal['phase']='COMPLETE';durable_journal(journal)
    write_json(stage/'application.json',{'status':'PASS','candidate_sha256':new_hash,'zip_sha256':report['zip_sha256'],'game_directory':str(game),'repaired_saves':len(changed),'save_backup':str(backup),'other_user_files_unchanged':True,'original_pack_backup':'PASS','money_preserved':[r['money'] for r in changed],'completed':datetime.datetime.now().isoformat()})
    print('패치 교체와 저장 4개 복구 완료',flush=True)
except BaseException:
    for row in reversed(changed):replace(Path(row['path']),backup/Path(row['path']).name,row['sha256'])
    journal['phase']='ROLLED_BACK';durable_journal(journal)
    raise
