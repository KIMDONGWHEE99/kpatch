"""원본/후보 PCK를 다시 읽어 허용된 자산과 글꼴 변경만 있는지 독립 검사한다."""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from pck_tools import ROOT, GAME, BASELINE, WORK, read_pack, read_settings, variant

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen

PCK = 'MR MAGEBOY DEMO.pck'
TITLE_RESOURCE = 'korean_patch/fonts/TitlePixel.ttf'
EN_RESOURCE = 'addons/maaacks_game_template/base/translations/menus_translations.en.translation'
TOOL = ROOT / 'tools/gdre_2.6.4/bin/gdre_tools.exe'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def run(candidate_id):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', candidate_id) or '..' in candidate_id:
        raise ValueError('후보 번호의 경로 구분자 금지')
    stage = WORK / candidate_id
    candidate = ROOT / 'build_candidate' / GAME / candidate_id
    failures = []
    def require(condition, detail):
        if not condition:
            failures.append(detail)
    baseline = read(WORK / 'baseline.json')
    source_bytes, source_base, source_directory, original_rows = read_pack(BASELINE / PCK)
    candidate_bytes, candidate_base, candidate_directory, candidate_rows = read_pack(candidate / PCK)
    original = {row['name']: row['data'] for row in original_rows}
    actual = {row['name']: row['data'] for row in candidate_rows}
    declared = read(stage / 'build_manifest.json')
    lock = read(stage / 'input_lock.json')
    inputs = stage / 'inputs'
    manifest = read(inputs / 'translation_meta/modified_manifest.json')
    require(sha(source_bytes) == next(row['sha256'] for row in baseline['files'] if row['path'] == PCK), '원본 PCK 기준 지문 불일치')
    require(sha(candidate_bytes) == declared['candidate_pck_sha256'], '후보 PCK 선언 지문 불일치')
    require(len(original) == 8688 and len(actual) == 8689, '원본/후보 항목 수 불일치')
    require(set(actual) == set(original) | {TITLE_RESOURCE}, '제목 글꼴 한 개 외 자산 추가/삭제')
    snapshot_inventory = {path.relative_to(inputs).as_posix(): sha(path.read_bytes()) for path in inputs.rglob('*') if path.is_file()}
    require(snapshot_inventory == lock['files'], '고정 입력 사본 목록/지문 불일치')
    expected = {}
    provenance = {}
    for item in manifest:
        logical = item['file']
        input_path = inputs / 'modified' / logical
        require(sha(input_path.read_bytes()) == item['modified_sha256'], {'source': logical, 'error': '수정 원본 선언 지문 불일치'})
        if logical == 'project.godot':
            target = 'project.binary'
            original_settings = read_settings(original[target])
            candidate_settings = read_settings(actual[target])
            require(set(original_settings) == set(candidate_settings), '프로젝트 설정 키 추가/삭제')
            changed_keys = {key for key in original_settings if original_settings[key] != candidate_settings[key]}
            require(changed_keys == set(item['settings_keys']) == {'application/config/description'}, '프로젝트 설정 허용 위치 외 변경')
            match = re.search(r'^config/description=(.*)$', input_path.read_text(encoding='utf-8-sig'), flags=re.M)
            require(candidate_settings['application/config/description'] == variant(json.loads(match[1])), '설명 문구 설정 기대값 불일치')
            payload = actual[target]
        else:
            remap = logical + '.remap'
            require(remap in original, {'source': logical, 'error': '원본 remap 없음'})
            target = re.search(r'path\s*=\s*"res://([^"]+)"', original[remap].decode('utf-8'))[1]
            require(target == item['original_asset'], {'source': logical, 'error': '원본 remap/명세 target 불일치'})
            require(sha(original[target]) == item['original_asset_sha256'], {'source': logical, 'error': '원본 target 지문 불일치'})
            output_path = stage / 'script_inputs' / Path(logical).with_suffix('.gdc') if logical.endswith('.gd') else stage / 'resource_outputs' / target
            payload = output_path.read_bytes()
        require(target not in expected, {'target': target, 'error': '허용 target 중복'})
        expected[target] = sha(payload)
        provenance[target] = {'kind': 'compiled_source', 'source': logical, 'source_sha256': sha(input_path.read_bytes())}
    expected[EN_RESOURCE] = sha((stage / 'menus_translations.en.translation').read_bytes())
    provenance[EN_RESOURCE] = {'kind': 'translation', 'source_sha256': sha((inputs / 'translation_meta/translation_table.json').read_bytes())}
    font_paths = sorted(path for path in original if path.endswith('.fontdata') and 'PixelOperator' in path)
    require(len(font_paths) == 2, '본문/굵은 글꼴 항목 수 불일치')
    for path in font_paths:
        expected[path] = sha((stage / 'fonts' / Path(path).name).read_bytes())
        provenance[path] = {'kind': 'korean_fallback'}
    expected[TITLE_RESOURCE] = sha((inputs / 'fonts/title/TitlePixel.ttf').read_bytes())
    provenance[TITLE_RESOURCE] = {'kind': 'title_font_addition'}
    observed_changed = {path for path in set(original) | set(actual) if original.get(path) != actual.get(path)}
    require(observed_changed == set(expected), {'error': '명시 허용 목록 외 변경/허용 변경 누락', 'difference': sorted(observed_changed.symmetric_difference(expected))})
    require(expected == declared['pck_changes'], '원본 remap/실제 조립 산출물에서 독립 구성한 허용 SHA가 선언 목록과 다름')
    all_payloads = []
    for path in sorted(actual):
        digest = sha(actual[path])
        before = sha(original[path]) if path in original else None
        permitted = path in expected
        require(digest == (expected[path] if permitted else before), {'path': path, 'error': 'PCK 실제 payload SHA 불일치'})
        all_payloads.append({'path': path, 'size': len(actual[path]), 'original_sha256': before,
            'candidate_sha256': digest, 'permitted_change': permitted, **provenance.get(path, {})})
    file_rows = []
    require({path.name for path in candidate.iterdir() if path.is_file()} == {row['path'] for row in baseline['files']}, '후보 실행 폴더 파일 추가/삭제')
    for row in baseline['files']:
        if row['path'] == PCK:
            continue
        before = sha((BASELINE / row['path']).read_bytes())
        after = sha((candidate / row['path']).read_bytes())
        require(before == after == row['sha256'], {'path': row['path'], 'error': '엔진/DLL 원본 지문 불일치'})
        file_rows.append({'path': row['path'], 'sha256': after, 'status': 'PASS' if before == after == row['sha256'] else 'FAIL'})
    probe = stage / 'independent_boundary_probe'
    probe.mkdir(exist_ok=True)
    native_font_rows = []
    for index, path in enumerate(font_paths):
        before = probe / ('original_%d.fontdata' % index)
        after = probe / ('candidate_%d.fontdata' % index)
        before.write_bytes(original[path]); after.write_bytes(actual[path])
        native_font_rows.append({'resource': path, 'original': before.as_posix(), 'candidate': after.as_posix()})
    title_payload = probe / 'ActualTitlePixel.ttf'
    title_payload.write_bytes(actual[TITLE_RESOURCE])
    title_manifest = read(inputs / 'fonts/title/source_manifest.json')
    require(sha(actual[TITLE_RESOURCE]) == title_manifest['output_sha256'], '제목 글꼴 명세/실제 PCK SHA 불일치')
    selected = TTFont(io.BytesIO(actual[TITLE_RESOURCE]))
    title_source = TTFont(inputs / 'fonts/title/Source.ttf')
    required_title = {ord(char) for char in '채집 마법사'}
    selected_cmap = selected.getBestCmap(); source_cmap = title_source.getBestCmap()
    require(set(selected_cmap) == required_title, '제목 글꼴 필요 문자 외 cmap/누락')
    require(required_title.issubset(source_cmap), '제목 원본 글꼴 문자 누락')
    require(sha((inputs / 'fonts/title/Source.ttf').read_bytes()) == title_manifest['source_sha256'], '제목 원본 글꼴 명세 SHA 불일치')
    require(sha((inputs / 'fonts/title/LICENSE.txt').read_bytes()) == title_manifest['license_sha256'], '제목 라이선스 명세 SHA 불일치')
    title_shape_rows = []
    for code in sorted(required_title):
        before_pen, after_pen = RecordingPen(), RecordingPen()
        title_source.getGlyphSet()[source_cmap[code]].draw(before_pen)
        selected.getGlyphSet()[selected_cmap[code]].draw(after_pen)
        shape_equal = before_pen.value == after_pen.value
        advance_equal = title_source['hmtx'].metrics[source_cmap[code]] == selected['hmtx'].metrics[selected_cmap[code]]
        require(shape_equal and advance_equal, {'code': code, 'error': '제목 글리프 모양/간격 변경'})
        title_shape_rows.append({'code': code, 'character': chr(code), 'shape_equal': shape_equal, 'advance_equal': advance_equal})
    require(selected['OS/2'].usWeightClass == 700 and selected['OS/2'].fsSelection & 32 and selected['head'].macStyle & 1, '제목 굵기 메타데이터 불일치')
    require(selected['name'].getDebugName(1) == 'MageboyKoreanTitle', '제목 파생 글꼴 이름 불일치')
    declared_character_path = inputs / 'translation_meta/required_characters.json'
    declared_characters = set(read(declared_character_path)['characters'])
    translation_values = read(inputs / 'translation_meta/translation_table.json')
    translation_entries = read(inputs / 'translation_meta/translation.json')
    # 작성 메타를 그대로 믿지 않고 실제 최종 표시값에서 필요 글자를 다시 계산한다.
    required_characters = set(''.join(translation_values.values()) + ''.join(row['korean'] for row in translation_entries['entries']) + ''.join(row['korean'] for row in translation_entries['runtime_entries']))
    require(required_characters.issubset(declared_characters), {'error': '작성 메타에 실제 필요 글자 누락', 'missing': sorted(required_characters - declared_characters)})
    for row in translation_entries['runtime_entries']:
        require(translation_values.get(row['translation_key']) == row['korean'], {'error': '런타임/표 표시값 불일치', 'id': row['id']})
    character_recalculation = {'status': 'PASS', 'required_count': len(required_characters), 'characters': ''.join(sorted(required_characters)),
                              'declared_count': len(declared_characters), 'declared_unused': sorted(declared_characters - required_characters),
                              'declared_missing': sorted(required_characters - declared_characters), 'declared_metadata_sha256': sha(declared_character_path.read_bytes()),
                              'translation_values_sha256': sha((inputs / 'translation_meta/translation_table.json').read_bytes()),
                              'translation_entries_sha256': sha((inputs / 'translation_meta/translation.json').read_bytes()),
                              'reason': '실제 위치별 번역·런타임 표시·번역표 전체의 합집합. 사용하지 않는 과거 글자는 글꼴 요구로 취급하지 않는다. 고정 입력은 수정하지 않는다.'}
    write(probe / 'required_characters_recalculated.json', character_recalculation)
    required = ''.join(sorted(required_characters))
    config = {'fonts': native_font_rows, 'characters': sorted(set(required) - set('\r\n\t ')),
        'title': title_payload.as_posix(), 'title_text': sorted(set('채집 마법사')),
        'report': (probe / 'native_fonts.json').as_posix()}
    write(probe / 'config.json', config)
    (probe / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="독립 글꼴 경계 검사"\n', encoding='utf-8')
    env = os.environ.copy(); env['APPDATA'] = str(probe / 'roaming'); env['LOCALAPPDATA'] = str(probe / 'local')
    script = Path(__file__).with_name('audit_boundary_fonts.gd')
    command = [str(TOOL), '--headless', '--path', str(probe), '--script', str(script), '--', str(probe / 'config.json')]
    result = subprocess.run(command, env=env, capture_output=True, timeout=120)
    (probe / 'stdout.log').write_bytes(result.stdout); (probe / 'stderr.log').write_bytes(result.stderr)
    require(result.returncode == 0, {'error': '독립 글꼴 속성 조회 실패', 'exit_code': result.returncode})
    native = read(probe / 'native_fonts.json') if (probe / 'native_fonts.json').exists() else {}
    font_checks = []
    for row in native.get('fonts', []):
        before, after = row['original'], row['candidate']
        require('error' not in before and 'error' not in after, {'font': row['resource'], 'error': '글꼴 재열기 실패'})
        if 'error' in before or 'error' in after:
            continue
        require(before['font_data_sha256'] == after['font_data_sha256'], {'font': row['resource'], 'error': '원본 본문 글꼴 data 변경'})
        require(before['properties'] == after['properties'], {'font': row['resource'], 'error': '원본 저장 속성 변경', 'keys': sorted(key for key in set(before['properties']) | set(after['properties']) if before['properties'].get(key) != after['properties'].get(key))})
        require(after['fallbacks'][:len(before['fallbacks'])] == before['fallbacks'] and len(after['fallbacks']) == len(before['fallbacks']) + 1, {'font': row['resource'], 'error': '한글 대체 글꼴 한 개 외 fallback 변경'})
        weight = 700 if 'Bold' in row['resource'] else 400
        extra_sha = sha((stage / 'fonts' / ('Korean%d.ttf' % weight)).read_bytes())
        require(after['fallbacks'][-1]['data_sha256'] == extra_sha and after['fallbacks'][-1]['antialiasing'] == 1, {'font': row['resource'], 'error': '한글 fallback data/속성 불일치'})
        require(after['missing'] == [], {'font': row['resource'], 'error': '번역 필요 글자 누락', 'missing': after['missing']})
        info_keys = ['ver_major', 'ver_minor', 'uid', 'stored_big_endian', 'stored_use_real64']
        require(all(before['resource_info'].get(key) == after['resource_info'].get(key) for key in info_keys), {'font': row['resource'], 'error': '원본 FontFile 저장 형식/UID 변경'})
        font_checks.append({'resource': row['resource'], 'source_data_sha256': before['font_data_sha256'], 'properties_count': len(before['properties']), 'properties_preserved': before['properties'] == after['properties'], 'original_fallback_count': len(before['fallbacks']), 'candidate_fallback_count': len(after['fallbacks']), 'fallback_sha256': extra_sha, 'missing': after['missing']})
    require(len(font_checks) == 2, '독립 본문/굵은 글꼴 조회 수 불일치')
    require(native.get('title', {}).get('data_sha256') == expected[TITLE_RESOURCE] and native.get('title', {}).get('missing') == [], '제목 원시 글꼴 로딩/필요 글리프 실패')
    report = {'status': 'FAIL' if failures else 'PASS', 'candidate': candidate_id, 'source_pck_sha256': sha(source_bytes),
        'candidate_pck_sha256': sha(candidate_bytes), 'original_entries': len(original), 'candidate_entries': len(actual),
        'permitted_changes': len(expected), 'observed_changes': len(observed_changed), 'unchanged_payloads': len(actual) - len(observed_changed),
        'allowed_additions': [TITLE_RESOURCE], 'input_lock_sha256': sha((stage / 'input_lock.json').read_bytes()),
        'executable_files': file_rows, 'characters': character_recalculation, 'fonts': font_checks, 'title_font': {'resource': TITLE_RESOURCE, 'sha256': expected[TITLE_RESOURCE],
        'required_text': '채집 마법사', 'cmap': sorted(selected_cmap), 'glyphs': title_shape_rows, 'native': native.get('title')},
        'payloads': all_payloads, 'probe': {'tool_sha256': sha(TOOL.read_bytes()), 'script_sha256': sha(script.read_bytes()), 'native_report_sha256': sha((probe / 'native_fonts.json').read_bytes()) if native else None},
        'failures': failures, 'scope': 'read_pack로 실제 원본·후보 PCK를 재열기. 빌더 성공 카운터는 사용하지 않음. 글꼴 속성/글리프 조회는 격리 도구 엔진이며 실제 GPU 검수는 별도.'}
    write(stage / 'independent_boundary.json', report)
    print(json.dumps({key: report[key] for key in ['status', 'candidate', 'original_entries', 'candidate_entries', 'permitted_changes', 'observed_changes', 'unchanged_payloads']}))
    return bool(failures)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate_id')
    sys.exit(run(parser.parse_args().candidate_id))
