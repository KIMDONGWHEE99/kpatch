"""실제 Ghidra 소비 코드와 원본 FX 명령 표에 연결된 문자열만 분류 제안합니다."""
import hashlib
import json
import re
import struct
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
SOURCE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
OUT = NATIVE / 'media_keyword_review_01'
INVENTORY = NATIVE / 'native_inventory_v11.jsonl'
INVENTORY_SHA = '199ba6bf72f220bafb91c37cac873e2cf8a1efcca100f066fc52a79e1891dd2f'
FILE = 'Modules/mmf2d3d9.dll'
FILE_SHA = '4971b2294b825196a628a0a6855a14db99b491c66f39b046055f39b6dfbfc110'
EVIDENCE = OUT / 'rea_d3d9_fx_keyword_tables.json'
SDK = Path('C:/Program Files (x86)/Windows Kits/10/Include/10.0.22621.0/shared/d3d9types.h')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    inventory_data = INVENTORY.read_bytes()
    data = (SOURCE / FILE).read_bytes()
    if sha(inventory_data) != INVENTORY_SHA or sha(data) != FILE_SHA:
        raise ValueError('고정한 입력 지문 변경')
    rows = [json.loads(line) for line in inventory_data.decode('utf-8').splitlines()]
    pe = pefile.PE(data=data)
    relocations = {entry.rva for block in pe.DIRECTORY_ENTRY_BASERELOC for entry in block.entries if entry.type == 3}
    image_base = pe.OPTIONAL_HEADER.ImageBase

    def offset(pointer):
        rva = pointer-image_base
        section = pe.get_section_by_rva(rva)
        if section is None or section.IMAGE_SCN_MEM_EXECUTE:
            raise ValueError('자료 표 포인터가 자료 영역 밖임')
        return pe.get_offset_from_rva(rva)

    def text_pointer(pointer, pointer_field):
        if pe.get_rva_from_offset(pointer_field) not in relocations:
            raise ValueError('문자열 포인터의 PE 주소 재배치 근거 누락')
        start = offset(pointer)
        end = data.index(b'\0', start, start+100)
        text = data[start:end].decode('ascii')
        if not re.fullmatch(r'\$?[A-Za-z0-9_]+', text):
            raise ValueError(f'명령 식별자 형식에 맞지 않는 문자열: {text!r} @ {start:x}')
        return {'start': start, 'end': end, 'source': text, 'source_bytes_sha256': sha(data[start:end]),
                'preferred_va': hex(pointer), 'pointer_field': pointer_field}

    tables = {}

    def enum_table(pointer):
        if not pointer:
            return None
        start = offset(pointer)
        if start in tables:
            return tables[start]
        entries = []
        for index in range(500):
            cursor = start+index*8
            name_ptr, value = struct.unpack_from('<2I', data, cursor)
            if not name_ptr:
                table = {'id': f'FX_ENUM:{start:x}', 'start': start, 'end': cursor+8,
                         'entries': entries, 'terminator': [name_ptr, value],
                         'raw_sha256': sha(data[start:cursor+8]), 'preferred_va': hex(pointer)}
                tables[start] = table
                return table
            entries.append({**text_pointer(name_ptr, cursor), 'value': value, 'record_offset': cursor})
        raise ValueError('값 이름 표 종료 포인터를 찾지 못함')

    descriptors = []
    for cursor in range(0xe01b8, 0xe15a0, 28):
        values = struct.unpack_from('<7I', data, cursor)
        duplicate_cursor = cursor+0x9580
        duplicate_values = struct.unpack_from('<7I', data, duplicate_cursor)
        name = text_pointer(values[0], cursor)
        duplicate_name = text_pointer(duplicate_values[0], duplicate_cursor)
        enum = enum_table(values[6])
        duplicate_enum = enum_table(duplicate_values[6])
        if name['source'] != duplicate_name['source'] or values[1:6] != duplicate_values[1:6]:
            raise ValueError('명령 표 복제본의 이름/메타데이터 불일치')
        enum_values = None if enum is None else [(x['source'], x['value']) for x in enum['entries']]
        duplicate_enum_values = None if duplicate_enum is None else [(x['source'], x['value']) for x in duplicate_enum['entries']]
        if enum_values != duplicate_enum_values:
            raise ValueError('명령 표 복제본의 값 이름/정수 대응 불일치')
        for field, pointer in [(cursor+24, values[6]), (duplicate_cursor+24, duplicate_values[6])]:
            if pointer and pe.get_rva_from_offset(field) not in relocations:
                raise ValueError('값 표 포인터의 PE 주소 재배치 근거 누락')
        descriptors.append({'id': f'FX_STATE:{cursor:x}', 'record_offset': cursor,
                            'raw_sha256': sha(data[cursor:cursor+28]), 'dwords': list(values), 'name': name,
                            'enum_id': enum['id'] if enum else None,
                            'duplicate_record_offset': duplicate_cursor, 'duplicate_name': duplicate_name,
                            'duplicate_enum_id': duplicate_enum['id'] if duplicate_enum else None,
                            'duplicate_logical_fields_match': True})

    # 코드의 첫 포인터 0 종료 조건과 자료의 실제 경계를 맞춥니다.
    terminators = []
    for cursor in (0xe15a0, 0xe15a0+0x9580):
        values = struct.unpack_from('<7I', data, cursor)
        if values[0] != 0:
            raise ValueError('명령 표의 널 이름 종료 레코드 누락')
        terminators.append({'record_offset': cursor, 'dwords': list(values), 'raw_sha256': sha(data[cursor:cursor+28])})

    # FVF 텍스처 좌표 크기 4의 여덟 항목은 설치된 SDK의 계산식과도 별도로 대조합니다.
    sdk_data = SDK.read_bytes()
    sdk = sdk_data.decode('utf-8-sig')
    if not re.search(r'#define\s+D3DFVF_TEXTUREFORMAT4\s+2\b', sdk):
        raise ValueError('SDK 텍스처 형식 상수 변경')
    if not re.search(r'#define\s+D3DFVF_TEXCOORDSIZE4\(CoordIndex\)\s+\(D3DFVF_TEXTUREFORMAT4\s*<<\s*\(CoordIndex\*2\s*\+\s*16\)\)', sdk):
        raise ValueError('SDK 텍스처 좌표 크기 계산식 변경')
    fvf = tables[0xdfff0]
    sdk_comparisons = []
    for index in range(8):
        entry = next(x for x in fvf['entries'] if x['source'] == f'TEXCOORDSIZE4_{index}')
        expected = 2 << (index*2+16)
        if entry['value'] != expected:
            raise ValueError('SDK의 텍스처 좌표 크기 값 불일치')
        sdk_comparisons.append({'source': entry['source'], 'actual': entry['value'], 'expected': expected})

    bundle = json.loads(EVIDENCE.read_text(encoding='utf-8'))
    functions = []
    for procedure in ('0x10013fb3', '0x10016b9b'):
        record = next(x for x in bundle['records'] if x.get('operation') == 'procedure_pseudo_code' and x.get('parameters', {}).get('procedure') == procedure)
        if record['provider']['id'] != 'ghidra' or record['subject']['digest']['sha256'] != FILE_SHA or not record['normalized_result']:
            raise ValueError('Ghidra 실제 응답/입력 지문 불일치')
        functions.append({'procedure': procedure, 'evidence_id': record['evidence_id'], 'provider': record['provider'],
                          'pseudocode_sha256': sha(record['normalized_result'].encode()),
                          'limitations': record['limitations']})

    # 실제 응답을 판독해 확인한 주소·간격·문자열 비교·종료·값 사용을 고정합니다.
    lookup = next(x['normalized_result'] for x in bundle['records'] if x.get('parameters', {}).get('procedure') == '0x10016b9b' and x.get('operation') == 'procedure_pseudo_code')
    enum_lookup = next(x['normalized_result'] for x in bundle['records'] if x.get('parameters', {}).get('procedure') == '0x10013fb3' and x.get('operation') == 'procedure_pseudo_code')
    expected_lookup = ['FUN_10016aaf', 'ppuVar10 = &PTR_s_ZENABLE_100e19b8;',
                       '__stricmp(*ppuVar8,*(char **)(iVar5 + 0x18))', 'ppuVar8 = ppuVar8 + 7;',
                       'ppuVar10 = ppuVar10 + param_1 * 7;', 'if (*ppuVar10 == (undefined *)0x0)',
                       'Unrecognized state', 'FUN_10012729(pvVar6,param_1,local_8']
    expected_enum = ['FUN_1001371a', 'param_4 = &PTR_PTR_100e19d0 + (int)param_1 * 7;',
                     '__stricmp((char *)piVar5[param_3 * 2],*(char **)(iVar10 + 0x18))',
                     'if (*(int *)(*param_4 + param_3 * 8) == 0)',
                     'uVar9 = *(uint *)((int)(*param_4 + param_3 * 8) + 4);',
                     'param_8 = (float)((uint)param_8 | uVar9);', 'does not accept', 'FVFs must not evaluate to NULL']
    if not all(x in lookup for x in expected_lookup) or not all(x in enum_lookup for x in expected_enum):
        raise ValueError('명령 이름/값 이름의 실제 검색·소비 경로가 달라짐')
    functions[0]['observed_use'] = 'FUN_1001371a: 상태 번호×7DWORD+24의 값 표 포인터를 읽고, 8바이트 이름/값 쌍에서 __stricmp로 검색해 +4 DWORD를 읽어 OR 조합. 이름 포인터0은 실패 경계.'
    functions[1]['observed_use'] = 'FUN_10016aaf: 0x100e19b8의 첫 이름 포인터를 __stricmp로 검색하고 7DWORD(28바이트)씩 진행. 널 이름은 미지원 상태 오류, 일치 항목 번호·형식·인덱스를 컴파일된 상태 객체에 기록.'

    proofs = {}
    for descriptor in descriptors:
        for key in ('name', 'duplicate_name'):
            name = descriptor[key]
            proofs.setdefault(name['start'], []).append({'id': descriptor['id'], 'role': 'FX_STATE_NAME', 'name': name})
    for table in tables.values():
        for name in table['entries']:
            proofs.setdefault(name['start'], []).append({'id': table['id'], 'role': 'FX_ENUM_NAME', 'name': name})
    proposals, remaining = [], []
    for row in rows:
        if row['classification'] != 'UNKNOWN':
            continue
        matches = proofs.get(row['file_offset'], []) if row['file'] == FILE else []
        matches = [x for x in matches if x['name']['source'] == row['source'] and x['name']['end']-x['name']['start'] == row['bytes']]
        if not matches:
            remaining.append(row)
            continue
        if row['encoding'] != 'ascii' or row['file_sha256'] != FILE_SHA or row['source_bytes_sha256'] != sha(data[row['file_offset']:row['file_offset']+row['bytes']]):
            raise ValueError('제안 문자열의 현재 위치/인코딩/지문 불일치')
        reason = 'FX 그래픽 명령 해석기의 이름 검색 표에 등록된 식별자. 실제 Ghidra 응답의 표 소비와 현재 원본의 포인터·정수 대응을 연결했으며 자연어 오류 문구는 범위에 포함하지 않음.'
        proposals.append({**row, 'classification': 'INTERNAL', 'reason': reason, 'proposal_only': True,
                          'keyword_evidence_ids': sorted({x['id'] for x in matches}),
                          'keyword_roles': sorted({x['role'] for x in matches}),
                          'keyword_review_evidence': str((OUT/'structures.json').relative_to(ROOT))})
    dependencies = {'inventory': str(INVENTORY.relative_to(ROOT)), 'inventory_sha256': INVENTORY_SHA,
                    'source_file': FILE, 'source_sha256': FILE_SHA, 'script_sha256': sha(Path(__file__).read_bytes()),
                    'rea_evidence': str(EVIDENCE.relative_to(ROOT)), 'rea_evidence_sha256': sha(EVIDENCE.read_bytes())}
    structures = {'dependencies': dependencies, 'functions': functions, 'descriptors': descriptors, 'descriptor_terminators': terminators,
                  'enum_tables': list(tables.values()), 'sdk': {'path': str(SDK), 'sha256': sha(sdk_data), 'comparisons': sdk_comparisons},
                  'limits': '현재 입력 v11 UNKNOWN 중 실제 이름 표의 정확한 문자열 위치만 제안. 인접 자연어·진단 메시지·임의 대문자 문자열 미포함.'}
    for filename, value in [('structures.json', structures), ('classification_proposals.json', {'dependencies': dependencies, 'proposals': proposals}), ('remaining_unknown.json', {'dependencies': dependencies, 'rows': remaining})]:
        (OUT/filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {**dependencies, 'status': 'PROPOSAL_READY', 'proposed_internal': len(proposals), 'remaining_unknown': len(remaining),
               'descriptors': len(descriptors), 'enum_tables_including_duplicates': len(tables),
               'proposal_sha256': sha((OUT/'classification_proposals.json').read_bytes()),
               'structures_sha256': sha((OUT/'structures.json').read_bytes()), 'shared_inventory_modified': False}
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
