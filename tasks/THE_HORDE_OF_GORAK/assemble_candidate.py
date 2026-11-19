"""검증한 DAT·네이티브 후보를 원본 전체 파일 집합에 합쳐 검수용 game 폴더를 만든다."""
import argparse
import json
import shutil
from pathlib import Path

from dat_container import sha
from build_patch import verify_ranges

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'source_original/THE_HORDE_OF_GORAK/steam_26336311'
WORK = ROOT / 'working_private/THE_HORDE_OF_GORAK'
BASELINE = WORK / 'investigation_20261031/baseline_manifest.json'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def build(candidate, native):
    candidate, native = candidate.resolve(), native.resolve()
    if not candidate.is_relative_to(ROOT / 'build_candidate/THE_HORDE_OF_GORAK') or not native.is_relative_to(WORK):
        raise ValueError('허용하지 않은 후보 경로')
    output = candidate / 'game'
    if output.exists():
        raise ValueError('기존 game 폴더를 덮어쓰지 않음')
    manifest, dat_report = read_json(BASELINE), read_json(candidate / 'build_report.json')
    audit_path = native / 'native_patch_audit.json'
    audit = read_json(audit_path)
    if dat_report['status'] != 'PASS' or audit['status'] != 'PASS':
        raise ValueError('정적 입력 검증 미통과')
    baseline = {row['path']: row for row in manifest['files']}
    files = {p.relative_to(BASE).as_posix(): p for p in BASE.rglob('*') if p.is_file()}
    assert set(files) == set(baseline) and len(files) == 32
    for relative, path in files.items():
        data = path.read_bytes()
        assert len(data) == baseline[relative]['size'] and sha(data) == baseline[relative]['sha256']
    dat_input = candidate / 'THOG.dat'
    assert sha(dat_input.read_bytes()) == dat_report['candidate_sha256']
    replacements = {'THOG.dat': {'input': dat_input, 'sha256': dat_report['candidate_sha256'],
                                'boundary_evidence': 'build_report.json',
                                'reason': '글꼴·번역·메뉴/대화상자·이미지4개·배치5필드'}}
    for item in audit['files']:
        for relative in item['paths']:
            path = native / relative
            if not path.resolve().is_relative_to(native) or relative not in baseline or relative in replacements:
                raise ValueError('잘못되었거나 중복된 네이티브 경로')
            assert baseline[relative]['sha256'] == item['original_sha256']
            before, after = files[relative].read_bytes(), path.read_bytes()
            assert sha(after) == item['candidate_sha256']
            verify_ranges(before, after, item['allowed_ranges'])
            replacements[relative] = {'input': path, 'sha256': item['candidate_sha256'],
                                     'boundary_evidence': str(audit_path),
                                     'allowed_ranges': item['allowed_ranges'],
                                     'reason': '원본 위치가 고정된 네이티브 표시 문구·대화상자'}
    locked = {str(BASELINE): sha(BASELINE.read_bytes()), str(audit_path): sha(audit_path.read_bytes()),
              str(candidate / 'build_report.json'): sha((candidate / 'build_report.json').read_bytes()),
              str(Path(__file__).resolve()): sha(Path(__file__).read_bytes())}
    locked.update({str(item['input']): item['sha256'] for item in replacements.values()})
    shutil.copytree(BASE, output)
    for relative, item in replacements.items():
        shutil.copyfile(item['input'], output / relative)
    final_files = {p.relative_to(output).as_posix(): p for p in output.rglob('*') if p.is_file()}
    assert set(final_files) == set(baseline)
    rows = []
    for relative, path in sorted(final_files.items()):
        data = path.read_bytes()
        digest = sha(data)
        expected = replacements[relative]['sha256'] if relative in replacements else baseline[relative]['sha256']
        assert digest == expected
        rows.append({'path': relative, 'size': len(data), 'original_sha256': baseline[relative]['sha256'],
                     'candidate_sha256': digest, 'changed': digest != baseline[relative]['sha256'],
                     'boundary': {k: v for k, v in replacements.get(relative, {}).items() if k not in ('input', 'sha256')},
                     'status': 'PASS'})
    for path, digest in locked.items():
        assert sha(Path(path).read_bytes()) == digest
    report = {'status': 'PASS', 'candidate_root': str(candidate), 'game_path': str(output),
              'files': rows, 'files_total': len(rows), 'changed_files': sum(row['changed'] for row in rows),
              'baseline_manifest_sha256': locked[str(BASELINE)], 'native_audit_sha256': locked[str(audit_path)],
              'inputs': locked, 'qa_overrides_included': False, 'runtime_qa': 'NOT_RUN',
              'scope': '검수 후보 조립. 공개 ZIP·설치·실제 실행은 수행하지 않음'}
    (candidate / 'assembly_manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'game': str(output), 'files': len(rows), 'changed': report['changed_files'],
                      'assembly_manifest_sha256': sha((candidate / 'assembly_manifest.json').read_bytes())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    args = parser.parse_args()
    build(args.candidate, args.native)
