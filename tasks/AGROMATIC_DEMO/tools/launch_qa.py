"""게임을 격리 실행하고 실제 프로세스 경로·사용자 저장 경계를 기록합니다."""
from pathlib import Path
from datetime import datetime, timezone
import ctypes
import json
import os
import subprocess
import sys
from common import ROOT, WORK, sha, save


def user_snapshot():
    paths = [Path(os.environ['APPDATA']) / 'Godot/app_userdata/Agromatic',
             Path(os.environ['LOCALAPPDATA']) / 'Agromatic']
    steam = Path('D:/steam/userdata')
    if steam.exists():
        for user in steam.iterdir():
            if user.is_dir():
                paths.extend([user / '4252500', user / '4179990'])
    rows = []
    for root in paths:
        rows.append({'root': str(root), 'exists': root.exists(), 'files': [
            {'path': str(path.relative_to(root)), 'size': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(root.rglob('*')) if path.is_file()] if root.exists() else []})
    return rows


if __name__ == '__main__':
    if sys.argv[1] == 'snapshot':
        save(WORK / (sys.argv[2] + '.json'), user_snapshot())
        print('사용자 저장 목록 기록 완료')
        raise SystemExit(0)
    game = Path(sys.argv[1]).resolve()
    if not game.is_relative_to(WORK) or game.name != 'game':
        raise ValueError('검수 전용 게임 사본만 실행합니다.')
    run = WORK / 'runs' / sys.argv[2]
    if run.exists():
        raise ValueError('기존 실행 기록은 덮어쓰지 않습니다.')
    run.mkdir(parents=True)
    save(run / 'user_before.json', user_snapshot())
    env = os.environ.copy()
    env['APPDATA'] = str(run / 'roaming')
    env['LOCALAPPDATA'] = str(run / 'local')
    env['AGROMATIC_QA_DRIVER'] = '1'
    for key in ('APPDATA', 'LOCALAPPDATA'):
        Path(env[key]).mkdir(parents=True)
    args = [str(game / 'AgromaticDemo.exe'), '--windowed', '--resolution', '1440x810',
            '--max-fps', '60', '--log-file', str(run / 'player.log')]
    with (run / 'stdout.log').open('wb') as out, (run / 'stderr.log').open('wb') as err:
        process = subprocess.Popen(args, cwd=game, env=env, stdout=out, stderr=err)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, process.pid)
    value, size = ctypes.create_unicode_buffer(32768), ctypes.c_uint32(32768)
    try:
        if not kernel.QueryFullProcessImageNameW(handle, 0, value, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)
    actual = Path(value.value).resolve()
    if actual != (game / 'AgromaticDemo.exe').resolve():
        process.terminate()
        raise ValueError('실행 사본 경로 불일치')
    save(run / 'launch.json', {'pid': process.pid, 'actual_process_path': str(actual),
         'exe_sha256': sha(actual), 'args': args, 'start_utc': datetime.now(timezone.utc).isoformat(),
         'appdata': env['APPDATA'], 'localappdata': env['LOCALAPPDATA']})
    print(json.dumps({'pid': process.pid, 'run_id': run.name, 'actual_path_matches': True}, ensure_ascii=False))
    sys.stdout.flush()
    code = process.wait()
    save(run / 'user_after.json', user_snapshot())
    print('실행 종료 코드:', code)
