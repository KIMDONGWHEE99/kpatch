import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from build import BASE, CANDIDATE, ROOT, WORK, GAME


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    info = json.loads((WORK / 'package_info.json').read_text(encoding='utf-8'))
    archive = Path(info['path'])
    assert sha(archive.read_bytes()) == info['sha256']
    run = WORK / ('installer_tests_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    pack = run / '최종 ZIP 압축 해제'
    pack.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == set(info['file_allowlist'])
        for name in z.namelist():
            assert (pack/name).resolve().is_relative_to(pack.resolve())
        z.extractall(pack)
    for row in json.loads((pack / 'package_manifest.json').read_text(encoding='utf-8'))['files']:
        assert sha((pack / row['path']).read_bytes()) == row['sha256']
    original = (BASE / 'VanillaPlus/Config/Localization.csv').read_bytes()
    candidate = (CANDIDATE / 'VanillaPlus/Config/Localization.csv').read_bytes()
    records = []

    def fixture(name, content=original):
        mod = run / name / '모드 폴더 공백' / 'VanillaPlus'
        target = mod / 'Config/Localization.csv'
        target.parent.mkdir(parents=True)
        target.write_bytes(content)
        shutil.copy2(BASE / 'VanillaPlus/ModInfo.xml', mod / 'ModInfo.xml')
        (mod.parent / 'untouched.sentinel').write_bytes(b'unrelated file remains intact')
        return target

    def run_tool(name, target, mode, success, expected, package=pack, lock=False):
        script = package / 'Patch.ps1'
        command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-File', str(script), '-Mode', mode, '-Path', str(target)]
        if lock:
            quote = lambda value: "'" + str(value).replace("'", "''") + "'"
            code = "$lock = [System.IO.File]::Open(" + quote(target) + ", 'Open', 'Read', 'Read'); try { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
            code += quote(script) + ' -Mode ' + mode + ' -Path ' + quote(target) + '; $result = $LASTEXITCODE } finally { $lock.Dispose() }; exit $result'
            command = ['powershell.exe', '-NoProfile', '-Command', code]
        result = subprocess.run(command, capture_output=True, timeout=60)
        assert (result.returncode == 0) == success, (name, result.returncode, result.stdout.decode('utf-8', errors='replace'), result.stderr.decode('utf-8', errors='replace'))
        assert target.read_bytes() == expected, name
        assert (target.parents[2] / 'untouched.sentinel').read_bytes() == b'unrelated file remains intact'
        record = {'id': name, 'status': 'PASS', 'exit_code': result.returncode,
            'target_sha256': sha(target.read_bytes()), 'installer_sha256': sha(script.read_bytes())}
        records.append(record)
        print(name, 'PASS', flush=True)

    clean = fixture('정상 설치')
    run_tool('install_original', clean, 'Install', True, candidate)
    assert Path(str(clean) + '.vanillaplus-ko.original').read_bytes() == original
    run_tool('install_duplicate', clean, 'Install', True, candidate)
    run_tool('remove', clean, 'Remove', True, original)
    run_tool('remove_duplicate', clean, 'Remove', True, original)
    run_tool('reinstall', clean, 'Install', True, candidate)
    missing_backup = fixture('백업 없이 복구', candidate)
    run_tool('remove_without_backup', missing_backup, 'Remove', True, original)
    changed = fixture('수정본 거부', original + b'changed')
    run_tool('reject_modified', changed, 'Install', False, original + b'changed')
    partial = fixture('부분 번역 거부', original[:5000] + candidate[5000:])
    partial_data = partial.read_bytes()
    run_tool('reject_partial_install', partial, 'Install', False, partial_data)
    updated = fixture('모드 버전 거부')
    modinfo = updated.parents[1] / 'ModInfo.xml'
    modinfo.write_bytes(modinfo.read_bytes().replace(b'1.6.0', b'1.6.1'))
    run_tool('reject_new_version', updated, 'Install', False, original)
    corrupt_pack = run / '손상된 패키지'
    shutil.copytree(pack, corrupt_pack)
    delta_file = corrupt_pack / 'korean.delta.json'
    delta_file.write_bytes(delta_file.read_bytes() + b' ')
    corrupt = fixture('패키지 손상 거부')
    run_tool('reject_corrupt_delta', corrupt, 'Install', False, original, corrupt_pack)
    blocked_backup = fixture('다른 백업 거부')
    Path(str(blocked_backup) + '.vanillaplus-ko.original').write_bytes(b'not the original backup')
    run_tool('reject_unknown_backup', blocked_backup, 'Install', False, original)
    locked = fixture('교체 실패 복구')
    run_tool('locked_target_rollback', locked, 'Install', False, original, lock=True)
    run_tool('retry_after_locked_failure', locked, 'Install', True, candidate)
    interrupted = fixture('교체 전 중단 상태')
    Path(str(interrupted) + '.vanillaplus-ko.pending').write_bytes(candidate)
    run_tool('recover_pending_before_commit', interrupted, 'Install', True, candidate)
    after_commit = fixture('교체 후 중단 상태', candidate)
    Path(str(after_commit) + '.vanillaplus-ko.pending').write_bytes(original)
    run_tool('recover_pending_after_commit', after_commit, 'Install', True, candidate)
    unknown_pending = fixture('알 수 없는 임시 파일')
    Path(str(unknown_pending) + '.vanillaplus-ko.pending').write_bytes(b'incomplete output')
    run_tool('preserve_partial_pending_and_retry', unknown_pending, 'Install', True, candidate)
    preserved = list(unknown_pending.parent.glob('Localization.csv.vanillaplus-ko.pending.recovered.*'))
    assert len(preserved) == 1 and preserved[0].read_bytes() == b'incomplete output'
    partial_backup = fixture('백업 쓰기 중 중단')
    Path(str(partial_backup) + '.vanillaplus-ko.original').write_bytes(original[:2000])
    run_tool('recover_partial_backup', partial_backup, 'Install', True, candidate)
    preserved = list(partial_backup.parent.glob('Localization.csv.vanillaplus-ko.original.recovered.*'))
    assert len(preserved) == 1 and preserved[0].read_bytes() == original[:2000]
    launcher_target = fixture('CMD 실행기')
    for filename, expected in [('적용.cmd', candidate), ('제거.cmd', original)]:
        result = subprocess.run(['cmd.exe', '/d', '/c', 'call', str(pack / filename), str(launcher_target)],
            input=b'\n', capture_output=True, timeout=60)
        assert result.returncode == 0 and launcher_target.read_bytes() == expected, (filename, result.stdout, result.stderr)
        records.append({'id': 'launcher_' + filename, 'status': 'PASS', 'exit_code': result.returncode,
            'target_sha256': sha(launcher_target.read_bytes()), 'installer_sha256': sha((pack / filename).read_bytes())})
        print(filename, 'PASS', flush=True)
    assert sha(archive.read_bytes()) == info['sha256']
    report = {'game_id': GAME, 'build_id': 'ko_0.1.0', 'status': 'PASS', 'zip_sha256': info['sha256'],
        'zip_size': archive.stat().st_size, 'tests': records, 'count': len(records), 'allowlist_verified': True,
        'source_sha256': sha(original), 'candidate_sha256': sha(candidate),
        'scope': '최종 ZIP에서 추출한 실제 PowerShell 설치기를 격리된 한글·공백 경로에서 실행. 중단은 교체 전후 잔여 상태로 재현.',
        'not_run': ['실제 게임 설치', '실제 게임 실행', '실제 프로세스 강제 종료', 'GUI 파일 선택 대화상자'],
        'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    output = ROOT / 'validation' / GAME / 'ko_0.1.0/package_checks.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('TOTAL', len(records), 'PASS')


if __name__ == '__main__':
    main()
