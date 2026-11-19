"""검증 도구(validate_candidate.py)가 잘못된 후보를 실제로 걸러 내는지 결함을 넣어 시험합니다.

번역 두 칸을 서로 바꾸고, 한 칸을 비우고, 직접 문구 하나를 바꾼 후보를 만들어 검증이 FAIL을 내는지 봅니다.
시험이 만든 후보·작업 폴더는 끝나면 이 도구가 스스로 지웁니다(게임 사본을 남기지 않음).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import WORK, CANDIDATE, save, load

TOOLS = Path(__file__).parent
BUILD_ID = 'defect_test'


def main():
    for folder in (CANDIDATE / BUILD_ID, WORK / BUILD_ID):
        if folder.exists():
            shutil.rmtree(folder)
    data = load(WORK / 'translation/build_input.json')
    slots = sorted(data['slots'])
    first, second, third = slots[10], slots[400], slots[800]
    data['slots'][first], data['slots'][second] = data['slots'][second], data['slots'][first]
    data['slots'][third] = ''
    direct_key = sorted(data['direct'])[0]
    data['direct'][direct_key] = '잘못된 번역'
    (WORK / BUILD_ID).mkdir(parents=True)
    save(WORK / BUILD_ID / 'defect_input.json', data)
    build = subprocess.run([sys.executable, str(TOOLS / 'build.py'), BUILD_ID, str(WORK / BUILD_ID / 'defect_input.json')], capture_output=True)
    if build.returncode != 0:
        print('defect build failed', build.stderr.decode('utf-8', errors='replace')[-800:])
        sys.exit(2)
    result = subprocess.run([sys.executable, str(TOOLS / 'validate_candidate.py'), BUILD_ID], capture_output=True)
    report = load(WORK / BUILD_ID / 'verify/validation_report.json')
    slot_failures = {f.get('slot') for f in report['checks']['V2_locale_slots']['failures']}
    detected = {'validator_exit_nonzero': result.returncode != 0, 'overall_fail': report['status'] == 'FAIL',
                'swap_detected': {first, second} <= slot_failures, 'empty_detected': third in slot_failures,
                'direct_detected': report['checks']['V3_direct_keys']['status'] == 'FAIL',
                'other_checks_pass': all(report['checks'][name]['status'] == 'PASS' for name in ('V1_file_boundary', 'V4_scripts', 'V5_scenes'))}
    outcome = {'test': 'validator defect injection', 'status': 'PASS' if all(detected.values()) else 'FAIL', 'detected': detected,
               'injected': {'swapped': [first, second], 'emptied': third, 'direct_changed': direct_key[:40]}}
    save(WORK / 'validator_selftest.json', outcome)
    for folder in (CANDIDATE / BUILD_ID, WORK / BUILD_ID):
        shutil.rmtree(folder)
    print(json.dumps(outcome, ensure_ascii=False))
    sys.exit(0 if outcome['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
