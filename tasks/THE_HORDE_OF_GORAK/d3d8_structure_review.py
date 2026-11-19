"""D3D8 자료 중 구조·소비 명령으로 입증한 항목만 별도 분류한다."""
import hashlib
import json
import struct
from pathlib import Path

import pefile
from native_inspect import disassemble

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'working_private/THE_HORDE_OF_GORAK/investigation_20261031'
SOURCE = ROOT / 'source_original/THE_HORDE_OF_GORAK/steam_26336311/mmf2d3d8.dll'
SOURCE_SHA = '4b1c79736b8ed90b098aef60a402e4ccf66879be478b54f9f7b821e8dbaae335'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    data = SOURCE.read_bytes()
    assert sha(data) == SOURCE_SHA
    pe = pefile.PE(data=data)
    base = pe.OPTIONAL_HEADER.ImageBase
    # Microsoft의 .x 이진 토큰 정의로 내장 템플릿 전체를 읽는다.
    start = data.index(b'xof 0302bin 0064')
    assert start == 0x664E8
    cursor, depth, templates, tokens = start + 16, 0, 0, []
    while True:
        offset = cursor
        token = struct.unpack_from('<H', data, cursor)[0]
        if token == 0:
            break
        cursor += 2
        item = {'offset': offset, 'token': token}
        if token == 31:
            assert depth == 0
            templates += 1
        elif token == 1:
            length = struct.unpack_from('<I', data, cursor)[0]
            cursor += 4
            item['name'] = data[cursor:cursor+length].decode('ascii')
            cursor += length
        elif token == 3:
            item['integer'] = struct.unpack_from('<I', data, cursor)[0]
            cursor += 4
        elif token == 5:
            item['guid'] = data[cursor:cursor+16].hex()
            cursor += 16
        elif token in range(10, 21) or token in range(40, 53):
            pass
        else:
            raise ValueError(f'지원하지 않는 템플릿 토큰 {token} @{offset:x}')
        if token == 10:
            depth += 1
        elif token == 11:
            depth -= 1
        assert depth >= 0
        item['bytes'] = cursor - offset
        tokens.append(item)
    assert templates == 35 and depth == 0 and cursor == 0x671B6

    rows = [json.loads(line) for line in (OUT / 'native_string_inventory.jsonl').read_text(encoding='utf-8').splitlines()]
    rows = [row for row in rows if row['file'] == SOURCE.name and row['classification'] == 'UNKNOWN']
    decisions, token_consumers = [], []
    numeric_ranges = [(0x626D8, 0x62DB0, 'parser1'), (0x635F0, 0x63F04, 'parser2')]
    for row in rows:
        offset, length = row['file_offset'], row['bytes']
        assert sha(data[offset:offset+length]) == row['source_bytes_sha256']
        reason = group = None
        if start <= offset and offset + length <= cursor:
            group = 'DIRECTX_X_BINARY_TEMPLATE'
            reason = '내장 .X 이진자료의 템플릿35개/토큰474개를 공식 형식으로 끝까지 해석. 필드 이름·자료형·GUID·구조 토큰이며 사용자 표시 문장이 아님.'
        elif any(a <= offset and offset + length <= b for a, b, _ in numeric_ranges):
            group = 'INDEXED_INT16_PARSER_TABLE'
            reason = '구문해석기가 movsx word 및 2배 인덱스로 읽는 연속 int16 상태·전이 배열. parser1은 전이 인덱스0x107, parser2는0xf0까지 검사하며 문자열 API로 읽지 않음.'
        elif 0x4FF44 <= offset <= 0x50198 and ' ' not in row['source']:
            refs = [pointer for ref in row['static_references'] for pointer in ref['pointer_offsets']]
            assert refs
            for pointer in refs:
                # mov edi,문자열 주소 뒤의 REPE CMPSB로 어셈블리 토큰을 인식하는 실제 코드.
                assert data[pointer-1] == 0xBF and b'\xf3\xa6' in data[pointer+4:pointer+24]
                address = base + pe.get_rva_from_offset(pointer-1)
                token_consumers.append({'source': row['source'], 'pointer_offset': pointer,
                                        'instructions': disassemble(SOURCE, address, 42)})
            group = 'ASSEMBLY_LEXICAL_TOKEN'
            reason = '셰이더 어셈블리 어휘 분석 코드가 문자열을 EDI에 놓고 REPE CMPSB 비교 후 opcode/레지스터/수정자 숫자를 반환. 번역하면 프로그램 문법이 깨지는 식별자.'
        elif offset in (0x4EC00, 0x4ECD8):
            group = 'BUILTIN_SHADER_PROGRAM'
            reason = '기본 반전·회색조 효과의 고정 셰이더 프로그램 원문. 0x1002bfea/0x1002c02a에서 길이0xc3/0xd5와 함께 D3DXCreateEffect에 전달하며 ppErrors=NULL.'
        elif offset == 0x4F68C:
            group = 'SHADER_TECHNIQUE_IDENTIFIER'
            reason = '위 고정 프로그램의 technique tech_main 선언과 일치. 생성 성공 뒤 effect 가상함수+0x2c에 전달하는 기법 식별자.'
        if reason:
            item = {k: row[k] for k in ('file', 'file_sha256', 'file_offset', 'bytes', 'source', 'source_bytes_sha256', 'encoding')}
            item.update(classification='INTERNAL', reason=reason, evidence_group=group,
                        evidence='d3d8_structure_review_evidence.json')
            decisions.append(item)
    evidence = {'status': 'PASS', 'file': SOURCE.name, 'file_sha256': SOURCE_SHA,
                'x_templates': {'start': start, 'end': cursor, 'templates': templates,
                                'tokens': tokens, 'sha256': sha(data[start:cursor])},
                'typed_numeric_ranges': [{'start': a, 'end': b, 'type': 'int16', 'function': name,
                                          'sha256': sha(data[a:b])} for a, b, name in numeric_ranges],
                'assembly_token_consumers': token_consumers,
                'evidence_hashes': {name: sha((OUT / name).read_bytes()) for name in
                                   ['d3d8_focused_disasm.json', 'd3d8_resource_rea_evidence.json']},
                'format_sources': ['https://learn.microsoft.com/en-us/windows/win32/direct3d9/tokens',
                                   'https://learn.microsoft.com/en-us/windows/win32/direct3d9/token-records',
                                   'https://learn.microsoft.com/en-us/windows/win32/direct3d9/binary-encoding'],
                'tool_sha256': sha(Path(__file__).read_bytes()), 'classified': len(decisions),
                'scope': '구조·직접 소비가 확인된 행만 별도 패치로 반환. 공용 목록·게임·후보·프로세스 변경 없음.'}
    for name, value in [('d3d8_structure_review_evidence.json', evidence), ('d3d8_structure_classification_patch.json', decisions)]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = {group: sum(x['evidence_group'] == group for x in decisions) for group in sorted({x['evidence_group'] for x in decisions})}
    print(json.dumps({'classified': len(decisions), 'groups': counts}))


if __name__ == '__main__':
    main()
