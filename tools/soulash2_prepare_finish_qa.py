"""고정한 통합 자산·배포 가능 글꼴을 격리된 새 실행 사본에 준비한다."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BUILD = '0.10.4.0.1_20261029'
PRIVATE = ROOT / 'working_private/SOULASH_2'
SOURCE = ROOT / 'source_original/SOULASH_2' / BUILD


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font-dir', type=Path, required=True)
    parser.add_argument('--qa-save', type=Path)
    parser.add_argument('--native-dir', type=Path)
    parser.add_argument('--allow-incomplete-investigation', action='store_true',
                        help='미해결 위치만 남은 사본으로 표시 경로를 조사한다. 배포·최종 검수 허용이 아니다.')
    args = parser.parse_args()
    stage, output, fonts = args.stage.resolve(), args.output.resolve(), args.font_dir.resolve()
    if not stage.is_relative_to(ROOT / 'build_candidate/SOULASH_2') or not output.is_relative_to(PRIVATE) or not fonts.is_relative_to(PRIVATE):
        raise ValueError('검수 경계 이탈')
    if output.exists():
        raise ValueError('기존 검수 사본 덮어쓰기 금지')
    base_path = ROOT / 'extracted_private/SOULASH_2' / BUILD / 'baseline_manifest.json'
    manifest = read(base_path)
    if sha(base_path) != '56672598007cff88e3fe74558d063d3a652a553697d3b42bd73e56c14ec1eb24':
        raise ValueError('원본 목록 지문 변경')
    report_path = stage / 'stage_report.json'
    report = read(report_path)
    checked_path = stage / 'independent_validation.json'
    checked = read(checked_path)
    partial_investigation = False
    if args.allow_incomplete_investigation and checked['status'] == 'FAIL':
        expected_failure = [{'reason': '로스터에 미해결 위치가 남음',
                             'missing': report['missing_rows'], 'held': report['held_rows']}]
        partial_investigation = (checked.get('failures') == expected_failure
            and checked.get('unresolved_total') == report['missing_rows'] + report['held_rows']
            and report['generation_status'] == 'PASS' and bool(checked.get('files'))
            and all(row['status'] == 'PASS' for row in checked['files']))
    if (checked['status'] != 'PASS' and not partial_investigation) or checked['stage_report_sha256'] != sha(report_path):
        raise ValueError('통합 자산 독립검사 불일치')
    font_report_path = fonts / 'build_report.json'
    font_report = read(font_report_path)
    settings = PRIVATE / 'qa_isolation/settings_proposed.json'
    isolation = PRIVATE / 'qa_isolation/g1_isolation_manifest.json'
    patches = read(isolation)
    if sha(isolation) != '2fcda5f858ffeb321871279509116ce1b109c4377b454f89a79a5301f9f67e5d':
        raise ValueError('검수 격리 명세 변경')
    inputs = [base_path, report_path, checked_path, font_report_path, settings, isolation, Path(__file__)]
    native_data = None
    native_sha = patches['source_sha256']
    if args.native_dir:
        native = args.native_dir.resolve()
        if not native.is_relative_to(PRIVATE):
            raise ValueError('실행 파일 변경 입력 경계 이탈')
        native_manifest_path = native / 'generation_manifest.json'
        native_validation_path = native / 'independent_validation.json'
        native_executable = native / 'Soulash 2.exe'
        native_manifest, native_validation = read(native_manifest_path), read(native_validation_path)
        native_sha = sha(native_executable)
        if (native_validation['status'] != 'PASS'
                or native_validation['source_sha256'] != patches['source_sha256']
                or native_manifest['source_sha256'] != patches['source_sha256']
                or native_manifest['contract_sha256'] != native_validation['contract_sha256']
                or native_manifest['candidate_sha256'] != native_sha
                or native_validation['candidate_sha256'] != native_sha
                or native_manifest['candidate_size'] != native_executable.stat().st_size):
            raise ValueError('실행 파일 변경의 독립검사·지문 불일치')
        native_data = native_executable.read_bytes()
        inputs += [native_manifest_path, native_validation_path, native_executable]
    inputs += [stage / 'payload' / item['file'] for item in report['files']]
    inputs += [fonts / 'fonts' / item['output'] for item in font_report['files']]
    input_hashes = {path: sha(path) for path in inputs}
    expected = {item['path']: item['sha256'] for item in manifest['files']}
    output.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()

    copy_tasks = []
    for item in manifest['files']:
        relative = item['path']
        source, target = SOURCE / relative, output / relative
        resolved_source, resolved_target = source.resolve(), target.resolve()
        if not resolved_source.is_relative_to(SOURCE) or not resolved_target.is_relative_to(output):
            raise ValueError('복사 경계 이탈: ' + repr((relative, str(resolved_source), str(resolved_target))))
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_tasks.append((item, source, target))

    def copy_original(task):
        item, source, target = task
        if source.stat().st_size != item['size'] or sha(source) != item['sha256']:
            raise ValueError('원본 변경: ' + item['path'])
        shutil.copyfile(source, target)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(copy_original, copy_tasks))
    print(json.dumps({'copied': len(expected)}), flush=True)
    executable = output / 'Soulash 2.exe'
    original = executable.read_bytes()
    if hashlib.sha256(original).hexdigest() != patches['source_sha256']:
        raise ValueError('실행 파일 원본 변경')
    modified = bytearray(native_data if native_data is not None else original)
    for patch in patches['patches']:
        offset, before, after = patch['offset'], bytes.fromhex(patch['before']), bytes.fromhex(patch['after'])
        if modified[offset:offset+len(before)] != before or len(before) != len(after):
            raise ValueError('격리 코드 변경 경계 불일치')
        modified[offset:offset+len(after)] = after
    if native_data is None and hashlib.sha256(modified).hexdigest() != patches['qa_sha256']:
        raise ValueError('검수 코드 지문 불일치')
    # 격리 변경만 되돌리면 선택한 실행 파일과 한 바이트도 달라서는 안 된다.
    restored = bytearray(modified)
    for patch in patches['patches']:
        offset, before = patch['offset'], bytes.fromhex(patch['before'])
        restored[offset:offset+len(before)] = before
    if hashlib.sha256(restored).hexdigest() != native_sha:
        raise ValueError('실행 파일 번역·검수 격리 결합 경계 불일치')
    executable.write_bytes(modified)
    expected['Soulash 2.exe'] = sha(executable)
    differences = [{'file': 'Soulash 2.exe', 'role': 'QA_ONLY_DO_NOT_DISTRIBUTE',
                    'sha256': expected['Soulash 2.exe'], 'underlying_native_sha256': native_sha,
                    'qa_reversal_boundary': 'PASS'}]
    for font in font_report['files']:
        path = fonts / 'fonts' / font['output']
        relative = 'data/mods/core_2/assets/fonts/' + font['source']
        if sha(path) != font['sha256']:
            raise ValueError('글꼴 지문 불일치')
        shutil.copyfile(path, output / relative)
        expected[relative] = font['sha256']
        differences.append({'file': relative, 'role': 'KOREAN_FONT', 'sha256': font['sha256']})
    for item in report['files']:
        relative = item['file']
        if expected[relative] != item['source_sha256'] or sha(stage / 'payload' / relative) != item['candidate_sha256']:
            raise ValueError('번역 자산 지문 불일치')
        shutil.copyfile(stage / 'payload' / relative, output / relative)
        expected[relative] = item['candidate_sha256']
        differences.append({'file': relative, 'role': 'TRANSLATION', 'sha256': expected[relative]})
    shutil.copyfile(settings, output / 'data/user_settings.json')
    expected['data/user_settings.json'] = sha(settings)
    if args.qa_save:
        save = args.qa_save.resolve()
        if not save.is_relative_to(PRIVATE):
            raise ValueError('검수용 저장만 복사 가능')
        for file in save.rglob('*'):
            if not file.is_file():
                continue
            relative = 'saves/qa/' + file.relative_to(save).as_posix()
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            input_hashes[file] = sha(file)
            shutil.copyfile(file, target)
            expected[relative] = sha(file)
    if any((output / 'data' / name).exists() for name in ('tutorial_values.json', 'user.settings.json')):
        raise ValueError('사용자 설정 이주 파일 발견')
    files = [p for p in output.rglob('*') if p.is_file()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        actual = dict(zip((p.relative_to(output).as_posix() for p in files), pool.map(sha, files)))
    if actual != expected:
        raise ValueError('사본 전체 지문 재읽기 불일치')
    if any(sha(p) != digest for p, digest in input_hashes.items()):
        raise ValueError('준비 도중 입력 변경')
    evidence = {'status': 'PASS', 'purpose': 'QA_ONLY_DO_NOT_DISTRIBUTE', 'started': started,
                'finished': datetime.now(timezone.utc).isoformat(), 'candidate': output.relative_to(ROOT).as_posix(),
                'stage': stage.relative_to(ROOT).as_posix(), 'files': len(actual), 'locations': report['accepted_rows'],
                'investigation_only': partial_investigation, 'unresolved_locations': report.get('unresolved_total', 0),
                'difference_allowlist': 'PASS', 'migration_files_absent': 'PASS', 'g5': 'NOT_RUN', 'release_ready': False,
                'differences': differences, 'expected_files': expected,
                'inputs': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': s} for p, s in input_hashes.items()]}
    (output.parent / (output.name + '_preparation.json')).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'files': len(actual), 'locations': report['accepted_rows']}))


if __name__ == '__main__':
    main()
