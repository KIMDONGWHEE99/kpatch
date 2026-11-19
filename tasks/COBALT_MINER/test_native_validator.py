"""번역 검사가 빈 값·위치 교환·원문 잔존·누락을 실제로 거부하는지 시험합니다."""
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
OUT = ROOT / 'working_private/COBALT_MINER/native_validator_fault_tests'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    OUT.mkdir(exist_ok=True)
    expected = json.loads((WORK / 'native_visible_worklist.json').read_text(encoding='utf-8'))
    cases = {'normal': copy.deepcopy(expected)}
    cases['missing_position'] = copy.deepcopy(expected[:-1])
    cases['duplicate_position'] = copy.deepcopy(expected + [expected[0]])
    cases['empty_translation'] = copy.deepcopy(expected)
    cases['empty_translation'][0]['translation'] = ''
    cases['swapped_translations'] = copy.deepcopy(expected)
    cases['swapped_translations'][0]['translation'], cases['swapped_translations'][1]['translation'] = expected[1]['translation'], expected[0]['translation']
    cases['english_remains'] = copy.deepcopy(expected)
    cases['english_remains'][0]['translation'] = expected[0]['source']
    reports = []
    validator = ROOT / 'tasks/COBALT_MINER/validate_native_candidate.py'
    for name, rows in cases.items():
        path = OUT / (name + '.json')
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        args = [sys.executable, str(validator), '--expected', str(path)]
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        should_pass = name == 'normal'
        if (result.returncode == 0) != should_pass:
            raise AssertionError((name, result.returncode, result.stdout, result.stderr))
        reports.append({'case': name, 'expected_acceptance': should_pass, 'exit_code': result.returncode,
                        'status': 'PASS', 'expected_file_sha256': digest(path),
                        'stdout': result.stdout, 'stderr': result.stderr, 'command': args})
    report = {'status': 'PASS', 'cases': reports, 'validator_sha256': digest(validator),
              'candidate_id': 'native_candidate_02', 'candidate_game_files_modified': False}
    (OUT / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'normal_accepted': 1, 'faults_rejected': len(reports) - 1}))

if __name__ == '__main__':
    main()
