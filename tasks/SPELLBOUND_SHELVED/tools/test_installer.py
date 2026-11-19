"""최종 ZIP에서 추출한 실제 설치기를 격리 사본에서 시험한다."""
import os
import json
import hashlib
import subprocess
import shutil
import time
from pathlib import Path
from pck_tools import ROOT,BASELINE,WORK

scratch=WORK/'package_1.0.0_r3'
package=scratch/'from_final_zip'
tests=scratch/'tests'
tests.mkdir(exist_ok=True)
records=[]
env=dict(os.environ)
env['LOCALAPPDATA']=str(tests/'state')
env['PSModulePath']=r'C:\Windows\System32\WindowsPowerShell\v1.0\Modules;C:\Program Files\WindowsPowerShell\Modules'
shell=r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
manifest=json.loads((package/'manifest.json').read_text())
change=manifest['changes'][0]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def folder(name):
    p=tests/name/'windows'
    assert not p.exists(),p
    shutil.copytree(BASELINE/'windows',p)
    return p
def state_for(p, environment=env):
    key=hashlib.sha256(str(p).lower().encode()).hexdigest().upper()[:16]
    return Path(environment['LOCALAPPDATA'])/'SpellboundShelvedKoreanPatch/working_private'/key
def run(name,mode,path,expected_exit=0,expected_hash=None,package_path=package,environment=env):
    cmd=[shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(package_path/'Patch.ps1'),'-Mode',mode,'-GameDirectory',str(path)]
    p=subprocess.run(cmd,env=environment,capture_output=True,timeout=60)
    (tests/(name+'.stdout')).write_bytes(p.stdout);(tests/(name+'.stderr')).write_bytes(p.stderr)
    assert (p.returncode==0)==(expected_exit==0),(name,p.returncode,p.stderr.decode('utf-8',errors='replace'))
    actual=path/'SpellboundShelved.pck'
    if not actual.exists():actual=path/'windows/SpellboundShelved.pck'
    if expected_hash:assert sha(actual)==expected_hash,name
    records.append({'test':name,'exit_code':p.returncode,'status':'PASS','pck_sha256':sha(actual) if actual.exists() else None})
    print(name,'PASS',flush=True)

p=folder('한국어 공백 & 경로')
run('install_original','Install',p.parent,expected_hash=change['patched_sha256'])
run('duplicate_install','Install',p,expected_hash=change['patched_sha256'])
run('status','Status',p,expected_hash=change['patched_sha256'])
run('remove','Uninstall',p.parent,expected_hash=change['original_sha256'])
run('duplicate_remove','Uninstall',p,expected_hash=change['original_sha256'])
run('reinstall','Install',p,expected_hash=change['patched_sha256'])
fresh=dict(env);fresh['LOCALAPPDATA']=str(tests/'fresh_state')
run('remove_without_backup','Uninstall',p,expected_hash=change['original_sha256'],environment=fresh)

for kind,file in [('altered_pack','SpellboundShelved.pck'),('updated_executable','SpellboundShelved.exe')]:
    q=folder(kind);target=q/file;b=bytearray(target.read_bytes());b[-1]^=1;target.write_bytes(b)
    before=sha(q/'SpellboundShelved.pck')
    run(kind,'Install',q,1,before)
q=folder('partial_file');f=q/'SpellboundShelved.pck';f.write_bytes(f.read_bytes()[:5000]);run('partial_file','Install',q,1,sha(f))
q=folder('missing_file');f=q/'steam_api64.dll';f.unlink();run('missing_file','Install',q,1,change['original_sha256'])
damaged=tests/'damaged_package';shutil.copytree(package,damaged);delta=damaged/'patches/00.forward.xdelta';delta.write_bytes(b'broken')
q=folder('damaged_payload');run('damaged_payload','Install',q,1,change['original_sha256'],package_path=damaged)

# 게임 파일을 바꾼 다음 완료 영수증 쓰기에 실패해도 원래 상태로 복원해야 한다.
q=folder('receipt_failure');blocked=state_for(q)/'receipt.json';blocked.mkdir(parents=True)
run('rollback_after_commit_failure','Install',q,1,change['original_sha256'])
assert json.loads((state_for(q)/'transaction.json').read_text(encoding='utf-8-sig'))['phase']=='ROLLED_BACK'
blocked.rmdir()
run('retry_after_commit_failure','Install',q,expected_hash=change['patched_sha256'])
run('remove_after_commit_failure','Uninstall',q,expected_hash=change['original_sha256'])

# 실제 프로세스를 APPLYING 기록이 나타나는 순간 강제로 끝낸다.
q=folder('interrupted')
cmd=[shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(package/'Patch.ps1'),'-Mode','Install','-GameDirectory',str(q)]
log=(tests/'forced_stop.stdout').open('wb')
proc=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
journal=state_for(q)/'transaction.json'
observed=False
while proc.poll() is None:
    if journal.exists():
        try:data=json.loads(journal.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):continue
        if data['phase']=='APPLYING':
            proc.kill();proc.wait(timeout=10);observed=True;break
    time.sleep(0.001)
log.close()
assert observed,'강제 중단 시점을 포착하지 못함'
records.append({'test':'forced_process_stop','status':'PASS','phase':'APPLYING','exit_code':proc.returncode})
run('resume_after_forced_stop','Install',q,expected_hash=change['patched_sha256'])
run('remove_after_recovery','Uninstall',q,expected_hash=change['original_sha256'])

# 교체를 마친 뒤 완료 기록 전에 중단된 상태도 원래 설치기로 복구한다.
run('prepare_committed_interruption','Install',q,expected_hash=change['patched_sha256'])
data=json.loads(journal.read_text(encoding='utf-8-sig'));data['phase']='APPLYING';data['entries'][0]['before']=change['original_sha256'];journal.write_text(json.dumps(data),encoding='utf-8')
run('recover_after_atomic_replace','Uninstall',q,expected_hash=change['original_sha256'])

result={'game_id':'SPELLBOUND_SHELVED','candidate':'ko_1.0.0_c02','zip_sha256':sha(ROOT/'release_output/SPELLBOUND_SHELVED_KOREAN_PATCH_1.0.0.zip'),'status':'PASS','tests':records}
(scratch/'installer_tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('검사 수',len(records))
