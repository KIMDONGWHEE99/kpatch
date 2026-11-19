"""실제 배포 후보와 검수 사본을 재열어 검수 전용 변경 경계를 독립 대조한다."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from pck_tools import ROOT, GAME, WORK, EXTRACTED, read_pack, read_settings, variant
from build_candidate import comparable, run_tool


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(candidate_id, driver_source=None, driver_review=None):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', candidate_id) or '..' in candidate_id:
        raise ValueError('후보 번호 경로 구분자 금지')
    stage = WORK / candidate_id
    candidate = ROOT / 'build_candidate' / GAME / candidate_id
    qa = stage / 'qa_game'
    pack = 'MR MAGEBOY DEMO.pck'
    original = {r['name']: r['data'] for r in read_pack(candidate / pack)[3]}
    actual = {r['name']: r['data'] for r in read_pack(qa / pack)[3]}
    failures = []
    allowed = {'project.binary', 'game/scripts/steamworks.gdc', 'korean_qa_driver.gd', 'korean_qa_config.json'}
    observed = {path for path in set(original) | set(actual) if original.get(path) != actual.get(path)}
    if observed != allowed or set(actual) != set(original) | {'korean_qa_driver.gd', 'korean_qa_config.json'}:
        failures.append({'error': '허용 검수 자산 경계 불일치', 'difference': sorted(observed.symmetric_difference(allowed))})
    properties = {'application/config/name': 'MR_MAGEBOY_KO_QA_' + candidate_id,
                  'application/config/use_custom_user_dir': False,
                  'debug/file_logging/log_path': (qa / 'runtime.log').as_posix(),
                  'display/window/size/mode': 0, 'maaacks_game_template/disable_update_check': True,
                  'autoload/KoreanQA': '*res://korean_qa_driver.gd'}
    before_settings = read_settings(original['project.binary'])
    after_settings = read_settings(actual['project.binary'])
    changed = {key for key in set(before_settings) | set(after_settings) if before_settings.get(key) != after_settings.get(key)}
    if changed != set(properties) or any(after_settings.get(key) != variant(value) for key, value in properties.items()):
        failures.append({'error': '프로젝트 설정의 검수 허용6필드 불일치', 'changed': sorted(changed)})
    review_source = Path(driver_source) if driver_source else WORK / 'qa_driver_c04_review/qa_driver.gd'
    review_path = Path(driver_review) if driver_review else WORK / 'qa_driver_c04_review/qa_driver_revision_c04.json'
    review = json.loads(review_path.read_text(encoding='utf-8'))
    if review.get('status') != 'PASS' or review.get('lexical_roundtrip') != 'PASS' or review.get('driver_sha256') != sha(review_source.read_bytes()):
        failures.append({'error': '검수 driver 고정 source와 검토 명세/왕복 결과 연결 불일치'})
    if actual['korean_qa_driver.gd'] != review_source.read_bytes():
        failures.append({'error': '왕복 검증한 검수 driver와 실제 PCK 내용 불일치'})
    config = json.loads(actual['korean_qa_config.json'])
    expected_config = {'command': (stage / 'command.json').as_posix(), 'info': (stage / 'runtime_info.json').as_posix(),
                       'screens': (stage / 'screens').as_posix(), 'ledger': (stage / 'screens.json').as_posix()}
    if config != expected_config:
        failures.append({'error': '검수 입력/출력 경로 경계 불일치'})
    probe = stage / 'independent_qa_boundary_probe'
    probe.mkdir(exist_ok=True)
    script = probe / 'steamworks.gdc'
    script.write_bytes(actual['game/scripts/steamworks.gdc'])
    output = probe / 'decompiled'
    output.mkdir(exist_ok=True)
    run_tool(['--decompile=' + script.as_posix(), '--bytecode=4.5.0', '--output=' + output.as_posix()], probe, 'actual_qa_steam_decompile')
    source = EXTRACTED / 'recovered/game/scripts/steamworks.gd'
    marker = 'func initialize_steam(app_id: int) -> void :\n'
    original_text = source.read_text(encoding='utf-8')
    if original_text.count(marker) != 1:
        failures.append({'error': '원본 Steam 초기화 위치 수 불일치'})
    expected_text = original_text.replace(marker, marker + '\tprint("Korean QA: Steam initialization disabled")\n\treturn\n')
    if comparable(expected_text) != comparable((output / 'steamworks.gd').read_text(encoding='utf-8')):
        failures.append({'error': '실제 검수 bytecode의 Steam 초기화 메서드 허용 외 변경'})
    files = []
    for path in sorted(candidate.iterdir()):
        if path.is_file() and path.name != pack:
            before = sha(path.read_bytes())
            after = sha((qa / path.name).read_bytes())
            if before != after:
                failures.append({'path': path.name, 'error': '검수 사본 엔진/DLL 변경'})
            files.append({'path': path.name, 'sha256': after})
    report = {'status': 'FAIL' if failures else 'PASS', 'candidate': candidate_id,
              'candidate_pck_sha256': sha((candidate / pack).read_bytes()), 'qa_pck_sha256': sha((qa / pack).read_bytes()),
              'candidate_entries': len(original), 'qa_entries': len(actual), 'allowed_changes': sorted(allowed),
              'observed_changes': sorted(observed), 'unchanged_payloads': len(actual) - len(observed),
              'changed_payload_sha256': {name: sha(actual[name]) for name in sorted(allowed)},
              'project_properties': properties, 'steam_original_source_sha256': sha(source.read_bytes()),
              'steam_actual_decompile_sha256': sha((output / 'steamworks.gd').read_bytes()), 'executable_files': files,
              'driver_source_path': str(review_source.resolve()), 'driver_source_sha256': sha(review_source.read_bytes()),
              'driver_review_path': str(review_path.resolve()), 'driver_review_sha256': sha(review_path.read_bytes()),
              'failures': failures, 'scope': '실제 검수 PCK를 재열기, Steam bytecode를 새로 복원해 초기화 입구 print/return 두 줄만 변경된 것을 비교. 별도 driver 내부 허용 변경은 연결된 후보별 고정 검토 명세에 기록.'}
    # 이전 후보별 감사 결과는 그대로 보존하고 현재 연결 결과를 새로 기록합니다.
    previous_path = stage / 'independent_qa_boundary.json'
    if previous_path.exists():
        previous_bytes = previous_path.read_bytes()
        history = stage / 'independent_qa_boundary_history'
        history.mkdir(exist_ok=True)
        (history / (sha(previous_bytes) + '.json')).write_bytes(previous_bytes)
    (stage / 'independent_qa_boundary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'unchanged_payloads': report['unchanged_payloads'], 'failures': len(failures)}))
    return bool(failures)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate_id')
    parser.add_argument('--driver-source')
    parser.add_argument('--driver-review')
    args = parser.parse_args()
    raise SystemExit(run(args.candidate_id, args.driver_source, args.driver_review))
