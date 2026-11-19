"""검증을 통과한 최종 ZIP의 설치기를 사용자의 실제 설치본에 실행하고 결과를 독립적으로 확인합니다.

사용: python install_target.py <버전_리비전>   예) python install_target.py 1.0.0_r1
실행 전 확인(하나라도 어긋나면 아무것도 하지 않음):
  - 최종 ZIP 해시가 패키지 기록과 같고, 설치 시험(G7)이 같은 ZIP에 대해 PASS
  - 설치기 폴더의 모든 파일이 ZIP 안의 목록(manifest payload) 지문과 같음
  - 실제 설치본의 4개 파일이 원본 기준선과 같음, 게임이 실행 중이 아님
설치는 ZIP에 든 Patch.ps1이 합니다. 이 도구는 게임 파일을 직접 고치지 않습니다.
"""
import datetime
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, WORK, PCK_NAME, EXE_NAME, save, load, sha

TARGET = Path('D:/steam/steamapps/common/Clicky Islands')
SHELL = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


def user_snapshot():
    roots = [Path(os.environ['APPDATA']) / 'Karrot Games', Path(os.environ['APPDATA']) / 'Godot/app_userdata/Clicky Islands']
    steam = Path('D:/steam/userdata')
    if steam.exists():
        roots += [user / app for user in steam.iterdir() if user.is_dir() for app in ('4178790', '4401470')]
    return {str(root): ({p.relative_to(root).as_posix(): {'size': p.stat().st_size, 'sha256': sha(p)} for p in root.rglob('*') if p.is_file()}
                        if root.exists() else None) for root in roots}


def target_hashes():
    return {p.name: {'size': p.stat().st_size, 'sha256': sha(p)} for p in sorted(TARGET.iterdir()) if p.is_file()}


def main():
    tag = sys.argv[1]
    scratch = WORK / f'package_{tag}'
    report = load(scratch / 'package.json')
    tests = load(scratch / 'installer_tests.json')
    release = ROOT / 'release_output' / f'CLICKY_ISLANDS_KOREAN_PATCH_{tag}'
    archive = Path(report['archive'])
    out = WORK / f'install_{tag}'
    if out.exists():
        raise SystemExit('같은 판의 설치 기록이 이미 있습니다. 덮어쓰지 않습니다.')
    assert sha(archive) == report['zip_sha256'], '최종 ZIP이 기록과 다릅니다.'
    assert tests['status'] == 'PASS' and tests['zip_sha256'] == report['zip_sha256'], 'G7이 같은 ZIP에 대해 PASS가 아닙니다.'
    manifest = load(release / 'manifest.json')
    assert sha(release / 'manifest.json') == report['manifest_sha256']
    with zipfile.ZipFile(archive) as source:
        names = set(source.namelist())
    present = {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}
    assert present == names, '설치기 폴더의 파일 목록이 ZIP과 다릅니다.'
    for item in manifest['payload']:
        assert sha(release / item['path']) == item['sha256'], item['path']
    baseline = {f['path']: f for f in manifest['baseline']}
    before = target_hashes()
    assert set(before) == set(baseline), '설치본의 파일 목록이 기준선과 다릅니다.'
    for name, row in baseline.items():
        assert before[name]['sha256'] == row['sha256'], '설치본이 원본 기준선과 다릅니다: ' + name
    running = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ' + EXE_NAME], capture_output=True).stdout.decode('cp949', errors='replace')
    assert EXE_NAME not in running, '게임이 실행 중입니다.'
    out.mkdir(parents=True)
    users_before = user_snapshot()
    save(out / 'user_before.json', users_before)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    command = [str(SHELL), '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(release / 'Patch.ps1'),
               '-Mode', 'Install', '-GameDirectory', str(TARGET)]
    result = subprocess.run(command, capture_output=True, timeout=900, creationflags=subprocess.CREATE_NO_WINDOW)
    (out / 'install.stdout').write_bytes(result.stdout)
    (out / 'install.stderr').write_bytes(result.stderr)
    after = target_hashes()
    users_after = user_snapshot()
    save(out / 'user_after.json', users_after)
    change = next(c for c in manifest['changes'] if c['path'] == PCK_NAME)
    checks = {'installer_exit_code': result.returncode,
              'pck_is_patched': after.get(PCK_NAME, {}).get('sha256') == change['patched_sha256'],
              'other_files_unchanged': all(after[n]['sha256'] == before[n]['sha256'] for n in before if n != PCK_NAME),
              'no_extra_files': set(after) == set(before),
              'user_saves_unchanged': users_before == users_after}
    status = 'PASS' if result.returncode == 0 and all(v is True for k, v in checks.items() if k != 'installer_exit_code') else 'FAIL'
    save(out / 'install.json', {'game_id': 'CLICKY_ISLANDS', 'target': str(TARGET), 'version': tag, 'status': status,
                                'started_utc': started, 'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                'zip_sha256': report['zip_sha256'], 'command': command, 'checks': checks, 'before': before, 'after': after,
                                'steam_launch_after_install': 'NOT_RUN'})
    print(json.dumps({'status': status, **checks}, ensure_ascii=False))
    print(result.stdout.decode('utf-8', errors='replace')[-400:])
    sys.exit(0 if status == 'PASS' else 1)


if __name__ == '__main__':
    main()
