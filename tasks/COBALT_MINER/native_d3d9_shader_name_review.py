"""D3D9 어휘 분석 및 셰이더 명령 표의 정확한 이름 위치만 분류 제안합니다."""
import hashlib
import json
import re
import struct
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
OUT = NATIVE / 'media_keyword_review_03'
INVENTORY = NATIVE / 'native_inventory_v15.jsonl'
INVENTORY_SHA = '121d5686d724478b458b8eaae0214b4a2b7e5a80456a728712667b8141631663'
FILE = 'Modules/mmf2d3d9.dll'
FILE_SHA = '4971b2294b825196a628a0a6855a14db99b491c66f39b046055f39b6dfbfc110'
SOURCE = ROOT / 'source_original/COBALT_MINER/steam_24347666' / FILE
EVIDENCE = OUT / 'rea_d3d9_shader_names.json'
LEXER_UNKNOWN_NAMES = set('catch const_cast delete dynamic_cast enum explicit friend goto mutable private protected public pixelshader reinterpret_cast sampler1D sampler2D sampler3D samplerCUBE sampler_state signed sizeof static_cast template texture1D texture2D texture3D textureCUBE this throw typename union using virtual vertexshader decl'.split())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    data = SOURCE.read_bytes()
    inventory = INVENTORY.read_bytes()
    if sha(data) != FILE_SHA or sha(inventory) != INVENTORY_SHA:
        raise ValueError('고정한 입력 지문 변경')
    pe = pefile.PE(data=data)
    relocations = {entry.rva for block in pe.DIRECTORY_ENTRY_BASERELOC for entry in block.entries if entry.type == 3}

    def name_at(pointer, pointer_field):
        if pe.get_rva_from_offset(pointer_field) not in relocations:
            raise ValueError('이름 주소 필드에 PE HIGHLOW 항목 없음')
        rva = pointer-pe.OPTIONAL_HEADER.ImageBase
        section = pe.get_section_by_rva(rva)
        if section is None or section.IMAGE_SCN_MEM_EXECUTE:
            raise ValueError('문자열 포인터가 자료 영역 밖임')
        start = pe.get_offset_from_rva(rva)
        end = data.index(b'\0', start, start+90)
        source = data[start:end].decode('ascii')
        if not re.fullmatch(r'[A-Za-z0-9_.]+', source):
            raise ValueError('원시 명령 이름 형식 불일치')
        return {'source': source, 'start': start, 'end': end, 'preferred_va': hex(pointer),
                'pointer_field': pointer_field, 'source_bytes_sha256': sha(data[start:end])}

    tables = []
    specs = [('SHADER_PROFILE', 0xebf28, 44, 12, '0x1004cadd'),
             ('SHADER_OPCODE', 0xec908, 84, 68, '0x1005fa5a'),
             ('SHADER_COMPARISON_OPCODE', 0xedf58, 2, 72, '0x1005fa5a'),
             ('SHADER_REGISTER', 0xedfe8, 21, 72, '0x10061a4d')]
    for role, start, count, stride, procedure in specs:
        entries = []
        for index in range(count):
            cursor = start+index*stride
            values = struct.unpack_from('<'+'I'*(stride//4), data, cursor)
            entries.append({'record_offset': cursor, 'dwords': list(values), 'name': name_at(values[0], cursor),
                            'raw_sha256': sha(data[cursor:cursor+stride])})
        tables.append({'id': f'{role}:{start:x}', 'role': role, 'start': start, 'end': start+count*stride,
                       'count': count, 'stride': stride, 'raw_sha256': sha(data[start:start+count*stride]),
                       'entries': entries, 'consumer_query': procedure})

    bundle = json.loads(EVIDENCE.read_text(encoding='utf-8'))
    functions, pseudocode = [], {}
    for procedure in ('0x1002118e', '0x1004cadd', '0x1005fa5a', '0x10061a4d'):
        record = next(r for r in bundle['records'] if r.get('operation') == 'procedure_pseudo_code' and r.get('parameters', {}).get('procedure') == procedure)
        if record['provider']['id'] != 'ghidra' or record['subject']['digest']['sha256'] != FILE_SHA or not record['normalized_result']:
            raise ValueError('실제 Ghidra 응답 또는 현재 DLL 지문 불일치')
        functions.append({'query': procedure, 'evidence_id': record['evidence_id'], 'provider': record['provider'],
                          'pseudocode_sha256': sha(record['normalized_result'].encode()), 'limitations': record['limitations']})
        pseudocode[procedure] = record['normalized_result']

    checks = {
        '0x1002118e': ['FUN_100207df', 'FUN_100122ea', 'case 9:',
                       'pcVar3 = *(char **)((int)param_1 + 0x28);', 'bVar9 = *pcVar8 == *pcVar7;',
                       'return 0x151;', 'return 0x108;'],
        '0x1004cadd': ['FUN_1004cab3', 'local_8 = 0x2c;', 'uVar3 = local_8 + uVar5 >> 1;',
                       'pbVar6 = *(byte **)(&UNK_100ed728 + uVar3 * 0xc);',
                       'if (bVar1 != *pbVar7)', 'param_3[1] = *(undefined4 *)(&UNK_100ed72c + iVar4);',
                       'param_3[2] = *(undefined4 *)(&DAT_100ed730 + iVar4);'],
        '0x1005fa5a': ['FUN_1005f9a1', 'pbVar9 = *(byte **)((int)&PTR_DAT_100ee108 + uVar3);',
                       'uVar3 = uVar3 + 0x44;', 'while (uVar3 < 0x1650);', 'if (iVar8 == 0x54)',
                       'local_44 = (&DAT_100ee10c)[iVar8 * 0x11];',
                       '(&DAT_100ef760 + *(int *)((int)local_14 + 0x38) * 4)',
                       '(&DAT_100ef7a8 + *(int *)((int)local_14 + 0x38) * 4)',
                       'local_44 = 0x29;', 'local_44 = 0x2d;'],
        '0x10061a4d': ['FUN_10061919', 'pbVar9 = *(byte **)((int)&PTR_DAT_100ef7e8 + uVar2);',
                       'uVar2 = uVar2 + 0x48;', 'while (uVar2 < 0x5e8);', 'if (iVar3 != 0x15)',
                       'local_c = (&DAT_100ef7ec)[iVar3 * 0x12];',
                       'local_2c = (&DAT_100ef82c)[iVar3 * 0x12];',
                       'FUN_1009d10a(pvVar5,local_c,local_14,local_8,local_2c,0)'],
    }
    for query, fragments in checks.items():
        if not all(fragment in pseudocode[query] for fragment in fragments):
            raise ValueError(f'실제 이름 비교·표 간격·상한·반환 경계 불일치: {query}')
    functions[0]['observed_use'] = '입력 토큰의 식별자 문자열을 예약어와 비교해 문법 토큰 번호 또는 예약된 미지원 토큰0x151을 반환. 자연어 진단 출력은 이 이름 집합에 없음.'
    functions[1]['observed_use'] = '44개 이름/버전/플래그3DWORD 레코드를 이름의 바이트 비교로 이진 검색하고 일치한 레코드를 호출자에게 반환.'
    functions[2]['observed_use'] = '84개68바이트 명령 레코드를 이름으로 검색해 opcode와 프로필별 피연산자 제약을 읽음. if/break 비교형은 별도2개 설명자의+8 제약을 읽고 opcode41/45로 변환.'
    functions[3]['observed_use'] = '21개72바이트 레지스터 설명자를 이름으로 검색하고 종류·번호 한계·플래그를 읽어 셰이더 레지스터 객체 생성.'

    profile_names = [entry['name']['source'] for entry in tables[0]['entries']]
    if profile_names != sorted(profile_names) or len(set(profile_names)) != 44:
        raise ValueError('프로필 이진 검색 표의 정렬/중복 불일치')
    if tables[2]['entries'][0]['dwords'][1] != 0x29 or tables[2]['entries'][1]['dwords'][1] != 0x2d:
        raise ValueError('비교 명령 설명자의 opcode 값 불일치')
    # 현재 원본 코드의 즉시 문자열 주소와 실제 함수 안의 리터럴을 함께 확인합니다.
    lexer = []
    for rva in sorted(relocations):
        if not 0x207df <= rva < 0x212a6:
            continue
        field = pe.get_offset_from_rva(rva)
        pointer = struct.unpack_from('<I', data, field)[0]
        section = pe.get_section_by_rva(pointer-pe.OPTIONAL_HEADER.ImageBase)
        if section is None or section.IMAGE_SCN_MEM_EXECUTE:
            continue
        try:
            text = name_at(pointer, field)
        except ValueError:
            continue
        if text['source'] not in LEXER_UNKNOWN_NAMES:
            continue
        if data[field-1] not in (0xbf, 0x68) or '"'+text['source']+'"' not in pseudocode['0x1002118e']:
            raise ValueError('예약어 주소가 문자열 즉시값 또는 실제 함수 리터럴과 다름')
        lexer.append({'id': f'HLSL_LEXER:{field:x}', 'role': 'HLSL_RESERVED_WORD', 'name': text,
                      'reference_preferred_va': hex(rva+pe.OPTIONAL_HEADER.ImageBase),
                      'instruction_prefix_hex': data[field-1:field+4].hex(),
                      'consumer_query': '0x1002118e'})
    if {entry['name']['source'] for entry in lexer} != LEXER_UNKNOWN_NAMES:
        raise ValueError('검토한 예약어의 실제 코드 참조가 빠짐')
    proofs = {}
    for entry in lexer:
        proofs.setdefault(entry['name']['start'], []).append(entry)
    for table in tables:
        for entry in table['entries']:
            proof = {'id': table['id'], 'role': table['role'], 'name': entry['name'], 'record_offset': entry['record_offset']}
            proofs.setdefault(entry['name']['start'], []).append(proof)
    reasons = {
        'HLSL_RESERVED_WORD': '실제 HLSL 어휘 분석 함수가 입력 식별자와 비교해 문법 토큰 또는 예약된 미지원 토큰을 반환하는 고정 예약어. 원본 즉시 주소·Ghidra 문자열 리터럴·현재 문자열 지문을 연결함.',
        'SHADER_PROFILE': '실제 셰이더 프로필 검색 함수가44개3DWORD 레코드를 이름으로 이진 검색하는 지원 버전 식별자. 원본 이름·버전·플래그 레코드와 함수의12바이트 간격/44개 상한을 연결함.',
        'SHADER_OPCODE': '실제 어셈블러가84개68바이트 설명자에서 이름을 검색해 opcode와 프로필별 피연산자 제약을 읽는 명령 식별자. 자연어 오류 메시지는 이 범위에 포함하지 않음.',
        'SHADER_COMPARISON_OPCODE': 'if/break 비교형의 내부 설명자 이름. 입력 이름 직접 검색과 구분하며, 실제 어셈블러가 해당 레코드+8의 프로필 제약을 읽어 opcode41/45로 변환하는 근거에 연결함.',
        'SHADER_REGISTER': '실제 어셈블러가21개72바이트 설명자를 이름으로 검색하고 레지스터 종류·번호 한계·플래그를 읽어 객체를 생성하는 문법 식별자.',
    }
    proposals, remaining = [], []
    for row in [json.loads(line) for line in inventory.decode('utf-8').splitlines()]:
        if row['classification'] != 'UNKNOWN':
            continue
        matches = proofs.get(row['file_offset'], []) if row['file'] == FILE else []
        matches = [p for p in matches if p['name']['source'] == row['source'] and p['name']['end']-p['name']['start'] == row['bytes']]
        if not matches:
            remaining.append(row)
            continue
        if row['encoding'] != 'ascii' or row['file_sha256'] != FILE_SHA or row['source_bytes_sha256'] != sha(data[row['file_offset']:row['file_offset']+row['bytes']]):
            raise ValueError('제안 문자열의 위치·인코딩·지문 불일치')
        proposals.append({**row, 'classification': 'INTERNAL', 'proposal_only': True,
                          'reason': ' '.join(dict.fromkeys(reasons[p['role']] for p in matches)),
                          'keyword_evidence_ids': sorted({p['id'] for p in matches}),
                          'keyword_roles': sorted({p['role'] for p in matches}),
                          'keyword_review_evidence': str((OUT/'structures.json').relative_to(ROOT))})
    dependencies = {'inventory': str(INVENTORY.relative_to(ROOT)), 'inventory_sha256': INVENTORY_SHA,
                    'source_file': FILE, 'source_sha256': FILE_SHA, 'script_sha256': sha(Path(__file__).read_bytes()),
                    'rea_evidence': str(EVIDENCE.relative_to(ROOT)), 'rea_evidence_sha256': sha(EVIDENCE.read_bytes())}
    structures = {'dependencies': dependencies, 'functions': functions, 'tables': tables, 'lexer': lexer,
                  'limits': '고정 입력v15 UNKNOWN 중 확인한 식별자만. 인접 자연어 진단·에러 메시지를 제외하지 않으며 공유 분류표 미수정.'}
    for filename, value in [('structures.json', structures), ('classification_proposals.json', {'dependencies': dependencies, 'proposals': proposals}), ('remaining_unknown.json', {'dependencies': dependencies, 'rows': remaining})]:
        (OUT/filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {**dependencies, 'status': 'PROPOSAL_READY', 'proposed_internal': len(proposals), 'remaining_unknown': len(remaining),
               'table_records': {table['role']: table['count'] for table in tables}, 'lexer_names': len(lexer),
               'by_role': {role: sum(role in row['keyword_roles'] for row in proposals) for role in reasons},
               'proposal_sha256': sha((OUT/'classification_proposals.json').read_bytes()),
               'structures_sha256': sha((OUT/'structures.json').read_bytes()), 'shared_inventory_modified': False}
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
