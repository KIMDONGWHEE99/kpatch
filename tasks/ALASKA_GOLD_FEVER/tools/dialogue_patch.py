"""대화 966개만 교체하고 비어 있는 선택지 966개는 그대로 보존합니다."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/python_deps'))
import UnityPy
from scan_assets import GameGenerator, configure_reader, read_bounded
from validate_translation import signature

WORK = ROOT / 'working_private/ALASKA_GOLD_FEVER/dialogue_translation'
EXTRACTED = ROOT / 'extracted_private/ALASKA_GOLD_FEVER/25782395/dialogue_scan/dialogue_entries.json'
GROUPS = {'main_story': 418, 'side_quests': 387, 'generic': 107, 'dlc': 42, 'playtest': 12}
FILES = ('Alaska Gold Fever_Data/sharedassets2.assets', 'Alaska Gold Fever_Data/sharedassets3.assets')
OBJECTS = {FILES[0]: {33517: 12}, FILES[1]: {2: 42, 3: 107, 4: 387, 5: 418}}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_json(path):
    return json.loads(path.read_text('utf-8'))


def descriptor(path, rows=None):
    result = {'path': str(path.relative_to(ROOT)), 'sha256': sha(path.read_bytes())}
    if rows is not None:
        result['rows'] = rows
    return result


def load_inputs(require_review=True):
    original = load_json(EXTRACTED)
    canonical_path = WORK / 'dialogue_canonical.json'
    empty_path = WORK / 'preserved_empty_menu_fields.json'
    canonical, empty = load_json(canonical_path), load_json(empty_path)
    source_map = {row['id']: row for row in original}
    if len(original) != 1932 or len(source_map) != 1932 or len(canonical) != 966 or len(empty) != 966:
        raise ValueError('대화 원본 1932개·교정 966개·빈 선택지 966개 조건이 다릅니다.')
    original_visible = {key for key, row in source_map.items() if row['field_title'] == 'ko' and (row['english'] or row['original_korean'])}
    original_empty = {key for key, row in source_map.items() if row['field_title'] == 'Menu Text ko' and not row['english'] and not row['original_korean']}
    if len(original_visible) != 966 or len(original_empty) != 966 or original_visible & original_empty:
        raise ValueError('대화와 비어 있는 선택지의 분류가 예상과 다릅니다.')
    for items, wanted in ((canonical, original_visible), (empty, original_empty)):
        if len({row['id'] for row in items}) != len(items) or {row['id'] for row in items} != wanted:
            raise ValueError('대화 원본과 작업 목록의 위치가 다릅니다.')
        for row in items:
            before = source_map[row['id']]
            if any(row.get(key) != value for key, value in before.items() if key != 'review_status'):
                raise ValueError(f'대화 추출 원본 정보가 변경되었습니다: {row["id"]}')
    expected = {row['id']: row for row in canonical}
    rows, inputs = [], []
    for group, count in GROUPS.items():
        path = WORK / (group + '.json')
        items = load_json(path)
        if len(items) != count or any(row['group'] != group for row in items):
            raise ValueError(f'대화 그룹과 개수가 다릅니다: {group}')
        inputs.append(descriptor(path, len(items)))
        rows.extend(items)
    if len(rows) != 966 or len({row['id'] for row in rows}) != 966 or {row['id'] for row in rows} != expected.keys():
        raise ValueError('교정 대화의 중복·누락·추가 항목이 있습니다.')
    mutable = {'translation', 'review_status', 'review_reason', 'translator_note'}
    for row in rows:
        before = expected[row['id']]
        if any(row.get(key) != value for key, value in before.items() if key not in mutable):
            raise ValueError(f'교정 대화의 원문·위치·조건이 바뀌었습니다: {row["id"]}')
        value = row.get('translation')
        if not isinstance(value, str) or not value.strip() or unicodedata.normalize('NFC', value) != value or '\ufffd' in value:
            raise ValueError(f'대화 번역이 비었거나 잘못되었습니다: {row["id"]}')
        if require_review and (row.get('review_status') not in ('EDITED', 'KEEP') or not row.get('review_reason')):
            raise ValueError(f'검토가 끝나지 않은 대화가 있습니다: {row["id"]}')
        if require_review:
            if signature(row['english']) != signature(value) or Counter(re.findall(r'\[lua\(.*?\)\]', row['english'])) != Counter(re.findall(r'\[lua\(.*?\)\]', value)):
                raise ValueError(f'대화 태그·호출식·줄바꿈이 바뀌었습니다: {row["id"]}')
    observed = Counter((row['file'], row['path_id']) for row in rows)
    wanted = Counter({(file, path_id): count for file, objects in OBJECTS.items() for path_id, count in objects.items()})
    if observed != wanted:
        raise ValueError('대화 대상 파일·객체·개수가 예상과 다릅니다.')
    sources = [descriptor(EXTRACTED), descriptor(canonical_path), descriptor(empty_path)]
    return rows, empty, inputs, sources


@lru_cache(maxsize=1)
def generator():
    result = GameGenerator('6000.0.62f1')
    result.load_local_dll_folder(str(ROOT / 'extracted_private/ALASKA_GOLD_FEVER/25782395/code/dummy'))
    configure_reader(result)
    return result


def source_environment(path):
    environment = UnityPy.load(str(path))
    environment.path = str(path.parent)
    environment.typetree_generator = generator()
    return environment


def field_container(tree, row):
    match = re.fullmatch(r'/conversations/(\d+)/dialogueEntries/(\d+)/fields/(\d+)/value', row['field'])
    if not match:
        raise ValueError('대화 필드 경로가 예상한 형식이 아닙니다.')
    ci, ei, fi = map(int, match.groups())
    conversation = tree['conversations'][ci]
    entry = conversation['dialogueEntries'][ei]
    field = entry['fields'][fi]
    if conversation['id'] != row['conversation_id'] or entry['id'] != row['entry_id'] or field['title'] != row['field_title'] or tree['m_Name'] != row['database']:
        raise ValueError(f'대화 위치의 ID·필드·DB 이름이 다릅니다: {row["id"]}')
    return field


def save_preserving_metadata(raw, environment):
    """원본 객체는 유지하고 수정 객체만 16바이트 경계에 추가합니다."""
    output = bytearray(raw)
    header = environment.file.header
    if header.version < 22 or header.endian != '<':
        raise ValueError('지원하지 않는 자산 형식입니다.')
    original = UnityPy.load(raw)
    if original.file.objects.keys() != environment.file.objects.keys():
        raise ValueError('원본 객체 목록이 달라졌습니다.')
    for path_id, obj in environment.file.objects.items():
        old = original.file.objects[path_id]
        payload = obj.data if obj.data is not None else obj.get_raw_data()
        if payload == old.get_raw_data():
            continue
        needle = struct.pack('<qqIi', old.path_id, old.byte_start - header.data_offset, old.byte_size, old.type_id)
        if raw[:header.data_offset].count(needle) != 1:
            raise ValueError(f'객체 목록 위치를 확정하지 못했습니다: {path_id}')
        position = raw.index(needle)
        output.extend(b'\0' * (-len(output) % 16))
        offset = len(output)
        output.extend(payload)
        struct.pack_into('<qI', output, position + 8, offset - header.data_offset, len(payload))
    struct.pack_into('>q', output, 24, len(output))
    return bytes(output)


def build_file(source_path, relative, rows):
    raw = source_path.read_bytes()
    file_hash = sha(raw)
    environment = source_environment(source_path)
    selected = [row for row in rows if row['file'] == relative]
    records = []
    for path_id, count in OBJECTS[relative].items():
        obj = environment.file.objects[path_id]
        object_hash = sha(obj.get_raw_data())
        entries = [row for row in selected if row['path_id'] == path_id]
        if len(entries) != count or any(row['file_sha256'] != file_hash or row['raw_sha256'] != object_hash for row in entries):
            raise ValueError('대화 원본 파일·객체 해시 또는 행 수가 다릅니다.')
        tree = read_bounded(obj)
        changed = 0
        for row in entries:
            field = field_container(tree, row)
            if field['value'] != row['original_korean'] or sha(field['value'].encode('utf-8')) != row['original_sha256']:
                raise ValueError(f'대화 원본 문구가 지정 위치와 다릅니다: {row["id"]}')
            if field['value'] != row['translation']:
                field['value'] = row['translation']
                changed += 1
        if changed:
            obj.save_typetree(tree)
        records.append({'file': relative, 'path_id': path_id, 'rows': len(entries), 'changed': changed})
    return save_preserving_metadata(raw, environment), records
