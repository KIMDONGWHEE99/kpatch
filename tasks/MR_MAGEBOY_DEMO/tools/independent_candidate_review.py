"""기대 수정본을 독립 재작성하고 완성 PCK의 새 복원값을 전수 대조합니다."""
import argparse
import collections
import csv
import difflib
import hashlib
import io
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'working_private/MR_MAGEBOY_DEMO'
ORIGINAL = ROOT / 'extracted_private/MR_MAGEBOY_DEMO/steam_25734075/recovered'
RECOVERY = ROOT / 'extracted_private/MR_MAGEBOY_DEMO/steam_25734075/candidate_recovery'
TRANSLATION = WORK / 'translation'
TOOLS = Path(__file__).parent
CSV_PATH = 'addons/maaacks_game_template/base/translations/menus_translations.csv'
SNAPSHOTS = {}
CODE_ATOM = re.compile(r'[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    SNAPSHOTS[path] = digest(data)
    return data


def load(path):
    return json.loads(read_bytes(path).decode('utf-8-sig'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def scan(text, suffix):
    # 제작 스캐너를 호출하지 않고 주석·문자열·나머지 코드를 직접 나눕니다.
    result = []
    position = 0
    literal_index = 0
    while position < len(text):
        character = text[position]
        if character.isspace():
            position += 1
            continue
        if character == '#' and suffix == '.gd' or character == ';' and suffix == '.godot':
            newline = text.find('\n', position)
            position = newline if newline >= 0 else len(text)
            continue
        if character in ('"', "'"):
            start = position
            width = 3 if text.startswith(character * 3, position) else 1
            position += width
            value = []
            while not text.startswith(character * width, position):
                if position >= len(text):
                    raise ValueError(('종료되지 않은 문자열', start))
                if text[position] == '\\' and position + 1 < len(text):
                    following = text[position + 1]
                    value.append({'n': '\n', 'r': '\r', 't': '\t', '"': '"', "'": "'", '\\': '\\'}.get(following, '\\' + following))
                    position += 2
                else:
                    value.append(text[position])
                    position += 1
            position += width
            result.append({'kind': 'string', 'value': ''.join(value), 'start': start, 'end': position,
                           'ordinal': literal_index, 'line': text.count('\n', 0, start) + 1})
            literal_index += 1
        else:
            atom = CODE_ATOM.match(text, position)
            value = atom[0] if atom else character
            result.append({'kind': 'code', 'value': value, 'start': position})
            position += len(value)
    # 리소스의 최상위 UID는 복원기의 되붙임 동작만 별도로 분리합니다.
    if suffix in ('.tscn', '.tres'):
        header = text.split('\n', 1)[0]
        uid = re.search(r'\buid\s*=\s*"[^"\n]*"', header)
        if uid:
            result = [token for token in result if not uid.start() <= token['start'] < uid.end()]
    return result


def pairs(tokens, skeleton=False):
    return [(token['kind'], '' if skeleton and token['kind'] == 'string' else token['value']) for token in tokens]


def compare_asset(expected_data, observed_data, suffix):
    # 후보 전체 검사와 작은 실패 주입 시험이 같은 대조 함수를 사용합니다.
    expected_tokens = scan(expected_data.decode('utf-8-sig'), suffix)
    actual_tokens = scan(observed_data.decode('utf-8-sig'), suffix)
    equal = pairs(expected_tokens) == pairs(actual_tokens)
    difference = [] if equal else [row for row in difflib.SequenceMatcher(
        a=pairs(expected_tokens), b=pairs(actual_tokens), autojunk=False).get_opcodes() if row[0] != 'equal']
    return expected_tokens, actual_tokens, equal, difference


def compare_source_input(expected_data, actual_data, suffix):
    # 편집기가 LF/CRLF 파일 줄끝만 바꾼 경우를 구분합니다.
    # 문자열 안의 실제 제어 줄바꿈은 토큰 값도 같아야 허용합니다.
    if expected_data == actual_data:
        return True, False
    if expected_data.replace(b'\r\n', b'\n') != actual_data.replace(b'\r\n', b'\n'):
        return False, False
    _, _, equal, _ = compare_asset(expected_data, actual_data, suffix)
    return equal, equal


def quote_value(value, quotation):
    # 원본 인용 방식과 제어 문자를 보존합니다.
    escaped = value.replace('\\', '\\\\').replace(quotation, '\\' + quotation)
    if len(quotation) == 1:
        escaped = escaped.replace('\t', '\\t').replace('\r', '\\r').replace('\n', '\\n')
    return quotation + escaped + quotation


def reconstruct(original, entries, declaration, issues):
    text = original.decode('utf-8-sig')
    for entry in sorted(entries, key=lambda row: row['start'], reverse=True):
        text = text[:entry['start']] + quote_value(entry['korean'], entry['quote']) + text[entry['end']:]
    if declaration.get('code_changes'):
        text = text.replace('\r\n', '\n')
        for change in declaration['code_changes']:
            before, after = change['before'], change['after']
            actual_count = text.count(before) if before else 1
            if actual_count != change['count']:
                issues.append({'kind': 'code_change_count', 'file': declaration['file'], 'method': change['method'],
                               'expected': change['count'], 'actual': actual_count})
            text = text.replace(before, after) if before else text.rstrip() + after
    return (b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b'') + text.encode('utf-8')


def dump_translation(candidate, stage, expected_keys):
    probe = stage / 'resource_probe'
    probe.mkdir(parents=True, exist_ok=True)
    (probe / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="Independent Translation Read"\n', encoding='utf-8')
    output = stage / 'candidate_translation_values.json'
    config = stage / 'translation_read.json'
    save(config, {'pack': str(candidate / 'MR MAGEBOY DEMO.pck'), 'output': str(output), 'keys': expected_keys, 'locales': {
        'en': 'addons/maaacks_game_template/base/translations/menus_translations.en.translation',
        'fr': 'addons/maaacks_game_template/base/translations/menus_translations.fr.translation'}})
    environment = os.environ.copy()
    for key, folder in (('APPDATA', 'roaming'), ('LOCALAPPDATA', 'local'), ('TEMP', 'temp'), ('TMP', 'temp')):
        destination = probe / folder
        destination.mkdir(exist_ok=True)
        environment[key] = str(destination)
    tool = ROOT / 'tools/gdre_2.6.4/bin/gdre_tools.exe'
    command = [str(tool), '--headless', '--path', str(probe), '--script', str(TOOLS / 'independent_translation_dump.gd'), '--', str(config)]
    process = subprocess.run(command, env=environment, capture_output=True, timeout=90)
    (stage / 'translation_read.stdout.log').write_bytes(process.stdout)
    (stage / 'translation_read.stderr.log').write_bytes(process.stderr)
    save(stage / 'translation_read.execution.json', {'command': command, 'exit_code': process.returncode,
        'tool_sha256': digest(tool.read_bytes()), 'scope': '게임 흐름 실행 없이 Translation 자산만 읽음',
        'stdout_sha256': digest(process.stdout), 'stderr_sha256': digest(process.stderr)})
    if process.returncode:
        raise ValueError(('완성 번역 자산 읽기 실패', process.returncode))
    return load(output)


def review(candidate_id, translation_directory=None, modified_directory=None):
    global TRANSLATION
    snapshot = WORK / candidate_id / 'inputs'
    if translation_directory is not None:
        TRANSLATION = Path(translation_directory).resolve()
    elif (snapshot / 'translation_meta/translation.json').is_file():
        TRANSLATION = snapshot / 'translation_meta'
    TRANSLATION.relative_to(WORK.resolve())
    candidate = ROOT / 'build_candidate/MR_MAGEBOY_DEMO' / candidate_id
    recovered = RECOVERY / candidate_id
    stage = WORK / candidate_id / 'independent_comparison'
    stage.mkdir(parents=True, exist_ok=True)
    census = load(TRANSLATION / 'census.json')
    listed_files = load(TRANSLATION / 'text_files.json')
    translated = load(TRANSLATION / 'translation.json')
    declared = load(TRANSLATION / 'modified_manifest.json')
    runtime = load(TRANSLATION / 'runtime_manifest.json')
    table = load(TRANSLATION / 'translation_table.json')
    additions = load(TRANSLATION / 'translation_table_additions.json')
    build = load(WORK / candidate_id / 'build_manifest.json')
    census_by_id = {row['id']: row for row in census}
    entries_by_id = {row['id']: row for row in translated['entries']}
    declarations = {row['file']: row for row in declared}
    visible_ids = {row['id'] for row in census if row['classification'] in ('VISIBLE_KEEP', 'VISIBLE_TRANSLATE')}
    issues = []
    input_lock_path = WORK / candidate_id / 'input_lock.json'
    if input_lock_path.is_file():
        input_lock = load(input_lock_path)
        inventory = {path.relative_to(snapshot).as_posix(): digest(read_bytes(path))
                     for path in snapshot.rglob('*') if path.is_file()}
        if inventory != input_lock['files']:
            issues.append({'kind': 'input_snapshot_inventory'})
        if digest(input_lock_path.read_bytes()) != build.get('input_lock_sha256'):
            issues.append({'kind': 'input_lock_hash'})
    matrix = []
    new_literals = []
    file_results = []
    if set(entries_by_id) != visible_ids:
        issues.append({'kind': 'visible_position_scope', 'missing': sorted(visible_ids - entries_by_id.keys()),
                       'unexpected': sorted(entries_by_id.keys() - visible_ids)})
    if len(entries_by_id) != len(translated['entries']) or len(declarations) != len(declared):
        issues.append({'kind': 'duplicate_declaration'})
    if translated['runtime_entries'] != runtime:
        issues.append({'kind': 'runtime_manifest_copy'})
    for entry in translated['entries']:
        original = census_by_id.get(entry['id'])
        if original is None or any(entry.get(key) != original.get(key) for key in original):
            issues.append({'kind': 'original_position_link', 'id': entry['id']})
        if digest(entry['korean'].encode('utf-8')) != entry['expected_sha256']:
            issues.append({'kind': 'expected_translation_hash', 'id': entry['id']})
    modified = Path(modified_directory).resolve() if modified_directory is not None else (
        snapshot / 'modified' if (snapshot / 'modified').is_dir() else TRANSLATION / 'modified')
    modified.resolve().relative_to(WORK.resolve())
    actual_files = {path.relative_to(modified).as_posix() for path in modified.rglob('*') if path.is_file()}
    if actual_files != set(declarations):
        issues.append({'kind': 'modified_scope', 'missing': sorted(set(declarations) - actual_files),
                       'unexpected': sorted(actual_files - set(declarations))})
    build_inputs = {row['path']: row['sha256'] for row in build['modified_inputs']}
    if build_inputs != {path: row['modified_sha256'] for path, row in declarations.items()}:
        issues.append({'kind': 'build_input_stale'})
    files_to_compare = {row['path']: row for row in listed_files if not row['path'].endswith('.csv')}
    for file in files_to_compare:
        declaration = declarations.get(file)
        source_line_endings_only = False
        original_data = read_bytes(ORIGINAL / file)
        if digest(original_data) != files_to_compare[file]['sha256']:
            issues.append({'kind': 'original_source_hash', 'file': file})
        if declaration:
            modified_data = read_bytes(modified / file)
            if digest(original_data) != declaration['source_sha256'] or digest(modified_data) != declaration['modified_sha256']:
                issues.append({'kind': 'source_or_modified_hash', 'file': file})
            replacements = [entry for entry in translated['entries'] if entry['file'] == file and entry['classification'] == 'VISIBLE_TRANSLATE' and entry['implementation'] == 'literal']
            if set(declaration['changed_positions']) != {entry['id'] for entry in replacements}:
                issues.append({'kind': 'changed_position_scope', 'file': file})
            expected_data = reconstruct(original_data, replacements, declaration, issues)
            source_equal, source_line_endings_only = compare_source_input(expected_data, modified_data, Path(file).suffix)
            if not source_equal:
                issues.append({'kind': 'undeclared_source_change', 'file': file,
                               'expected_sha256': digest(expected_data), 'actual_sha256': digest(modified_data)})
        else:
            modified_data = original_data
            expected_data = original_data
        observed_path = recovered / file
        if not observed_path.is_file():
            issues.append({'kind': 'missing_recovered_file', 'file': file})
            continue
        observed_data = read_bytes(observed_path)
        original_tokens = scan(original_data.decode('utf-8-sig'), Path(file).suffix)
        expected_tokens, actual_tokens, equal, difference = compare_asset(expected_data, observed_data, Path(file).suffix)
        if not equal:
            issues.append({'kind': 'fresh_recovered_tokens', 'file': file, 'opcodes': difference})
        actual_strings = {row['ordinal']: row for row in actual_tokens if row['kind'] == 'string'}
        mapped = {}
        matcher = difflib.SequenceMatcher(a=pairs(original_tokens, True), b=pairs(expected_tokens, True), autojunk=False)
        for block in matcher.get_matching_blocks():
            for offset in range(block.size):
                before, after = original_tokens[block.a + offset], expected_tokens[block.b + offset]
                if before['kind'] == 'string':
                    mapped[after['ordinal']] = before
        for expected in (row for row in expected_tokens if row['kind'] == 'string'):
            observed = actual_strings.get(expected['ordinal'])
            before = mapped.get(expected['ordinal'])
            row = {'file': file, 'expected_token': expected['ordinal'], 'expected_line': expected['line'],
                   'expected': expected['value'], 'observed': observed['value'] if observed else None,
                   'observed_line': observed['line'] if observed else None,
                   'status': 'PASS' if observed and observed['value'] == expected['value'] else 'FAIL'}
            if before:
                identifier = f"{file}::string{before['ordinal']}"
                row.update({'id': identifier, 'original': before['value'], 'original_line': before['line'],
                            'classification': census_by_id.get(identifier, {}).get('classification', 'UNKNOWN')})
                entry = entries_by_id.get(identifier)
                if entry and entry['implementation'] == 'literal' and entry['korean'] != expected['value']:
                    issues.append({'kind': 'position_expected_translation', 'id': identifier,
                                   'declared': entry['korean'], 'reconstructed': expected['value']})
                matrix.append(row)
            else:
                row['origin'] = '수정 manifest에 선언한 표시 연결 코드의 새 문자열'
                new_literals.append(row)
        file_results.append({'file': file, 'source_sha256': digest(original_data), 'modified_sha256': digest(modified_data),
                             'modified': declaration is not None,
                             'source_line_endings_only': source_line_endings_only,
                             'recovered_sha256': digest(observed_data), 'source_literal_count': sum(x['kind'] == 'string' for x in original_tokens),
                             'expected_literal_count': sum(x['kind'] == 'string' for x in expected_tokens),
                             'observed_literal_count': sum(x['kind'] == 'string' for x in actual_tokens),
                             'all_code_and_literal_tokens': 'PASS' if equal else 'FAIL'})
    # 정적 번역표 키 충돌·삭제·추가 허용 목록 및 동적 기록을 독립 확인합니다.
    original_csv = read_bytes(ORIGINAL / CSV_PATH).decode('utf-8-sig')
    original_rows = list(csv.DictReader(io.StringIO(original_csv, newline='')))
    original_keys = {row['key'] for row in original_rows}
    locale_by_id = {f'{CSV_PATH}::row{index}/en': row['key'] for index, row in enumerate(original_rows, 2)}
    for entry in translated['entries']:
        if entry['implementation'] == 'translation_table':
            key = locale_by_id.get(entry['id'], entry['source'])
            if table.get(key) != entry['korean']:
                issues.append({'kind': 'static_table_position', 'id': entry['id'], 'key': key})
    if set(additions) != table.keys() - original_keys or any(table.get(key) != value for key, value in additions.items()):
        issues.append({'kind': 'translation_addition_allowlist'})
    for entry in runtime:
        if table.get(entry['translation_key']) != entry['korean'] or digest(entry['source'].encode('utf-8')) != entry['source_sha256']:
            issues.append({'kind': 'runtime_table_link', 'id': entry['id']})
        if not entry.get('evidence') or not entry.get('consumer') or not entry.get('original_asset_sha256'):
            issues.append({'kind': 'runtime_evidence', 'id': entry['id']})
    observed_locales = dump_translation(candidate, stage, {'en': sorted(table), 'fr': sorted(original_keys)})
    locale_rows = []
    for locale, expected in (('en', table), ('fr', {row['key']: row['fr'] for row in original_rows})):
        actual = observed_locales[locale]['values']
        if set(expected) != set(actual):
            issues.append({'kind': 'native_translation_key_scope', 'locale': locale,
                           'missing': sorted(expected.keys() - actual.keys()), 'unexpected': sorted(actual.keys() - expected.keys())})
        for key in expected.keys() | actual.keys():
            row = {'locale': locale, 'key': key, 'expected': expected.get(key), 'observed': actual.get(key),
                   'status': 'PASS' if key in expected and key in actual and expected[key] == actual[key] else 'FAIL'}
            locale_rows.append(row)
            if row['status'] == 'FAIL':
                issues.append({'kind': 'native_translation_value', 'locale': locale, 'key': key})
    if build.get('translation_input_sha256') != SNAPSHOTS[(TRANSLATION / 'translation_table.json').resolve()]:
        issues.append({'kind': 'translation_build_input_stale'})
    stale = [str(path) for path, before in SNAPSHOTS.items() if not path.is_file() or digest(path.read_bytes()) != before]
    if stale:
        issues.append({'kind': 'input_changed_during_review', 'paths': stale})
    status = 'STALE' if stale else ('FAIL' if issues else 'PASS')
    save(stage / 'position_matrix.json', {'original_positions': matrix, 'added_code_literals': new_literals, 'native_translation_positions': locale_rows})
    report = {'game_id': 'MR_MAGEBOY_DEMO', 'steam_build': '25734075', 'candidate': candidate_id, 'status': status,
              'scope': '독립 기대 수정본 재작성·후보 새 복원 코드/문자열·PCK 실제 Translation 값 전수 대조. 그래픽 검수 아님.',
              'reviewed_utc': datetime.now(timezone.utc).isoformat(), 'candidate_pck_sha256': digest(read_bytes(candidate / 'MR MAGEBOY DEMO.pck')),
              'tool_sha256': digest(Path(__file__).read_bytes()), 'input_hashes': {str(path): value for path, value in SNAPSHOTS.items()},
              'modified_files': len(declared), 'visible_positions': len(translated['entries']), 'runtime_positions': len(runtime),
              'compared_source_files': len(files_to_compare), 'translation_directory': str(TRANSLATION),
              'modified_directory': str(modified),
              'compared_original_literals': len(matrix), 'added_code_literals': len(new_literals), 'native_translation_positions': len(locale_rows),
              'files': file_results, 'issues': issues, 'graphics_status': 'NOT_RUN'}
    save(stage / 'independent_candidate_review.json', report)
    print(json.dumps({key: report[key] for key in ('status', 'modified_files', 'visible_positions', 'runtime_positions', 'compared_original_literals', 'added_code_literals', 'native_translation_positions', 'issues')}, ensure_ascii=False))
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate_id')
    parser.add_argument('--translation-directory', type=Path)
    parser.add_argument('--modified-directory', type=Path)
    arguments = parser.parse_args()
    raise SystemExit(0 if review(arguments.candidate_id, arguments.translation_directory, arguments.modified_directory) == 'PASS' else 1)
