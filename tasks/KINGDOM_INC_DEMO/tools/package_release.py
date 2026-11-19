"""고정한 후보로 정·역 차이 파일을 만들고 최종 ZIP의 시험용 사본을 준비합니다."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GAME = 'KINGDOM_INC_DEMO'
BUILD = '25631786'
APP_ID = '4702410'
EXE = 'KingdomInc.exe'
BASELINE = ROOT / 'source_original' / GAME / ('steam_' + BUILD) / 'game'
WORK = ROOT / 'working_private' / GAME
TEMPLATE = ROOT / 'tasks' / GAME / 'release_template'
TOOL_ROOT = ROOT / 'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0'
ENCODER = TOOL_ROOT / 'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
FONT_LICENSE = ROOT / 'tasks/TFC2/third_party/NotoSansKR/OFL.txt'
EMPTY_HASH = hashlib.sha256(b'').hexdigest()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def file_map(folder):
    return {p.relative_to(folder).as_posix(): p for p in sorted(folder.rglob('*')) if p.is_file()}


def safe_relative(name):
    assert name and not name.startswith(('/', '\\')) and ':' not in name
    assert not any(part in ('', '.', '..') for part in name.replace('\\', '/').split('/'))


def make_package(source, candidate, files, changes, release, scratch, version, candidate_id, readme):
    """기존 파일 수정과 신규 파일 추가를 동일한 복구 규칙으로 처리합니다."""
    started = utc_now()
    source, candidate, release, scratch = map(Path, (source, candidate, release, scratch))
    assert not release.exists() and not scratch.exists(), '기존 결과를 덮어쓰지 않습니다.'
    release.mkdir(parents=True)
    scratch.mkdir(parents=True)
    for directory in ('tools', 'licenses', 'patches'):
        (release / directory).mkdir()
    shutil.copy2(ENCODER, release / 'tools/xdelta3.exe')
    shutil.copy2(TOOL_ROOT / 'LICENSE-APACHE-2.0.txt', release / 'licenses/xdelta3-APACHE-2.0.txt')
    shutil.copy2(FONT_LICENSE, release / 'licenses/NotoSansKR-OFL.txt')
    for name in ('Patch.ps1', 'ChooseGame.ps1'):
        text = (TEMPLATE / name).read_text(encoding='utf-8-sig').replace('@VERSION@', version)
        assert '@VERSION@' not in text
        (release / name).write_text(text, encoding='utf-8-sig')
    for name, mode in (('Install.cmd', 'Install'), ('Remove.cmd', 'Uninstall')):
        text = ('@echo off\ncd /d "%~dp0"\npowershell.exe -NoLogo -NoProfile '
                '-ExecutionPolicy Bypass -File "%~dp0Patch.ps1" -Mode ' + mode + ' %*\n'
                'set "PATCH_EXIT=%ERRORLEVEL%"\npause\nexit /b %PATCH_EXIT%\n')
        (release / name).write_text(text, encoding='ascii', newline='\r\n')
    (release / 'README.txt').write_text(readme, encoding='utf-8-sig')
    empty = scratch / 'empty_original'
    empty.write_bytes(b'')
    delta_records = []
    assert len(changes) == len(set(changes)) and changes
    for index, name in enumerate(changes):
        safe_relative(name)
        original, patched = source / name, candidate / name
        assert patched.is_file(), name
        added = not original.exists()
        assert not added or original.parent.is_dir(), '신규 파일은 기존 폴더 안에만 추가합니다.'
        before = empty if added else original
        assert added or sha(before) != sha(patched), name
        record = {'path': name, 'original_sha256': None if added else sha(before),
                  'patched_sha256': sha(patched), 'original_absent': added}
        for direction, start, target in (('forward', before, patched), ('reverse', patched, before)):
            relative = f'patches/{index:02d}.{direction}.xdelta'
            delta, rebuilt = release / relative, scratch / f'{index:02d}.{direction}.rebuilt'
            subprocess.run([str(ENCODER), '-f', '-e', '-9', '-s', str(start), str(target), str(delta)],
                           check=True, capture_output=True)
            subprocess.run([str(ENCODER), '-d', '-s', str(start), str(delta), str(rebuilt)],
                           check=True, capture_output=True)
            assert sha(rebuilt) == sha(target), direction
            record[direction] = relative
            record[direction + '_roundtrip'] = {'status': 'PASS', 'sha256': sha(rebuilt), 'delta_sha256': sha(delta)}
        delta_records.append(record)
    baseline = [{'path': name, 'size': (source / name).stat().st_size, 'sha256': sha(source / name)}
                for name in sorted(files)]
    payload = [{'path': p.relative_to(release).as_posix(), 'size': p.stat().st_size, 'sha256': sha(p)}
               for p in sorted(release.rglob('*')) if p.is_file()]
    manifest = {'game_id': GAME, 'steam_build': BUILD, 'steam_app_id': APP_ID, 'version': version,
                'candidate': candidate_id, 'baseline': baseline, 'changes': delta_records, 'payload': payload}
    write_json(release / 'manifest.json', manifest)
    allow = {'Install.cmd', 'Remove.cmd', 'Patch.ps1', 'ChooseGame.ps1', 'README.txt', 'manifest.json',
             'tools/xdelta3.exe', 'licenses/xdelta3-APACHE-2.0.txt', 'licenses/NotoSansKR-OFL.txt'}
    for record in delta_records:
        allow.update((record['forward'], record['reverse']))
    assert set(file_map(release)) == allow
    archive = release.parent / (release.name + '.zip')
    assert not archive.exists(), '기존 ZIP을 덮어쓰지 않습니다.'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name in sorted(allow):
            output.write(release / name, name)
    extracted = scratch / 'from_final_zip'
    with zipfile.ZipFile(archive) as source_zip:
        assert len(source_zip.namelist()) == len(allow)
        assert set(source_zip.namelist()) == allow and source_zip.testzip() is None
        source_zip.extractall(extracted)
    for name in allow:
        assert sha(release / name) == sha(extracted / name), name
    report = {'game_id': GAME, 'steam_build': BUILD, 'candidate': candidate_id, 'version': version,
              'started_utc': started, 'completed_utc': utc_now(), 'archive': str(archive),
              'scratch': str(scratch), 'zip_sha256': sha(archive),
              'manifest_sha256': sha(extracted / 'manifest.json'), 'allowed_files': sorted(allow),
              'encoder_sha256': sha(ENCODER), 'changes': delta_records,
              'font_license_sha256': sha(FONT_LICENSE), 'G6': 'PASS', 'G7': 'NOT_RUN', 'exit_code': 0}
    write_json(scratch / 'package.json', report)
    return report


def default_readme(version):
    return f'''Kingdom Inc. Demo 한국어 패치 {version}

지원: Windows / Steam 앱 {APP_ID}, 빌드 {BUILD}.
설치: 게임을 종료하고 ZIP을 모두 푼 뒤 Install.cmd를 실행하세요.
KingdomInc.exe가 있는 게임 폴더를 선택합니다.
제거: Remove.cmd를 실행하여 같은 폴더를 선택하세요.

원본 백업과 중단 복구 기록:
%LOCALAPPDATA%\\KingdomIncKoreanPatch\\working_private
중간에 멈췄다면 같은 설치기를 다시 실행하세요.
게임 업데이트·미지원 파일·손상 파일에는 강제로 적용하지 않습니다.
신규 파일이 포함된 경우 제거 시 패치가 추가한 파일만 원래의 부재 상태로 복원합니다.

번역·화면 검수 범위와 남긴 표기, 최종 ZIP 설치·복구 시험은 ZIP 밖의
동일 ZIP 해시를 참조하는 결과 보고서에서 확인하세요.
게임 원본 자산·검수 코드·사용자 저장 파일은 이 ZIP에 포함하지 않습니다.
Noto Sans KR: SIL Open Font License 1.1.
xdelta3 3.2.0: Apache License 2.0.
'''


def main():
    parser = argparse.ArgumentParser(description='후보의 변경·추가 파일을 차이 패치로 묶습니다.')
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--baseline-manifest', required=True, type=Path)
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--revision', default='r1')
    parser.add_argument('--readme', type=Path)
    parser.add_argument('--allow-added', action='append', default=[], help='후보 신규 파일의 명시적 허용 경로. 여러 번 지정할 수 있습니다.')
    args = parser.parse_args()
    assert re.fullmatch(r'\d+\.\d+\.\d+', args.version)
    assert re.fullmatch(r'[a-z0-9_-]+', args.revision)
    candidate = args.candidate.resolve()
    candidate.relative_to((ROOT / 'build_candidate' / GAME).resolve())
    baseline_data = json.loads(args.baseline_manifest.read_text(encoding='utf-8'))
    if isinstance(baseline_data, dict):
        assert baseline_data['game_id'] == GAME
        assert baseline_data['build_id'] in (BUILD, 'steam_' + BUILD)
        assert str(baseline_data['steam_app_id']) == APP_ID
    rows = baseline_data if isinstance(baseline_data, list) else baseline_data['files']
    original, patched = file_map(BASELINE), file_map(candidate)
    expected = {r['path']: r for r in rows}
    assert set(original) == set(expected), '원본 파일 목록이 다릅니다.'
    assert set(original) <= set(patched), '후보에서 원본 파일이 삭제됐습니다.'
    assert set(patched) - set(original) == set(args.allow_added), '신규 파일 허용 목록이 후보와 다릅니다.'
    for name, path in original.items():
        assert path.stat().st_size == expected[name]['size'] and sha(path) == expected[name]['sha256'], name
    changes = [name for name in sorted(patched) if name not in original or sha(patched[name]) != expected[name]['sha256']]
    readme = args.readme.read_text(encoding='utf-8-sig') if args.readme else default_readme(args.version)
    release = ROOT / 'release_output' / f'{GAME}_KOREAN_PATCH_{args.version}_{args.revision}'
    scratch = WORK / f'package_{args.version}_{args.revision}'
    candidate_id = candidate.relative_to((ROOT / 'build_candidate' / GAME).resolve()).parts[0]
    report = make_package(BASELINE, candidate, list(original), changes, release, scratch, args.version, candidate_id, readme)
    report['baseline_manifest_sha256'] = sha(args.baseline_manifest)
    report['package_tool_sha256'] = sha(Path(__file__))
    report['candidate_files'] = [{'path': name, 'size': path.stat().st_size, 'sha256': sha(path)} for name, path in patched.items()]
    report['scope'] = '차이 복원·허용 목록 확인. G4·G5 검수 완료를 뜻하지 않음.'
    write_json(scratch / 'package.json', report)
    print(json.dumps({'archive': report['archive'], 'zip_sha256': report['zip_sha256'], 'changes': len(changes)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
