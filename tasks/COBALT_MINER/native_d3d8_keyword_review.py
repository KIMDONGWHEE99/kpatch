"""D3D8 FX 상태·값·타입 이름을 현재 원본과 실제 Ghidra 소비 코드로 연결합니다."""
import hashlib
import json
import re
import struct
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
OUT = NATIVE / 'media_keyword_review_02'
INVENTORY = NATIVE / 'native_inventory_v15.jsonl'
INVENTORY_SHA = '121d5686d724478b458b8eaae0214b4a2b7e5a80456a728712667b8141631663'
SOURCE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
FILE = 'Modules/mmf2d3d8.dll'
FILE_SHA = '4b1c79736b8ed90b098aef60a402e4ccf66879be478b54f9f7b821e8dbaae335'
EVIDENCE = OUT / 'rea_d3d8_fx_keyword_tables.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    data = (SOURCE/FILE).read_bytes()
    inventory = INVENTORY.read_bytes()
    if sha(data) != FILE_SHA or sha(inventory) != INVENTORY_SHA:
        raise ValueError('고정한 원본 또는 분류표 지문 변경')
    pe = pefile.PE(data=data)
    relocations = {entry.rva for block in pe.DIRECTORY_ENTRY_BASERELOC for entry in block.entries if entry.type == 3}

    def offset(pointer):
        rva = pointer-pe.OPTIONAL_HEADER.ImageBase
        section = pe.get_section_by_rva(rva)
        if section is None or section.IMAGE_SCN_MEM_EXECUTE:
            raise ValueError('자료 포인터가 실행 명령 또는 파일 밖을 가리킴')
        return pe.get_offset_from_rva(rva)

    def name(pointer, field):
        if pe.get_rva_from_offset(field) not in relocations:
            raise ValueError('문자열 포인터에 HIGHLOW 재배치 항목이 없음')
        start = offset(pointer)
        end = data.index(b'\0', start, start+100)
        source = data[start:end].decode('ascii')
        if not re.fullmatch(r'[A-Za-z0-9_]+', source):
            raise ValueError(f'명령 이름 형식 불일치: {source!r}')
        return {'start': start, 'end': end, 'source': source, 'source_bytes_sha256': sha(data[start:end]),
                'pointer_field': field, 'preferred_va': hex(pointer)}

    tables = {}

    def pairs(start, role):
        if start in tables:
            return tables[start]
        entries = []
        for index in range(500):
            cursor = start+index*8
            pointer, value = struct.unpack_from('<2I', data, cursor)
            if not pointer:
                table = {'id': f'{role}:{start:x}', 'role': role, 'start': start, 'end': cursor+8,
                         'entries': entries, 'terminator': [pointer, value], 'raw_sha256': sha(data[start:cursor+8])}
                tables[start] = table
                return table
            entries.append({**name(pointer, cursor), 'value': value, 'record_offset': cursor})
        raise ValueError('이름/값 표의 널 포인터 종료를 찾지 못함')

    descriptors = []
    for cursor in range(0x64640, 0x650b8, 20):
        values = struct.unpack_from('<5I', data, cursor)
        enum = None
        if values[4]:
            if pe.get_rva_from_offset(cursor+16) not in relocations:
                raise ValueError('값 표 포인터의 PE 재배치 근거 없음')
            enum = pairs(offset(values[4]), 'FX_ENUM_NAME')
        descriptors.append({'id': f'FX_STATE:{cursor:x}', 'record_offset': cursor, 'dwords': list(values),
                            'raw_sha256': sha(data[cursor:cursor+20]), 'name': name(values[0], cursor),
                            'enum_id': enum['id'] if enum else None})
    terminal = struct.unpack_from('<5I', data, 0x650b8)
    if any(terminal):
        raise ValueError('상태 표 종료 레코드 불일치')
    types = pairs(0x63f08, 'FX_TYPE_NAME')
    if [(x['source'], x['value']) for x in types['entries']] != [('DWORD', 0), ('FLOAT', 1), ('VECTOR', 2), ('MATRIX', 3), ('TEXTURE', 4), ('VERTEXSHADER', 5), ('PIXELSHADER', 6), ('STRING', 8)]:
        raise ValueError('타입 표 이름/숫자 대응 변경')

    bundle = json.loads(EVIDENCE.read_text(encoding='utf-8'))
    functions, pseudocode = [], {}
    for procedure in ('0x10011db1', '0x10011870', '0x10011d53'):
        record = next(r for r in bundle['records'] if r.get('operation') == 'procedure_pseudo_code' and r.get('parameters', {}).get('procedure') == procedure)
        if record['provider']['id'] != 'ghidra' or record['subject']['digest']['sha256'] != FILE_SHA or not record['normalized_result']:
            raise ValueError('실제 Ghidra 응답 또는 현재 DLL 지문 불일치')
        functions.append({'procedure': procedure, 'evidence_id': record['evidence_id'], 'provider': record['provider'],
                          'pseudocode_sha256': sha(record['normalized_result'].encode()), 'limitations': record['limitations']})
        pseudocode[procedure] = record['normalized_result']
    checks = {
        '0x10011db1': ['FUN_10011dac', 'ppuVar3 = &PTR_s_ZENABLE_10066040;',
                       '__stricmp(_Str1,*ppuVar3)', 'ppuVar3 = ppuVar3 + 5;',
                       'if (puVar1 == (undefined *)0x0)', '*param_3 = (int)ppuVar3[1];', '*param_4 = (int)ppuVar3[3];'],
        '0x10011870': ['FUN_10011845', 'ppuVar7 = &PTR_s_ZENABLE_10066040;',
                       'ppuVar7 = ppuVar7 + 5;', 'piVar2 = (int *)ppuVar7[4];',
                       '__stricmp((char *)*piVar11,(char *)piVar9[2])', 'piVar11 = piVar11 + 2;',
                       'if (*piVar11 == 0)', 'local_8 = local_8 | piVar11[1];'],
        '0x10011d53': ['FUN_10011d51', 'ppuVar3 = &PTR_s_DWORD_10065908;',
                       '__stricmp(_Str1,*ppuVar3)', 'ppuVar3 = ppuVar3 + 2;',
                       'if (puVar1 == (undefined *)0x0)', '*param_2 = (int)ppuVar3[1];'],
    }
    for procedure, fragments in checks.items():
        if not all(fragment in pseudocode[procedure] for fragment in fragments):
            raise ValueError('실제 함수의 이름 검색·배열 간격·종료·숫자 값 소비가 달라짐')
    functions[0]['observed_use'] = '상태 이름을 __stricmp로 검색하며 5DWORD씩 진행. 이름0에서 실패, 일치 레코드의 타입·연산 정수 필드를 호출자에게 반환.'
    functions[1]['observed_use'] = '5DWORD 상태 설명자의 +16 값 표를 읽고 이름/정수2DWORD 쌍을 __stricmp로 검색. 일치하는 정수를 OR 조합해 DWORD 식의 결과에 기록.'
    functions[2]['observed_use'] = '자료형 이름 표를2DWORD씩 __stricmp로 검색. 이름0에서 실패, 일치한 다음 정수 필드를 반환.'
    proofs = {}
    for descriptor in descriptors:
        proofs.setdefault(descriptor['name']['start'], []).append({'id': descriptor['id'], 'role': 'FX_STATE_NAME', 'name': descriptor['name']})
    for table in tables.values():
        for entry in table['entries']:
            proofs.setdefault(entry['start'], []).append({'id': table['id'], 'role': table['role'], 'name': entry})
    proposals, remaining = [], []
    for row in [json.loads(line) for line in inventory.decode('utf-8').splitlines()]:
        if row['classification'] != 'UNKNOWN':
            continue
        matches = proofs.get(row['file_offset'], []) if row['file'] == FILE else []
        matches = [x for x in matches if x['name']['source'] == row['source'] and x['name']['end']-x['name']['start'] == row['bytes']]
        if not matches:
            remaining.append(row)
            continue
        if row['encoding'] != 'ascii' or row['file_sha256'] != FILE_SHA or row['source_bytes_sha256'] != sha(data[row['file_offset']:row['file_offset']+row['bytes']]):
            raise ValueError('제안 문자열의 인코딩·현재 위치 지문 불일치')
        proposals.append({**row, 'classification': 'INTERNAL', 'proposal_only': True,
                          'reason': 'D3D8 FX 명령 해석기의 상태·값·자료형 식별자. 현재 원본의 정확한 이름 위치·포인터 표·정수 대응과 실제 Ghidra의 __stricmp 검색 및 정수 결과 소비를 연결함. 자연어 진단은 제외 범위에 포함하지 않음.',
                          'keyword_evidence_ids': sorted({x['id'] for x in matches}),
                          'keyword_roles': sorted({x['role'] for x in matches}),
                          'keyword_review_evidence': str((OUT/'structures.json').relative_to(ROOT))})
    dependencies = {'inventory': str(INVENTORY.relative_to(ROOT)), 'inventory_sha256': INVENTORY_SHA,
                    'source_file': FILE, 'source_sha256': FILE_SHA, 'script_sha256': sha(Path(__file__).read_bytes()),
                    'rea_evidence': str(EVIDENCE.relative_to(ROOT)), 'rea_evidence_sha256': sha(EVIDENCE.read_bytes())}
    structures = {'dependencies': dependencies, 'functions': functions, 'descriptors': descriptors,
                  'descriptor_terminator': {'file_offset': 0x650b8, 'dwords': list(terminal)}, 'name_value_tables': list(tables.values()),
                  'scope': '현재 원본의 이름 표에 정확히 일치하는 v15 UNKNOWN만 제안. 공유 분류표 미수정.'}
    for filename, value in [('structures.json', structures), ('classification_proposals.json', {'dependencies': dependencies, 'proposals': proposals}), ('remaining_unknown.json', {'dependencies': dependencies, 'rows': remaining})]:
        (OUT/filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {**dependencies, 'status': 'PROPOSAL_READY', 'proposed_internal': len(proposals), 'remaining_unknown': len(remaining),
               'descriptors': len(descriptors), 'name_value_tables': len(tables),
               'proposal_sha256': sha((OUT/'classification_proposals.json').read_bytes()),
               'structures_sha256': sha((OUT/'structures.json').read_bytes()), 'shared_inventory_modified': False}
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
