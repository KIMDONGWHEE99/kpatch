"""수정 원본을 다시 열어 위치별 값과 허용한 코드 변경 경계를 검사한다."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from census_text import tokens


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory
    manifest = json.loads((directory / 'modified_manifest.json').read_text(encoding='utf-8'))
    translation = json.loads((directory / 'translation.json').read_text(encoding='utf-8'))
    entries = {entry['id']: entry for entry in translation['entries']}
    failures = []
    checked_positions = 0
    checked_structural_positions = 0
    for item in manifest:
        path = item['file']
        original = (args.source / path).read_bytes()
        modified = (directory / 'modified' / path).read_bytes()
        if sha(original) != item['source_sha256'] or sha(modified) != item['modified_sha256']:
            failures.append({'file': path, 'error': '입력 지문 불일치'})
            continue
        modified_text = modified.decode('utf-8-sig').replace('\r\n', '\n')
        for change in reversed(item.get('code_changes', [])):
            needle = change['after']
            count = modified_text.count(needle)
            # 다음 함수를 덧붙일 때 앞 함수 끝의 빈 줄만 정리될 수 있다.
            if not change['before'] and count == 0:
                needle = needle.rstrip('\n')
                count = modified_text.count(needle)
            if count != change['count']:
                failures.append({'file': path, 'method': change['method'], 'error': '허용 코드 위치 수 불일치', 'actual': count, 'expected': change['count']})
                continue
            modified_text = modified_text.replace(needle, change['before'])
        original_text = original.decode('utf-8-sig').replace('\r\n', '\n')
        original_tokens = list(tokens(original_text, script=path.endswith('.gd'), config=path.endswith('.godot')))
        modified_tokens = list(tokens(modified_text, script=path.endswith('.gd'), config=path.endswith('.godot')))
        if len(original_tokens) != len(modified_tokens):
            failures.append({'file': path, 'error': '허용 코드 복원 뒤 문자열 위치 수 불일치', 'original': len(original_tokens), 'modified': len(modified_tokens)})
            continue
        expected_ids = set(item['changed_positions'])
        for index, (before, after) in enumerate(zip(original_tokens, modified_tokens)):
            entry_id = path + '::string' + str(index)
            expected = entries[entry_id]['korean'] if entry_id in expected_ids else before['value']
            if after['value'] != expected:
                failures.append({'id': entry_id, 'error': '위치별 실제값 불일치', 'expected': expected, 'actual': after['value']})
            if entry_id in expected_ids:
                checked_positions += 1
            else:
                checked_structural_positions += 1
        # 인용부호 밖 구조는 승인된 표시 연결을 되돌린 뒤 같아야 한다.
        for value, stream in [(original_text, original_tokens), (modified_text, modified_tokens)]:
            normalized = value
            for token in reversed(stream):
                normalized = normalized[:token['start']] + '"<STRING>"' + normalized[token['end']:]
            if value is original_text:
                original_structure = normalized.strip()
            else:
                modified_structure = normalized.strip()
        if original_structure != modified_structure:
            failures.append({'file': path, 'error': '허용 변경 외 코드·자원 구조 차이'})
    result = {'status': 'FAIL' if failures else 'PASS', 'files': len(manifest), 'literal_positions': checked_positions, 'preserved_string_positions': checked_structural_positions, 'failures': failures, 'scope': '수정 원본 단계의 재열기 검사. PCK 후보 재추출·실제 그래픽 검사와 별개이다.'}
    (directory / 'source_reopen_check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key not in ('failures', 'scope')}))
    sys.exit(bool(failures))


if __name__ == '__main__':
    main()
