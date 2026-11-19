"""후보를 처음부터 다시 풀어 번역 원본·원본 게임과 대조합니다(G4). build.py의 결과 표시는 근거로 쓰지 않습니다.

사용: python validate_candidate.py <build_id>
검사:
  V1 파일 경계   : exe·dll 3개가 원본과 같고, PCK에서 바뀐 항목이 허용 목록과 정확히 같은지
  V2 언어표      : 후보의 kr 표를 엔진으로 다시 읽어 칸마다 기대 번역과 같은지(빈 칸·위치 교환·개수 포함), en 등 다른 표 무변경
  V3 직접 문구   : 영어 문구를 키로 조회했을 때 기대 번역이 나오는지
  V4 스크립트    : 바뀐 스크립트 3개를 다시 풀어 원본과 비교했을 때 추가된 줄만 있고 그 줄이 허용 내용인지
  V5 장면        : 바뀐 장면 2개를 글자로 풀어 원본과 비교했을 때 한국어 버튼과 글꼴 참조만 추가됐는지
  V6 글꼴        : 글꼴 자원 안의 TTF가 만든 파일과 같고, 실제 표에 든 모든 글자를 게임 글꼴+한글 글꼴이 그릴 수 있는지
"""
import collections
import difflib
import json
import re
import sys
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, BASE, RECOVERED, PACK, WORK, CANDIDATE, PCK_NAME, save, load, sha, sha_bytes, run_gdre
from pck_tools import read_pack
import optimized_translation as ot

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from fontTools.ttLib import TTFont

TOOLS = Path(__file__).parent
ALLOWED_CHANGED = {'locale/locale.kr.translation', 'globals/font_locale_resolver/font_locale_resolver.gdc',
                   'globals/game_settings/resolvers/locale_game_settings_resolver.gdc', 'ui/island_naming_ui/island_naming_ui.gdc',
                   '.godot/exported/1323966856/export-dd25a33c6e6f3d9fc38706343b39458a-language_modal.scn',
                   '.godot/exported/1323966856/export-49324c22d1f9ff46c523a70b7ae3b286-settings_window_ui.scn'}
ALLOWED_NEW = {'korean_patch/NotoSansKR-Regular.fontdata', 'korean_patch/NotoSansKR-Bold.fontdata'}
SCRIPTS = {'globals/font_locale_resolver/font_locale_resolver.gd': r'"kr": \{|"regular": preload\("res://korean_patch/NotoSansKR-Regular\.fontdata"\),|"bold": preload\("res://korean_patch/NotoSansKR-Bold\.fontdata"\),|\},',
           'globals/game_settings/resolvers/locale_game_settings_resolver.gd': r'if language == "ko" and loaded_locales\.has\("kr"\):|return "kr"',
           'ui/island_naming_ui/island_naming_ui.gd': r'"kr": \[|\],|("[^"\\]{1,16}", )*"[^"\\]{1,16}",?'}
SCENES = {'ui/language_modal/language_modal.tscn': '.godot/exported/1323966856/export-dd25a33c6e6f3d9fc38706343b39458a-language_modal.scn',
          'ui/settings_window_ui/settings_window_ui.tscn': '.godot/exported/1323966856/export-49324c22d1f9ff46c523a70b7ae3b286-settings_window_ui.scn'}
BASE_FONTS = {'assets/fonts/gill_sans/Cabin-Regular.ttf': 'NotoSansKR-Regular', 'assets/fonts/gill_sans/Cabin-Bold.ttf': 'NotoSansKR-Bold',
              'assets/fonts/Merriweather_24pt-Bold.ttf': 'NotoSansKR-Bold', 'assets/fonts/Thin Sans.ttf': 'NotoSansKR-Bold',
              'assets/fonts/Harmonic.ttf': 'NotoSansKR-Bold'}


def normalized_scene(text):
    """ext_resource 번호는 저장할 때마다 달라질 수 있으므로 번호 대신 경로로 바꿔 비교합니다."""
    ids = dict((m[2], m[1]) for m in re.finditer(r'\[ext_resource [^\]]*path="([^"]+)" id="([^"]+)"\]', text))
    text = re.sub(r'ExtResource\("([^"]+)"\)', lambda m: 'ExtResource<' + ids.get(m[1], '?' + m[1]) + '>', text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r'^\[gd_scene[^\]]*\]$', '[gd_scene]', line)
        line = re.sub(r'^(\[ext_resource [^\]]*?) id="[^"]+"\]$', r'\1]', line)
        line = re.sub(r' uid="uid://[a-z0-9]+"', '', line)
        if line.strip():
            lines.append(line)
    return lines


def main():
    build_id = sys.argv[1]
    candidate, stage = CANDIDATE / build_id, WORK / build_id / 'verify'
    stage.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    checks, baseline = {}, load(WORK / 'baseline.json')
    canonical = load(WORK / 'translation/canonical.json')

    # V1 파일 경계
    failures = []
    expected = {f['path']: f for f in baseline['files']}
    present = {p.name for p in candidate.iterdir()}
    if present != set(expected):
        failures.append({'files': sorted(present ^ set(expected))})
    for name, row in expected.items():
        if name != PCK_NAME and sha(candidate / name) != row['sha256']:
            failures.append({'changed_outside_pck': name})
    original, patched = read_pack(BASE / PCK_NAME), read_pack(candidate / PCK_NAME)
    changed = {n for n, e in patched['entries'].items() if n in original['entries'] and e['data'] != original['entries'][n]['data']}
    added = set(patched['entries']) - set(original['entries'])
    removed = set(original['entries']) - set(patched['entries'])
    if changed != ALLOWED_CHANGED or added != ALLOWED_NEW or removed:
        failures.append({'changed_unexpected': sorted(changed ^ ALLOWED_CHANGED), 'added_unexpected': sorted(added ^ ALLOWED_NEW), 'removed': sorted(removed)})
    header_same = original['data'][:32] == patched['data'][:32] and original['data'][40:112] == patched['data'][40:112]
    # 머리말의 목록 위치 값(32~40바이트)만 바뀌어야 하고, 원본 자산 본문 구간은 한 바이트도 달라지면 안 됩니다.
    start, end = original['absolute_base'], original['absolute_directory']
    body_same = patched['data'][start:end] == original['data'][start:end]
    if not header_same or not body_same:
        failures.append({'header_same': header_same, 'original_body_preserved': body_same})
    checks['V1_file_boundary'] = {'status': 'FAIL' if failures else 'PASS', 'entries_original': len(original['entries']), 'entries_candidate': len(patched['entries']),
                                  'changed': len(changed), 'added': len(added), 'unchanged_identical': len(patched['entries']) - len(changed) - len(added), 'failures': failures}

    # V2·V3 언어표: 후보 PCK를 엔진에 올려 kr 표를 다시 읽습니다.
    locales = ['kr', 'en', 'ja', 'de']
    config = {'translations': [f'res://locale/locale.{n}.translation' for n in locales], 'report': str(stage / 'translation_dump.json')}
    save(stage / 'translation_dump_config.json', config)
    run_gdre(['--path', WORK / 'tool_runtime', '--script', TOOLS / 'dump_translations.gd', '--', candidate / PCK_NAME, stage / 'translation_dump_config.json'], f'{build_id}_verify_dump')
    dump = load(stage / 'translation_dump.json')
    kr = dump['res://locale/locale.kr.translation']
    slots = ot.parse(kr['hash_table'], kr['bucket_table'], kr['messages'])
    index = ot.index_slots(slots)
    inventory = load(WORK / 'census/locale_inventory.json')
    expected_by_slot = {r['slot']: r['target'] for r in canonical['slots']}
    failures, matched, used = [], 0, set()
    for item in inventory:
        found = [s for s in index.get(item['table_index'], []) if s['key_hash'] == item['key_hash'] and s['seed'] == item['seed']]
        want = expected_by_slot.get(item['slot'], '')
        if len(found) != 1:
            failures.append({'slot': item['slot'], 'problem': '칸 없음 또는 중복'})
            continue
        used.add(found[0]['slot'])
        if found[0]['message'] != want:
            failures.append({'slot': item['slot'], 'key': item['key'], 'problem': '기대 번역과 다름', 'actual': found[0]['message'][:60], 'expected': want[:60]})
        elif want:
            matched += 1
        if want and want == item['source'] and item['slot'] not in {r['slot'] for r in canonical['slots'] if r['classification'] == 'VISIBLE_KEEP'}:
            failures.append({'slot': item['slot'], 'problem': '원문 잔존'})
    direct_failures, direct_matched = [], 0
    for row in canonical['direct']:
        slot = ot.find(index, len(kr['hash_table']), row['source'])
        if slot is None or slot['message'] != row['target']:
            direct_failures.append({'source': row['source'][:50], 'actual': slot['message'][:50] if slot else None})
        else:
            direct_matched += 1
            used.add(slot['slot'])
    leftovers = [s['slot'] for s in slots if s['slot'] not in used]
    en = dump['res://locale/locale.en.translation']
    en_messages_same = en['messages'] == [r['source'] for r in sorted(inventory, key=lambda r: (r['table_index'], r['element']))]
    if leftovers:
        failures.append({'problem': '기대에 없는 칸', 'slots': leftovers[:10]})
    if kr['class'] != 'OptimizedTranslation' or kr['locale'] != 'kr' or not en_messages_same:
        failures.append({'class': kr['class'], 'locale': kr['locale'], 'en_messages_same': en_messages_same})
    checks['V2_locale_slots'] = {'status': 'FAIL' if failures else 'PASS', 'slots_total': len(inventory), 'expected_translated': len(expected_by_slot),
                                 'matched': matched, 'empty_kept': len(inventory) - len(expected_by_slot), 'candidate_slots': len(slots), 'failures': failures[:30], 'failure_count': len(failures)}
    checks['V3_direct_keys'] = {'status': 'FAIL' if direct_failures else 'PASS', 'expected': len(canonical['direct']), 'matched': direct_matched, 'failures': direct_failures}

    # V4 스크립트: 후보의 바이트코드를 다시 풀어 원본 복원 소스와 비교합니다.
    failures, script_report = [], []
    for number, (path, allowed) in enumerate(SCRIPTS.items()):
        folder = stage / 'scripts' / str(number)
        folder.mkdir(parents=True, exist_ok=True)
        binary = folder / (Path(path).stem + '.gdc')
        binary.write_bytes(patched['entries'][path[:-3] + '.gdc']['data'])
        run_gdre(['--decompile=' + str(binary), '--bytecode=4.5.0', '--output=' + str(folder)], f'{build_id}_verify_script_{number}')
        before = [line.strip() for line in (RECOVERED / path).read_text(encoding='utf-8').splitlines() if line.strip()]
        after = [line.strip() for line in (folder / Path(path).name).read_text(encoding='utf-8').splitlines() if line.strip()]
        removed_lines = [l[2:] for l in difflib.ndiff(before, after) if l.startswith('- ')]
        added_lines = [l[2:] for l in difflib.ndiff(before, after) if l.startswith('+ ')]
        bad = [l for l in added_lines if not re.fullmatch(allowed, l)]
        if removed_lines or bad or not added_lines:
            failures.append({'file': path, 'removed': removed_lines[:5], 'unexpected_added': bad[:5]})
        if path.endswith('island_naming_ui.gd'):
            names = re.findall(r'"([^"]+)"', ' '.join(added_lines).replace('"kr"', ''))
            if names != [r['target'] for r in canonical['island_names']]:
                failures.append({'file': path, 'problem': '섬 이름 목록이 번역 원본과 다름', 'count': len(names)})
        script_report.append({'file': path, 'added_lines': len(added_lines), 'removed_lines': len(removed_lines)})
    checks['V4_scripts'] = {'status': 'FAIL' if failures else 'PASS', 'scripts': script_report, 'failures': failures}

    # V5 장면
    failures, scene_config, scene_report = [], [], []
    for path, target in SCENES.items():
        source = stage / 'scenes' / Path(target).name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(patched['entries'][target]['data'])
        scene_config.append({'source': str(source), 'output': str(stage / 'scenes' / Path(path).name), 'path': path})
    save(stage / 'scene_config.json', {'scenes': scene_config, 'report': str(stage / 'scene_report.json')})
    run_gdre(['--path', WORK / 'tool_runtime', '--script', TOOLS / 'verify_scenes.gd', '--', stage / 'scene_config.json'], f'{build_id}_verify_scenes')
    for entry, row in zip(scene_config, load(stage / 'scene_report.json')):
        before = normalized_scene((RECOVERED / entry['path']).read_text(encoding='utf-8'))
        after = normalized_scene(Path(entry['output']).read_text(encoding='utf-8'))
        diff = list(difflib.ndiff(before, after))
        removed_lines = [l[2:] for l in diff if l.startswith('- ')]
        added_lines = [l[2:] for l in diff if l.startswith('+ ')]
        expected_added = {'[ext_resource type="FontFile" path="res://korean_patch/NotoSansKR-Bold.fontdata"]', 'layout_mode = 2',
                          'theme_override_fonts/font = ExtResource<res://korean_patch/NotoSansKR-Bold.fontdata>', 'text = "한국어"', 'locale = "kr"',
                          'custom_minimum_size = Vector2(76, 36)', 'small = true'}
        bad = [l for l in added_lines if l not in expected_added and not l.startswith('[node name="LanguageButtonKorean" parent="')]
        if row['error'] != 0 or removed_lines or bad or 'text = "한국어"' not in added_lines or row['info'].get('ver_minor') != 5:
            failures.append({'scene': entry['path'], 'error': row['error'], 'removed': removed_lines[:5], 'unexpected_added': bad[:5]})
        scene_report.append({'scene': entry['path'], 'added_lines': len(added_lines), 'removed_lines': len(removed_lines), 'format': [row['info'].get('ver_major'), row['info'].get('ver_minor'), row['info'].get('ver_format')]})
    checks['V5_scenes'] = {'status': 'FAIL' if failures else 'PASS', 'scenes': scene_report, 'failures': failures}

    # V6 글꼴: 후보 표에 실제로 든 글자를 기준으로 계산합니다.
    failures, font_report = [], load(WORK / 'fonts/fonts_report.json')
    built = {f['name']: f for f in font_report['fonts']}
    korean_maps = {}
    for name, row in built.items():
        data = patched['entries'][f'korean_patch/{name}.fontdata']['data']
        ttf = (ROOT / row['path']).read_bytes()
        # 자원 파일은 압축되어 있을 수 있어, 엔진이 다시 연 결과(build 단계 보고)와 원본 TTF 지문으로 확인합니다.
        korean_maps[name] = set(TTFont(ROOT / row['path']).getBestCmap())
        if sha_bytes(ttf) != row['sha256']:
            failures.append({'font': name, 'problem': 'TTF 지문이 기록과 다름'})
        if sha_bytes(data) != load(WORK / build_id / 'build.json')['changes'][f'korean_patch/{name}.fontdata']['sha256']:
            failures.append({'font': name, 'problem': '후보 안 글꼴 자원이 빌드 기록과 다름'})
    actual_text = ''.join(s['message'] for s in slots) + ''.join(r['target'] for r in canonical['island_names']) + '한국어'
    required = sorted({c for c in actual_text if not c.isspace() and ord(c) >= 32})
    coverage = {}
    for base, korean in BASE_FONTS.items():
        base_map = set(TTFont(RECOVERED / base).getBestCmap())
        missing = [c for c in required if ord(c) not in base_map and ord(c) not in korean_maps[korean]]
        coverage[base] = {'fallback': korean, 'missing': missing}
        if missing:
            failures.append({'font': base, 'missing': ''.join(missing)})
    hangul = [c for c in required if '가' <= c <= '힣']
    if any(ord(c) not in korean_maps[n] for n in korean_maps for c in hangul):
        failures.append({'problem': '한글 글꼴에 없는 한글 음절'})
    checks['V6_fonts'] = {'status': 'FAIL' if failures else 'PASS', 'required_characters': len(required), 'hangul': len(hangul),
                          'coverage': {k: {'fallback': v['fallback'], 'missing_count': len(v['missing'])} for k, v in coverage.items()}, 'failures': failures}

    status = 'PASS' if all(c['status'] == 'PASS' for c in checks.values()) else 'FAIL'
    report = {'game_id': 'CLICKY_ISLANDS', 'baseline': 'steam_26701014', 'build_id': build_id, 'gate': 'G4', 'status': status,
              'started': started, 'ended': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'inputs': {'candidate_pck_sha256': sha(candidate / PCK_NAME), 'baseline_pck_sha256': sha(BASE / PCK_NAME),
                         'canonical_sha256': sha(WORK / 'translation/canonical.json'), 'validator_sha256': sha(Path(__file__))},
              'checks': checks}
    save(stage / 'validation_report.json', report)
    print(json.dumps({'status': status, **{k: (v['status'], {a: b for a, b in v.items() if a in ('matched', 'expected', 'changed', 'added', 'unchanged_identical', 'required_characters', 'failure_count')}) for k, v in checks.items()}}, ensure_ascii=False))
    for name, check in checks.items():
        if check['status'] != 'PASS':
            print(name, json.dumps(check['failures'], ensure_ascii=False)[:1500])
    sys.exit(0 if status == 'PASS' else 1)


if __name__ == '__main__':
    main()
