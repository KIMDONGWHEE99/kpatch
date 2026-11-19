"""고정한 후보로 정·역 차이 파일을 만들고 최종 ZIP의 시험용 사본을 준비합니다."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME = 'COBALT_MINER'
BUILD = '24347666'
APP_ID = '4601880'
EXE = 'COBALT MINER.exe'
BASELINE = ROOT / 'source_original' / GAME / 'steam_24347666'
WORK = ROOT / 'working_private' / GAME
TEMPLATE = ROOT / 'tasks' / GAME / 'release_template'
TOOL_ROOT = ROOT / 'tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0'
ENCODER = TOOL_ROOT / 'extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe'
FONT_ROOT = WORK / 'font_complete_02/fonts'
FONT_LICENSES = {name: FONT_ROOT / name for name in ('NotoSansKR-OFL.txt', 'NotoSans-OFL.txt')}
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
    folder = Path(folder).resolve()
    result = {}
    seen = set()
    for p in sorted(folder.rglob('*')):
        if p.is_symlink() or getattr(p.lstat(), 'st_file_attributes', 0) & 1024:
            raise ValueError('연결 경로가 있습니다: ' + str(p))
        if p.is_file():
            name = p.relative_to(folder).as_posix()
            assert name.casefold() not in seen, '대소문자 중복 경로'
            seen.add(name.casefold())
            result[name] = p
    return result


def safe_relative(name):
    assert name and not name.startswith(('/', '\\')) and ':' not in name
    assert not any(part in ('', '.', '..') for part in name.replace('\\', '/').split('/'))


def make_package(source, candidate, files, changes, release, scratch, version, candidate_id, readme, gate_record=None):
    """기존 파일 수정과 신규 파일 추가를 동일한 복구 규칙으로 처리합니다."""
    started = utc_now()
    source, candidate, release, scratch = map(Path, (source, candidate, release, scratch))
    source, candidate, release, scratch = [p.resolve() for p in (source, candidate, release, scratch)]
    scratch.relative_to(WORK.resolve())
    synthetic = source != BASELINE.resolve()
    if synthetic:
        source.relative_to(WORK.resolve())
        candidate.relative_to(WORK.resolve())
        release.relative_to(WORK.resolve())
    else:
        candidate.relative_to((ROOT / 'build_candidate' / GAME).resolve())
        release.relative_to((ROOT / 'release_output').resolve())
        assert gate_record and gate_record['status'] in ('PASS', 'USER_WAIVER'), '후보 고정 증거와 검증 또는 명시적 사용자 생략 기록이 필요합니다.'
        assert '@VERSION@' not in readme and '제작용 안내:' not in readme, '실제 검수 범위로 완성한 README가 필요합니다.'
    assert not release.exists() and not scratch.exists(), '기존 결과를 덮어쓰지 않습니다.'
    release.mkdir(parents=True)
    scratch.mkdir(parents=True)
    for directory in ('tools', 'licenses', 'patches'):
        (release / directory).mkdir()
    shutil.copy2(ENCODER, release / 'tools/xdelta3.exe')
    shutil.copy2(TOOL_ROOT / 'LICENSE-APACHE-2.0.txt', release / 'licenses/xdelta3-APACHE-2.0.txt')
    for name, path in FONT_LICENSES.items():
        shutil.copy2(path, release / 'licenses' / name)
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
    if gate_record and gate_record['status'] == 'USER_WAIVER':
        write_json(release / 'REVIEW_STATUS.json', gate_record['public_review_status'])
    empty = scratch / 'empty_original'
    empty.write_bytes(b'')
    delta_records = []
    assert len(changes) == len(set(changes)) and changes
    def prepare_delta(task):
        index, name = task
        safe_relative(name)
        original, patched = source / name, candidate / name
        assert patched.is_file(), name
        added = not original.exists()
        assert not added or original.parent.is_dir(), '신규 파일은 기존 폴더 안에만 추가합니다.'
        before = empty if added else original
        assert added or sha(before) != sha(patched), name
        record = {'path': name, 'original_sha256': None if added else sha(before), 'original_size': None if added else before.stat().st_size,
                  'patched_sha256': sha(patched), 'patched_size': patched.stat().st_size, 'original_absent': added}
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
        assert sha(patched) == record['patched_sha256'] and (added or sha(before) == record['original_sha256']), '차이 생성 중 입력 변경'
        return record
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, record in enumerate(pool.map(prepare_delta, enumerate(changes)), 1):
            delta_records.append(record)
            if index % 1000 == 0:
                print(json.dumps({'delta_files_completed': index, 'total': len(changes)}), flush=True)
    baseline = [{'path': name, 'size': (source / name).stat().st_size, 'sha256': sha(source / name)}
                for name in sorted(files)]
    payload = [{'path': p.relative_to(release).as_posix(), 'size': p.stat().st_size, 'sha256': sha(p)}
               for p in sorted(release.rglob('*')) if p.is_file()]
    manifest = {'schema_version': 1, 'game_id': GAME, 'steam_build': BUILD, 'steam_app_id': APP_ID, 'version': version,
                'candidate': candidate_id, 'baseline': baseline, 'changes': delta_records, 'payload': payload}
    write_json(release / 'manifest.json', manifest)
    allow = {'Install.cmd', 'Remove.cmd', 'Patch.ps1', 'ChooseGame.ps1', 'README.txt', 'manifest.json',
             'tools/xdelta3.exe', 'licenses/xdelta3-APACHE-2.0.txt'}
    allow.update('licenses/' + name for name in FONT_LICENSES)
    if gate_record and gate_record['status'] == 'USER_WAIVER':
        allow.add('REVIEW_STATUS.json')
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
              'font_licenses': [{'path': name, 'sha256': sha(path)} for name, path in FONT_LICENSES.items()],
              'synthetic_fixture': synthetic, 'gates': gate_record, 'G6': 'PASS', 'G7': 'NOT_RUN', 'exit_code': 0,
              'scope': '차이 정역복원·패키지 허용목록 검사. 합성자료면 실제 게임의 G6/G7 완료 근거가 아닙니다.'}
    write_json(scratch / 'package.json', report)
    return report


def default_readme(version):
    return (TEMPLATE / 'README.txt').read_text(encoding='utf-8-sig').replace('@VERSION@', version)


def verify_release_gate(path, candidate):
    """보고서의 성공 문구뿐 아니라 같은 후보 목록·파일과 증거 지문을 확인한다."""
    path = Path(path).resolve()
    path.relative_to(WORK.resolve())
    gate = json.loads(path.read_text(encoding='utf-8'))
    assert gate['game_id'] == GAME and str(gate['steam_build']) == BUILD
    assert gate['status'] in ('PASS', 'USER_WAIVER')
    assert len(gate['allowed_changes']) == len(set(gate['allowed_changes'])) and gate['allowed_changes']
    for name in gate['allowed_changes']:
        safe_relative(name)
    assert isinstance(gate['dependencies'], list) and gate['dependencies'], '번역·도구·원본 의존 지문 목록이 필요합니다.'
    dependency_paths = set()
    for item in gate['dependencies']:
        safe_relative(item['path'])
        assert item['path'] not in dependency_paths, '중복 의존 지문'
        dependency_paths.add(item['path'])
        assert sha(ROOT / item['path']) == item['sha256'], 'STALE 의존 입력: ' + item['path']
    freeze_ref = gate['candidate_manifest']
    safe_relative(freeze_ref['path'])
    freeze_path = ROOT / freeze_ref['path']
    assert sha(freeze_path) == freeze_ref['sha256'], 'STALE 후보 목록'
    freeze = json.loads(freeze_path.read_text(encoding='utf-8'))
    assert freeze['game_id'] == GAME and str(freeze['steam_build']) == BUILD
    assert freeze['candidate_id'] == gate['candidate_id']
    actual = file_map(candidate)
    frozen = {r['path']: r for r in freeze['files']}
    assert len(frozen) == len(freeze['files']) and set(actual) == set(frozen)
    for name, actual_path in actual.items():
        assert actual_path.stat().st_size == frozen[name]['size'] and sha(actual_path) == frozen[name]['sha256'], 'STALE 후보 파일: ' + name
    waived = gate['status'] == 'USER_WAIVER'
    waiver = None
    if waived:
        ref = gate['waiver']
        safe_relative(ref['path'])
        assert sha(ROOT / ref['path']) == ref['sha256'], '사용자 생략 기록 지문 변경'
        waiver = json.loads((ROOT / ref['path']).read_text(encoding='utf-8'))
        assert waiver['authorization'] == 'EXPLICIT_USER_REQUEST'
        assert waiver['candidate_manifest_sha256'] == freeze_ref['sha256']
        assert isinstance(waiver['user_instruction'], str) and waiver['user_instruction'].strip()
        # 현재 요청은 추가 조사·화면 검수 종료입니다. 최종 정적 검사와 설치·복구는 생략하지 않습니다.
        assert set(waiver['waived_checks']) == {'G2', 'G5'}
    for name in ('G2', 'G3', 'G4', 'G5'):
        item = gate['checks'][name]
        safe_relative(item['path'])
        evidence_path = ROOT / item['path']
        permitted = ('PASS', 'FAIL', 'NOT_RUN') if waived and name in waiver['waived_checks'] else ('PASS',)
        assert item['status'] in permitted and sha(evidence_path) == item['sha256'], 'STALE ' + name
        evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
        assert evidence['status'] == item['status'] and evidence['candidate_manifest_sha256'] == freeze_ref['sha256'], '후보가 다른 ' + name
    result = {'status': gate['status'], 'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path), 'candidate_manifest': freeze_ref,
              'candidate_id': gate['candidate_id'], 'allowed_changes': gate['allowed_changes'], 'checks': gate['checks'], 'dependencies': gate['dependencies']}
    if waived:
        result['waiver'] = gate['waiver']
        result['public_review_status'] = {'game_id': GAME, 'steam_build': BUILD, 'candidate_id': gate['candidate_id'], 'status': 'RELEASED_WITH_USER_REQUESTED_REVIEW_OMISSIONS', 'user_instruction': waiver['user_instruction'], 'checks': {key: {'status': item['status'], 'scope': json.loads((ROOT / item['path']).read_text(encoding='utf-8')).get('scope')} for key, item in gate['checks'].items()}, 'waived_checks': waiver['waived_checks'], 'candidate_manifest_sha256': freeze_ref['sha256']}
    return result


def main():
    parser = argparse.ArgumentParser(description='후보의 변경·추가 파일을 차이 패치로 묶습니다.')
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--baseline-manifest', required=True, type=Path)
    parser.add_argument('--release-gate', required=True, type=Path, help='같은 최종 후보의 G2·G3·G4·G5 PASS와 허용 변경 목록·지문 연결 기록')
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
        baseline_id = baseline_data.get('baseline_id', baseline_data.get('build_id'))
        assert baseline_id == 'steam_24347666'
    rows = baseline_data if isinstance(baseline_data, list) else baseline_data['files']
    original, patched = file_map(BASELINE), file_map(candidate)
    expected = {r['path']: r for r in rows}
    assert len(expected) == len(rows), '중복 원본 위치 ID'
    assert set(original) == set(expected), '원본 파일 목록이 다릅니다.'
    assert set(original) <= set(patched), '후보에서 원본 파일이 삭제됐습니다.'
    assert set(patched) - set(original) == set(args.allow_added), '신규 파일 허용 목록이 후보와 다릅니다.'
    for name, path in original.items():
        assert path.stat().st_size == expected[name]['size'] and sha(path) == expected[name]['sha256'], name
    changes = [name for name in sorted(patched) if name not in original or sha(patched[name]) != expected[name]['sha256']]
    gate_record = verify_release_gate(args.release_gate, candidate)
    assert set(changes) == set(gate_record['allowed_changes']), '검수한 변경 경계와 실제 후보가 다릅니다.'
    readme = (args.readme.read_text(encoding='utf-8-sig') if args.readme else default_readme(args.version)).replace('@VERSION@', args.version)
    release = ROOT / 'release_output' / f'{GAME}_KOREAN_PATCH_{args.version}_{args.revision}'
    scratch = WORK / f'package_{args.version}_{args.revision}'
    candidate_id = candidate.relative_to((ROOT / 'build_candidate' / GAME).resolve()).parts[0]
    assert candidate_id == gate_record['candidate_id']
    report = make_package(BASELINE, candidate, list(original), changes, release, scratch, args.version, candidate_id, readme, gate_record)
    assert verify_release_gate(args.release_gate, candidate) == gate_record, '패키징 중 입력 변경'
    report['baseline_manifest_sha256'] = sha(args.baseline_manifest)
    report['package_tool_sha256'] = sha(Path(__file__))
    report['candidate_files'] = [{'path': name, 'size': path.stat().st_size, 'sha256': sha(path)} for name, path in patched.items()]
    report['scope'] = '차이 복원·허용 목록 확인. G4·G5 검수 완료를 뜻하지 않음.'
    write_json(scratch / 'package.json', report)
    print(json.dumps({'archive': report['archive'], 'zip_sha256': report['zip_sha256'], 'changes': len(changes)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
