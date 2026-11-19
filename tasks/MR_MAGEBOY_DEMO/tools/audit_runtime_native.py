"""실제 게임 엔진이 수집한 입력·색 선택 속성을 고정 번역표와 대조한다."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from pck_tools import ROOT, GAME, WORK


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(candidate_id):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', candidate_id) or '..' in candidate_id:
        raise ValueError('후보 번호 경로 구분자 금지')
    stage = WORK / candidate_id
    table_path = stage / 'inputs/translation_meta/translation_table.json'
    table = read(table_path)
    info = read(stage / 'runtime_info.json')
    # 같은 명령을 재시험한 경우 현재 PNG와 연결된 마지막 기록만 사용한다.
    all_events = read(stage / 'screens.json')
    events = list({event['id']: event for event in all_events}.values())
    failures, unknowns, color_reports, input_reports, dialog_reports = [], [], [], [], []
    expected_engine = {'major': 4, 'minor': 7, 'patch': 2}
    if any(info['engine'].get(key) != value for key, value in expected_engine.items()):
        failures.append({'error': '원래 게임 엔진 버전과 다름', 'actual': info['engine']})
    executable = Path(info['executable'])
    if executable.resolve() != (stage / 'qa_game/MR MAGEBOY DEMO.exe').resolve():
        failures.append({'error': '실제 프로세스 실행 경로 불일치', 'actual': str(executable)})
    if info['qa_pack'] != sha(stage / 'qa_game/MR MAGEBOY DEMO.pck'):
        failures.append({'error': '실행 검수 PCK 지문 불일치'})
    seen_color_sources = set()
    for event in events:
        dump_record = event.get('detail', {}).get('native_dump')
        if not dump_record:
            if event['operation'] in ('loading_dialog', 'loading_error'):
                detail = event.get('detail', {})
                reference = detail.get('default_dialog_reference', {})
                source = reference.get('default_ok_text')
                expected = table.get(source, source)
                valid = source == 'OK' and reference.get('node_tr') == expected and detail.get('game_ok_node_tr') == expected
                if not valid:
                    failures.append({'event': event['id'], 'error': '기본 확인 버튼 원문/번역 조회 불일치', 'detail': detail})
                dialog_reports.append({'event': event['id'], 'source': source, 'expected': expected, 'game_property': detail.get('game_ok_text'), 'lookup_status': 'PASS' if valid else 'FAIL', 'render_status': 'NOT_RUN', 'image': event['image'], 'image_sha256': sha(event['image']), 'reason': '원문 속성과 tr 조회는 화면 렌더링 판정을 대신하지 않는다.'})
            continue
        path = Path(dump_record['path'])
        if sha(path) != dump_record['sha256']:
            failures.append({'path': str(path), 'error': 'native 덤프 지문 불일치'})
        dump = read(path)
        if dump.get('status') != 'PASS':
            failures.append({'path': str(path), 'error': '프로브 자체 FAIL', 'detail': dump})
            continue
        if event['operation'] == 'input_native_dump':
            rows = []
            for row in dump['rows']:
                source = row['helper_text']
                key = 'INPUT_DISPLAY::' + source
                expected = table.get(key)
                if expected is None:
                    expected = '+'.join(table.get('INPUT_DISPLAY::' + part, part) for part in source.split('+'))
                valid = expected == row['display_text']
                if not valid:
                    failures.append({'event': event['id'], 'error': '실제 입력 표시 불일치', 'source': source, 'expected': expected, 'actual': row['display_text']})
                rows.append(dict(row, expected=expected, status='PASS' if valid else 'FAIL'))
            input_reports.append({'event': event['id'], 'path': str(path), 'sha256': sha(path), 'display_server': dump.get('display_server'), 'positions': len(rows), 'rows': rows})
        elif event['operation'] == 'color_picker_dump':
            modes = []
            for mode in dump['modes']:
                actual = {(row['trail'], row['class'], row['field']): row for row in mode['game']}
                rows = []
                for native in mode['native']:
                    source = native['value']
                    seen_color_sources.add(source)
                    namespace = 'ENGINE_UI::' + source
                    expected = table.get(namespace)
                    classification = 'UNKNOWN'
                    reason = ''
                    if expected is not None:
                        classification = 'VISIBLE_TRANSLATE'
                        reason = '색 선택 표시 전용 번역 키'
                    elif source in ('RGB', 'HSV', 'OKHSL', 'R', 'G', 'B', 'A', 'I', 'H', 'S', 'V', '#', ''):
                        classification = 'VISIBLE_KEEP'
                        reason = '색상 공간·채널 약자 또는 기호·구분선'
                    elif native['class'] in ('LineEdit', 'SpinBoxLineEdit') and native['field'] == 'text' and re.fullmatch(r'[+\-\d.eE %]+|[0-9a-fA-F]{6,8}', source):
                        classification = 'VISIBLE_KEEP'
                        reason = '변경 가능한 색상 수치·입력값; 번역하지 않는 필드'
                    else:
                        unknowns.append({'event': event['id'], 'mode': mode['mode'], **native})
                    position = (native['trail'], native['class'], native['field'])
                    observed = actual.get(position)
                    target = source if expected is None else expected
                    valid = observed is not None and observed['value'] == target
                    if not valid:
                        failures.append({'event': event['id'], 'mode': mode['mode'], 'error': '색 선택 내부 위치별 번역 불일치', 'position': position, 'source': source, 'expected': expected, 'actual': observed})
                    rows.append({'native': native, 'game': observed, 'expected': expected, 'classification': classification, 'reason': reason, 'status': 'UNKNOWN' if classification == 'UNKNOWN' else ('PASS' if valid else 'FAIL')})
                native_positions = {(row['trail'], row['class'], row['field']) for row in mode['native']}
                extra_positions = set(actual) - native_positions
                if extra_positions:
                    failures.append({'event': event['id'], 'mode': mode['mode'], 'error': '원래 색 선택 내부에 없던 표시 위치 추가', 'positions': sorted(extra_positions)})
                modes.append({'mode': mode['mode'], 'positions': len(rows), 'rows': rows})
            color_reports.append({'event': event['id'], 'path': str(path), 'sha256': sha(path), 'engine': dump['engine'], 'game_popup_visible': dump['game_popup_visible'], 'color_unchanged': dump['color_unchanged'], 'modes': modes})
    legacy = read(stage / 'inputs/translation_meta/engine_ui_census.json')
    not_present = [dict(row, candidate_runtime_verification='NOT_APPLICABLE', candidate_reason='실제4.7.2 내부 자식 전체를4모드 수집했으나 이4.8.dev 생성값은 나타나지 않음') for row in legacy if row['source'] not in seen_color_sources]
    missing = []
    if not color_reports:
        missing.append('color_picker_dump')
    if not input_reports:
        missing.append('input_native_dump')
    if not dialog_reports:
        missing.append('loading_dialog')
    report = {'status': 'FAIL' if failures or unknowns else ('NOT_RUN' if missing else 'PASS'), 'candidate': candidate_id,
              'candidate_pck_sha256': sha(ROOT / 'build_candidate' / GAME / candidate_id / 'MR MAGEBOY DEMO.pck'),
              'runtime_info_sha256': sha(stage / 'runtime_info.json'), 'qa_pck_sha256': info['qa_pack'], 'executable': str(executable),
              'engine': info['engine'], 'adapter': info.get('adapter'), 'table_sha256': sha(table_path),
              'color_picker': color_reports, 'input': input_reports, 'default_dialog': dialog_reports,
              'event_policy': 'id별 마지막 기록만 사용하며 이전 시험 기록은 원래 screens.json에 보존',
              'legacy_4_8_only': not_present if color_reports else [], 'unknown': unknowns, 'failures': failures, 'missing_commands': missing,
              'scope': '실제4.7.2 프로세스의 내부 표시 속성과 번역 조회·명시 연결 검사. 자동번역된 실제 렌더링·글꼴·배치 판정은 연결된 PNG를 제작자가 별도 육안 확인한다.'}
    output = stage / 'independent_native_check.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'unknown': len(unknowns), 'failures': len(failures), 'missing_commands': missing}))
    return bool(failures or unknowns)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate_id')
    raise SystemExit(run(parser.parse_args().candidate_id))
