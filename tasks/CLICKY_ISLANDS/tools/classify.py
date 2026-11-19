"""census.py가 UNKNOWN으로 남긴 문자열에 근거가 있는 판정을 붙입니다(G2).

규칙으로 확정하지 못한 항목은 UNKNOWN으로 남기고 review.json에 모읍니다.
사람이 확인한 판정은 manual_decisions.json(값 또는 위치 → 판정·근거)에서 읽습니다.
"""
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import RECOVERED, WORK, save, load

OUT = WORK / 'census'
EDITOR_ADDONS = ('addons/resources_spreadsheet_view/', 'addons/brackeys_particle_controls/')
DISPLAY_FIELDS = {'text', 'tooltip_text', 'placeholder_text', 'title', 'ok_button_text', 'cancel_button_text', 'dialog_text',
                  'description', 'plural_name', 'goal_text', 'stage_name', 'stage_description', 'print_value',
                  'default_text', 'default_text_ml'}
API_ARG = re.compile(r'(get_node|get_node_or_null|has_node|find_child|is_action\w*|get_action\w*|set_meta|get_meta|has_meta|remove_meta|tween_property|tween_method|has_method|call|call_deferred|callv|connect|disconnect|emit_signal|has_signal|set_shader_parameter|get_shader_parameter|set_instance_shader_parameter|add_to_group|is_in_group|get_nodes_in_group|get_first_node_in_group|get_setting|set_setting|has_feature|play|travel|has_animation|get_animation|set_value|get_value|has_section_key|get_theme_\w+|add_theme_\w+_override|remove_theme_\w+_override|has_theme_\w+|get_indexed|set_indexed|set|get|Input\.\w+|InputMap\.\w+|preload|load|get_bus_index|set_deferred|has|erase|get_or_add|add_command|add_user_signal|begins_with|ends_with|trim_prefix|trim_suffix|replace|split|join|find|contains)\(\s*$')


def field_of(record):
    match = re.match(r'^([A-Za-z_0-9/\.]+)\s*=', record['prefix'])
    return match[1] if match else None


def has_letters(value):
    return bool(re.search(r'[A-Za-zÀ-ɏ぀-鿿]', re.sub(r'\[[^\]]*\]', '', value)))


def scene_index():
    """장면마다 노드 이름·고유 이름 여부·붙은 스크립트를 모읍니다."""
    cache = {}

    def load_scene(path):
        if path in cache:
            return cache[path]
        text = (RECOVERED / path).read_text(encoding='utf-8-sig')
        externals = dict((m[2], m[1]) for m in re.finditer(r'\[ext_resource type="Script"[^\]]*path="res://([^"]+)" id="([^"]+)"\]', text))
        nodes, scripts = [], set()
        for block in re.finditer(r'\[node name="([^"]+)"([^\]]*)\]\n((?:[^\n\[][^\n]*\n|\n(?!\[))*)', text):
            body = block[3]
            script = re.search(r'^script = ExtResource\("([^"]+)"\)', body, re.M)
            nodes.append({'name': block[1], 'start': block.start(), 'end': block.end(),
                          'unique': 'unique_name_in_owner = true' in body,
                          'script': externals.get(script[1]) if script else None})
            if script and externals.get(script[1]):
                scripts.add(externals[script[1]])
        cache[path] = {'nodes': nodes, 'scripts': sorted(scripts)}
        return cache[path]
    return load_scene


def overwritten_by(scene, record, sources):
    """이 노드의 글자를 실행 중에 덮어쓰는 스크립트 줄을 찾습니다. 없으면 None."""
    node = next((n for n in scene['nodes'] if n['start'] <= record['start'] < n['end']), None)
    if node is None:
        return None, None
    name = re.escape(node['name'])
    writers = r'(?:\.text\s*(?:=|\+=)|\.set_text\(|\.parse_bbcode\(|\.append_text\(|\.placeholder_text\s*=|\.tooltip_text\s*=|\.title\s*=)'
    for path in scene['scripts']:
        source = sources(path)
        # 고유 이름(%이름)이나 경로($…/이름)로 변수에 받은 뒤 글자를 쓰는 경우
        for variable in re.findall(r'var\s+(\w+)[^\n=]*=\s*(?:%' + name + r'\b|\$[^\n]*\b' + name + r'\b|get_node\("[^"\n]*' + name + r'"\))', source):
            hit = re.search(r'^.*\b' + re.escape(variable) + writers + r'.*$', source, re.M)
            if hit:
                return path, hit[0].strip()[:160]
        hit = re.search(r'^.*(?:%' + name + r'|\$[^\n]*' + name + r')' + writers + r'.*$', source, re.M)
        if hit:
            return path, hit[0].strip()[:160]
    if node['script']:
        source = sources(node['script'])
        hit = re.search(r'^\s*(?:self\.)?text\s*=.*$', source, re.M)
        if hit:
            return node['script'], hit[0].strip()[:160]
    return None, node


def main():
    records = load(OUT / 'strings.json')
    manual_path = OUT / 'manual_decisions.json'
    manual = load(manual_path) if manual_path.exists() else {'by_id': {}, 'by_value': {}, 'by_file_prefix': {}}
    source_cache = {}

    def sources(path):
        if path not in source_cache:
            file = RECOVERED / path
            source_cache[path] = file.read_text(encoding='utf-8-sig') if file.exists() else ''
        return source_cache[path]
    scenes = scene_index()
    for record in records:
        if record['classification'] != 'UNKNOWN':
            continue
        file, value, prefix, context = record['file'], record['source'], record['prefix'], record['context']
        suffix = Path(file).suffix
        field = field_of(record)

        def decide(status, reason, handling=None):
            record['classification'], record['evidence'] = status, reason
            if handling:
                record['handling'] = handling
        if record['id'] in manual['by_id']:
            decide(*manual['by_id'][record['id']])
            continue
        prefix_rule = next((rule for start, rule in manual['by_file_prefix'].items() if file.startswith(start)), None)
        if file.startswith(EDITOR_ADDONS):
            decide('INTERNAL', '편집기 전용 플러그인(@tool EditorPlugin). 게임 장면·스크립트에서 참조 0건(2026-11-19 grep), 실행 중 생성되지 않음')
        elif suffix == '.import':
            decide('INTERNAL', '가져오기 설정(importer·type·경로). 게임 화면에 전달되지 않음')
        elif suffix in ('.cfg', '.gdextension', '.json'):
            decide('INTERNAL', '플러그인·확장 설정 파일의 식별자·경로·편집기 상태')
        elif suffix == '.godot':
            if field in ('config/name', 'config/name.demo'):
                decide('VISIBLE_KEEP', '창 제목에 쓰이는 게임 제목(고유명사). 저장 폴더 이름과 연결되어 유지')
            else:
                decide('INTERNAL', '프로젝트 설정의 입력 이름·경로·기능 표식·자동 실행 목록')
        elif value == '':
            decide('INTERNAL', '빈 문자열 초기값')
        elif suffix == '.gdshader':
            decide('INTERNAL', '셰이더 코드 내부 문자열')
        elif prefix_rule:
            decide(*prefix_rule)
        elif value in manual['by_value']:
            decide(*manual['by_value'][value])
        elif suffix in ('.tscn', '.tres'):
            if field in DISPLAY_FIELDS or (field and re.fullmatch(r'popup/item_\d+/text', field)):
                if not has_letters(value):
                    decide('VISIBLE_KEEP', f'표시 필드 {field}의 숫자·기호 자리 채움 값(번역할 글자 없음)')
                elif suffix == '.tscn':
                    script, line = overwritten_by(scenes(file), record, sources)
                    if script:
                        decide('INTERNAL', f'편집용 자리 채움 글자. 실행 중 {script} 가 덮어씀: {line}')
                    # 그 밖은 UNKNOWN으로 남겨 직접 확인
            elif field is not None:
                decide('INTERNAL', f'자원 구조 필드 {field}의 식별자·이름·분류 값(표시 필드 아님)')
            elif re.search(r'(PackedStringArray|StringName|NodePath|&)\(?[^=]*$', prefix) or context.startswith(('"', '}', ']')) or re.search(r'^\s*"[^"]*":', context):
                decide('INTERNAL', '배열·사전 안의 식별자·경로 값(표시 필드 아님)')
        elif suffix == '.gd':
            if re.search(r'(print|print_debug|print_rich|push_error|push_warning|printerr|assert)\s*\(', prefix):
                decide('INTERNAL', '콘솔 진단 출력 인자. 게임 화면 객체로 전달되지 않음')
            elif file.startswith('addons/console/') or file == 'globals/game/game_console.gd':
                decide('VISIBLE_KEEP', '개발자 명령창(` 키)의 명령어·안내·진단 문구. 원작도 모든 언어에서 영어이며 명령어는 입력값이라 유지')
            elif re.fullmatch(r'#?[0-9a-fA-F]{6,8}', value):
                decide('INTERNAL', '색상 코드')
            elif not re.search(r'[A-Za-z]', value):
                decide('VISIBLE_KEEP' if re.search(r'\.text|%s|format|\+', context) else 'INTERNAL', '글자 없는 기호·숫자·구분자')
            elif API_ARG.search(prefix):
                decide('INTERNAL', '노드·입력·설정·애니메이션·속성 조회 함수의 인자')
            elif re.search(r'@export\w*\(|@warning_ignore\(', prefix):
                decide('INTERNAL', '편집기 주석(@export·@warning_ignore) 인자')
            elif re.fullmatch(r'[a-z0-9_]+(:[a-z_]+)?', value):
                decide('INTERNAL', '소문자 식별자(사전 키·속성 경로·신호·그룹·설정 이름) 형식')
            elif re.fullmatch(r'\[/?[a-z_]+(=[^\]]*)?\]( ?\[/?[a-z_]+(=[^\]]*)?\])*', value) or re.fullmatch(r'[\[\]/a-z=#A-F0-9 %s\xa0]*', value) and '[' in value:
                decide('VISIBLE_KEEP', 'BBCode 서식 태그 조각(번역할 글자 없음)')
    save(OUT / 'strings.json', records)
    unknown = [r for r in records if r['classification'] == 'UNKNOWN']
    groups = collections.defaultdict(list)
    for record in unknown:
        groups[(Path(record['file']).suffix, record['source'])].append(record)
    review = [{'suffix': key[0], 'value': key[1], 'count': len(rows), 'files': sorted({r['file'] for r in rows})[:4],
               'fields': sorted({field_of(r) or '' for r in rows}), 'context': rows[0]['context'][:200], 'ids': [r['id'] for r in rows][:6]}
              for key, rows in sorted(groups.items())]
    save(OUT / 'review.json', review)
    summary = {'classifications': dict(collections.Counter(r['classification'] for r in records)),
               'unknown_unique': len(review), 'unknown_by_suffix': dict(collections.Counter(Path(r['file']).suffix for r in unknown))}
    save(OUT / 'classify_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
