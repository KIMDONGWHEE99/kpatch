"""빌더를 불러오지 않고 번역 위치와 비대상 바이트를 독립 검사합니다."""
from __future__ import annotations
import argparse
import copy
import importlib.util
import io
import json
import re
import struct
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REUSE = ROOT / 'tasks/THE_HORDE_OF_GORAK'
sys.path.insert(0, str(ROOT / 'tools/python_deps'))
sys.path.insert(0, str(REUSE))
from dat_container import DatFile, sha, utf16z, u32
from extra_chunk_review import parse_player_controls
from fontTools.ttLib import TTFont
spec = importlib.util.spec_from_file_location('fusion_event_reader', REUSE / 'inventory.py')
event_reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(event_reader)

WORK = ROOT / 'working_private/COBALT_MINER'
SOURCE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
CLASSIFICATION = WORK / 'investigation_20261101/classification'
TRANSLATIONS = WORK / 'translation_01/translations.json'
NATIVE = WORK / 'native_candidate_02'
NATIVE_EXPECTED = WORK / 'investigation_20261101/native/native_visible_worklist.json'
BASELINE = WORK / 'investigation_20261101/baseline_manifest.json'
SOURCE_HASH = '01733d5907692df4cfa462dc709cb3c96180dba056f6249a1abf334fd2bb70e7'
FAMILY = 'Cobalt Noto Sans KR'
FONT_DIR = WORK / 'font_complete_02/fonts'
FONT_HASHES = {400: 'dc487963f96b935718a41238ee588d046994b352ef7c96bcbcb40da018d0317f',
               700: '814bb56415e9ffc0a6ae1045a6cf024598274909a3f2e1297bc9f9c4a46269eb'}
RESOURCE_KINDS = {'menu_text', 'control_key_name', 'dialog_title', 'dialog_item_title'}
TOKEN = re.compile(r'<[^<>]+>|\{[^{}]+\}|(?<!\d)%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?[diuoxXfFeEgGaAcsp]|\r\n|\r|\n|\t|\\[nrt]')

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def read_inventory():
    rows = [json.loads(s) for s in (CLASSIFICATION / 'inventory.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    if len({r['location'] for r in rows}) != len(rows):
        raise ValueError('조사 위치 중복')
    if any(r['source_file_sha256'] != SOURCE_HASH or r['classification'] == 'UNKNOWN' or not r['reason'] for r in rows):
        raise ValueError('원본 연결 또는 분류 근거 누락')
    return rows

def check_tokens(source, translated, kind):
    if not isinstance(translated, str) or not translated.strip() or '\0' in translated:
        raise ValueError('빈 번역 또는 NUL 문자')
    if TOKEN.findall(source) != TOKEN.findall(translated):
        raise ValueError('태그·자리표시자·제어 줄바꿈의 순서 또는 값 변경')
    stack = []
    for token in re.findall(r'<[^<>]+>', translated):
        match = re.fullmatch(r'<(/?)([A-Za-z][\w-]*)(?:[ =][^<>]*)?(/?)>', token)
        if not match:
            continue
        closing, name, single = match.groups()
        if single or name.lower() in {'br', 'img', 'sprite'}:
            continue
        if closing:
            if not stack or stack.pop() != name:
                raise ValueError('태그 중첩 오류')
        else:
            stack.append(name)
    if stack:
        raise ValueError('닫히지 않은 태그')
    if kind == 'menu_text':
        if source.split('\t')[1:] != translated.split('\t')[1:]:
            raise ValueError('메뉴 단축키 변경')
        mnemonic = lambda text: [x.lower() for x in re.findall(r'(?<!&)&(?!&)(.)', text)]
        if mnemonic(source) != mnemonic(translated):
            raise ValueError('메뉴 접근 키 변경')

def load_plan(path=TRANSLATIONS, inventory=None):
    inventory = read_inventory() if inventory is None else inventory
    expected = {r['location']: r for r in inventory if r['classification'] == 'VISIBLE_TRANSLATE'}
    plan, sources = {}, set()
    for group in load(path):
        if not isinstance(group, dict) or group['source'] in sources:
            raise ValueError('번역 원문 그룹 중복 또는 형식 오류')
        sources.add(group['source'])
        if not group.get('occurrences'):
            raise ValueError('번역 위치 없는 그룹')
        for occurrence in group['occurrences']:
            location = occurrence['location']
            if location not in expected or location in plan:
                raise ValueError(f'미분류·중복·예상 밖 번역 위치: {location}')
            row = expected[location]
            if row['source'] != group['source'] or any(occurrence.get(k) != row[k] for k in ('kind', 'target', 'offset', 'slot_bytes')):
                raise ValueError(f'원문 또는 위치 메타데이터 변경: {location}')
            translated = occurrence.get('translation', group.get('translation'))
            check_tokens(row['source'], translated, row['kind'])
            if translated == row['source']:
                raise ValueError(f'번역 대상 위치의 원문 잔존: {location}')
            if row['kind'] not in RESOURCE_KINDS | {'button_text'} and len(translated.encode('utf-16le')) + 2 > row['slot_bytes']:
                raise ValueError(f'고정 슬롯 용량 초과: {location}')
            plan[location] = dict(row, translated=translated)
    if set(plan) != set(expected):
        raise ValueError(f'번역 위치 누락: {len(set(expected) - set(plan))}')
    return plan

def compare_positions(expected, actual):
    if set(expected) != set(actual):
        raise ValueError('문구 위치의 추가·삭제 또는 누락')
    for key, wanted in expected.items():
        if actual[key] != wanted:
            raise ValueError(f'위치별 기대값 불일치: {key}')

def same_except(before, after, ranges, label):
    if len(before) != len(after):
        raise ValueError(f'비대상 길이 변경: {label}')
    cursor = 0
    for start, end in sorted(ranges, key=lambda pair: (pair[0], pair[1])):
        if start < 0 or end < start or end > len(before):
            raise ValueError(f'허용 범위 오류: {label}')
        if start > cursor and before[cursor:start] != after[cursor:start]:
            raise ValueError(f'허용 범위 밖 바이트 변경: {label}@{cursor}:{start}')
        cursor = max(cursor, end)
    if before[cursor:] != after[cursor:]:
        raise ValueError(f'허용 범위 밖 바이트 변경: {label}@{cursor}')

def word(data, offset=0):
    return struct.unpack_from('<H', data, offset)[0]

def menu_items(data):
    result = {}
    header, offset, length, accel, accel_size = struct.unpack_from('<5I', data)
    if header != 20 or offset != 20 or data[offset:offset + 4] != b'\0' * 4:
        raise ValueError('메뉴 헤더 손상')
    def read(position, parent='menu'):
        index = 0
        while True:
            flags = word(data, position)
            position += 2
            ident = None
            if not flags & 16:
                ident = word(data, position)
                position += 2
            start = position
            value, position = utf16z(data, position)
            key = f'{parent}/{index}'
            result[key] = dict(source=value, flags=flags, id=ident, offset=start)
            if flags & 16:
                position = read(position, key)
            if flags & 128:
                return position
            index += 1
    end = read(offset + 4)
    if end != offset + length or end != accel or accel + accel_size != len(data):
        raise ValueError('메뉴 크기 또는 단축키 표 경계 오류')
    return result, data[accel:]

def control_key(row):
    context = row.get('control_context', row)
    if row['kind'] == 'control_key_name':
        return row['kind'], context['id']
    return row['kind'], context['dialog_id'], context.get('item_index')

def dialog_structure(parsed):
    result = copy.deepcopy(parsed['dialogs'])
    for dialog in result:
        for key in ('offset', 'size', 'title'):
            dialog.pop(key)
        for item in dialog['controls']:
            item.pop('offset')
            item.pop('title')
    return result

def controls_boundaries(data, parsed):
    """길이 변화로 이동한 상대 표와 모든 정렬/생성 데이터를 별도로 검사합니다."""
    string_table, dialog_table = u32(data, 4), u32(data, 8)
    count = u32(data, string_table)
    base = string_table + 4 + count * 8
    cursor = base
    for index in range(count):
        offset = base + u32(data, string_table + 8 + index * 8)
        if offset != cursor:
            raise ValueError('키 이름 표의 중복·공백·역순')
        _, cursor = utf16z(data, cursor)
    if dialog_table != (cursor + 3) & ~3 or any(data[cursor:dialog_table]):
        raise ValueError('키 이름 표의 정렬 오류')
    count = u32(data, dialog_table)
    base = dialog_table + 4 + count * 8
    cursor = base
    extras = []
    def field_end(position):
        return position + 4 if word(data, position) == 0xFFFF else utf16z(data, position)[1]
    for index, dialog in enumerate(parsed['dialogs']):
        start = base + u32(data, dialog_table + 8 + index * 8)
        if start != cursor or start % 4:
            raise ValueError('대화상자 표의 공백·역순·정렬 오류')
        position = start + 18
        for _ in range(3):
            position = field_end(position)
        if dialog['font']:
            position = field_end(position + 2)
        for item in dialog['controls']:
            aligned = (position + 3) & ~3
            if any(data[position:aligned]) or item['offset'] != aligned:
                raise ValueError('컨트롤 정렬 패딩 변경')
            position = aligned + 18
            position = field_end(field_end(position))
            extra_size = word(data, position)
            if extra_size == 1:
                raise ValueError('잘못된 생성 데이터 크기')
            end = position + (extra_size or 2)
            extras.append((dialog['id'], item['index'], data[position:end].hex()))
            position = end
        cursor = (position + 3) & ~3
        if cursor != start + dialog['size'] or any(data[position:cursor]):
            raise ValueError('대화상자 후미 정렬 오류')
    if cursor != len(data):
        raise ValueError('Windows 자원의 해석되지 않은 후미')
    return extras

def compressed_records(data):
    result, position = [], 0
    while position < len(data):
        size, packed = struct.unpack_from('<II', data, position)
        end = position + 8 + packed
        if end > len(data):
            raise ValueError('내장 글꼴 블록 경계 오류')
        decoder = zlib.decompressobj()
        raw = decoder.decompress(data[position + 8:end]) + decoder.flush()
        if len(raw) != size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('내장 글꼴 압축 크기 또는 후미 오류')
        result.append((position, raw))
        position = end
    return result

def check_logfont(before, after, offset, label):
    weight = 700 if u32(before, offset + 16) >= 600 else 400
    face = (FAMILY.encode('utf-16le') + b'\0\0').ljust(64, b'\0')
    if u32(after, offset + 16) != weight or after[offset + 23] != 129 or after[offset + 28:offset + 92] != face:
        raise ValueError(f'한글 글꼴 연결 또는 굵기 불일치: {label}')
    ranges = [(offset + 16, offset + 20), (offset + 23, offset + 24), (offset + 28, offset + 92)]
    return ranges

def extract_positions(dat, inventory):
    menus, _ = menu_items(dat.one(0x2226).decoded)
    controls = {control_key(r): r for r in parse_player_controls(dat.one(0x225D).decoded)['strings']}
    event_values, event_counts = {}, []
    for fi, frame in enumerate(c for c in dat.chunks if c.chunk_id == 0x3333):
        chunk = next(c for c in frame.children if c.chunk_id == 0x333D)
        events = event_reader.event_operations(chunk.decoded)
        event_counts.append(len(events))
        for event in events:
            for kind in ('Conditions', 'Actions'):
                for op in event[kind]:
                    for param in op['parameters']:
                        for value in param['strings']:
                            location = f"frame:{fi}/event:{event['index']}/{kind}:{op['index']}/param:{param['index']}/{value['field']}"
                            event_values[location] = value['value']
    actual, offsets = {}, {}
    for row in inventory:
        kind, location = row['kind'], row['location']
        _, data = dat.get_target(row['target'])
        offset = row['offset']
        if kind == 'menu_text':
            actual[location], offset = menus[location]['source'], menus[location]['offset']
        elif kind.startswith('dialog_') or kind == 'control_key_name':
            value = controls[control_key(row)]
            actual[location], offset = value['source'], value['offset']
        elif kind == 'event_string':
            actual[location] = event_values[location]
        elif kind == 'paragraph':
            start = word(data, 36)
            count = u32(data, start + 12)
            if row['paragraph'] >= count:
                raise ValueError('문단 삭제')
            offset = start + u32(data, start + 16 + row['paragraph'] * 4) + 8
            actual[location] = utf16z(data, offset)[0]
        elif kind == 'button_text':
            offset = word(data, 12) + 20 + 212
            actual[location] = utf16z(data, offset)[0]
        elif kind == 'extension_utf16_candidate':
            actual[location] = data[offset:offset + row['slot_bytes']].decode('utf-16le')
        else:
            actual[location] = utf16z(data, offset)[0]
        offsets[location] = offset
    return actual, offsets, event_counts

def runtime_checksum(data):
    value, full = 0, len(data) & ~3
    for offset in range(0, full, 4):
        value = ((value * 2 + (value >> 31)) + int.from_bytes(data[offset:offset + 4], 'little')) & 0xFFFFFFFF
    for byte in data[full:]:
        value = ((value * 2 + (value >> 31)) + byte) & 0xFFFFFFFF
    return value ^ 13

def validate_images(original, candidate, manifest_path):
    from PIL import Image
    manifest_path = Path(manifest_path)
    plan = load(manifest_path)
    expected = {row['handle']: row for row in plan['files']}
    allowed_handles = {1123, 1374, 1486, 1491, 1492, 1498, 1499, 1500, 1501, 1503, 1504, 1513}
    if set(expected) != allowed_handles:
        raise ValueError('승인된12개 미디어 위치와 다름')
    def records(dat):
        bank, table = dat.one(0x6666).decoded, dat.one(0x5555).decoded
        cursor, result = 4, []
        for _ in range(u32(bank)):
            stored, size, compressed = struct.unpack_from('<III', bank, cursor)
            end = cursor + 12 + compressed
            raw = bank[cursor:end]
            decoder = zlib.decompressobj()
            body = decoder.decompress(raw[12:]) + decoder.flush()
            if len(body) != size or not decoder.eof or decoder.unused_data or u32(table, (stored - 1) * 4) != cursor + 260:
                raise ValueError('이미지 압축/위치표 오류')
            result.append((stored - 1, cursor, raw, body))
            cursor = end
        if cursor != len(bank):
            raise ValueError('이미지 묶음 후미')
        return result
    before, after = records(original), records(candidate)
    if [x[0] for x in before] != [x[0] for x in after]:
        raise ValueError('이미지 개수·핸들·순서 변경')
    untouched_table = bytearray(candidate.one(0x5555).decoded)
    old_table = original.one(0x5555).decoded
    reports = []
    for a, b in zip(before, after):
        handle, _, old_raw, old = a
        _, _, new_raw, new = b
        untouched_table[handle * 4:handle * 4 + 4] = old_table[handle * 4:handle * 4 + 4]
        if handle not in expected:
            if old_raw != new_raw:
                raise ValueError('비대상 이미지 압축 원문 변경')
            continue
        if old[:32] != new[:32] or len(old) != len(new) or old_raw == new_raw or new[16:18] != b'\x04\0':
            raise ValueError('이미지 메타데이터 변경 또는 지원 밖 형식')
        width, height = struct.unpack_from('<HH', new, 12)
        stride = (width + width % 2) * 3
        if len(new) != 32 + stride * height:
            raise ValueError('이미지 본문 크기 오류')
        row = expected[handle]
        png = manifest_path.parent / f'{handle:05d}.png'
        if sha(png.read_bytes()) != row['output_sha256']:
            raise ValueError('기대 PNG 지문 변경')
        with Image.open(png) as image:
            if image.mode != 'RGBA' or image.size != (width, height):
                raise ValueError('기대 PNG 형식·크기 변경')
            wanted = image.tobytes()
        rgb = Image.frombytes('RGB', (width, height), new[32:], 'raw', 'BGR', stride).tobytes()
        region = (47, 197, 187, 236) if handle == 1123 else (234, 99, 375, 166)
        if tuple(row['allowed_region']) != region:
            raise ValueError('미디어 허용 사각형 변경')
        actual = bytearray()
        for pos in range(0, len(rgb), 3):
            pixel = rgb[pos:pos + 3]
            actual.extend(pixel + (b'\0' if pixel == new[28:31] else b'\xff'))
        if bytes(actual) != wanted:
            raise ValueError('독립 재추출 픽셀과 기대 PNG 불일치')
        ranges = [(32 + y * stride + region[0] * 3, 32 + y * stride + region[2] * 3) for y in range(region[1], region[3])]
        same_except(old, new, ranges, f'image:{handle}')
        old_rgb = Image.frombytes('RGB', (width, height), old[32:], 'raw', 'BGR', stride).tobytes()
        for pos in range(0, len(rgb), 3):
            if (old_rgb[pos:pos + 3] == old[28:31]) != (rgb[pos:pos + 3] == new[28:31]):
                raise ValueError('투명색/알파 경계 변경')
        reports.append(dict(handle=handle, png_sha256=sha(png.read_bytes()), rgba_sha256=sha(actual), outside_region='PASS', alpha='PASS'))
    if bytes(untouched_table) != old_table:
        raise ValueError('사용하지 않는 이미지 위치표 변경')
    return dict(status='PASS', manifest_sha256=sha(manifest_path.read_bytes()), image_count=len(after), changed=len(reports), records=reports)

def validate_dat(original, candidate, inventory, plan, media_manifest=None):
    if sha(original.original) != SOURCE_HASH:
        raise ValueError('지원하지 않는 원본 DAT')
    if original.header != candidate.header or set(original.by_location) != set(candidate.by_location):
        raise ValueError('DAT 헤더 또는 청크 목록 변경')
    if len(original.objects) != len(candidate.objects) or len(original.fonts) != len(candidate.fonts):
        raise ValueError('객체 또는 글꼴 개수 변경')
    old_values, old_offsets, old_counts = extract_positions(original, inventory)
    new_values, new_offsets, new_counts = extract_positions(candidate, inventory)
    compare_positions({r['location']: r['source'] for r in inventory}, old_values)
    expected = {r['location']: (plan[r['location']]['translated'] if r['location'] in plan else
                FAMILY if r['kind'] in {'font_name', 'button_font'} else r['source']) for r in inventory}
    compare_positions(expected, new_values)
    if old_counts != new_counts:
        raise ValueError('프레임 이벤트 수 변경')
    fixed = defaultdict(list)
    for row in plan.values():
        if row['kind'] not in RESOURCE_KINDS | {'button_text'}:
            offset, size = row['offset'], row['slot_bytes']
            if old_offsets[row['location']] != offset or new_offsets[row['location']] != offset:
                raise ValueError('고정 슬롯 위치 이동')
            _, raw = candidate.get_target(row['target'])
            wanted = (row['translated'].encode('utf-16le') + b'\0\0').ljust(size, b'\0')
            if raw[offset:offset + size] != wanted:
                raise ValueError('고정 슬롯 번역 또는 패딩 불일치')
            fixed[row['target']].append((offset, offset + size))
    # 모든 메뉴 명령 ID와 접근 키 표, Windows 대화상자 구조를 별도 판독합니다.
    old_menu, old_accel = menu_items(original.one(0x2226).decoded)
    new_menu, new_accel = menu_items(candidate.one(0x2226).decoded)
    if set(old_menu) != set(new_menu) or old_accel != new_accel or any((old_menu[k]['flags'], old_menu[k]['id']) != (new_menu[k]['flags'], new_menu[k]['id']) for k in old_menu):
        raise ValueError('메뉴 구조 또는 단축키 표 변경')
    old_control = parse_player_controls(original.one(0x225D).decoded)
    new_control = parse_player_controls(candidate.one(0x225D).decoded)
    if (dialog_structure(old_control) != dialog_structure(new_control)
            or Counter(control_key(r) for r in old_control['strings']) != Counter(control_key(r) for r in new_control['strings'])
            or controls_boundaries(original.one(0x225D).decoded, old_control) != controls_boundaries(candidate.one(0x225D).decoded, new_control)):
        raise ValueError('대화상자 필드·ID·좌표·글꼴 구조 변경')
    buttons = {r['object_handle'] for r in inventory if r['kind'] == 'button_font'}
    for before, after in zip(original.objects, candidate.objects):
        label = f'object:{before.index}'
        a, b = before.decoded, after.decoded
        ranges = fixed[label]
        if before.index in buttons:
            extension, other_extension = word(a, 12), word(b, 12)
            start = extension + 20
            text_start = start + 212
            if extension != other_extension or u32(b, 0) != len(b) or u32(b, extension) != len(b) - extension:
                raise ValueError('KcBoxA 확장 위치 또는 길이 오류')
            text_size = u32(b, start + 208)
            if text_size < 2 or text_size % 2 or text_start + text_size + 8 != len(b) or utf16z(b, text_start)[1] != text_start + text_size:
                raise ValueError('KcBoxA 문구·후미 경계 오류')
            if a[-8:] != b[-8:]:
                raise ValueError('KcBoxA 후미 플래그 변경')
            ranges = check_logfont(a, b, start + 36, label) + [(0, 4), (extension, extension + 4), (start + 208, start + 212)]
            same_except(a[:text_start], b[:text_start], ranges, label)
        else:
            same_except(a, b, ranges, label)
    # 글꼴의 모든 연결과 실제 글리프를 압축 묶음부터 다시 읽습니다.
    required = {ord(c) for value in expected.values() for c in value if ord(c) >= 32 and c not in '\r\n\t'}
    embedded_before = compressed_records(original.one(0x2259).decoded)
    embedded_after = compressed_records(candidate.one(0x2259).decoded)
    if len(embedded_before) != len(embedded_after):
        raise ValueError('내장 글꼴 개수 변경')
    font_reports, offset_map = [], {}
    for (old_offset, old_raw), (new_offset, raw) in zip(embedded_before, embedded_after):
        with TTFont(io.BytesIO(old_raw)) as font:
            weight = 700 if font['OS/2'].usWeightClass >= 600 else 400
        if sha(raw) != FONT_HASHES[weight]:
            raise ValueError('위험 시험 글꼴과 다른 입력')
        with TTFont(io.BytesIO(raw)) as font:
            cmap = font.getBestCmap()
            missing = sorted(c for c in required if c not in cmap or cmap[c] == '.notdef')
            if missing or font['name'].getDebugName(1) != FAMILY or font['OS/2'].usWeightClass != weight or font['OS/2'].fsType != 0 or 'fvar' in font:
                raise ValueError(f'실제 글리프·임베딩·가변 글꼴 오류: {missing}')
            font_reports.append(dict(weight=weight, sha256=sha(raw), required=len(required), missing=missing))
        offset_map[old_offset] = new_offset
    old_info, new_info = original.one(0x2258).decoded, candidate.one(0x2258).decoded
    if len(old_info) != len(new_info) or len(old_info) % 96:
        raise ValueError('내장 글꼴 참조 표 크기 변경')
    for offset in range(0, len(old_info), 96):
        a, b = old_info[offset:offset + 96], new_info[offset:offset + 96]
        ranges = check_logfont(a, b, 0, f'font_mapping:{offset // 96}')
        if u32(b, 92) != offset_map[u32(a, 92)]:
            raise ValueError('내장 글꼴 오프셋 참조 오류')
        same_except(a, b, ranges + [(92, 96)], 'font_mapping')
    for before, after in zip(original.fonts, candidate.fonts):
        if before.handle != after.handle:
            raise ValueError('논리 글꼴 핸들 변경')
        ranges = check_logfont(before.decoded, after.decoded, 12, f'font:{before.handle}')
        same_except(before.decoded, after.decoded, ranges, f'font:{before.handle}')
    # 객체·글꼴 위치표는 새 압축 블록 경계와 직접 대조합니다.
    object_offsets = candidate.one(0x2257).decoded
    if object_offsets != b''.join(struct.pack('<I', x.offset) for x in candidate.objects):
        raise ValueError('객체 위치표 오류')
    font_table = bytearray(candidate.one(0x5556).decoded)
    old_font_table = bytearray(original.one(0x5556).decoded)
    for block in candidate.fonts:
        if u32(font_table, (block.handle - 1) * 4) != block.offset + 260:
            raise ValueError('논리 글꼴 위치표 오류')
        font_table[(block.handle - 1) * 4:block.handle * 4] = old_font_table[(block.handle - 1) * 4:block.handle * 4]
    if font_table != old_font_table:
        raise ValueError('사용하지 않는 글꼴 위치표 항목 변경')
    special = {0x2256, 0x2257, 0x2258, 0x2259, 0x6667, 0x5556, 0x2242, 0x2226, 0x225D}
    media_report = validate_images(original, candidate, media_manifest) if media_manifest else dict(status='NOT_RUN')
    if media_manifest:
        special |= {0x6666, 0x5555}
    changed = []
    for location, before in original.by_location.items():
        after = candidate.by_location[location]
        if before.flag != after.flag or before.chunk_id != after.chunk_id:
            raise ValueError('청크 암호·압축 방식 변경')
        if before.children:
            continue
        if before.decoded != after.decoded:
            changed.append(location)
        if before.chunk_id not in special:
            same_except(before.decoded, after.decoded, fixed[location], location)
    start = 48 + candidate.one(0x222F).offset
    end = 48 + candidate.one(0x2242).offset
    if runtime_checksum(candidate.original[start:end]) != u32(candidate.one(0x2242).decoded):
        raise ValueError('실행기 검사값 불일치')
    font_positions = sum(r['kind'] in {'font_name', 'button_font'} for r in inventory)
    return dict(status='PASS', translated_positions=len(plan), preserved_positions=len(inventory) - len(plan) - font_positions,
                extracted_positions=len(inventory), frame_event_counts=new_counts, changed_leaf_chunks=changed,
                fonts=font_reports, object_count=len(candidate.objects), font_count=len(candidate.fonts),
                save_keys='PASS', original_window_settings='PASS', non_target_bytes='PASS', media=media_report), [
                    dict(location=r['location'], kind=r['kind'], expected=expected[r['location']], actual=new_values[r['location']],
                         original_offset=old_offsets[r['location']], output_offset=new_offsets[r['location']], status='PASS') for r in inventory]

def validate_native(candidate_dir, native_source=NATIVE, native_expected=NATIVE_EXPECTED, native_inventory_path=None):
    import pefile
    spec = importlib.util.spec_from_file_location('native_independent_reader', Path(__file__).with_name('validate_native_candidate.py'))
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    audit = load(NATIVE / 'native_patch_audit.json')
    native_source, native_expected = Path(native_source), Path(native_expected)
    expected = load(native_expected)
    native_inventory_path = Path(native_inventory_path) if native_inventory_path else WORK / 'investigation_20261101/native/native_inventory.jsonl'
    native_inventory = [json.loads(s) for s in native_inventory_path.read_text(encoding='utf-8').splitlines() if s]
    identity = lambda r: (r['file'], r['kind'], r['file_offset'], r['source_bytes_sha256'], r.get('string_id'), r.get('role'))
    wanted = Counter(identity(r) for r in native_inventory if r['classification'] == 'VISIBLE_TRANSLATE')
    supplied = Counter(identity(r) for r in expected)
    if wanted != supplied or any(count != 1 for count in supplied.values()):
        raise ValueError('네이티브 기대 위치 누락·중복·추가')
    parsed, reports = {}, []
    title_path = native_source / 'native_title_audit.json'
    title_audit = load(title_path) if title_path.exists() else None
    json_source = native_source
    if title_audit:
        json_source = (ROOT / title_audit['parent_candidate']).resolve()
        if not json_source.is_relative_to(WORK):
            raise ValueError('제목 보완의 부모 후보 경계 오류')
        title_proof = load(native_source / 'independent_validation.json')
        if title_proof['status'] != 'PASS' or title_proof['parent_validation_sha256'] != sha((json_source / 'independent_validation.json').read_bytes()):
            raise ValueError('제목 보완 독립 증거 연결 오류')
    json_audit_path = json_source / 'native_json_audit.json'
    json_audit = load(json_audit_path) if json_audit_path.exists() else None
    json_proof = load(json_source / 'independent_validation.json') if json_audit else None
    if json_audit and (json_proof['status'] != 'PASS' or json_proof['audit_sha256'] != sha(json_audit_path.read_bytes())
                       or json_proof['file_sha256'] != json_audit['candidate_sha256']):
        raise ValueError('네이티브 JSON 보완의 독립 증거 연결 불일치')
    for entry in audit['files']:
        name = entry['file']
        before, after = (SOURCE / name).read_bytes(), (candidate_dir / name).read_bytes()
        extended = json_audit and name == json_audit['file']
        digest = json_audit['candidate_sha256'] if extended else entry['candidate_sha256']
        title_ranges = []
        if title_audit:
            title_file = next(r for r in title_audit['files'] if r['file'] == name)
            parent = (json_source / name).read_bytes()
            if sha(parent) != digest or title_file['parent_sha256'] != digest:
                raise ValueError('제목 보완 부모 파일 불일치')
            for patch in title_audit['patches']:
                if patch['file'] != name:
                    continue
                pos, old, new = patch['offset'], bytes.fromhex(patch['before']), bytes.fromhex(patch['after'])
                if len(old) != len(new) or parent[pos:pos + len(old)] != old or after[pos:pos + len(new)] != new:
                    raise ValueError('제목 보완 허용 변경 불일치')
                title_ranges.append((pos, pos + len(new)))
            same_except(parent, after, title_ranges, name)
            digest = title_file['candidate_sha256']
        if sha(before) != entry['source_sha256'] or sha(after) != digest or sha((native_source / name).read_bytes()) != digest:
            raise ValueError(f'네이티브 해시 불일치: {name}')
        boundary_source = before
        if extended:
            previous = (NATIVE / name).read_bytes()
            if sha(previous) != entry['candidate_sha256'] or sha(previous) != json_audit['source_sha256']:
                raise ValueError('네이티브 JSON 보완의 이전 후보 지문 불일치')
            ranges = list(json_audit['header_ranges'])
            for patch in json_audit['patches']:
                pos = patch['offset']
                old, new = bytes.fromhex(patch['before']), bytes.fromhex(patch['after'])
                if previous[pos:pos + len(old)] != old or after[pos:pos + len(new)] != new or len(old) != len(new):
                    raise ValueError('네이티브 JSON 허용 패치 불일치')
                ranges.append((pos, pos + len(new)))
            same_except(previous, after[:len(previous)], ranges, name)
            boundary_source = previous
        else:
            same_except(before, after, list(entry['allowed_ranges']) + title_ranges, name)
        old_pe, pe = pefile.PE(data=boundary_source), pefile.PE(data=after)
        if extended:
            if len(old_pe.sections) + 1 != len(pe.sections) or pe.sections[-1].Name.rstrip(b'\0') != b'.kjson':
                raise ValueError('네이티브 JSON 보완 섹션 구조 불일치')
            section = pe.sections[-1]
            if section.VirtualAddress != json_audit['new_section']['rva'] or section.get_data()[:json_audit['wrapper']['size']].hex() != json_audit['wrapper']['bytes']:
                raise ValueError('네이티브 JSON Unicode 경계 코드 불일치')
            relocations = {pe.get_offset_from_rva(x.rva) for block in pe.DIRECTORY_ENTRY_BASERELOC for x in block.entries if x.type == 3}
            for row in json_audit['translations']:
                if pe.get_offset_from_rva(row['candidate_rva']) != row['candidate_file_offset']:
                    raise ValueError('네이티브 새 문구 위치 변환 불일치')
                for reference in row['pointer_offsets']:
                    if reference not in relocations or u32(after, reference) != pe.OPTIONAL_HEADER.ImageBase + row['candidate_rva']:
                        raise ValueError('네이티브 새 문구 재배치 참조 불일치')
        elif len(old_pe.sections) != len(pe.sections):
            raise ValueError('네이티브 섹션 수 변경')
        for a, b in zip(old_pe.sections, pe.sections):
            if (a.Name, a.VirtualAddress, a.SizeOfRawData, a.Characteristics) != (b.Name, b.VirtualAddress, b.SizeOfRawData, b.Characteristics):
                raise ValueError('네이티브 섹션 배치 변경')
            if not extended and a.Characteristics & 0x20000000 and a.get_data() != b.get_data():
                raise ValueError('네이티브 실행 코드 변경')
        resources = {}
        for typ in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            for ident in typ.directory.entries:
                for language in ident.directory.entries:
                    r = language.data.struct
                    resources[(typ.id, ident.id, language.id)] = pe.get_data(r.OffsetToData, r.Size)
        parsed[name] = after, resources
        reports.append(dict(file=name, sha256=sha(after), boundary='PASS', code='APPROVED_JSON_UNICODE_BOUNDARY' if extended else 'UNCHANGED',
                            reused_proof_sha256=sha((json_source / 'independent_validation.json').read_bytes()) if extended else None))
    fields = []
    for row in expected:
        data, resources = parsed[row['file']]
        if row['kind'] == 'section_string':
            if 'candidate_file_offset' in row:
                offset = row['candidate_file_offset']
                actual = data[offset:data.index(0, offset)].decode('utf-8')
            else:
                actual = utf16z(data, row['file_offset'])[0]
        else:
            raw = resources[(row['resource_type']['id'], row['resource_name']['id'], row['resource_language']['id'])]
            if row['kind'] == 'RT_STRING':
                values, offset = [], 0
                for _ in range(16):
                    length = word(raw, offset)
                    values.append(raw[offset + 2:offset + 2 + length * 2].decode('utf-16le'))
                    offset += 2 + length * 2
                actual = values[row['string_id'] % 16]
            elif row['kind'] == 'RT_DIALOG':
                actual = reader.dialog_texts(raw)[row['role']]
            else:
                raise ValueError('검증하지 않은 네이티브 종류')
        if actual != row['translation']:
            raise ValueError('네이티브 위치별 번역 불일치')
        fields.append(dict(file=row['file'], kind=row['kind'], offset=row['file_offset'], expected=row['translation'], actual=actual, status='PASS'))
    return dict(status='PASS', files=reports, checked_fields=len(fields),
                inventory_sha256=sha(native_inventory_path.read_bytes()),
                classification_counts=dict(Counter(r['classification'] for r in native_inventory)),
                scope='번역 대상 필드와 변경 경계의 정적 검사. 전체 네이티브 분류와 화면 검수의 완료 판정 아님'), fields

def rejection_checks():
    outcomes = []
    def rejected(name, action):
        try:
            action()
        except (ValueError, KeyError) as error:
            outcomes.append(dict(case=name, status='PASS', rejected_by=str(error)))
        else:
            raise ValueError(f'합성 결함을 거부하지 않음: {name}')
    expected = {'object:60': '새 게임', 'object:61': '이어하기'}
    compare_positions(expected, dict(expected))
    rejected('빈 값', lambda: compare_positions(expected, {'object:60': '', 'object:61': '이어하기'}))
    rejected('위치 교환', lambda: compare_positions(expected, {'object:60': '이어하기', 'object:61': '새 게임'}))
    rejected('위치 누락', lambda: compare_positions(expected, {'object:60': '새 게임'}))
    rejected('태그 순서', lambda: check_tokens('<b><i>{0}</i></b>', '<i><b>{0}</b></i>', 'paragraph'))
    rejected('태그 중첩', lambda: check_tokens('<b><i>{0}</i></b>', '<b><i>{0}</b></i>', 'paragraph'))
    rejected('제어 줄바꿈', lambda: check_tokens('A\r\nB\nC', '가\n나\r\n다', 'paragraph'))
    before = b'TEXT____saveprofile.ini'
    rejected('저장 파일명 변경', lambda: same_except(before, b'TEXT____fakeprofile.ini', [(0, 8)], 'save_key_fixture'))
    check_tokens('&New\tF2', '새 게임(&N)\tF2', 'menu_text')
    rejected('메뉴 접근 키 변경', lambda: check_tokens('&New\tF2', '새 게임(&S)\tF2', 'menu_text'))
    return dict(status='PASS', scope='실제 검증 함수에 합성 결함을 넣는 거부 검사. 게임 실행 아님', cases=outcomes)

def validate_nebula(extracted, candidate_dir, translation_path=TRANSLATIONS):
    """독립 .NET 추출기의 의미 구조에서 문단·이벤트·버튼·메뉴를 다시 확인합니다."""
    extracted, candidate_dir = Path(extracted), Path(candidate_dir)
    package = load(extracted / 'package.json')
    baseline = load(ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01/package.json')
    inventory, plan = read_inventory(), load_plan(translation_path)
    summary = load(extracted / 'summary.json')
    if summary['errors'] != 0 or len(package['Frames']) != len(baseline['Frames']) or set(package['FrameItems']['Items']) != set(baseline['FrameItems']['Items']):
        raise ValueError('Nebula 추출 오류·프레임/객체 추가 또는 삭제')
    menu = {}
    def visit(items, parent='menu'):
        for index, item in enumerate(items):
            key = f'{parent}/{index}'
            menu[key] = item
            if item['Items']:
                visit(item['Items'], key)
    visit(package['MenuBar']['Items'])
    checked, unsupported = [], []
    for row in inventory:
        kind, location = row['kind'], row['location']
        expected = plan[location]['translated'] if location in plan else row['source']
        if kind == 'paragraph':
            actual = package['FrameItems']['Items'][str(row['object_handle'])]['Properties']['ObjectParagraphs']['Paragraphs'][row['paragraph']]['Value']
        elif kind == 'event_string':
            operation = package['Frames'][row['frame']]['FrameEvents']['Events'][row['event']][row['operation_kind']][int(location.split(row['operation_kind'] + ':')[1].split('/')[0])]
            if (operation['ObjectType'], operation['Num'], operation['ObjectInfo']) != (row['operation_type'], row['operation_number'], row['object_handle']):
                raise ValueError('Nebula 이벤트 소비 위치 변경')
            parameter = operation['Parameters'][row['parameter_index']]['Data']
            if row['expression_index'] is not None:
                actual = parameter['Expressions'][row['expression_index']]['Expression']['Value']
            else:
                actual = parameter['Value']
        elif kind == 'button_text':
            raw = (extracted / f"extension_blobs/{row['object_handle']:04d}.bin").read_bytes()
            actual, end = utf16z(raw, 212)
            if end != 212 + u32(raw, 208) or end + 8 != len(raw):
                raise ValueError('Nebula KcBoxA 문자열 길이 불일치')
        elif kind == 'menu_text':
            item = menu[location]
            actual = item['Name']
            expected = expected.replace('&', '')
            if item['Flags']['Value'] != row['flags'] or item['ID'] != (row['command_id'] or 0):
                raise ValueError('Nebula 메뉴 구조 변경')
        else:
            if location in plan:
                unsupported.append(location)
            continue
        if actual != expected:
            raise ValueError(f'Nebula 위치별 기대값 불일치: {location}')
        checked.append(dict(location=location, expected=expected, actual=actual, translated=location in plan, status='PASS'))
    if any(plan[location]['kind'] not in {'control_key_name', 'dialog_title', 'dialog_item_title'} for location in unsupported):
        raise ValueError('독립 추출에서 예상하지 않은 미지원 번역 필드')
    binary = ROOT / 'tasks/THE_HORDE_OF_GORAK/tools/NebulaExtract/bin/Release/net8.0-windows'
    binary_hashes = {p.name: sha(p.read_bytes()) for p in binary.glob('*.dll')}
    return dict(status='PASS', candidate_dat_sha256=sha((candidate_dir / 'COBALT MINER.dat').read_bytes()),
                translation_sha256=sha(Path(translation_path).read_bytes()), package_sha256=sha((extracted / 'package.json').read_bytes()),
                summary=summary, checked_positions=len(checked), translated_positions=sum(r['translated'] for r in checked),
                unsupported_controls=len(unsupported), unsupported_locations=unsupported, tool_binary_sha256=binary_hashes,
                note='225D의47개 표준 Windows 필드는 Nebula 미지원. 별도 원시 자원 파서의 위치·구조 검사에 연결. 실제 실행 DLL 지문이며 Program.cs 소스와 동일 빌드라는 주장은 하지 않음',
                graphics_qa='NOT_RUN'), checked

def validate(candidate_dir, translation_path=TRANSLATIONS, native_source=NATIVE, native_expected=NATIVE_EXPECTED, native_inventory=None, media_manifest=None):
    candidate_dir = Path(candidate_dir).resolve()
    if not candidate_dir.is_relative_to(ROOT / 'build_candidate/COBALT_MINER'):
        raise ValueError('후보 경계 밖')
    inventory = read_inventory()
    plan = load_plan(translation_path, inventory)
    original = DatFile.load(SOURCE / 'COBALT MINER.dat')
    candidate = DatFile.load(candidate_dir / 'COBALT MINER.dat')
    dat_report, positions = validate_dat(original, candidate, inventory, plan, media_manifest)
    native_report, native_positions = validate_native(candidate_dir, native_source, native_expected, native_inventory)
    expected_files = {p.relative_to(SOURCE).as_posix(): sha(p.read_bytes()) for p in SOURCE.rglob('*') if p.is_file()}
    baseline_files = {r['path']: r['sha256'] for r in load(BASELINE)['files']}
    if expected_files != baseline_files:
        raise ValueError('고정 기준 목록과 원본 사본의 파일·해시 차이')
    actual_files = {p.relative_to(candidate_dir).as_posix(): sha(p.read_bytes()) for p in candidate_dir.rglob('*') if p.is_file()}
    if set(expected_files) != set(actual_files):
        raise ValueError('원본과 후보의 파일 목록 차이')
    allowed = {'COBALT MINER.dat'} | {r['file'] for r in native_report['files']}
    if any(expected_files[k] != actual_files[k] for k in expected_files if k not in allowed):
        raise ValueError('대상 밖 게임 파일 변경')
    report = dict(status='PASS', scope='텍스트·네이티브 표시 필드·글꼴·명시한 미디어 정적 검사. 실제 그래픽 검수는 별도',
                  candidate_id=candidate_dir.name, source_dat_sha256=SOURCE_HASH, candidate_dat_sha256=sha(candidate.original),
                  translation_sha256=sha(Path(translation_path).read_bytes()), inventory_sha256=sha((CLASSIFICATION / 'inventory.jsonl').read_bytes()),
                  validator_sha256=sha(Path(__file__).read_bytes()), native_expected_sha256=sha(Path(native_expected).read_bytes()),
                  baseline_manifest_sha256=sha(BASELINE.read_bytes()),
                  dat=dat_report, native=native_report, files=actual_files, synthetic_rejections=rejection_checks(),
                  media=dat_report['media']['status'], graphics_qa='NOT_RUN', release='NOT_RUN')
    return report, positions, native_positions

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--translations', type=Path, default=TRANSLATIONS)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--native-source', type=Path, default=NATIVE)
    parser.add_argument('--native-expected', type=Path, default=NATIVE_EXPECTED)
    parser.add_argument('--native-inventory', type=Path)
    parser.add_argument('--media-manifest', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(rejection_checks(), ensure_ascii=False))
        return
    if not args.candidate or not args.output:
        parser.error('--candidate 와 --output 이 필요합니다.')
    output = args.output.resolve()
    if not output.is_relative_to(WORK) or output.exists():
        raise ValueError('새 비공개 검증 출력 경로만 허용')
    report, positions, native_positions = validate(args.candidate, args.translations, args.native_source, args.native_expected, args.native_inventory, args.media_manifest)
    output.mkdir(parents=True)
    for name, value in [('validation.json', report), ('positions.json', positions), ('native_positions.json', native_positions)]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=report['status'], candidate=report['candidate_id'], dat_positions=report['dat']['translated_positions'], native_positions=report['native']['checked_fields'], graphics_qa='NOT_RUN')))

if __name__ == '__main__':
    main()
