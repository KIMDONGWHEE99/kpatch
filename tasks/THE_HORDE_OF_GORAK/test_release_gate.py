"""가짜 자료로 G2·G3·G4·G5의 누락·실패·다른 후보·오래된 근거를 거부한다."""
import copy

from release_package import ROOT, WORK, GAME, BUILD, sha, write_json, verify_release_gate


def main():
    base = WORK / 'gate_synthetic_01'
    assert not base.exists(), '기존 게이트 합성 시험을 덮어쓰지 않습니다.'
    candidate = base / 'candidate'
    candidate.mkdir(parents=True)
    (candidate / 'fake.dat').write_bytes(b'synthetic gate fixture only')
    freeze = base / 'freeze.json'
    write_json(freeze, {'game_id': GAME, 'steam_build': BUILD, 'candidate_id': 'SYNTHETIC',
                        'files': [{'path': 'fake.dat', 'size': (candidate / 'fake.dat').stat().st_size,
                                   'sha256': sha(candidate / 'fake.dat')}]})
    relative = lambda path: path.relative_to(ROOT).as_posix()
    checks = {}
    for stage in ['G2', 'G3', 'G4', 'G5']:
        path = base / (stage + '.json')
        write_json(path, {'status': 'PASS', 'candidate_manifest_sha256': sha(freeze)})
        checks[stage] = {'path': relative(path), 'status': 'PASS', 'sha256': sha(path)}
    gate = {'game_id': GAME, 'steam_build': BUILD, 'status': 'PASS', 'candidate_id': 'SYNTHETIC',
            'allowed_changes': ['fake.dat'], 'dependencies': [{'path': relative(candidate / 'fake.dat'), 'sha256': sha(candidate / 'fake.dat')}],
            'candidate_manifest': {'path': relative(freeze), 'sha256': sha(freeze)}, 'checks': checks}
    path = base / 'gate.json'
    write_json(path, gate)
    assert verify_release_gate(path, candidate)['status'] == 'PASS'
    records = [{'id': 'all_four_stages_same_candidate', 'status': 'PASS'}]
    def rejected(label, value):
        path = base / (label + '.json')
        write_json(path, value)
        try:
            verify_release_gate(path, candidate)
        except (AssertionError, KeyError):
            records.append({'id': label, 'status': 'PASS'})
            return
        raise AssertionError('유효하지 않은 게이트를 통과시켰음: ' + label)
    for stage in ['G2', 'G3', 'G4', 'G5']:
        value = copy.deepcopy(gate)
        del value['checks'][stage]
        rejected('missing_' + stage, value)
        value = copy.deepcopy(gate)
        value['checks'][stage]['status'] = 'FAIL'
        rejected('failed_' + stage, value)
        value = copy.deepcopy(gate)
        value['checks'][stage]['sha256'] = '0' * 64
        rejected('stale_' + stage, value)
    other = base / 'other_candidate.json'
    write_json(other, {'status': 'PASS', 'candidate_manifest_sha256': '0' * 64})
    value = copy.deepcopy(gate)
    value['checks']['G3'].update(path=relative(other), sha256=sha(other))
    rejected('different_candidate_G3', value)
    value = copy.deepcopy(gate)
    value['dependencies'][0]['sha256'] = '0' * 64
    rejected('stale_dependency', value)
    write_json(base / 'test_report.json', {'status': 'PASS', 'tests': records,
                'scope': '실제 게임·공개 패키지 없이 게이트 검사 함수의 거부 동작만 확인',
                'package_tool_sha256': sha(ROOT / 'tasks/THE_HORDE_OF_GORAK/release_package.py')})
    print('release_gate_checks PASS', len(records))


if __name__ == '__main__':
    main()
