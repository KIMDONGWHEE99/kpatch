"""실제 후보 비교 함수가 작은 합성 장면의 손상을 검출하는지 검사합니다."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from independent_candidate_review import ROOT, WORK, compare_asset, compare_source_input


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description='실제 대조 함수의 손상 검출을 합성 자료로 검사합니다.')
    parser.add_argument('--revision', default='r1')
    parser.add_argument('--candidate')
    arguments = parser.parse_args()
    assert arguments.revision and all(character.isalnum() or character == '_' for character in arguments.revision)
    candidate = None
    candidate_hash = None
    if arguments.candidate:
        candidate = (ROOT / 'build_candidate/MR_MAGEBOY_DEMO' / arguments.candidate).resolve()
        assert candidate.parent == (ROOT / 'build_candidate/MR_MAGEBOY_DEMO').resolve(), '후보는 정해진 비공개 경계 안에 있어야 합니다.'
        candidate_hash = sha((candidate / 'MR MAGEBOY DEMO.pck').read_bytes())
    directory = WORK / ('independent_reviews/validator_faults_' + arguments.revision)
    assert not directory.exists(), '기존 실패 주입 증거를 덮어쓰지 않습니다.'
    directory.mkdir(parents=True)
    expected = ('[gd_scene format=3 uid="uid://synthetic"]\n'
                '[node name="Root" type="Control"]\n'
                '[node name="Title" type="Label" parent="."]\n'
                'text = "채집 주문"\n'
                '[node name="Description" type="RichTextLabel" parent="."]\n'
                'text = "[b][i]효과[/i][/b]: %s 대상에게\\n%d 추가 위력"\n'
                '[node name="End" type="Label" parent="."]\n'
                'text = "게임 종료"\n')
    cases = {
        'unchanged_expected_pass': (expected, True),
        'empty_translation': (expected.replace('text = "채집 주문"', 'text = ""'), False),
        'swapped_positions_same_count': (expected.replace('채집 주문', '__SWAP__').replace('게임 종료', '채집 주문').replace('__SWAP__', '게임 종료'), False),
        'lost_closing_tag': (expected.replace('[/b]', ''), False),
        'changed_nested_tag_order_same_counts': (expected.replace('[b][i]효과[/i][/b]', '[i][b]효과[/b][/i]'), False),
        'original_english_retained': (expected.replace('채집 주문', 'Harvest Spell'), False),
        'deleted_scene_object': (expected.replace('[node name="End" type="Label" parent="."]\ntext = "게임 종료"\n', ''), False),
        'extra_duplicate_object': (expected + '[node name="Duplicate" type="Label" parent="."]\ntext = "게임 종료"\n', False),
        'lost_control_newline': (expected.replace('\\n%d', '%d'), False),
        'swapped_printf_placeholders_same_counts': (expected.replace('%s', '__FORMAT__').replace('%d', '%s').replace('__FORMAT__', '%d'), False),
        'changed_code_property': (expected.replace('format=3', 'format=4'), False),
    }
    expected_data = expected.encode('utf-8')
    (directory / 'expected.tscn').write_bytes(expected_data)
    records = []
    for name, (observed, should_equal) in cases.items():
        data = observed.encode('utf-8')
        (directory / (name + '.tscn')).write_bytes(data)
        before, after, equal, differences = compare_asset(expected_data, data, '.tscn')
        before_strings = [row['value'] for row in before if row['kind'] == 'string']
        after_strings = [row['value'] for row in after if row['kind'] == 'string']
        mismatches = [{'position': position, 'expected': before_strings[position] if position < len(before_strings) else None,
                       'observed': after_strings[position] if position < len(after_strings) else None}
                      for position in range(max(len(before_strings), len(after_strings)))
                      if (before_strings[position] if position < len(before_strings) else None) !=
                         (after_strings[position] if position < len(after_strings) else None)]
        records.append({'id': name, 'status': 'PASS' if equal == should_equal else 'FAIL',
                        'expected_candidate_result': 'PASS' if should_equal else 'FAIL',
                        'actual_candidate_result': 'PASS' if equal else 'FAIL',
                        'fixture_sha256': sha(data), 'original_literal_count': len(before_strings),
                        'observed_literal_count': len(after_strings), 'position_mismatches': mismatches,
                        'all_code_and_literal_differences': differences})
    # 원본 재작성 입력의 파일 줄끝만 허용하고 문자열·주석 변경은 거부합니다.
    multiline = 'extends Control\n# 승인된 주석\nvar caption = """도움말\n둘째 줄"""\n'
    source_cases = {
        'source_external_crlf_only_pass': (expected_data, expected_data.replace(b'\n', b'\r\n'), '.tscn', True),
        'source_internal_control_crlf_changed': (multiline.encode('utf-8'), multiline.replace('\n', '\r\n').encode('utf-8'), '.gd', False),
        'source_undeclared_comment_changed': (multiline.encode('utf-8'), multiline.replace('승인된 주석', '다른 주석').encode('utf-8'), '.gd', False),
    }
    for name, (before_data, data, suffix, should_equal) in source_cases.items():
        (directory / (name + suffix)).write_bytes(data)
        equal, line_endings_only = compare_source_input(before_data, data, suffix)
        records.append({'id': name, 'status': 'PASS' if equal == should_equal else 'FAIL',
                        'expected_candidate_result': 'PASS' if should_equal else 'FAIL',
                        'actual_candidate_result': 'PASS' if equal else 'FAIL',
                        'expected_fixture_sha256': sha(before_data), 'fixture_sha256': sha(data),
                        'source_line_endings_only': line_endings_only})
    report = {'game_id': 'MR_MAGEBOY_DEMO', 'steam_build': '25734075',
              'status': 'PASS' if all(row['status'] == 'PASS' for row in records) else 'FAIL',
              'scope': '원본 자산을 사용하지 않은 작은 합성 장면의 실패 주입. 최종 후보 전체 G4와 별개.',
              'tested_utc': datetime.now(timezone.utc).isoformat(), 'expected_sha256': sha(expected_data),
              'validator_sha256': sha((ROOT / 'tasks/MR_MAGEBOY_DEMO/tools/independent_candidate_review.py').read_bytes()),
              'test_tool_sha256': sha(Path(__file__).read_bytes()), 'tests': records}
    if candidate:
        assert candidate_hash == sha((candidate / 'MR MAGEBOY DEMO.pck').read_bytes()), '검사 중 후보가 바뀌었습니다.'
        report['candidate'] = arguments.candidate
        report['candidate_pck_sha256'] = candidate_hash
        report['candidate_link_scope'] = '같은 해시의 검증 함수를 이 후보의 전체 G4에서도 사용합니다. 이 합성 시험 자체는 후보 전체 검사로 계산하지 않습니다.'
    (directory / 'validator_fault_tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'tests': len(records), 'failed_candidates_detected': sum(
        row['actual_candidate_result'] == 'FAIL' for row in records)}, ensure_ascii=False))
    assert report['status'] == 'PASS'


if __name__ == '__main__':
    main()
