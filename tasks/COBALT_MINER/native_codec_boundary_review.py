"""JPEG/PNG 자료의 외부 참조 경계를 조사하되 미사용으로 추정 분류하지 않습니다."""
import collections
import hashlib
import json
import struct
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
OUT = NATIVE / 'media_codec_review_01'
SOURCE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
INVENTORY = NATIVE / 'native_inventory_v17.jsonl'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    rows = [json.loads(line) for line in INVENTORY.read_text(encoding='utf-8').splitlines()]
    results, pending = [], []
    for file, table_start, count, png_offsets in [
            ('Modules/mmf2d3d8.dll', 0x51bf8, 120, list(range(0x52fc4, 0x52ffc, 8))+[0x53720]),
            ('Modules/mmf2d3d9.dll', 0xef578, 124, list(range(0xf0a74, 0xf0aac, 8))+list(range(0xf6210, 0xf6230, 8))+[0xf6364])]:
        data = (SOURCE/file).read_bytes()
        pe = pefile.PE(data=data)
        base = pe.OPTIONAL_HEADER.ImageBase
        entries = []
        for index in range(count):
            field = table_start+index*4
            pointer = struct.unpack_from('<I', data, field)[0]
            start = pe.get_offset_from_rva(pointer-base)
            end = data.index(b'\0', start)+1
            source = data[start:end-1].decode('ascii')
            entries.append({'index': index, 'pointer_operand_offset': field, 'pointer': hex(pointer),
                            'string_start': start, 'string_end_with_nul': end, 'source': source,
                            'source_bytes_sha256': sha(data[start:end-1])})
        assert struct.unpack_from('<I', data, table_start+count*4)[0] == 0
        island_start, island_end = table_start, max(e['string_end_with_nul'] for e in entries)
        rva_start, rva_end = pe.get_rva_from_offset(island_start), pe.get_rva_from_offset(island_end)
        va_start, va_end = base+rva_start, base+rva_end
        internal, external, below, above = [], [], [], []
        relocations = []
        for block in pe.DIRECTORY_ENTRY_BASERELOC:
            for relocation in block.entries:
                if relocation.type != 3:
                    continue
                field = pe.get_offset_from_rva(relocation.rva)
                value = struct.unpack_from('<I', data, field)[0]
                relocations.append((field, value))
                try:
                    target = pe.get_offset_from_rva(value-base)
                except pefile.PEFormatError:
                    continue
                ref = {'pointer_operand_offset': field, 'preferred_va': hex(base+relocation.rva), 'target_offset': target, 'pointer_value': hex(value)}
                if island_start <= target < island_end:
                    (internal if island_start <= field < island_end else external).append(ref)
                elif not island_start <= field < island_end:
                    (below if target < island_start else above).append(ref)
        # 시작 주소뿐 아니라 영역 내부의 모든 바이트 주소를 대상으로 확인합니다.
        code_hits = {'absolute_va': [], 'rva': [], 'file_offset': []}
        relative_branches = []
        for section in pe.sections:
            if not section.IMAGE_SCN_MEM_EXECUTE:
                continue
            lower = section.PointerToRawData
            upper = lower+section.SizeOfRawData
            for position in range(lower, upper-3):
                value = struct.unpack_from('<I', data, position)[0]
                kinds = []
                if va_start <= value < va_end:
                    kinds.append('absolute_va')
                if rva_start <= value < rva_end:
                    kinds.append('rva')
                if island_start <= value < island_end:
                    kinds.append('file_offset')
                for kind in kinds:
                    code_hits[kind].append({'word_offset': position, 'word_va': hex(base+pe.get_rva_from_offset(position)),
                                           'value': hex(value), 'context_start': position-8, 'context_hex': data[position-8:position+12].hex(),
                                           'status': 'RAW_MATCH_NOT_A_VERIFIED_REFERENCE'})
                if position >= lower+1 and data[position-1] in (0xe8, 0xe9):
                    target = base+pe.get_rva_from_offset(position)+4+struct.unpack_from('<i', data, position)[0]
                    if va_start <= target < va_end:
                        relative_branches.append({'instruction_start': position-1, 'target_va': hex(target), 'opcode': hex(data[position-1])})
                if position >= lower+2 and data[position-2] == 0x0f and 0x80 <= data[position-1] <= 0x8f:
                    target = base+pe.get_rva_from_offset(position)+4+struct.unpack_from('<i', data, position)[0]
                    if va_start <= target < va_end:
                        relative_branches.append({'instruction_start': position-2, 'target_va': hex(target), 'opcode': data[position-2:position].hex()})
        exports = []
        for symbol in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', []):
            if rva_start <= symbol.address < rva_end:
                exports.append({'name': symbol.name.decode('ascii') if symbol.name else None, 'ordinal': symbol.ordinal, 'rva': symbol.address})
        resources = []

        def resource_walk(directory, trail):
            for entry in directory.entries:
                key = str(entry.name) if entry.name is not None else entry.id
                if hasattr(entry, 'directory'):
                    resource_walk(entry.directory, trail+[key])
                elif hasattr(entry, 'data'):
                    start = entry.data.struct.OffsetToData
                    end = start+entry.data.struct.Size
                    if start < rva_end and rva_start < end:
                        resources.append({'path': trail+[key], 'rva': start, 'size': end-start})
        if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
            resource_walk(pe.DIRECTORY_ENTRY_RESOURCE, [])

        def neighbours(refs, reverse):
            result = []
            for ref in sorted(refs, key=lambda x:x['target_offset'], reverse=reverse)[:4]:
                target = ref['target_offset']
                result.append({**ref, 'target_bytes_64_hex': data[target:target+64].hex()})
            return result

        png = []
        for start in png_offsets:
            tag = data[start:start+4].decode('ascii')
            assert tag in ('IHDR', 'IDAT', 'IEND', 'PLTE', 'gAMA', 'sRGB', 'tRNS') and data[start+4:start+8] == bytes(4)
            pointer = base+pe.get_rva_from_offset(start)
            refs = [{'pointer_operand_offset': f, 'value': hex(v)} for f,v in relocations if pointer <= v < pointer+5]
            png.append({'file_offset': start, 'tag': tag, 'eight_bytes_sha256': sha(data[start:start+8]),
                        'external_highlow_references': refs, 'status': 'IDENTIFIER_SHAPE_CONFIRMED_CONSUMER_UNKNOWN'})
        covered = [(e['string_start'],e['string_end_with_nul']) for e in entries]+[(p['file_offset'],p['file_offset']+4) for p in png]
        selected = [row for row in rows if row['file']==file and row['classification']=='UNKNOWN' and
                    any(row['file_offset'] < end and start < row['file_offset']+row['bytes'] for start,end in covered)]
        for row in selected:
            assert row['file_sha256'] == sha(data)
            assert row['source_bytes_sha256'] == sha(data[row['file_offset']:row['file_offset']+row['bytes']])
        pending.extend(selected)
        results.append({'file': file, 'file_sha256': sha(data), 'jpeg_table_start': table_start, 'jpeg_table_entries': entries,
                        'island_start': island_start, 'island_end': island_end, 'island_sha256': sha(data[island_start:island_end]),
                        'internal_highlow_references': internal, 'external_highlow_references': external,
                        'export_targets': exports, 'overlapping_resource_rvas': resources,
                        'relative_branch_raw_candidates': relative_branches, 'raw_code_coordinate_candidates': code_hits,
                        'nearest_external_targets_below': neighbours(below, True), 'nearest_external_targets_above': neighbours(above, False),
                        'png_identifier_records': png, 'pending_inventory_rows': len(selected),
                        'limitations': 'HIGHLOW·exports·resource 직접 유입 부재는 확인했으나 계산된 주소 접근까지 배제한 증거는 아님. 코드의 원시 좌표 일치는 명령 경계/용도 검토가 필요한 후보이며 직접 참조로 보지 않음. UNKNOWN 유지.'})
    dependencies = {'inventory': str(INVENTORY.relative_to(ROOT)), 'inventory_sha256': sha(INVENTORY.read_bytes()),
                    'script_sha256': sha(Path(__file__).read_bytes()), 'references': [
                        {'url': 'https://www.w3.org/TR/PNG-Structure.html', 'use': 'PNG8바이트 시그니처와4바이트 고정 이진 청크 코드의 의미 확인. 게임 사용함수 근거를 대신하지 않음.'},
                        {'url': 'https://www.w3.org/TR/PNG-Chunks.html', 'use': 'IHDR/IDAT/IEND/PLTE 등의 형식상 역할. 실제 DLL 도달성은 미해결.'}]}
    for filename, value in [('structures.json', {'dependencies': dependencies, 'results': results}),
                            ('pending_items.json', {'dependencies': dependencies, 'rows': pending}),
                            ('classification_proposals.json', {'dependencies': dependencies, 'proposals': []})]:
        (OUT/filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {**dependencies, 'status': 'CONSUMER_UNRESOLVED', 'proposed_classifications': 0, 'pending_items': len(pending),
               'files': [{'file': r['file'], 'jpeg_messages': len(r['jpeg_table_entries']), 'external_highlow': len(r['external_highlow_references']),
                          'exports': len(r['export_targets']), 'resource_rvas': len(r['overlapping_resource_rvas']),
                          'raw_code_candidates': {k:len(v) for k,v in r['raw_code_coordinate_candidates'].items()},
                          'relative_branch_candidates': len(r['relative_branch_raw_candidates'])} for r in results],
               'structures_sha256': sha((OUT/'structures.json').read_bytes()), 'shared_inventory_modified': False}
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
