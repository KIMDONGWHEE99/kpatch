"""최종 ZIP에서 추출한 설치기의 성공·실패·실제 중단 복구를 시험합니다."""
from common import *
SOURCE=BASE
CANDIDATE=ROOT/"build_candidate/ALCHEMORTIS_DEMO/ko_1.0.1_c01"
def write_json(path,value):save(path,value)
def sha(path):return __import__("hashlib").sha256(Path(path).read_bytes()).hexdigest()
from pathlib import Path
import os,json,shutil,subprocess,time,ctypes

scratch=WORK/'package_v3';package=scratch/'from_final_zip';game=scratch/'한글 공백 시험본'
assert not game.exists()
shutil.copytree(SOURCE,game)
env=os.environ.copy();env['LOCALAPPDATA']=str(scratch/'test_local');env['APPDATA']=str(scratch/'test_roaming')
for k in ('LOCALAPPDATA','APPDATA'):Path(env[k]).mkdir(exist_ok=True)
ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
manifest=json.loads((package/'manifest.json').read_text('utf-8'))
original={r['path']:r['sha256'] for r in manifest['baseline']}
patched=dict(original,**{r['path']:r['patched_sha256'] for r in manifest['changes']});results=[]
def snapshot():return {p.relative_to(game).as_posix():sha(p) for p in game.rglob('*') if p.is_file()}
def check(expected):assert snapshot()==expected
def command(root=package,mode='Install',target=game):return [str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(root/'Patch.ps1'),'-Mode',mode,'-GameDirectory',str(target)]
def run(case,mode='Install',expected=0,root=package,run_env=None,target=game,contains=None):
    p=subprocess.run(command(root,mode,target),env=run_env or env,capture_output=True,timeout=180)
    (scratch/(case+'.stdout.log')).write_bytes(p.stdout);(scratch/(case+'.stderr.log')).write_bytes(p.stderr)
    assert (p.returncode==0)==(expected==0),(case,p.returncode,p.stderr[-1700:])
    if contains:assert contains in (p.stdout+p.stderr).decode('utf-8',errors='replace')
    results.append({'case':case,'status':'PASS','exit_code':p.returncode})
    write_json(scratch/'installer_tests_progress.json',results);print(case,'PASS',flush=True)
def restore(name):shutil.copy2(SOURCE/name,game/name)
run('original_install');check(patched)
run('duplicate_install');check(patched)
run('status','Status');check(patched)
run('uninstall','Uninstall');check(original)
run('duplicate_uninstall','Uninstall');check(original)
data='data_Alchemortis_windows_x86_64/Alchemortis.dll'
shutil.copy2(CANDIDATE/data,game/data)
run('partial_install_repair');check(patched)
fresh=env.copy();fresh['LOCALAPPDATA']=str(scratch/'reverse_without_backup');Path(fresh['LOCALAPPDATA']).mkdir()
run('reverse_without_backup','Uninstall',run_env=fresh);check(original)
shutil.copy2(CANDIDATE/data,game/data)
run('partial_uninstall','Uninstall');check(original)
for case,name in [('modified_asset',data),('unsupported_dependency','data_Alchemortis_windows_x86_64/GodotSharp.dll')]:
    with (game/name).open('ab') as f:f.write(b'KOREAN_PATCH_NEGATIVE_TEST')
    before=snapshot();run(case,expected=1);check(before);restore(name)
name='Alchemortis Demo.pck'
(game/name).unlink();before=snapshot();run('missing_file',expected=1);check(before);restore(name)
old_file="data_Alchemortis_windows_x86_64/Alchemortis.dll"
shutil.copy2(ROOT/"build_candidate/ALCHEMORTIS_DEMO/ko_1.0.0_c07"/old_file,game/old_file)
before=snapshot();run('previous_build_patch_rejected',expected=1);check(before);restore(old_file)
for case,relative in [('damaged_payload','patches/00.forward.xdelta'),('damaged_decoder','tools/xdelta3.exe')]:
    damaged=scratch/case;shutil.copytree(package,damaged)
    with (damaged/relative).open('ab') as f:f.write(b'TAMPER')
    run(case,expected=1,root=damaged);check(original)
wrong=scratch/'없는 게임 위치';run('wrong_directory',expected=1,target=wrong);assert not wrong.exists();check(original)

kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
kernel.CreateFileW.restype=ctypes.c_void_p;kernel.CloseHandle.argtypes=[ctypes.c_void_p]
def lock():
    h=kernel.CreateFileW(str(game/data),0x80000000,1,None,3,0x80,None)
    assert h!=ctypes.c_void_p(-1).value
    return h
h=lock()
try:run('install_mid_failure_rollback',expected=1)
finally:kernel.CloseHandle(h)
check(original)
run('install_after_rollback');check(patched)
h=lock()
try:run('uninstall_mid_failure_rollback','Uninstall',expected=1)
finally:kernel.CloseHandle(h)
check(patched)
run('uninstall_after_rollback','Uninstall');check(original)
temporary=game/'data_Alchemortis_windows_x86_64/Alchemortis.dll.alchemortis-korean-new'
hard_lock=lock()
with (scratch/'hard_stop.stdout.log').open('wb') as out,(scratch/'hard_stop.stderr.log').open('wb') as err:
    proc=subprocess.Popen(command(),env=env,stdout=out,stderr=err);deadline=time.time()+90;stopped=False
    while proc.poll() is None and time.time()<deadline:
        if temporary.exists() and temporary.stat().st_size>1024:
            proc.kill();proc.wait(timeout=10);stopped=True
            journals=list((Path(env['LOCALAPPDATA'])/'AlchemortisKoreanPatch/working_private').glob('*/*/transaction.json'))
            pending=json.loads(journals[0].read_text('utf-8-sig'));assert pending['phase']=='APPLYING'
            write_json(scratch/'hard_stop_pending.json',pending);break
        time.sleep(.002)
    if not stopped:
        if proc.poll() is None:proc.kill();proc.wait()
        raise AssertionError('실제 교체 중 중단 지점을 포착하지 못했습니다')
kernel.CloseHandle(hard_lock)
run('hard_stop_recovery');check(patched);assert not temporary.exists()
run('final_uninstall','Uninstall');check(original)

# 실제 게임 실행 대신 같은 경로의 대기용 프로그램으로 실행 중 경로 검사를 시험합니다.
hold=scratch/'Hold.cs';hold.write_text('using System.Threading; class Hold { static void Main() { Thread.Sleep(60000); } }','utf-8')
compiler=Path(os.environ['SystemRoot'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
helper=scratch/'Hold.exe'
subprocess.run([str(compiler),'/nologo','/target:winexe','/out:'+str(helper),str(hold)],check=True,capture_output=True)
exe='Alchemortis Demo.exe';shutil.copy2(helper,game/exe);holding=snapshot()
proc=subprocess.Popen([str(game/exe)],env=env,cwd=game)
try:
    time.sleep(.5);assert proc.poll() is None
    run('running_target_rejected',expected=1);check(holding)
finally:
    if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
restore(exe);check(original)
log=(scratch/'running_target_rejected.stderr.log').read_bytes()
assert b'data_Alchemortis_windows_x86_64' not in log, '버전 오류에 앞서 실행 중 경로 거부가 동작해야 합니다'
write_json(scratch/'installer_tests.json',{'status':'PASS','final_zip_sha256':sha(scratch/'ALCHEMORTIS_DEMO_KOREAN_PATCH_1.0.1.zip'),'cases':results,'hard_stop_actual':True,'final_game_matches_original':True,'original_files':len(original),'running_check_scope':'게임과 동일 파일 경로의 자체 대기용 실행 파일. 게임 화면 검수와 구분','previous_public_release':'이전 공개판 1.0.0은 이전 게임 빌드용이므로 거부. Steam 업데이트 원본에서 새 설치 시험.'})
print('INSTALLER ALL PASS',len(results))
