"""패키징 완료 검사기가 정상과 만료·누락·위치 오류를 구별하는지 합성 시험한다."""
from copy import deepcopy
import json
from pathlib import Path

from soulash2_release_package import ROOT, WORK, sha, write_json, verify_release_gate, utc_now


def main():
    fixture = WORK / 'release_preparation/gate_selftest_r1'
    fixture.mkdir(parents=True, exist_ok=False)
    candidate = fixture / 'candidate'
    candidate.mkdir()
    data = candidate / 'fake.dat'
    data.write_bytes(b'synthetic-only')
    dependency = fixture / 'translation_fixture.txt'
    dependency.write_text('합성 번역만 포함', encoding='utf-8')
    def link(path):
        return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}
    freeze = fixture / 'candidate_manifest.json'
    original_freeze = {'game_id': 'SOULASH_2', 'steam_build': '25967323', 'candidate_id': 'synthetic_only',
                       'files': [{'path': 'fake.dat', 'size': data.stat().st_size, 'sha256': sha(data)}]}
    write_json(freeze, original_freeze)
    checks = {}
    for name in ('G4', 'G5'):
        path = fixture / (name + '.json')
        write_json(path, {'status': 'PASS', 'candidate_manifest_sha256': sha(freeze), 'purpose': 'SYNTHETIC_TEST_ONLY_NOT_GAME_EVIDENCE'})
        checks[name] = {'status': 'PASS', **link(path)}
    original_gate = {'game_id': 'SOULASH_2', 'steam_build': '25967323', 'status': 'PASS', 'candidate_id': 'synthetic_only',
                     'candidate_manifest': link(freeze), 'checks': checks, 'allowed_changes': ['fake.dat'], 'dependencies': [link(dependency)]}
    gate_path = fixture / 'gate.json'
    records = []
    def run(label, gate, expect_pass):
        write_json(gate_path, gate)
        try:
            verify_release_gate(gate_path, candidate)
            observed = True
        except (AssertionError, KeyError, FileNotFoundError, ValueError):
            observed = False
        assert observed == expect_pass, label
        records.append({'id': label, 'status': 'PASS', 'accepted': observed})
    run('valid_synthetic_gate', original_gate, True)
    data.write_bytes(b'changed')
    run('reject_changed_candidate', original_gate, False)
    data.write_bytes(b'synthetic-only')
    data.rename(candidate / 'moved.dat')
    run('reject_moved_location', original_gate, False)
    (candidate / 'moved.dat').rename(data)
    extra = candidate / 'extra.dat'
    extra.write_bytes(b'extra')
    run('reject_unrecorded_candidate_file', original_gate, False)
    extra.unlink()
    gate = deepcopy(original_gate)
    gate['checks'].pop('G5')
    run('reject_missing_g5', gate, False)
    gate = deepcopy(original_gate)
    gate['checks']['G5']['status'] = 'NOT_RUN'
    run('reject_not_run_g5', gate, False)
    gate = deepcopy(original_gate)
    gate['allowed_changes'].append('fake.dat')
    run('reject_duplicate_change_id', gate, False)
    gate = deepcopy(original_gate)
    gate['allowed_changes'] = ['../escape.dat']
    run('reject_path_escape', gate, False)
    dependency.write_text('변경된 합성 번역', encoding='utf-8')
    run('reject_stale_translation_dependency', original_gate, False)
    dependency.write_text('합성 번역만 포함', encoding='utf-8')
    g5 = fixture / 'G5.json'
    old_g5 = g5.read_bytes()
    write_json(g5, {'status': 'PASS', 'candidate_manifest_sha256': '0' * 64})
    run('reject_changed_g5_evidence', original_gate, False)
    gate = deepcopy(original_gate)
    gate['checks']['G5'] = {'status': 'PASS', **link(g5)}
    run('reject_g5_of_other_candidate', gate, False)
    g5.write_bytes(old_g5)
    invalid_freeze = deepcopy(original_freeze)
    invalid_freeze['files'].append(invalid_freeze['files'][0])
    write_json(freeze, invalid_freeze)
    gate = deepcopy(original_gate)
    gate['candidate_manifest'] = link(freeze)
    run('reject_duplicate_frozen_location', gate, False)
    write_json(freeze, original_freeze)
    run('valid_after_fixture_restore', original_gate, True)
    report = {'status': 'PASS', 'created_utc': utc_now(), 'tests': records, 'tool_sha256': sha(__file__), 'scope': '합성 완료검사기 결함 시험;실제 게임 G4/G5 완료 근거가 아님'}
    write_json(fixture / 'report.json', report)
    print(json.dumps({'status': 'PASS', 'tests': len(records)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
