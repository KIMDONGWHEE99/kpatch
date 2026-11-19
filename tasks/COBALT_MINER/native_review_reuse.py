"""동일 DLL의 보존된 구조·호출 근거를 현재 바이트와 다시 대조하여 적용합니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv

OLD = inv.ROOT / 'working_private/THE_HORDE_OF_GORAK'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verify_assembly(data, pe, items):
    checked = 0
    for item in items:
        offset = pe.get_offset_from_rva(int(item['address'], 16) - pe.OPTIONAL_HEADER.ImageBase)
        raw = bytes.fromhex(item['bytes'])
        assert data[offset:offset + len(raw)] == raw, item
        checked += 1
    return checked


def main():
    input_path = inv.OUT / 'native_inventory_v3.jsonl'
    rows = [json.loads(x) for x in input_path.read_text(encoding='utf-8').split('\n') if x]
    by_location = {(x['file'], x['file_offset']): x for x in rows}
    evidence_paths = []
    data = (inv.BASE / 'Modules/mmf2d3d8.dll').read_bytes()
    pe = pefile.PE(data=data)
    folder = OLD / 'investigation_20261031'
    proof_path = folder / 'd3d8_structure_review_evidence.json'
    proof = read(proof_path)
    assert proof['file_sha256'] == inv.sha(data)
    evidence_paths += [proof_path, folder / 'd3d8_structure_classification_patch.json', folder / 'd3d8_focused_disasm.json']
    template = proof['x_templates']
    assert inv.sha(data[template['start']:template['end']]) == template['sha256']
    assert data[template['start']:template['start'] + 16] == b'xof 0302bin 0064'
    cursor, depth, templates = template['start'] + 16, 0, 0
    for expected in template['tokens']:
        assert cursor == expected['offset']
        token = struct.unpack_from('<H', data, cursor)[0]
        assert token == expected['token']
        start = cursor
        cursor += 2
        if token == 31:
            assert depth == 0
            templates += 1
        elif token == 1:
            size = struct.unpack_from('<I', data, cursor)[0]
            cursor += 4
            assert data[cursor:cursor + size].decode('ascii') == expected['name']
            cursor += size
        elif token == 3:
            assert struct.unpack_from('<I', data, cursor)[0] == expected['integer']
            cursor += 4
        elif token == 5:
            assert data[cursor:cursor + 16].hex() == expected['guid']
            cursor += 16
        else:
            assert token in range(10, 21) or token in range(40, 53)
        depth += (token == 10) - (token == 11)
        assert depth >= 0 and cursor - start == expected['bytes']
    assert cursor == template['end'] and depth == 0 and templates == 35
    assert data[cursor:cursor + 2] == b'\0\0'
    for region in proof['typed_numeric_ranges']:
        assert inv.sha(data[region['start']:region['end']]) == region['sha256']
    checked_instructions = sum(verify_assembly(data, pe, items) for items in read(folder / 'd3d8_focused_disasm.json').values())
    checked_instructions += sum(verify_assembly(data, pe, item['instructions']) for item in proof['assembly_token_consumers'])
    changes = []
    for decision in read(folder / 'd3d8_structure_classification_patch.json'):
        row = by_location['Modules/mmf2d3d8.dll', decision['file_offset']]
        assert row['classification'] == 'UNKNOWN'
        assert row['file_sha256'] == decision['file_sha256'] == inv.sha(data)
        assert row['source_bytes_sha256'] == decision['source_bytes_sha256'] == inv.sha(data[row['file_offset']:row['file_offset'] + row['bytes']])
        row.update(classification='INTERNAL', reason=decision['reason'], additional_evidence={
            'type': decision['evidence_group'], 'evidence_path': str(proof_path.relative_to(inv.ROOT)),
            'evidence_sha256': inv.sha(proof_path.read_bytes()), 'method': '보존 Capstone 명령 바이트 재검증 및 독립 .X 토큰 재해석; 새 Ghidra 분석이라고 주장하지 않음'})
        changes.append(row)
    folder = OLD / 'native_steam_closure_01'
    message_path = folder / 'json_messagebox_evidence.json'
    decisions_path = folder / 'json_display_patch.json'
    message = read(message_path)
    evidence_paths += [message_path, decisions_path]
    data = (inv.BASE / 'Modules/Steamworks.mfx').read_bytes()
    pe = pefile.PE(data=data)
    assert inv.sha(data) == message['file_sha256']
    for name in message['disassembly']:
        path = folder / name
        checked_instructions += verify_assembly(data, pe, read(path))
        evidence_paths.append(path)
    new_visible = []
    for decision in read(decisions_path):
        row = by_location['Modules/Steamworks.mfx', decision['file_offset']]
        assert row['classification'] == 'UNKNOWN'
        assert row['file_sha256'] == decision['file_sha256'] == inv.sha(data)
        assert row['source_bytes_sha256'] == decision['source_bytes_sha256'] == inv.sha(data[row['file_offset']:row['file_offset'] + row['bytes']])
        row.update(classification='VISIBLE_TRANSLATE', reason=decision['reason'], additional_evidence={
            'evidence_path': str(message_path.relative_to(inv.ROOT)), 'evidence_sha256': inv.sha(message_path.read_bytes()),
            'encoding_boundary': message['encoding'], 'patch_status': 'NOT_RUN'})
        changes.append(row)
        new_visible.append(row)
    inv.save('native_inventory_v4.jsonl', rows)
    inv.save('native_new_visible_v4.json', new_visible)
    inv.save('reused_closure_evidence.json', {'input_sha256': inv.sha(input_path.read_bytes()),
        'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'verified_instruction_records': checked_instructions,
        'evidence_files': [{'path': str(p.relative_to(inv.ROOT)), 'sha256': inv.sha(p.read_bytes())} for p in evidence_paths],
        'changes': changes, 'limits': ['정적 구조·소비 분류. 실행·글꼴·최종 후보 검증 아님', '새 표시 22개는 기존 167개 후보에 아직 반영되지 않음']})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': 183, 'additional_visible_translate': len(new_visible), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v4.jsonl').read_bytes()),
               'native_candidate_02_complete': False, 'native_candidate_02_selected_167_validation_reusable': True}
    inv.save('summary_v4.json', summary)
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == '__main__':
    main()
