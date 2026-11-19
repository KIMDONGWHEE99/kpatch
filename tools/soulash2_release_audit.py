"""고정 ZIP의 허용목록과 파일 지문을 독립 검사하고 추출한 도구로 정·역복원한다."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

from soulash2_release_package import ROOT, WORK, BASELINE, GAME, BUILD, APP_ID, FONT_LICENSES, sha, safe_relative, write_json, utc_now, verify_release_gate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-report', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=BASELINE)
    args = parser.parse_args()
    report_path = args.package_report.resolve()
    report_path.relative_to(WORK.resolve())
    report = json.loads(report_path.read_text(encoding='utf-8'))
    archive, scratch = Path(report['archive']), report_path.parent
    candidate, original = args.candidate.resolve(), args.source.resolve()
    if report['synthetic_fixture']:
        candidate.relative_to(WORK.resolve())
        original.relative_to(WORK.resolve())
        archive.resolve().relative_to(WORK.resolve())
    else:
        candidate.relative_to((ROOT / 'build_candidate/SOULASH_2').resolve())
        assert original == BASELINE.resolve()
        archive.resolve().relative_to((ROOT / 'release_output').resolve())
        assert verify_release_gate(ROOT / report['gates']['path'], candidate) == report['gates']
    assert sha(archive) == report['zip_sha256']
    allowed = {'Install.cmd', 'Remove.cmd', 'Patch.ps1', 'ChooseGame.ps1', 'README.txt', 'manifest.json',
               'tools/xdelta3.exe', 'licenses/xdelta3-APACHE-2.0.txt'} | {'licenses/' + name for name in FONT_LICENSES}
    checks = []
    extracted = scratch / 'independent_zip_contents'
    extracted.mkdir(exist_ok=False)
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        assert len(names) == len(set(name.casefold() for name in names)) and zipped.testzip() is None
        manifest = json.loads(zipped.read('manifest.json').decode('utf-8'))
        assert manifest['schema_version'] == 1 and manifest['game_id'] == GAME
        assert str(manifest['steam_build']) == BUILD and str(manifest['steam_app_id']) == APP_ID
        for entry in manifest['changes']:
            safe_relative(entry['path'])
            for direction in ('forward', 'reverse'):
                name = entry[direction]
                safe_relative(name)
                assert name.startswith('patches/') and name.endswith('.' + direction + '.xdelta')
                allowed.add(name)
        assert set(names) == allowed == set(report['allowed_files'])
        assert len(manifest['payload']) == len(allowed) - 1
        assert {r['path'] for r in manifest['payload']} == allowed - {'manifest.json'}
        for entry in manifest['payload']:
            data = zipped.read(entry['path'])
            assert hashlib.sha256(data).hexdigest() == entry['sha256'] and len(data) == entry['size']
        for name in names:
            safe_relative(name)
            path = extracted / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zipped.read(name))
    assert sha(extracted / 'manifest.json') == report['manifest_sha256']
    with tempfile.TemporaryDirectory(prefix='private_roundtrip_', dir=scratch) as directory:
        temporary = Path(directory).resolve()
        temporary.relative_to(scratch.resolve())
        empty = temporary / 'empty'
        empty.write_bytes(b'')
        for i, row in enumerate(manifest['changes']):
            source = original / row['path'] if row['original_sha256'] is not None else empty
            target = candidate / row['path']
            assert sha(source) == (row['original_sha256'] or hashlib.sha256(b'').hexdigest())
            assert sha(target) == row['patched_sha256']
            for direction, base, desired in [('forward', source, row['patched_sha256']), ('reverse', target, sha(source))]:
                output = temporary / (str(i) + '.' + direction)
                result = subprocess.run([str(extracted / 'tools/xdelta3.exe'), '-d', '-s', str(base), str(extracted / row[direction]), str(output)], capture_output=True, timeout=120)
                assert result.returncode == 0 and sha(output) == desired, (row['path'], direction)
                checks.append({'path': row['path'], 'direction': direction, 'status': 'PASS', 'sha256': desired})
                output.unlink()
    result = {'game_id': GAME, 'steam_build': BUILD, 'status': 'PASS', 'scope': '최종 ZIP 독립 허용목록·추출 도구 정역복원;합성자료는 실제 게임 완료 근거가 아님',
              'created_utc': utc_now(), 'archive': str(archive), 'zip_sha256': sha(archive), 'manifest_sha256': sha(extracted / 'manifest.json'),
              'synthetic_fixture': report['synthetic_fixture'], 'allowed_file_count': len(allowed), 'roundtrip_checks': checks, 'G6': 'PASS', 'G7': 'NOT_RUN',
              'tool_sha256': sha(__file__), 'game_execution': 'NOT_RUN', 'actual_steam_installation': 'NOT_RUN'}
    installer_path = scratch / 'installer_tests.json'
    if installer_path.exists():
        tests = json.loads(installer_path.read_text(encoding='utf-8'))
        assert tests['status'] == 'PASS' and tests['zip_sha256'] == result['zip_sha256'] and tests['manifest_sha256'] == result['manifest_sha256']
        result['G7'] = 'PASS'
        result['installer_tests_sha256'] = sha(installer_path)
    write_json(scratch / 'independent_zip_audit.json', result)
    print(json.dumps({'status': 'PASS', 'files': len(allowed), 'roundtrips': len(checks), 'synthetic': report['synthetic_fixture'], 'G7': result['G7']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
