"""검토한 번역 원본에서 변경 파일과 위치별 기대값을 생성한다."""
import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def signature(text):
    # 색상 태그·자리표시자·입력 아이콘·숫자·제어 줄바꿈을 각자 대조한다.
    tags = re.findall(r'\[[^\]]*\]|\{[a-zA-Z_#][a-zA-Z0-9_#]*\}', text)
    stripped = re.sub(r'\[[^\]]*\]|\{[a-zA-Z_#][a-zA-Z0-9_#]*\}', '', text)
    return {'tags': tags, 'printf': re.findall(r'%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[sdif]|%%', text), 'numbers': re.findall(r'(?<![A-Za-z])\d[\d,]*(?:\.\d+)?%?', stripped), 'icons': re.findall(r';[A-Z0-9_]+;', text), 'newlines': re.findall(r'\r\n|\r|\n', text)}

def quote_value(value, quote):
    if len(quote) == 3:
        return quote + value.replace('\\', '\\\\').replace(quote, '\\' + quote) + quote
    return quote + value.replace('\\', '\\\\').replace(quote, '\\' + quote).replace('\t', '\\t').replace('\r', '\\r').replace('\n', '\\n') + quote

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory
    records = json.loads((directory / 'census.json').read_text(encoding='utf-8'))
    draft = json.loads((directory / 'draft_map.json').read_text(encoding='utf-8'))
    entries, failures, changes = [], [], defaultdict(list)
    table = dict(draft)
    for record in records:
        if record['classification'] not in ('VISIBLE_TRANSLATE', 'VISIBLE_KEEP'):
            continue
        entry = dict(record)
        korean = draft[record['source']] if record['classification'] == 'VISIBLE_TRANSLATE' else record['source']
        entry['korean'] = korean
        entry['expected_sha256'] = sha(korean.encode())
        entry['implementation'] = 'translation_table' if record['kind'] == 'locale' or record.get('translation_mode') == 'table_only' else 'literal'
        entry['review'] = 'PASS'
        entries.append(entry)
        if signature(record['source']) != signature(korean):
            failures.append({'id': record['id'], 'source': signature(record['source']), 'korean': signature(korean)})
        if not korean and record['source'].strip():
            failures.append({'id': record['id'], 'error': '번역 공백'})
        if record['classification'] == 'VISIBLE_TRANSLATE' and entry['implementation'] == 'literal':
            changes[record['file']].append(entry)
    original_csv = args.source / 'addons/maaacks_game_template/base/translations/menus_translations.csv'
    for row in csv.DictReader(io.StringIO(original_csv.read_text(encoding='utf-8-sig'), newline='')):
        table[row['key']] = draft.get(row['en'], row['en'])
    # 동적 표시의 생성 코드·소비 라벨을 개별 기록에 연결한다.
    runtime = []
    runtime_overrides_path = directory / 'runtime_overrides.json'
    runtime_overrides = json.loads(runtime_overrides_path.read_text(encoding='utf-8')) if runtime_overrides_path.exists() else {}
    def add_runtime(source, korean, producer, consumer, category='VISIBLE_TRANSLATE', detail='', namespace=''):
        translation_key = namespace + source
        korean = runtime_overrides.get(translation_key, korean)
        table[translation_key] = korean
        record = next((item for item in records if item['file'] == producer), None)
        runtime.append({'id': f'runtime::{producer}::{sha(translation_key.encode())[:20]}', 'source': source, 'source_sha256': sha(source.encode()), 'translation_key': translation_key, 'korean': korean, 'classification': category, 'producer': producer, 'consumer': consumer, 'original_asset': record['original_asset'] if record else None, 'original_asset_sha256': record['original_asset_sha256'] if record else None, 'evidence': detail, 'implementation': 'translation_table'})
    helper = 'addons/maaacks_game_template/base/nodes/utilities/input_helper.gd'
    input_consumers = ['addons/maaacks_game_template/base/nodes/menus/options_menu/input/input_actions_list.gd::_add_action_options/_update_assigned_inputs_and_button/Button.text', 'addons/maaacks_game_template/base/nodes/menus/options_menu/input/input_actions_tree.gd::_add_action_inputs/TreeItem.set_text', 'addons/maaacks_game_template/base/nodes/menus/options_menu/input/key_assignment_window.gd::_record_input_event/InputLabel.text']
    input_words = {
        'Keyboard': '키보드', 'Mouse': '마우스', 'Generic': '일반', 'Left Stick': '왼쪽 스틱', 'Right Stick': '오른쪽 스틱', 'Dpad': '방향 패드', 'None': '없음', 'Left': '왼쪽', 'Right': '오른쪽', 'Middle': '가운데', 'Scroll Up': '위로 스크롤', 'Scroll Down': '아래로 스크롤', 'Wheel Left': '왼쪽 스크롤', 'Wheel Right': '오른쪽 스크롤', 'Trigger A': '트리거 A', 'Trigger B': '트리거 B', 'Trigger C': '트리거 C', 'Left Stick Press': '왼쪽 스틱 누르기', 'Right Stick Press': '오른쪽 스틱 누르기', 'Left Shoulder': '왼쪽 어깨 버튼', 'Right Shoulder': '오른쪽 어깨 버튼', 'Up': '위', 'Down': '아래', 'View': '보기', 'Home': '홈', 'Menu': '메뉴', 'Share': '공유', 'Minus': '빼기', 'Plus': '더하기', 'Capture': '캡처', 'Cross': '십자', 'Circle': '원', 'Square': '사각형', 'Triangle': '삼각형', 'Select': '선택', 'Options': '설정', 'Microphone': '마이크', 'Button A': 'A 버튼', 'Button B': 'B 버튼', 'Button X': 'X 버튼', 'Button Y': 'Y 버튼', 'Button Start': '시작 버튼', 'Button Guide': '가이드 버튼', 'Button Back': '뒤로 버튼', 'Misc': '기타 버튼', 'Left Trigger': '왼쪽 트리거', 'Right Trigger': '오른쪽 트리거', 'Left Mouse Button': '마우스 왼쪽 버튼', 'Right Mouse Button': '마우스 오른쪽 버튼', 'Middle Mouse Button': '마우스 가운데 버튼', 'Wheel Up Mouse Button': '마우스 위로 스크롤', 'Wheel Down Mouse Button': '마우스 아래로 스크롤', 'Wheel Left Mouse Button': '마우스 왼쪽 스크롤', 'Wheel Right Mouse Button': '마우스 오른쪽 스크롤', 'Mouse Button 8': '마우스 8번 버튼', 'Mouse Button 9': '마우스 9번 버튼', 'Mouse Button #8': '마우스 8번 버튼', 'Mouse Button #9': '마우스 9번 버튼'
    }
    for key in list(input_words):
        if key.startswith('Wheel ') and key.endswith(' Mouse Button') or key.startswith('Mouse Button '):
            del input_words[key]
    input_words.update({'Mouse Wheel Up': '마우스 위로 스크롤', 'Mouse Wheel Down': '마우스 아래로 스크롤', 'Mouse Wheel Left': '마우스 왼쪽 스크롤', 'Mouse Wheel Right': '마우스 오른쪽 스크롤', 'Mouse Thumb Button 1': '마우스 보조 버튼 1', 'Mouse Thumb Button 2': '마우스 보조 버튼 2'})
    input_dump = json.loads((directory / 'original_input_dump.json').read_text(encoding='utf-8'))
    observed_inputs = {row['get_text'] for row in input_dump['rows'] if row.get('get_text') and row['kind'] != 'key'}
    input_words = {source: korean for source, korean in input_words.items() if source in observed_inputs}
    for source, korean in input_words.items():
        add_runtime(source, korean, helper, input_consumers, detail='InputEventHelper.get_text와 실제 엔진 입력 덤프의 입력명 출력; 아이콘 조회에 쓰는 원래 키를 보존하고 표시 객체에서만 번역', namespace='INPUT_DISPLAY::')
    for stem, target in [('Left Stick', '왼쪽 스틱'), ('Right Stick', '오른쪽 스틱'), ('Dpad', '방향 패드')]:
        for direction, korean in [('Up', '위'), ('Down', '아래'), ('Left', '왼쪽'), ('Right', '오른쪽')]:
            add_runtime(stem + ' ' + direction, target + ' ' + korean, helper, input_consumers, detail='입력 축의 양수/음수 방향 조합 출력', namespace='INPUT_DISPLAY::')
    probe = json.loads((directory / 'independent_runtime_probe/dynamic_values.json').read_text(encoding='utf-8'))
    for source in sorted(set(probe['keycode_text'].values()) - {'Left', 'Right', 'Up', 'Down'}):
        add_runtime(source, source, helper, input_consumers, category='VISIBLE_KEEP', detail='실제 키에 인쇄된 표준 표기와 조합키를 유지한다. 전용 입력 문맥키로 Home/Menu 액션 의미와 구분한다.', namespace='INPUT_DISPLAY::')
    for record in records:
        if record['file'] == helper and record.get('translation_mode') == 'table_only':
            add_runtime(record['source'], draft[record['source']], helper, input_consumers, detail='내장 입력 액션 표시값')
    action_names = {
        'Ability 1': '수확 주문', 'Ability 2': '공격 주문', 'Interact': '상호작용', 'Inventory Toggle': '가방 열기 / 닫기', 'Close Menus': '메뉴 닫기', 'Jump': '구르기', 'Move Left': '왼쪽으로 이동', 'Move Right': '오른쪽으로 이동', 'Move Up': '위로 이동', 'Move Down': '아래로 이동', 'Show Stats': '능력치 보기', 'Camera Move': '화면 이동', 'Camera Zoom In': '화면 확대', 'Camera Zoom Out': '화면 축소', 'Camera Zoom Reset': '화면 배율 초기화', 'Camera Pan Left': '화면 왼쪽 이동', 'Camera Pan Right': '화면 오른쪽 이동', 'Camera Pan Up': '화면 위쪽 이동', 'Camera Pan Down': '화면 아래쪽 이동'
    }
    action_names['Ability 1'] = '수확 주문 1'
    action_names['Ability 2'] = '공격 주문 2'
    action_names.update({'Ui Accept': '확인', 'Ui Select': '선택', 'Ui Left': '왼쪽 (메뉴)', 'Ui Right': '오른쪽 (메뉴)', 'Ui Up': '위 (메뉴)', 'Ui Down': '아래 (메뉴)', 'Ui Colorpicker Delete Preset': '색상 선택 사전 설정 삭제'})
    for source, korean in action_names.items():
        add_runtime(source, korean, 'project.godot', input_consumers, detail='InputMap 액션 식별자를 capitalize한 대체 표시 이름; 입력 키는 원문 유지')
    level_names = {'The Village': '마을', 'The Forest': '숲', 'The Forest Ii': '숲 난이도 II', 'The Forest Iii': '숲 난이도 III', 'Level 1': '스테이지 1', 'Level 2': '스테이지 2', 'Level 3': '스테이지 3'}
    for source, korean in level_names.items():
        add_runtime(source, korean, 'game/scenes/menus/level_select_menu/level_select_menu.gd', ['add_levels_to_container/LevelButtonsContainer.add_item'], detail='저장 상태의 게임 장면 파일 이름에서 확장자 제거·밑줄 치환·capitalize한 레벨 선택 항목; 실제 파일 경로 보존')
    for source in ['Master :', 'Music :', 'SFX :']:
        add_runtime(source, draft[source], 'default_bus_layout.tres', ['addons/maaacks_game_template/base/nodes/menus/options_menu/audio/audio_options_menu.gd::_ready', 'addons/maaacks_game_template/base/nodes/menus/options_menu/option_control/option_control.gd::option_name/OptionLabel.text'], detail='오디오 버스 이름과 label_suffix를 합친 음량 항목; 음향 버스 조회 키 보존')
    engine_draft_path = directory / 'engine_ui_draft.json'
    if engine_draft_path.exists():
        engine_draft = json.loads(engine_draft_path.read_text(encoding='utf-8'))
        engine_rows = json.loads((directory / 'independent_runtime_probe/color_picker_values.json').read_text(encoding='utf-8'))
        for source, korean in engine_draft.items():
            consumers = [row['path'] + '::' + row['field'] for row in engine_rows if row['value'] == source]
            add_runtime(source, korean, 'game/scenes/game_scene/levels/old_levels/level.gd', consumers, detail='예비 레벨 ColorPickerButton의 엔진 내부 표시; 일반 Translation을 무시함을 시험했고 최종 Control 속성·PopupMenu 항목에 명시 연결. 원본 엔진 4.8.dev 조사값은 후보 4.7.2에서 재확인 필요.', namespace='ENGINE_UI::')
    for record in runtime:
        if signature(record['source'])['numbers'] != signature(record['korean'])['numbers']:
            failures.append({'id': record['id'], 'error': '조합 문구 숫자 변경'})
    if failures:
        write_json(directory / 'translation_control_check.json', {'status': 'FAIL', 'failures': failures})
        raise SystemExit(f'번역 제어 정보 불일치 {len(failures)}건')
    modified = directory / 'modified'
    manifest = []
    for file, file_entries in changes.items():
        data = (args.source / file).read_bytes()
        if sha(data) != file_entries[0]['file_sha256']:
            raise SystemExit(f'원본 지문 변경: {file}')
        text = data.decode('utf-8-sig')
        for entry in sorted(file_entries, key=lambda item: item['start'], reverse=True):
            text = text[:entry['start']] + quote_value(entry['korean'], entry['quote']) + text[entry['end']:]
        target = modified / file
        target.parent.mkdir(parents=True, exist_ok=True)
        result = (b'\xef\xbb\xbf' if data.startswith(b'\xef\xbb\xbf') else b'') + text.encode()
        target.write_bytes(result)
        manifest.append({'file': file, 'original_asset': file_entries[0]['original_asset'], 'original_asset_sha256': file_entries[0]['original_asset_sha256'], 'source_sha256': sha(data), 'modified_sha256': sha(result), 'changed_positions': [entry['id'] for entry in file_entries], 'mode': 'literal', 'settings_keys': ['application/config/description'] if file == 'project.godot' else []})
    # 입력 비교·아이콘 키는 원문을 유지하고, 마지막 표시 단계에만 번역을 연결한다.
    input_root = 'addons/maaacks_game_template/base/nodes/menus/options_menu/input/'
    code_changes = {
        input_root + 'input_actions_list.gd': [
            ('_update_assigned_inputs_and_button', 'button.text = new_readable_input_name', 'button.text = InputEventHelper.localize_display_text(new_readable_input_name)'),
            ('_add_new_button', 'new_button.text = content', 'new_button.text = InputEventHelper.localize_display_text(content)'),
            ('_add_action_options', 'new_action_box.get_child(0).text = readable_action_name', 'new_action_box.get_child(0).text = tr(readable_action_name)')],
        input_root + 'input_actions_tree.gd': [
            ('_add_input_event_as_tree_item', 'input_tree_item.set_text(0, InputEventHelper.get_text(input_event))', 'input_tree_item.set_text(0, InputEventHelper.localize_display_text(InputEventHelper.get_text(input_event)))'),
            ('_add_action_as_tree_item', 'action_tree_item.set_text(0, readable_name)', 'action_tree_item.set_text(0, tr(readable_name))')],
        input_root + 'key_assignment_window.gd': [
            ('_record_input_event', '%InputLabel.text = last_input_text', '%InputLabel.text = InputEventHelper.localize_display_text(last_input_text)'),
            ('_on_visibility_changed', '%InputLabel.text = text', '%InputLabel.text = InputEventHelper.localize_display_text(text)')],
        input_root + 'input_options_menu.gd': [
            ('_open_key_assignment_window/_on_input_actions_tree_remove_button_clicked', '.format({action = action_name})', '.format({action = tr(action_name)})'),
            ('_on_input_actions_tree_remove_button_clicked/_popup_already_assigned', '.format({key = input_name, action = action_name})', '.format({key = InputEventHelper.localize_display_text(input_name), action = tr(action_name)})'),
            ('_popup_minimum_reached', 'ONE_INPUT_MINIMUM_TEXT % action_name', 'tr(ONE_INPUT_MINIMUM_TEXT) % tr(action_name)')],
        'game/scenes/menus/level_select_menu/level_select_menu.gd': [('add_levels_to_container', 'level_buttons_container.add_item(button_name)', 'level_buttons_container.add_item(tr(button_name))')],
        'addons/maaacks_game_template/base/nodes/autoloads/app_config/app_config.gd': [('_ready', 'func _ready() -> void :\n', 'func _ready() -> void :\n\tTranslationServer.set_locale("en")\n')]
    }
    display_function = '''

# 입력 식별자는 유지하고 화면에 표시하는 이름만 한국어로 바꾼다.
static func localize_display_text(value: String) -> String:
\tvar display_key: String = "INPUT_DISPLAY::" + value
\tvar translated: String = TranslationServer.translate(display_key)
\tif translated != display_key:
\t\treturn translated
\tvar parts: PackedStringArray = value.split("+")
\tfor index in range(parts.size()):
\t\tvar part_key: String = "INPUT_DISPLAY::" + parts[index]
\t\tvar part_translated: String = TranslationServer.translate(part_key)
\t\tif part_translated != part_key:
\t\t\tparts[index] = part_translated
\treturn "+".join(parts)
'''
    code_changes[helper] = [('localize_display_text', '', display_function)]
    if engine_draft_path.exists():
        engine_function = '''

# 엔진이 생성한 도움말과 색 선택 문구를 표시할 때만 번역한다.
static func localize_engine_text(value: String) -> String:
\tvar display_key: String = "ENGINE_UI::" + value
\tvar translated: String = TranslationServer.translate(display_key)
\treturn value if translated == display_key else translated

static func localize_control_tree(node: Node) -> void:
\tif node is Control:
\t\tvar tooltip: String = localize_engine_text(node.tooltip_text)
\t\tif tooltip != node.tooltip_text:
\t\t\tnode.tooltip_text = tooltip
\tif node is Label or node is Button or node is LinkButton:
\t\tvar caption: String = localize_engine_text(node.text)
\t\tif caption != node.text:
\t\t\tnode.text = caption
\tif node is Window:
\t\tvar title: String = localize_engine_text(node.title)
\t\tif title != node.title:
\t\t\tnode.title = title
\tif node is LineEdit or node is TextEdit:
\t\tvar placeholder: String = localize_engine_text(node.placeholder_text)
\t\tif placeholder != node.placeholder_text:
\t\t\tnode.placeholder_text = placeholder
\tif node is PopupMenu or node is OptionButton:
\t\tfor index in range(node.get_item_count()):
\t\t\tvar caption: String = localize_engine_text(node.get_item_text(index))
\t\t\tif caption != node.get_item_text(index):
\t\t\t\tnode.set_item_text(index, caption)
\t\t\tvar tooltip: String = localize_engine_text(node.get_item_tooltip(index))
\t\t\tif tooltip != node.get_item_tooltip(index):
\t\t\t\tnode.set_item_tooltip(index, tooltip)
\tfor child in node.get_children(true):
\t\tlocalize_control_tree(child)
'''
        code_changes[helper].append(('localize_engine_text/localize_control_tree', '', engine_function))
        level = 'game/scenes/game_scene/levels/old_levels/level.gd'
        code_changes[level] = [('_process', '', '''

# 색상 모드가 바뀌면 엔진이 문구를 다시 생성하므로 열린 동안 표시를 갱신한다.
func _process(_delta: float) -> void:
\tvar picker: ColorPicker = %ColorPickerButton.get_picker()
\tif picker.is_visible_in_tree():
\t\tInputEventHelper.localize_control_tree(picker)
''')]
        code_changes['game/scenes/game_scene/input_display_label.gd'] = [('_get_inputs_as_string', 'all_inputs += action_name', 'all_inputs += tr(action_name.capitalize())'), ('_get_inputs_as_string', 'all_inputs += " + " + action_name', 'all_inputs += " + " + tr(action_name.capitalize())')]
    typography_path = directory / 'typography.json'
    if typography_path.exists():
        typography = json.loads(typography_path.read_text(encoding='utf-8'))
        for file in typography['consumers']:
            # 공유 pause 스크립트의 예비 창에는 부제가 없어 존재 여부를 확인한다.
            addition = '''\n\tvar subtitle_label: Label = get_node_or_null("MenuContainer/SubTitleMargin/SubTitleContainer/SubTitleLabel")
\tif subtitle_label != null:
\t\tvar subtitle_font: FontFile = FontFile.new()
\t\tsubtitle_font.data = FileAccess.get_file_as_bytes("res://korean_patch/fonts/TitlePixel.ttf")
\t\tsubtitle_font.antialiasing = TextServer.FONT_ANTIALIASING_NONE
\t\tsubtitle_label.add_theme_font_override("font", subtitle_font)
\t\tsubtitle_label.add_theme_color_override("font_color", Color("#fff0c2"))
\t\tsubtitle_label.add_theme_color_override("font_outline_color", Color("#252038"))
\t\tsubtitle_label.add_theme_constant_override("outline_size", 1)
'''
            code_changes.setdefault(file, []).append(('_ready', 'func _ready() -> void :\n', 'func _ready() -> void :\n' + addition))
    for file, replacements in code_changes.items():
        original = (args.source / file).read_bytes()
        path = modified / file
        data = path.read_bytes() if file in changes else original
        source_text = data.decode('utf-8-sig').replace('\r\n', '\n')
        approved_changes = []
        for method, before, after in replacements:
            count = source_text.count(before) if before else 1
            if before and count not in (1, 2):
                raise SystemExit(f'표시 연결 위치 수 불일치 {file}::{method}: {count}')
            source_text = source_text.replace(before, after) if before else source_text.rstrip() + after
            reason = '부제 Label 한 곳에 전용 픽셀 글꼴·색·테두리 적용; 기존 글자 크기 12 유지' if typography_path.exists() and file in typography['consumers'] else '최종 표시 번역 연결; 원래 식별자·저장·입력 비교·아이콘 조회 유지'
            approved_changes.append({'method': method, 'before': before, 'after': after, 'count': count, 'reason': reason})
        result = (b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b'') + source_text.encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result)
        item = next((item for item in manifest if item['file'] == file), None)
        if item is None:
            record = next(record for record in records if record['file'] == file)
            item = {'file': file, 'original_asset': record['original_asset'], 'original_asset_sha256': record['original_asset_sha256'], 'source_sha256': sha(original), 'changed_positions': [], 'settings_keys': []}
            manifest.append(item)
        item.update({'modified_sha256': sha(result), 'mode': 'literal_and_display_connection', 'code_changes': approved_changes})
    write_json(directory / 'translation.json', {'game_id': 'MR_MAGEBOY_DEMO', 'build_id': 'steam_25734075', 'entries': entries, 'runtime_entries': runtime})
    write_json(directory / 'modified_manifest.json', manifest)
    write_json(directory / 'translation_table.json', table)
    original_keys = {row['key'] for row in csv.DictReader(io.StringIO(original_csv.read_text(encoding='utf-8-sig'), newline=''))}
    write_json(directory / 'translation_table_additions.json', {key: value for key, value in table.items() if key not in original_keys})
    write_json(directory / 'runtime_manifest.json', runtime)
    write_json(directory / 'translation_control_check.json', {'status': 'PASS', 'positions': len(entries), 'runtime_positions': len(runtime), 'tag_order_nested_signature': '동일', 'printf': '동일', 'numbers': '동일', 'icons': '동일', 'newlines': '동일', 'failures': []})
    write_json(directory / 'required_characters.json', {'characters': ''.join(sorted(set(''.join(entry['korean'] for entry in entries) + ''.join(table.values())))), 'count': len(set(''.join(entry['korean'] for entry in entries) + ''.join(table.values())))})
    write_json(directory / 'translation_summary.json', {'translated_positions': sum(x['classification'] == 'VISIBLE_TRANSLATE' for x in entries), 'keep_positions': sum(x['classification'] == 'VISIBLE_KEEP' for x in entries), 'runtime_positions': len(runtime), 'files_modified': len(manifest), 'table_entries': len(table), 'status': 'PASS'})
    print(json.dumps({'modified_files': len(manifest), 'positions': len(entries), 'runtime': len(runtime), 'table': len(table)}))

if __name__ == '__main__':
    main()
