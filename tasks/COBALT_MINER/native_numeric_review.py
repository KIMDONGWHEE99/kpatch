"""CRC 수치표·서식 상태표·PE 재배치 구조의 전체 경계를 검증합니다."""
import collections
import argparse
import json
import re
import struct
from pathlib import Path
import pefile
import native_inventory as inv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-version', type=int, default=5)
    parser.add_argument('--output-version', type=int, default=6)
    args = parser.parse_args()
    input_path = inv.OUT / ('native_inventory_v%d.jsonl' % args.input_version)
    rows = [json.loads(x) for x in input_path.read_text(encoding='utf-8').split('\n') if x]
    arrays = []
    table = []
    for byte in range(256):
        value = byte
        for bit in range(8):
            value = (value >> 1) ^ (0xedb88320 if value & 1 else 0)
        table.append(value)
    initial = list(table)
    for index in range(8):
        for order in ['<', '>']:
            arrays.append({'type': 'CRC32_TABLE', 'slice': index, 'byte_order': order, 'raw': struct.pack(order + '256I', *table),
                           'reason': '다항식 0xEDB88320으로 독립 계산한 256개 32비트 CRC 표 전체와 정확히 일치. 문자처럼 보인 바이트도 수치 계산 자료임'})
        table = [(value >> 8) ^ initial[value & 255] for value in table]
    evidence_path = inv.ROOT / 'working_private/THE_HORDE_OF_GORAK/native_steam_closure_01/steam_api.dll_printf_table_consumer.json'
    instructions = json.loads(evidence_path.read_text(encoding='utf-8'))
    reference_data = (inv.BASE / 'Modules/steam_api.dll').read_bytes()
    reference_pe = pefile.PE(data=reference_data)
    # 소비 명령은 문자 범위 0x20..0x78 검사, 하위 4비트 문자 종류, 상위 4비트 상태 전이입니다.
    for item in instructions:
        offset = reference_pe.get_offset_from_rva(int(item['address'], 16) - reference_pe.OPTIONAL_HEADER.ImageBase)
        assert reference_data[offset:offset + len(bytes.fromhex(item['bytes']))] == bytes.fromhex(item['bytes'])
    required = ['and eax, 0xf', 'movsx edi, byte ptr [edi + eax*8 + 0x3b41bbd0]', 'sar eax, 4', 'cmp eax, 7']
    assert all(any(item['instruction'] == value for item in instructions) for value in required)
    start = reference_pe.get_offset_from_rva(0x1bbd0)
    packed = reference_data[start:start + 89]
    assert all((value & 15) <= 8 and (value >> 4) <= 7 for value in packed)
    arrays.append({'type': 'PRINTF_PACKED_STATE_TABLE', 'raw': packed,
                   'reason': '서식 파서의 89바이트 상태표 전체와 일치. 소비 코드는 하위 4비트를 문자 종류로, 상위 4비트를 다음 상태로 읽고 8개 처리 분기로 보냄',
                   'consumer_evidence': str(evidence_path.relative_to(inv.ROOT)), 'consumer_sha256': inv.sha(evidence_path.read_bytes()),
                   'reference_module_sha256': inv.sha(reference_data), 'reference_offset': start})
    # 새 CRT의 91개 상태/문자종류 쌍은 설치된 원문에서 독립 생성해 전부 비교합니다.
    source_path = Path('C:/Program Files (x86)/Windows Kits/10/Source/10.0.22621.0/ucrt/inc/corecrt_internal_stdio_output.h')
    source = source_path.read_text(encoding='utf-8-sig')
    body = source.split('standard_lookup_table_spectre', 1)[1].split('};', 1)[0]
    states = ['normal', 'percent', 'flag', 'width', 'dot', 'precision', 'size', 'type', 'invalid']
    classes = ['other', 'percent', 'dot', 'star', 'zero', 'digit', 'flag', 'size', 'type']
    pairs = re.findall(r'state::(\w+),.*?character_type::(\w+)', body)
    assert len(pairs) == 91
    modern = bytes((states.index(a) << 4) | classes.index(b) for a, b in pairs)
    modern_consumer = inv.ROOT / 'working_private/THE_HORDE_OF_GORAK/native_steam_closure_01/Steamworks.mfx_printf_table_consumer.json'
    modern_code = json.loads(modern_consumer.read_text(encoding='utf-8'))
    modern_data = (inv.BASE / 'Modules/Steamworks.mfx').read_bytes()
    modern_pe = pefile.PE(data=modern_data)
    for item in modern_code:
        at = modern_pe.get_offset_from_rva(int(item['address'], 16) - modern_pe.OPTIONAL_HEADER.ImageBase)
        assert modern_data[at:at + len(bytes.fromhex(item['bytes']))] == bytes.fromhex(item['bytes'])
    assert any(x['instruction'] == 'cmp al, 0x5a' for x in modern_code)
    assert any(x['instruction'] == 'movzx eax, byte ptr [eax + ecx*8 + 0x10063b70]' for x in modern_code)
    assert modern_data[modern_pe.get_offset_from_rva(0x63b70):modern_pe.get_offset_from_rva(0x63b70) + 91] == modern
    arrays.append({'type': 'PRINTF_PACKED_STATE_TABLE_91', 'raw': modern,
                   'reason': 'CRT 원문의 91개 상태/문자종류 쌍 전체와 일치. 실제 소비 코드는 문자범위 0x20..0x7A, 하위 4비트 종류와 상위 4비트 상태를 사용함',
                   'source_path': str(source_path), 'source_sha256': inv.sha(source_path.read_bytes()),
                   'consumer_evidence': str(modern_consumer.relative_to(inv.ROOT)), 'consumer_sha256': inv.sha(modern_consumer.read_bytes())})
    typed = []
    for file in sorted({row['file'] for row in rows}):
        data = (inv.BASE / file).read_bytes()
        pe = pefile.PE(data=data)
        for item in arrays:
            cursor = 0
            while True:
                start = data.find(item['raw'], cursor)
                if start < 0:
                    break
                end = start + len(item['raw'])
                if any(row['file'] == file and row['classification'] == 'UNKNOWN' and start <= row['file_offset'] and row['file_offset'] + row['bytes'] <= end for row in rows):
                    typed.append({**{key: value for key, value in item.items() if key != 'raw'}, 'file': file,
                                  'file_sha256': inv.sha(data), 'start': start, 'end': end, 'raw_sha256': inv.sha(data[start:end])})
                cursor = end
        for block in getattr(pe, 'DIRECTORY_ENTRY_BASERELOC', []):
            start = block.struct.get_file_offset()
            end = start + block.struct.SizeOfBlock
            assert struct.unpack_from('<II', data, start) == (block.struct.VirtualAddress, block.struct.SizeOfBlock)
            assert len(block.entries) == (block.struct.SizeOfBlock - 8) // 2
            assert all(x.type in [0, 3] for x in block.entries)
            if any(row['file'] == file and row['classification'] == 'UNKNOWN' and start <= row['file_offset'] and row['file_offset'] + row['bytes'] <= end for row in rows):
                typed.append({'type': 'PE_BASE_RELOCATION_BLOCK', 'file': file, 'file_sha256': inv.sha(data), 'start': start, 'end': end,
                              'raw_sha256': inv.sha(data[start:end]), 'entries': len(block.entries),
                              'reason': 'PE 재배치 블록 전체: 페이지 RVA·블록 크기·16비트 HIGHLOW/ABSOLUTE 항목. 문자열로 읽힌 주소 조정 정보'})
    changes = []
    for row in rows:
        if row['classification'] != 'UNKNOWN':
            continue
        match = next((item for item in typed if item['file'] == row['file'] and item['start'] <= row['file_offset'] and row['file_offset'] + row['bytes'] <= item['end']), None)
        if match:
            row.update(classification='INTERNAL', reason=match['reason'], additional_evidence=match)
            changes.append(row)
    output_name = 'native_inventory_v%d.jsonl' % args.output_version
    inv.save(output_name, rows)
    inv.save('numeric_classification_v%d.json' % args.output_version, {'input_sha256': inv.sha(input_path.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'structures': typed, 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'by_structure': dict(collections.Counter(x['additional_evidence']['type'] for x in changes)),
               'output_sha256': inv.sha((inv.OUT / output_name).read_bytes()), 'full_native_classification': 'NOT_RUN', 'native_candidate_03_content_affected': False}
    inv.save('summary_v%d.json' % args.output_version, summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
