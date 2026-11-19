"""최종 ZIP에서 꺼낸 설치기를 실제 사본과 파일 잠금·프로세스 중단으로 검증합니다."""
from common import *
import shutil,sys,time,ctypes

scratch=WORK/'package_v1'
package=scratch/'from_final_zip'
game=scratch/'한글 공백 시험본'
recovery_only='--recovery' in sys.argv
if not recovery_only:
    assert not game.exists()
    shutil.copytree(BASE,game)
env=os.environ.copy();env['LOCALAPPDATA']=str(scratch/'test_local');env['APPDATA']=str(scratch/'test_roaming')
Path(env['LOCALAPPDATA']).mkdir(exist_ok=True);Path(env['APPDATA']).mkdir(exist_ok=True)
baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf-8'))
manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8'))
original={r['path']:r['sha256'] for r in baseline}
patched=dict(original,**{r['path']:r['patched_sha256'] for r in manifest['changes']})
candidate=ROOT/'build_candidate/BOREWORKS_DEMO/ko_v002'
results=json.loads((scratch/'installer_tests_progress.json').read_text(encoding='utf-8')) if recovery_only else []
ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
def snapshot():return {p.relative_to(game).as_posix():sha(p.read_bytes()) for p in game.rglob('*') if p.is_file()}
def run(case,mode='Install',expected=0,root=package,run_env=None):
    command=[str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(root/'Patch.ps1'),'-Mode',mode,'-GameDirectory',str(game)]
    p=subprocess.run(command,env=run_env or env,capture_output=True,timeout=180)
    (scratch/(case+'.stdout.log')).write_bytes(p.stdout);(scratch/(case+'.stderr.log')).write_bytes(p.stderr)
    assert (p.returncode==0)==(expected==0),(case,p.returncode,p.stderr[-1500:])
    results.append(dict(case=case,status='PASS',exit_code=p.returncode))
    save_json(scratch/'installer_tests_progress.json',results)
    print(case,'PASS',flush=True)
def check(expected):assert snapshot()==expected
def replace_from(root,name):shutil.copy2(root/name,game/name)
if not recovery_only:
    run('original_install');check(patched)
    run('duplicate_install');check(patched)
    run('status',mode='Status');check(patched)
    run('uninstall',mode='Uninstall');check(original)
    run('duplicate_uninstall',mode='Uninstall');check(original)
    replace_from(candidate,'Boreworks.pck')
    run('partial_install_repair');check(patched)
    fresh=env.copy();fresh['LOCALAPPDATA']=str(scratch/'reverse_without_backup');Path(fresh['LOCALAPPDATA']).mkdir()
    run('reverse_without_backup',mode='Uninstall',run_env=fresh);check(original)
    for case,name in [('modified_pck','Boreworks.pck'),('unsupported_dependency','steam_api64.dll')]:
        with (game/name).open('ab') as f:f.write(b'KOREAN_PATCH_NEGATIVE_TEST')
        before=snapshot();run(case,expected=1);check(before);replace_from(BASE,name)
    name='data_Boreworks_windows_x86_64/Boreworks.dll'
    (game/name).unlink();before=snapshot();run('missing_file',expected=1);check(before);replace_from(BASE,name)
    replace_from(ROOT/'build_candidate/BOREWORKS_DEMO/ko_v001',name)
    before=snapshot();run('unreleased_old_candidate_rejected',expected=1);check(before);replace_from(BASE,name)
    damaged=scratch/'damaged_package';shutil.copytree(package,damaged)
    with (damaged/'patches/00.forward.xdelta').open('ab') as f:f.write(b'TAMPER')
    before=snapshot();run('damaged_payload',expected=1,root=damaged);check(before)
    
    # 읽기는 허용하고 교체만 막아 첫 파일 교체 이후 실패와 복원을 실제로 일으킵니다.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    kernel.CreateFileW.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    def lock_file():
        handle=kernel.CreateFileW(str(game/name),0x80000000,1,None,3,0x80,None)
        assert handle != ctypes.c_void_p(-1).value
        return handle
    handle=lock_file()
    try:run('install_mid_failure_rollback',expected=1)
    finally:kernel.CloseHandle(handle)
    check(original)
    run('install_after_rollback');check(patched)
    handle=lock_file()
    try:run('uninstall_mid_failure_rollback',mode='Uninstall',expected=1)
    finally:kernel.CloseHandle(handle)
    check(patched)
    run('uninstall_after_rollback',mode='Uninstall');check(original)
else:
    run('prepare_recovery_retry',mode='Uninstall');check(original)

command=[str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(package/'Patch.ps1'),'-Mode','Install','-GameDirectory',str(game)]
with (scratch/'hard_stop.stdout.log').open('wb') as out,(scratch/'hard_stop.stderr.log').open('wb') as err:
    proc=subprocess.Popen(command,env=env,stdout=out,stderr=err)
    temporary=game/'Boreworks.pck.boreworks-korean-new';deadline=time.time()+90;stopped=False
    while proc.poll() is None and time.time()<deadline:
        if temporary.exists() and temporary.stat().st_size>1024*1024:
            proc.kill();proc.wait(timeout=10);stopped=True
            journals=list((Path(env['LOCALAPPDATA'])/'BoreworksKoreanPatch/working_private').glob('*/transaction.json'))
            pending=json.loads(journals[0].read_text(encoding='utf-8-sig'))
            assert pending['phase']=='APPLYING'
            save_json(scratch/'hard_stop_pending.json',pending)
            break
        time.sleep(.003)
    if not stopped:
        if proc.poll() is None:proc.kill();proc.wait()
        raise AssertionError('실제 교체 중 강제 종료 지점을 포착하지 못했습니다.')
run('hard_stop_recovery');check(patched)
assert not temporary.exists()
run('final_uninstall',mode='Uninstall');check(original)

# 그래픽 화면 없이 SceneTree만 실행하여 실행 중인 대상 거부를 확인합니다.
hold=scratch/'hold.gd'
hold.write_text('extends SceneTree\nfunc _initialize():\n await create_timer(60).timeout\n quit()\n',encoding='utf-8')
with (scratch/'running_game.log').open('wb') as f:
    proc=subprocess.Popen([str(game/'Boreworks.exe'),'--headless','--script',str(hold),'--log-file',str(scratch/'hold.log')],env=env,cwd=game,stdout=f,stderr=f)
    try:
        time.sleep(2);assert proc.poll() is None
        run('running_game_rejected',expected=1);check(original)
    finally:
        if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
save_json(scratch/'installer_tests.json',dict(status='PASS',final_zip_sha256=sha((ROOT/'release_output/BOREWORKS_DEMO_KOREAN_PATCH_1.0.0.zip').read_bytes()),cases=results,hard_stop_actual=True,final_game_matches_original=True,original_files=len(original),previous_public_release='NOT_APPLICABLE: 첫 공개 가능 버전; 미배포 ko_v001 거부 별도 검증'))
print('INSTALLER_ALL_PASS',len(results))
