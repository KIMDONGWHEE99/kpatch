"""실제 x87/SSE 산술 명령이 읽는 수치 피연산자와 PE 디버그 구조를 좁게 조사합니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv
from native_api_boundary_review import Decoder


def main():
    input_path = inv.OUT / 'native_inventory_v13.jsonl'
    rows = [json.loads(x) for x in input_path.read_text(encoding='utf-8').split('\n') if x]
    decoder = Decoder()
    structures = []
    proposals = []
    for file in sorted({x['file'] for x in rows if x['classification'] == 'UNKNOWN'}):
        data = (inv.BASE / file).read_bytes()
        pe = pefile.PE(data=data)
        base = pe.OPTIONAL_HEADER.ImageBase
        unknowns = [x for x in rows if x['file'] == file and x['classification'] == 'UNKNOWN']
        ranges = collections.defaultdict(list)
        for block in getattr(pe, 'DIRECTORY_ENTRY_BASERELOC', []):
            for reloc in block.entries:
                if reloc.type != 3:
                    continue
                at = pe.get_offset_from_rva(reloc.rva)
                section = pe.get_section_by_rva(reloc.rva)
                if section is None or not section.Characteristics & 0x20000000:
                    continue
                start, width = None, 0
                if data[at - 2] in (0xd8, 0xdc) and data[at - 1] & 0xc7 == 5:
                    start, width = at - 2, 4 if data[at - 2] == 0xd8 else 8
                elif data[at - 4] in (0xf2, 0xf3) and data[at - 3] == 0x0f and data[at - 2] in (0x58, 0x59, 0x5c, 0x5e, 0x5d, 0x5f, 0x51) and data[at - 1] & 0xc7 == 5:
                    start, width = at - 4, 8 if data[at - 4] == 0xf2 else 4
                if start is None:
                    continue
                target = struct.unpack_from('<I', data, at)[0]
                target_section = pe.get_section_by_rva(target - base)
                if target_section is None or target_section.Characteristics & 0x20000000:
                    continue
                offset = pe.get_offset_from_rva(target - base)
                if not any(offset <= x['file_offset'] and x['file_offset'] + x['bytes'] <= offset + width for x in unknowns):
                    continue
                address = base + pe.get_rva_from_offset(start)
                code = decoder.read(data, start, address, {})
                if not code:
                    continue
                instruction = code[0]
                assert len(bytes.fromhex(instruction['bytes'])) == at - start + 4
                assert hex(target) in instruction['instruction']
                ranges[offset, offset + width].append(instruction)
        for (start, end), consumers in sorted(ranges.items()):
            proof = {'id': f'FLOAT_ARITHMETIC_OPERAND:{file}:{start:x}', 'type': 'FLOAT_ARITHMETIC_OPERAND',
                     'file': file, 'file_sha256': inv.sha(data), 'start': start, 'end': end,
                     'raw_sha256': inv.sha(data[start:end]), 'reason': '현재 PE 재배치가 지정한 주소에서 실제 x87/SSE 산술 명령이 32/64비트 부동소수 값으로 읽는 자료. 읽기 폭 안의 문자처럼 보인 바이트를 수치 필드로 판정',
                     'consumers': consumers, 'decoded_value': repr(struct.unpack('<f' if end - start == 4 else '<d', data[start:end])[0])}
            structures.append(proof)
        for item in getattr(pe, 'DIRECTORY_ENTRY_DEBUG', []):
            start = item.struct.get_file_offset()
            end = start + 28
            directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[6]
            directory_start = pe.get_offset_from_rva(directory.VirtualAddress)
            assert directory_start <= start and end <= directory_start + directory.Size
            if any(start <= x['file_offset'] and x['file_offset'] + x['bytes'] <= end for x in unknowns):
                structures.append({'id': f'PE_DEBUG_DIRECTORY:{file}:{start:x}', 'type': 'PE_DEBUG_DIRECTORY',
                    'file': file, 'file_sha256': inv.sha(data), 'start': start, 'end': end, 'raw_sha256': inv.sha(data[start:end]),
                    'reason': 'PE 데이터 디렉터리6이 가리키는 28바이트 IMAGE_DEBUG_DIRECTORY 구조. 시간값/정수 필드와 디버그 페이로드 주소로 구성되며 문자열이 아님',
                    'fields': item.struct.dump_dict()})
        for row in unknowns:
            owners = [x['id'] for x in structures if x['file'] == file and x['start'] <= row['file_offset'] and row['file_offset'] + row['bytes'] <= x['end']]
            if owners:
                proof = next(x for x in structures if x['id'] == owners[0])
                proposals.append({**row, 'classification': 'INTERNAL', 'reason': proof['reason'], 'numeric_evidence_ids': owners, 'proposal_only': True})
    out = inv.OUT / 'numeric_operand_review_01'
    out.mkdir(exist_ok=True)
    deps = {'input_inventory': str(input_path.relative_to(inv.ROOT)), 'input_sha256': inv.sha(input_path.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes())}
    (out / 'structures.json').write_text(json.dumps({'dependencies': deps, 'structures': structures}, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'classification_proposals.json').write_text(json.dumps({'dependencies': deps, 'proposals': proposals}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'proposals': len(proposals), 'structures': len(structures), 'by_file': dict(collections.Counter(x['file'] for x in proposals))}))
    print('\n'.join(str((x['file'], x['source'])) for x in proposals))


if __name__ == '__main__':
    main()
