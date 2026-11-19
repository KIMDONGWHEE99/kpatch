"""사용자가 지정한 Steam 설치본에 검증된 최종 ZIP 설치기를 적용합니다."""
from common import *
from datetime import datetime,timezone

target=Path('D:/steam/steamapps/common/Boreworks Demo')
assert str(target.resolve()).casefold()=='d:\\steam\\steamapps\\common\\boreworks demo'
ready=json.loads((WORK/'release_readiness.json').read_text(encoding='utf-8'))
assert all(ready['gates']['G'+str(i)]=='PASS' for i in range(8))
archive=ROOT/'release_output/BOREWORKS_DEMO_KOREAN_PATCH_1.0.0.zip'
assert sha(archive.read_bytes())==ready['zip_sha256']
package=WORK/'package_v1/from_final_zip'
manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8'))
for row in manifest['payload']:assert sha((package/row['path']).read_bytes())==row['sha256']
baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf-8'))
for row in baseline:assert sha((target/row['path']).read_bytes())==row['sha256'],row['path']
def save_snapshot():
    result=[]
    for row in json.loads((WORK/'user_saves_before.json').read_text(encoding='utf-8')):
        root=Path(row['root']);files=[dict(path=p.relative_to(root).as_posix(),sha256=sha(p.read_bytes())) for p in sorted(root.rglob('*')) if p.is_file()] if root.exists() else []
        result.append(dict(root=str(root),exists=root.exists(),files=files))
    return result
before_saves=save_snapshot()
ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
result=subprocess.run([str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(package/'Patch.ps1'),'-Mode','Install','-GameDirectory',str(target)],capture_output=True,timeout=180)
(WORK/'actual_install.stdout.log').write_bytes(result.stdout);(WORK/'actual_install.stderr.log').write_bytes(result.stderr)
assert result.returncode==0,result.stderr
candidate=ROOT/'build_candidate/BOREWORKS_DEMO/ko_v002'
files=[dict(path=p.relative_to(target).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(target.rglob('*')) if p.is_file()]
expected={r['path']:r['sha256'] for r in json.loads((WORK/'ko_v002/build_manifest.json').read_text(encoding='utf-8'))['files']}
assert {r['path']:r['sha256'] for r in files}==expected
root_key=sha(str(target.resolve()).lower().encode('utf-8')).upper()[:16]
state=Path(os.environ['LOCALAPPDATA'])/'BoreworksKoreanPatch/working_private'/root_key
receipt=json.loads((state/'receipt.json').read_text(encoding='utf-8-sig'))
assert receipt['status']=='COMPLETE' and receipt['mode']=='Install'
for i,row in enumerate(manifest['changes']):
    assert sha((state/f'cache/{i}/original').read_bytes())==row['original_sha256']
    assert sha((state/f'cache/{i}/patched').read_bytes())==row['patched_sha256']
after_saves=save_snapshot();assert before_saves==after_saves
save_json(WORK/'installed_verification.json',dict(status='PASS',completed_utc=datetime.now(timezone.utc).isoformat(),target=str(target),candidate='ko_v002',files=files,original_backups_verified=len(manifest['changes']),backup_directory=str(state),receipt=receipt,zip_sha256=sha(archive.read_bytes()),user_saves_unchanged=True,before_saves=before_saves,after_saves=after_saves))
print('INSTALLED_VERIFIED',len(files),'BACKUPS',len(manifest['changes']),str(state))
