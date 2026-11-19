"""미분류 숫자 후보를 전체 수학 표·SDK 자료 구조와 대조해 별도 제안을 만듭니다."""
from __future__ import annotations

import collections
import hashlib
import json
import math
import re
import struct
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
NATIVE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
OUT = NATIVE / 'media_numeric_review_02'
PREVIOUS = NATIVE / 'media_numeric_review_01/classification_proposals.json'
INPUT = NATIVE / 'native_inventory_v8.jsonl'
SDK = Path('C:/Program Files (x86)/Windows Kits/10/Source/10.0.22621.0/ucrt')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    OUT.mkdir(exist_ok=True)
    rows = [json.loads(line) for line in INPUT.read_text(encoding='utf-8').splitlines()]
    groups = read_json(NATIVE / 'unknown_groups.json')
    group = next(g for g in groups['groups'] if g['id'] == 'numeric_or_table_candidates')
    keys = {(r['file'], r['file_offset'], r['source_bytes_sha256']) for r in group['rows']}
    targets = [r for r in rows if r['classification'] == 'UNKNOWN' and (r['file'], r['file_offset'], r['source_bytes_sha256']) in keys]
    previous = read_json(PREVIOUS)
    already_proposed = {(r['file'], r['file_offset'], r['source_bytes_sha256']) for r in previous['proposals']}
    targets = [r for r in targets if (r['file'], r['file_offset'], r['source_bytes_sha256']) not in already_proposed]
    files = {name: (BASE / name).read_bytes() for name in {r['file'] for r in targets}}
    parsers = {name: pefile.PE(data=data) for name, data in files.items()}
    for row in targets:
        data = files[row['file']]
        if sha(data) != row['file_sha256'] or sha(data[row['file_offset']:row['file_offset'] + row['bytes']]) != row['source_bytes_sha256']:
            raise ValueError('원본 위치/파일 지문 불일치')
    structures = []

    def add(kind, file, start, end, reason, evidence):
        selected = [r for r in targets if r['file'] == file and start <= r['file_offset'] and r['file_offset'] + r['bytes'] <= end]
        if not selected:
            return
        structures.append({'id': f'{kind}:{file}:{start:x}', 'type': kind, 'file': file,
                           'file_sha256': sha(files[file]), 'start': start, 'end': end,
                           'raw_sha256': sha(files[file][start:end]), 'reason': reason,
                           'evidence': evidence, 'covered_offsets': [r['file_offset'] for r in selected]})

    # Ghidra 실제 응답을 현재 DLL 지문·배열 주소와 함께 연결합니다.
    ghidra_path = NATIVE / 'rea_d3d9_numeric_consumers.json'
    ghidra = read_json(ghidra_path)
    record = next(r for r in ghidra['records'] if r.get('parameters', {}).get('procedure') == '0x100046d3')
    file = 'Modules/mmf2d3d9.dll'
    if record['provider']['id'] != 'ghidra' or record['subject']['digest']['sha256'] != sha(files[file]):
        raise ValueError('Ghidra 응답과 현재 DLL 불일치')
    pseudo = record['normalized_result']
    if not all(t in pseudo for t in ('DAT_100ddf90', 'DAT_100de798', 'DAT_100de79c', 'DAT_100de7a0', '* 0xc', '(float10)*(float *)')):
        raise ValueError('수치 소비 응답의 필수 관계 불일치')
    pe, data = parsers[file], files[file]
    vector_start = pe.get_offset_from_rva(0xde798)
    vector_count = 514
    values = struct.unpack_from('<' + 'f' * vector_count * 3, data, vector_start)
    norms = [sum(x*x for x in values[i:i+3]) for i in range(0, len(values), 3)]
    # 성분은 소수점 여섯 자리 상수를 float로 저장한 값입니다. 세 성분의 반올림 오차 상한을 적용합니다.
    if not all(math.isfinite(x) and struct.pack('<f', x) == struct.pack('<f', round(x, 6)) for x in values) or max(abs(n-1) for n in norms) > 3.2e-6:
        raise ValueError('단위 벡터 전체 수학 관계 불일치')
    raw = data[vector_start:vector_start + vector_count * 12]
    if raw[:256*12] != raw[256*12:512*12] or raw[:24] != raw[512*12:]:
        raise ValueError('벡터 반복 구조 불일치')
    consumer = {'path': str(ghidra_path.relative_to(ROOT)), 'sha256': sha(ghidra_path.read_bytes()),
                'evidence_id': record['evidence_id'], 'provider': record['provider'],
                'procedure': 'FUN_100045cc', 'queried_address': '0x100046d3',
                'meaning': '정수 인덱스×12로 float 3성분을 읽어 좌표와 내적하고 보간함. 문자열 출력 소비가 아님.'}
    add('NOISE_UNIT_VECTOR_TABLE', file, vector_start, vector_start + vector_count * 12,
        '514개 float3 전체가 단위벡터이며 256개 두 번과 처음 2개의 반복 구조. 현재 DLL의 Ghidra 함수가 이 주소를 수치 내적·보간으로 소비함.',
        {'vectors': vector_count, 'max_squared_norm_error': max(abs(n-1) for n in norms),
         'squared_norm_error_limit': 3.2e-6, 'decimal_precision': 6,
         'repetition': [256, 256, 2], 'consumer': consumer})
    index_start = pe.get_offset_from_rva(0xddf90)
    indices = struct.unpack_from('<514I', data, index_start)
    if not all(0 <= n <= 255 for n in indices) or indices[:256] != indices[256:512] or indices[:2] != indices[512:]:
        raise ValueError('노이즈 인덱스 표 전체 관계 불일치')
    add('NOISE_INDEX_TABLE', file, index_start, index_start + 514 * 4,
        '0..255 정수 514항의 반복 인덱스 표. Ghidra 함수가 &0xff 좌표와 표 값을 주소 계산에 사용함. 중복값이 있어 완전한 순열이라고 단정하지 않음.',
        {'elements': 514, 'repetition': [256, 256, 2], 'consumer': consumer})

    # 256개 전체를 독립 공식으로 계산하고 단정밀도 반올림 오차를 비교합니다.
    old_path = ROOT / 'working_private/THE_HORDE_OF_GORAK/investigation_20261031/native_numeric_reads_disasm.json'
    old = read_json(old_path)['trig']['instructions']
    checked = []
    for item in old:
        offset = pe.get_offset_from_rva(int(item['address'], 16) - pe.OPTIONAL_HEADER.ImageBase)
        payload = bytes.fromhex(item['bytes'])
        if data[offset:offset + len(payload)] != payload:
            raise ValueError('보존된 수치 보간 명령과 현재 DLL 불일치')
        checked.append({'address': item['address'], 'bytes': item['bytes']})
    for rva, exponent in ((0xeca38, 10/11), (0xece38, 11/10)):
        start = pe.get_offset_from_rva(rva)
        values = struct.unpack_from('<256f', data, start)
        expected = [struct.unpack('<f', struct.pack('<f', (min(i, 254) / 254) ** exponent))[0] for i in range(256)]
        maximum = max(abs(a-b) for a, b in zip(values, expected))
        if maximum > 2**-22 or values[0] != 0 or values[254:] != (1, 1) or not all(a <= b for a, b in zip(values, values[1:])):
            raise ValueError('거듭제곱 표 전체 관계 불일치')
        add('POWER_FUNCTION_TABLE', file, start, start+1024,
            '256개 float 전부가 (min(i,254)/254)^지수의 독립 계산과 단정밀도 오차 이내 일치하며 단조 증가·끝값도 일치. 현재 바이트가 보존된 float 보간 소비 명령과 일치.',
            {'elements': 256, 'formula': '(min(i,254)/254)^exponent', 'exponent': exponent,
             'max_absolute_error': maximum, 'limit': 2**-22,
             'consumer_path': str(old_path.relative_to(ROOT)), 'consumer_sha256': sha(old_path.read_bytes()),
             'verified_instructions': checked,
             'consumer_limit': '이 보존 소비 자료는 기존 디스어셈블 결과이며 Ghidra 응답이라고 표시하지 않음. 전체 수학 관계가 독립 주근거.'})

    # 현재 SDK가 공개하는 상태/문자 종류 쌍을 그대로 패킹하여 전체 91바이트를 찾습니다.
    printf_path = SDK / 'inc/corecrt_internal_stdio_output.h'
    printf_source = printf_path.read_text(encoding='utf-8-sig')
    body = printf_source.split('format_validation_lookup_table_spectre', 1)[1].split('};', 1)[0]
    pairs = re.findall(r'state::(\w+),.*?character_type::(\w+)', body)
    states = ['normal', 'percent', 'flag', 'width', 'dot', 'precision', 'size', 'type', 'invalid']
    classes = ['other', 'percent', 'dot', 'star', 'zero', 'digit', 'flag', 'size', 'type']
    packed = bytes(states.index(a) << 4 | classes.index(b) for a, b in pairs)
    if len(packed) != 91:
        raise ValueError('SDK 상태 표 항목 수 변경')
    for file, data in files.items():
        cursor = 0
        while True:
            start = data.find(packed, cursor)
            if start < 0:
                break
            cursor = start + len(packed)
            add('PRINTF_VALIDATION_STATE_TABLE', file, start, cursor,
                'SDK format_validation_lookup_table_spectre의 91개 상태·문자종류 쌍과 전체 바이트 일치. printf 서식 검증기의 문자 종류와 다음 상태를 담은 패킹 자료.',
                {'source_path': str(printf_path), 'source_sha256': sha(printf_path.read_bytes()),
                 'symbol': 'format_validation_lookup_table_spectre', 'encoding': 'next_state<<4 | current_class',
                 'pairs': pairs, 'full_byte_match': True})

    # 포인터를 역참조한 문자열까지 SDK의 228항 두 표와 모두 대조합니다.
    locale_path = SDK / 'locale/lcidtoname_downlevel.cpp'
    locale_source = locale_path.read_text(encoding='utf-8-sig')
    a = locale_source.split('LcidToLocaleNameTable[]', 1)[1].split('};', 1)[0]
    lcid_pairs = [(int(code, 16), name) for code, name in re.findall(r'\{\s*(0x[\dA-Fa-f]+),\s*L"([^"]*)"\s*\}', a)]
    b = locale_source.split('LocaleNameToIndexTable[]', 1)[1].split('};', 1)[0]
    name_pairs = [(name, int(index)) for name, index in re.findall(r'\{\s*L"([^"]*)"\s*,\s*(\d+)\s*\}', b)]
    if len(lcid_pairs) != 228 or len(name_pairs) != 228:
        raise ValueError('SDK locale 표 항목 수 변경')
    file = 'Modules/steam_api.dll'
    data, pe = files[file], parsers[file]
    for kind, start, pairs in [('LCID_TO_NAME_TABLE', 0x1afb8, lcid_pairs), ('LOCALE_NAME_TO_INDEX_TABLE', 0x1b6d8, name_pairs)]:
        actual = []
        for index, pair in enumerate(pairs):
            x, y = struct.unpack_from('<II', data, start + index * 8)
            numeric, name, pointer = (x, pair[1], y) if kind == 'LCID_TO_NAME_TABLE' else (y, pair[0], x)
            expected_number = pair[0] if kind == 'LCID_TO_NAME_TABLE' else pair[1]
            target = pe.get_offset_from_rva(pointer - pe.OPTIONAL_HEADER.ImageBase)
            encoded = (name + '\0').encode('utf-16le')
            if not 0 <= target <= len(data)-len(encoded) or numeric != expected_number or data[target:target+len(encoded)] != encoded:
                raise ValueError('SDK locale 표/포인터 대상 불일치')
            actual.append({'index': index, 'number': numeric, 'name': name, 'pointer': hex(pointer),
                           'string_file_offset': target, 'string_bytes_sha256': sha(encoded)})
        add(kind, file, start, start+len(pairs)*8,
            'SDK의 Windows XP 언어 코드/이름 변환 표 228항과 순서·숫자·포인터 대상 UTF-16 문자열까지 전부 일치. 문자열로 오인한 구간은 실제로 32비트 정수·주소 필드.',
            {'source_path': str(locale_path), 'source_sha256': sha(locale_path.read_bytes()),
             'entries': actual, 'record_size': 8, 'full_entry_match': True})

    # Win32/소켓 오류 코드와 메시지 주소로 이루어진 레코드입니다. 메시지 본문은 포함하지 않습니다.
    relocation_slots = {pe.get_offset_from_rva(entry.rva) for block in pe.DIRECTORY_ENTRY_BASERELOC
                        for entry in block.entries if entry.type == 3}
    start, end = 0x1e220, 0x1e470
    error_rows = []
    for position in range(start, end, 8):
        code, pointer = struct.unpack_from('<II', data, position)
        target = pe.get_offset_from_rva(pointer-pe.OPTIONAL_HEADER.ImageBase)
        if position+4 not in relocation_slots or position in relocation_slots or not 0 < code < 65536 or not 0 <= target < len(data):
            raise ValueError('오류 표의 정수/주소 필드 형식 불일치')
        finish = data.find(b'\0', target, target+150)
        if finish < target or not all(32 <= c <= 126 for c in data[target:finish]):
            raise ValueError('오류 표의 메시지 주소 대상 불일치')
        section = pe.get_section_by_rva(pointer-pe.OPTIONAL_HEADER.ImageBase)
        if section is None or section.Characteristics & 0x20000000:
            raise ValueError('메시지 주소가 비실행 자료 구역이 아님')
        error_rows.append({'entry_offset': position, 'numeric_code': code, 'pointer_slot': position+4,
                           'pointer': hex(pointer), 'pointer_relocation_type': 'IMAGE_REL_BASED_HIGHLOW',
                           'message_offset': target, 'message_bytes_sha256': sha(data[target:finish]),
                           'message_preview': data[target:finish].decode('ascii')})
    if data[end:end+8] != bytes(8) or len(error_rows) != 74:
        raise ValueError('오류 표 종료 구조 불일치')
    add('ERROR_CODE_MESSAGE_POINTER_TABLE', file, start, end,
        '74개 레코드가 32비트 오류 코드와 실제 PE HIGHLOW 재배치 주소의 8바이트 쌍이며 모든 주소가 유효한 ASCII 메시지를 가리킴. 이 후보 바이트는 정수/포인터 필드 자체이고 메시지 본문은 별도 유지·검토함.',
        {'record_size': 8, 'records': error_rows, 'terminator_offset': end, 'terminator_hex': data[end:end+8].hex(),
         'scope_limit': '메시지 문자열 본문이나 메시지 표시 가능성을 INTERNAL로 판정하지 않음'})

    # 8×8 격자의 대각선 왕복 순서를 계산합니다. 확장 15항은 마지막 칸63으로 고정됩니다.
    order = []
    for diagonal in range(15):
        coordinates = [(y, diagonal-y) for y in range(8) if 0 <= diagonal-y < 8]
        if diagonal % 2 == 0:
            coordinates.reverse()
        order.extend(y*8+x for y, x in coordinates)
    if sorted(order) != list(range(64)):
        raise ValueError('격자 순서 독립 계산 실패')
    scan_table = bytes(order + [63]*15)
    png_magic = b'\x89PNG\r\n\x1a\n'
    for file, data in files.items():
        for kind, raw, reason, details in [
            ('ZIGZAG_GRID_ORDER_TABLE', scan_table, '8×8 격자 64칸을 대각선 왕복하는 정수 순서를 독립 계산한 전체79바이트와 일치. 뒤15항은 마지막 칸63으로 고정된 범위 보정 값이며 문장이 아님.',
             {'grid': [8, 8], 'elements': 79, 'order': order, 'tail': [63]*15}),
            ('PNG_BINARY_SIGNATURE', png_magic, 'PNG 이진 파일 식별자 전체8바이트(선두0x89, CR/LF 및0x1a 포함)와 일치. 표시용 PNG 명칭과 구별되는 파일 형식 식별 바이트.',
             {'signature_hex': png_magic.hex(), 'reference_file': str((ROOT/'working_private/COBALT_MINER/media_ko_02/01123.png').relative_to(ROOT)),
              'reference_file_sha256': sha((ROOT/'working_private/COBALT_MINER/media_ko_02/01123.png').read_bytes())})]:
            cursor = 0
            while True:
                position = data.find(raw, cursor)
                if position < 0:
                    break
                cursor = position+len(raw)
                add(kind, file, position, cursor, reason, details)

    proposed, remaining = [], []
    for row in targets:
        proofs = [p for p in structures if p['file'] == row['file'] and p['start'] <= row['file_offset'] and row['file_offset']+row['bytes'] <= p['end']]
        if proofs:
            proposed.append({**row, 'classification': 'INTERNAL', 'reason': proofs[0]['reason'],
                             'proposal_only': True, 'numeric_evidence_ids': [p['id'] for p in proofs],
                             'numeric_review_evidence': str((OUT / 'structures.json').relative_to(ROOT))})
        else:
            remaining.append(row)
    dependency = {'input_inventory': str(INPUT.relative_to(ROOT)), 'input_sha256': sha(INPUT.read_bytes()),
                  'previous_proposals': str(PREVIOUS.relative_to(ROOT)), 'previous_proposals_sha256': sha(PREVIOUS.read_bytes()),
                  'unknown_group_input_sha256': sha((NATIVE / 'unknown_groups.json').read_bytes()),
                  'script_sha256': sha(Path(__file__).read_bytes()), 'scope': 'numeric_or_table_candidates와 v8 UNKNOWN 교집합만. 공유 분류표 미수정.'}
    for name, value in [('structures.json', {'dependencies': dependency, 'structures': structures}),
                        ('classification_proposals.json', {'dependencies': dependency, 'proposals': proposed}),
                        ('remaining_unknown.json', {'dependencies': dependency, 'rows': remaining})]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {**dependency, 'status': 'PROPOSAL_READY', 'targets': len(targets), 'proposed_internal': len(proposed),
               'remaining_unknown': len(remaining), 'by_type': dict(collections.Counter(next(p['type'] for p in structures if p['id'] == r['numeric_evidence_ids'][0]) for r in proposed)),
               'proposal_sha256': sha((OUT / 'classification_proposals.json').read_bytes()),
               'structures_sha256': sha((OUT / 'structures.json').read_bytes()), 'shared_inventory_modified': False}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
