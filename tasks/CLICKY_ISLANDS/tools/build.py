"""번역 원본으로 후보 PCK를 만듭니다. 원본 항목은 그대로 두고 바꿀 항목만 끝에 덧붙입니다.

사용: python build.py <build_id> <번역 파일(JSON)>
번역 파일: {"slots": {"칸": "번역"}, "direct": {"영어 직접 문구": "번역"}, "island_names": [...]}
  - slots에 없는 칸은 비워 둡니다(게임이 영어로 대신 표시).
바꾸는 것(허용 변경 경계):
  1. locale/locale.kr.translation            한국어 언어표(원본은 빈 칸)
  2. korean_patch/NotoSansKR-*.fontdata       한글 글꼴 2개(새 파일)
  3. font_locale_resolver.gdc                 kr 언어에 한글 글꼴 연결
  4. locale_game_settings_resolver.gdc        Windows가 한국어면 kr 자동 선택
  5. island_naming_ui.gdc                     무작위 섬 이름의 한국어 목록(island_names가 있을 때만)
  6. language_modal.scn, settings_window_ui.scn  "한국어" 버튼
"""
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (ROOT, BASE, EXTRACTED, RECOVERED, PACK, WORK, CANDIDATE, PCK_NAME, save, load, sha,
                    sha_bytes, sha_text, run_gdre)
from pck_tools import patch_pack
import optimized_translation as ot

TOOLS = Path(__file__).parent
BYTECODE = '4.5.0'
FONT_DIR = 'korean_patch'
FONTS = {'NotoSansKR-Regular': FONT_DIR + '/NotoSansKR-Regular.fontdata', 'NotoSansKR-Bold': FONT_DIR + '/NotoSansKR-Bold.fontdata'}
# 값은 (복사할 본보기 버튼, 그 뒤에 끼워 넣을 버튼)입니다. 설정 창은 줄 수가 늘지 않도록 마지막 버튼 뒤에 넣습니다
# (2026-11-19 검수: 번체 버튼 뒤에 넣으면 한 줄이 늘어 아래 안내 문구가 가려짐).
SCENES = {'ui/language_modal/language_modal.tscn': ('LanguageButton5', 'LanguageButton5'),
          'ui/settings_window_ui/settings_window_ui.tscn': ('LanguageButton5', 'LanguageButton8')}
KOREAN_BUTTON = 'LanguageButtonKorean'


def comparable(text):
    """주석·공백을 뺀 토큰 열. 다시 풀어 본 스크립트가 넣은 소스와 같은지 비교할 때 씁니다."""
    return [t for t in re.findall(r'""".*?"""|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|#[^\n]*|[^\s]', text, re.S) if not t.startswith('#')]


def replace_once(text, before, after, label):
    if text.count(before) != 1:
        raise ValueError(f'고칠 위치가 정확히 한 곳이 아닙니다: {label} ({text.count(before)}곳)')
    return text.replace(before, after)


def script_changes(island_names):
    """(파일, 고친 소스, 변경 설명) 목록. 문자열 리터럴 삽입만 하며 기존 줄은 지우지 않습니다."""
    changes = []
    path = 'globals/font_locale_resolver/font_locale_resolver.gd'
    text = (RECOVERED / path).read_text(encoding='utf-8')
    anchor = '@onready var fonts: Dictionary = {\n'
    added = ('\t"kr": {\n\t\t"regular": preload("res://%s"), \n\t\t"bold": preload("res://%s"), \n\t}, \n'
             % (FONTS['NotoSansKR-Regular'], FONTS['NotoSansKR-Bold']))
    changes.append((path, replace_once(text, anchor, anchor + added, path), 'kr 언어에 한글 글꼴(보통·굵게) 대체 글꼴 연결'))
    path = 'globals/game_settings/resolvers/locale_game_settings_resolver.gd'
    text = (RECOVERED / path).read_text(encoding='utf-8')
    anchor = '\tif loaded_locales.has(language):\n'
    added = '\tif language == "ko" and loaded_locales.has("kr"):\n\t\treturn "kr"\n\n'
    changes.append((path, replace_once(text, anchor, added + anchor, path), '운영체제 언어가 한국어(ko)이면 게임의 kr 칸을 자동 선택'))
    if island_names:
        path = 'ui/island_naming_ui/island_naming_ui.gd'
        text = (RECOVERED / path).read_text(encoding='utf-8')
        anchor = '\t\t\t"en": [\n'
        if any('"' in name or '\\' in name or len(name) > 16 for name in island_names):
            raise ValueError('섬 이름은 16자 이하이고 따옴표가 없어야 합니다.')
        rows = [island_names[i:i + 5] for i in range(0, len(island_names), 5)]
        body = ', \n'.join('\t\t\t\t' + ', '.join(json.dumps(n, ensure_ascii=False) for n in row) for row in rows)
        added = '\t\t\t"kr": [\n' + body + '\n\t\t\t], \n'
        changes.append((path, replace_once(text, anchor, added + anchor, path), '무작위 섬 이름의 한국어 목록 추가(영어 목록은 그대로)'))
    return changes


def scene_changes():
    """언어 선택 장면 두 곳에 '한국어' 버튼을 넣습니다. 번체 중국어 버튼 묶음을 복사해 네 값만 바꿉니다."""
    result = {}
    for path, (after_node, insert_after) in SCENES.items():
        text = (RECOVERED / path).read_text(encoding='utf-8')
        fonts = re.findall(r'\[ext_resource type="FontFile"[^\n]*NotoSansTC-Bold\.ttf" id="([^"]+)"\]\n', text)
        if len(fonts) != 1:
            raise ValueError('번체 글꼴 참조를 찾지 못했습니다: ' + path)
        new_id = 'korean_bold'
        declaration = re.search(r'\[ext_resource type="FontFile"[^\n]*NotoSansTC-Bold\.ttf" id="[^"]+"\]\n', text)[0]
        text = replace_once(text, declaration, declaration + '[ext_resource type="FontFile" path="res://%s" id="%s"]\n' % (FONTS['NotoSansKR-Bold'], new_id), path)
        block = re.search(r'\[node name="%s" [^\n]*\n(?:[^\n\[][^\n]*\n)+' % after_node, text)
        if not block:
            raise ValueError('기준 버튼을 찾지 못했습니다: ' + path)
        copy = block[0]
        copy = replace_once(copy, 'name="%s"' % after_node, 'name="%s"' % KOREAN_BUTTON, path)
        copy = replace_once(copy, 'ExtResource("%s")' % fonts[0], 'ExtResource("%s")' % new_id, path)
        copy = replace_once(copy, 'text = "繁體中文"', 'text = "한국어"', path)
        copy = replace_once(copy, 'locale = "zh_Hant"', 'locale = "kr"', path)
        anchor = re.search(r'\[node name="%s" [^\n]*\n(?:[^\n\[][^\n]*\n)+' % insert_after, text)
        if not anchor:
            raise ValueError('끼워 넣을 위치를 찾지 못했습니다: ' + path)
        text = replace_once(text, anchor[0], anchor[0] + '\n' + copy, path)
        result[path] = text
    return result


def original_scene(path):
    remap = (PACK / (path + '.remap')).read_text(encoding='utf-8')
    return re.search(r'path="res://([^"]+)"', remap)[1]


def main():
    build_id, translation_path = sys.argv[1], Path(sys.argv[2])
    stage = WORK / build_id
    candidate = CANDIDATE / build_id
    if candidate.exists():
        raise SystemExit('같은 ID의 후보가 이미 있습니다. 덮어쓰지 않습니다: ' + str(candidate))
    stage.mkdir(parents=True, exist_ok=True)
    translation = load(translation_path)
    inventory = load(WORK / 'census/locale_inventory.json')
    changes = {}

    # 1. 언어표: 원본 영어 표와 같은 칸 구조에 한국어를 넣고, 직접 문구는 영어 문구 자체를 키로 추가합니다.
    slots = translation.get('slots', {})
    unknown = set(slots) - {r['slot'] for r in inventory}
    if unknown:
        raise ValueError('없는 칸의 번역이 있습니다: ' + ', '.join(sorted(unknown)[:5]))
    entries = [{'table_index': r['table_index'], 'seed': r['seed'], 'key_hash': r['key_hash'], 'slot': r['slot'],
                'key': r['key'], 'text': slots.get(r['slot'], '')} for r in inventory]
    index = ot.index_slots(entries)
    for key, text in translation.get('direct', {}).items():
        if ot.find(index, 1543, key) is not None:
            raise ValueError('직접 문구가 기존 칸과 겹칩니다: ' + key)
        ot.add_key(entries, 1543, key, text)
    hash_table, bucket_table, strings = ot.build(1543, entries)
    expect_by_key = {e['key']: e['text'] for e in entries if e.get('key') and e['text']}

    # 2. 스크립트: 고친 소스를 원본과 같은 바이트코드로 만들고, 다시 풀어 넣은 소스와 같은지 확인합니다.
    scripts = script_changes(translation.get('island_names'))
    code_report = []
    for number, (path, text, reason) in enumerate(scripts):
        source = stage / 'scripts' / str(number) / Path(path).name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(text, encoding='utf-8', newline='\n')
        compiled, recovered = stage / 'compiled' / str(number), stage / 'decompiled' / str(number)
        compiled.mkdir(parents=True, exist_ok=True)
        recovered.mkdir(parents=True, exist_ok=True)
        run_gdre(['--compile=' + str(source), '--bytecode=' + BYTECODE, '--output=' + str(compiled)], f'{build_id}_compile_{number}')
        binary = compiled / (Path(path).stem + '.gdc')
        run_gdre(['--decompile=' + str(binary), '--bytecode=' + BYTECODE, '--output=' + str(recovered)], f'{build_id}_decompile_{number}')
        if comparable(text) != comparable((recovered / Path(path).name).read_text(encoding='utf-8')):
            raise ValueError('다시 푼 스크립트가 넣은 소스와 다릅니다: ' + path)
        target = path[:-3] + '.gdc'
        changes[target] = binary.read_bytes()
        code_report.append({'file': path, 'target': target, 'reason': reason, 'source_sha256': sha_text(text),
                            'original_recovered_sha256': sha(RECOVERED / path), 'compiled_sha256': sha(binary)})

    # 3. 장면·글꼴·언어표를 GDRE(Godot 엔진 포함 도구)로 원본과 같은 형식의 자원으로 만듭니다.
    scene_config, scene_report = [], []
    for path, text in scene_changes().items():
        source = stage / 'scenes' / Path(path).name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(text, encoding='utf-8', newline='\n')
        target = original_scene(path)
        output = stage / 'scenes' / Path(target).name
        scene_config.append({'source': str(source), 'original': 'res://' + target, 'output': str(output),
                             'roundtrip': str(stage / 'scenes' / (Path(path).stem + '.roundtrip.tscn')), 'target': target, 'path': path})
    font_report = load(WORK / 'fonts/fonts_report.json')
    characters = sorted({c for text in list(slots.values()) + list(translation.get('direct', {}).values()) + list(translation.get('island_names', []) or []) + ['한국어']
                         for c in text if ord(c) >= 0x1100 and not c.isspace()})
    config = {'font_template': 'res://assets/fonts/noto_sans/NotoSansJP-Regular.ttf',
              'font_template_file': 'res://.godot/imported/NotoSansJP-Regular.ttf-6e8d4fdf4bd3ee5cfe30b4c662a5d126.fontdata',
              'fonts': [{'source': str(ROOT / f['path']), 'path': FONTS[f['name']], 'output': str(stage / 'resources' / Path(FONTS[f['name']]).name)} for f in font_report['fonts']],
              'characters': characters,
              'translation': {'original': 'res://locale/locale.kr.translation', 'output': str(stage / 'resources/locale.kr.translation'),
                              'hash_table': ot.signed(hash_table), 'bucket_table': ot.signed(bucket_table), 'strings_hex': strings.hex(),
                              'expect_by_key': expect_by_key},
              'scenes': scene_config, 'report': str(stage / 'resource_report.json')}
    (stage / 'resources').mkdir(parents=True, exist_ok=True)
    save(stage / 'resource_config.json', config)
    run_gdre(['--path', WORK / 'tool_runtime', '--script', TOOLS / 'build_resources.gd', '--', BASE / PCK_NAME, stage / 'resource_config.json'], f'{build_id}_resources')
    report = load(stage / 'resource_report.json')
    # 엔진이 다시 연 결과로 확인합니다(빌드 도구 자체의 성공 표시는 근거로 쓰지 않음).
    ordered = []
    for position in sorted({e['table_index'] for e in entries}):
        ordered += [e['text'] for e in entries if e['table_index'] == position]
    if report['translation']['messages'] != ordered or report['translation']['key_failures']:
        raise ValueError('다시 연 언어표가 기대와 다릅니다.')
    for font in report['fonts']:
        if font['missing_from_this_font'] or not font['data_matches_source'] or font['output_info']['ver_minor'] != 5:
            raise ValueError('글꼴 자원 검사 실패: ' + font['path'])
    if report['translation']['output_info']['ver_minor'] != 5 or report['translation']['class'] != 'OptimizedTranslation':
        raise ValueError('언어표 형식이 원본과 다릅니다.')
    changes['locale/locale.kr.translation'] = (stage / 'resources/locale.kr.translation').read_bytes()
    for font in config['fonts']:
        changes[font['path']] = Path(font['output']).read_bytes()
    for scene, row in zip(scene_config, report['scenes']):
        if row['error'] != 0 or row['output_info']['ver_minor'] != 5 or row['output_info']['ver_format'] != row['original_info']['ver_format']:
            raise ValueError('장면 변환 실패: ' + scene['path'])
        changes[scene['target']] = Path(scene['output']).read_bytes()
        scene_report.append({'file': scene['path'], 'target': scene['target'], 'edited_sha256': sha(scene['source']), 'output_sha256': sha(scene['output'])})

    # 4. 후보 폴더: PCK만 새로 만들고 나머지 3개 파일은 원본 그대로 복사합니다.
    candidate.mkdir(parents=True)
    for source in BASE.iterdir():
        if source.name != PCK_NAME:
            shutil.copy2(source, candidate / source.name)
    pack_report = patch_pack(BASE / PCK_NAME, candidate / PCK_NAME, changes)
    build = {'game_id': 'CLICKY_ISLANDS', 'baseline': 'steam_26701014', 'build_id': build_id, 'status': 'BUILT', 'qa': 'NOT_RUN',
             'translation_file': translation_path.as_posix(), 'translation_sha256': sha(translation_path),
             'slots_translated': sum(1 for e in entries if e.get('slot') and e['text']), 'slots_total': len(inventory),
             'direct_keys': len(translation.get('direct', {})), 'island_names': len(translation.get('island_names') or []),
             'korean_characters': len(characters), 'candidate': candidate.relative_to(ROOT).as_posix(),
             'files': {p.name: {'size': p.stat().st_size, 'sha256': sha(p)} for p in sorted(candidate.iterdir())},
             'changes': {name: {'size': len(data), 'sha256': sha_bytes(data), 'new': name.startswith(FONT_DIR)} for name, data in changes.items()},
             'scripts': code_report, 'scenes': scene_report, 'pack': pack_report,
             'tool_sha256': {p.name: sha(p) for p in sorted(TOOLS.glob('*')) if p.is_file()}}
    save(stage / 'build.json', build)
    print(json.dumps({'candidate': build['candidate'], 'pck_sha256': build['files'][PCK_NAME]['sha256'], 'changes': list(changes),
                      'slots_translated': build['slots_translated'], 'direct_keys': build['direct_keys']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
