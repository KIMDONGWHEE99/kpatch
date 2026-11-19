"""복원한 Godot 자산의 문자열을 위치별로 목록화한다."""
import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

VISIBLE_FIELDS = {'text', 'title', 'tooltip_text', 'placeholder_text', 'dialog_text', 'dialogue_text', 'dialogue', 'ok_button_text', 'cancel_button_text', 'label_text', 'text_array', 'description', 'credits_text', 'tutorial_text', 'button_text', 'action_name'}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def tokens(text, script=False, config=False):
    # 주석 안 인용부호를 코드 문자열로 잘못 추출하지 않는다.
    index = 0
    while index < len(text):
        if (script and text[index] == '#') or (config and text[index] == ';'):
            index = text.find('\n', index)
            if index < 0:
                break
            continue
        if text[index] not in ('"', "'"):
            index += 1
            continue
        quote = text[index]
        width = 3 if text[index:index + 3] == quote * 3 else 1
        start = index
        index += width
        inner = index
        while index < len(text):
            if text[index] == '\\':
                index += 2
                continue
            if text[index:index + width] == quote * width:
                break
            index += 1
        if index >= len(text):
            raise ValueError(f'문자열 종료 누락: {start}')
        raw = text[inner:index]
        value = re.sub(r'\\([nrt"\'\\])', lambda m: {'n': '\n', 'r': '\r', 't': '\t'}.get(m[1], m[1]), raw)
        index += width
        yield {'start': start, 'end': index, 'raw': raw, 'value': value, 'quote': quote * width}

def classify(token, path, text):
    value, start = token['value'], token['start']
    line_start = text.rfind('\n', 0, start) + 1
    line_end = text.find('\n', token['end'])
    line = text[line_start:line_end if line_end >= 0 else len(text)].strip()
    prefix = text[line_start:start]
    if value.startswith(('res://', 'uid://', 'user://', 'http://', 'https://')):
        return 'INTERNAL', '게임 자산·저장 경로 또는 외부 링크 인자로 사용', line
    if path.suffix in ('.tscn', '.tres'):
        if line.startswith('[') or re.search(r'(ExtResource|SubResource|NodePath)\([^)]*$', prefix):
            return 'INTERNAL', 'Godot 객체·자산·노드 참조 문법', line
        field = prefix.split('=')[0].strip()
        if field in VISIBLE_FIELDS or field.endswith(('/text', '/title', '_text', '_description')):
            if not re.search('[A-Za-z]', re.sub(r'\[[^]]*\]', '', value)) or not value.strip():
                return 'VISIBLE_KEEP', '화면 직접 표시 필드의 숫자·기호·빈 초기값', line
            return 'VISIBLE_TRANSLATE', f'화면 직접 표시 필드 {field}', line
        if field in {'name', 'resource_name', 'animation', 'resource_path', 'bus', 'autoplay', 'libraries', 'metadata/_edit_group_'} or value.isdigit() or not value.strip():
            return 'INTERNAL', f'Godot 리소스 식별·애니메이션·초기값 필드 {field}', line
        if any(x in prefix for x in ['&', 'StringName(', 'NodePath(']):
            return 'INTERNAL', 'Godot 식별자 형식(StringName/NodePath)', line
        return 'UNKNOWN', '사용 필드 추가 확인 필요', line
    if path.suffix == '.gd':
        if re.search(r'type\.(NAME|DESCRIPTION|INFORMATION):\s*$', prefix):
            if value in ('NONE', '', '???'):
                return 'VISIBLE_KEEP', '스킬·동물 표시 데이터의 빈 항목 또는 미해금 기호', line
            return 'VISIBLE_TRANSLATE', '스킬·동물·지역 표시 데이터; tooltip/companion/stage label에서 소비', line
        if re.search(r'(print|print_rich|push_error|push_warning|printerr)\s*\(', prefix):
            return 'INTERNAL', '콘솔 진단 출력 인자; 게임 표시 객체로 전달하지 않음', line
        if re.search(r'(get_node|has_node|find_child|is_action\w*|play|set_meta|get_meta|has_meta|tween_property|has_method|call|connect|disconnect|set|get|emit_signal|has_signal|get_shader_parameter|set_shader_parameter|create_timer)\([^\n]*$', prefix):
            return 'INTERNAL', '노드·입력·메서드·애니메이션·속성 조회 인자', line
        if start > 0 and text[start - 1] in ('&', '$', '^'):
            return 'INTERNAL', '노드 경로 또는 StringName 식별자', line
        if re.search(r'(\.text|tooltip_text)\s*=|add_text\(|_colored_text\(', prefix):
            if not re.search('[A-Za-z]', re.sub(r'\[[^]]*\]', '', value)) or value == '':
                return 'VISIBLE_KEEP', '숫자·서식·색상·빈 표시 조합', line
            return 'VISIBLE_TRANSLATE', '런타임 화면 표시 객체 또는 색상 문구 조합', line
        if re.fullmatch(r'#?[a-fA-F\d]{6,8}', value):
            return 'INTERNAL', 'Godot 색상 코드', line
        return 'UNKNOWN', '코드의 최종 소비 위치 확인 필요', line
    return 'UNKNOWN', '설정 문자열의 사용 위치 확인 필요', line

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records, errors, files = [], [], []
    for path in sorted(args.source.rglob('*')):
        relative = path.relative_to(args.source).as_posix()
        if path.suffix not in {'.tscn', '.tres', '.gd', '.godot', '.csv'} or relative.startswith(('.godot/', '.autoconverted/')):
            continue
        data = path.read_bytes()
        file_hash = sha(data)
        files.append({'path': relative, 'sha256': file_hash, 'size': len(data)})
        try:
            text = data.decode('utf-8-sig')
            if path.suffix == '.csv':
                for row_index, row in enumerate(csv.DictReader(io.StringIO(text, newline='')), 2):
                    for locale, value in row.items():
                        if value is None:
                            raise ValueError(f'CSV 필드 누락: {row_index}')
                        records.append({'id': f'{relative}::row{row_index}/{locale}', 'file': relative, 'file_sha256': file_hash, 'source_sha256': sha(value.encode()), 'source': value, 'kind': 'locale', 'locale': locale, 'row': row_index, 'classification': 'VISIBLE_TRANSLATE' if locale == 'en' else 'INTERNAL', 'evidence': '영어 화면 번역 슬롯' if locale == 'en' else '번역 키 또는 기존 프랑스어 슬롯; 한국어 기본 표시에 사용하지 않음'})
                continue
            for token_index, token in enumerate(tokens(text, path.suffix == '.gd', path.suffix == '.godot')):
                classification, evidence, context = classify(token, path, text)
                records.append({'id': f'{relative}::string{token_index}', 'file': relative, 'file_sha256': file_hash, 'source_sha256': sha(token['value'].encode()), 'source': token['value'], 'kind': 'script' if path.suffix == '.gd' else 'resource', 'token': token_index, 'line': text.count('\n', 0, token['start']) + 1, 'start': token['start'], 'end': token['end'], 'quote': token['quote'], 'classification': classification, 'evidence': evidence, 'context': context})
        except Exception as exception:
            errors.append({'file': relative, 'sha256': file_hash, 'error': str(exception), 'classification': 'UNKNOWN'})
    (args.output / 'census.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output / 'text_files.json').write_text(json.dumps(files, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output / 'extraction_errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {'files': len(files), 'strings': len(records), 'classification': dict(Counter(x['classification'] for x in records)), 'errors': len(errors)}
    (args.output / 'census_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary))

if __name__ == '__main__':
    main()
