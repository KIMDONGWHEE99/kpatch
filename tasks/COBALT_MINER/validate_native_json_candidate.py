"""확장 후보를 새로 읽어 포인터·재배치·실제 번역·이전 167필드 보존을 검사합니다."""
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv


def main():
    candidate = inv.ROOT / 'working_private/COBALT_MINER/native_candidate_03'
    previous = inv.ROOT / 'working_private/COBALT_MINER/native_candidate_02'
    audit_path = candidate / 'native_json_audit.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    original = (previous / audit['file']).read_bytes()
    raw = (candidate / audit['file']).read_bytes()
    assert inv.sha(original) == audit['source_sha256'] and inv.sha(raw) == audit['candidate_sha256']
    old_pe, new_pe = pefile.PE(data=original), pefile.PE(data=raw)
    assert new_pe.FILE_HEADER.NumberOfSections == old_pe.FILE_HEADER.NumberOfSections + 1
    section = new_pe.sections[-1]
    assert section.Name.rstrip(b'\0') == b'.kjson' and section.Characteristics == 0x60000020
    assert section.VirtualAddress == audit['new_section']['rva']
    assert new_pe.OPTIONAL_HEADER.SizeOfImage >= section.VirtualAddress + section.Misc_VirtualSize
    assert section.get_data()[:audit['wrapper']['size']].hex() == audit['wrapper']['bytes']
    allowed = list(audit['header_ranges'])
    for patch in audit['patches']:
        at = patch['offset']; before, after = bytes.fromhex(patch['before']), bytes.fromhex(patch['after'])
        assert original[at:at + len(before)] == before and raw[at:at + len(after)] == after
        assert len(before) == len(after)
        allowed.append([at, at + len(after)])
    assert all(any(start <= index < end for start, end in allowed) for index, (a, b) in enumerate(zip(original, raw)) if a != b)
    # 기존 Windows 리소스와 고정 문자열 영역은 새 경계 추가로 달라지지 않아야 합니다.
    old_resources = next(x for x in old_pe.sections if x.Name.rstrip(b'\0') == b'.rsrc')
    new_resources = next(x for x in new_pe.sections if x.Name.rstrip(b'\0') == b'.rsrc')
    assert old_resources.get_data() == new_resources.get_data()
    original_fields = json.loads((inv.OUT / 'native_visible_worklist.json').read_text(encoding='utf-8'))
    for row in original_fields:
        if row['file'] == audit['file'] and row['kind'] == 'section_string':
            start, end = row['file_offset'], row['file_offset'] + row['bytes']
            assert raw[start:end] == original[start:end]
        elif row['file'] != audit['file']:
            assert (candidate / row['file']).read_bytes() == (previous / row['file']).read_bytes()
    relocations = {new_pe.get_offset_from_rva(x.rva) for block in new_pe.DIRECTORY_ENTRY_BASERELOC for x in block.entries if x.type == 3}
    call_offset = new_pe.get_offset_from_rva(0x184ad)
    assert call_offset + 2 not in relocations
    assert raw[call_offset] == 0xe8 and raw[call_offset + 5] == 0x90
    destination = 0x184ad + 5 + struct.unpack_from('<i', raw, call_offset + 1)[0]
    assert destination == section.VirtualAddress
    checked = []
    for row in audit['translations']:
        at = new_pe.get_offset_from_rva(row['candidate_rva'])
        assert at == row['candidate_file_offset']
        text = raw[at:raw.index(0, at)].decode('utf-8')
        assert text == row['translation'] and text != row['source']
        for reference in row['pointer_offsets']:
            assert reference in relocations
            assert struct.unpack_from('<I', raw, reference)[0] == new_pe.OPTIONAL_HEADER.ImageBase + row['candidate_rva']
        checked.append({'source_offset': row['file_offset'], 'expected': row['translation'], 'actual': text, 'status': 'PASS'})
    parent_proof = previous / 'independent_validation.json'
    assert inv.sha(parent_proof.read_bytes()) == audit['parent_validation_sha256']
    report = {'status': 'PASS', 'new_fields': len(checked), 'inherited_fields_preserved': len(original_fields), 'records': checked,
              'file_sha256': inv.sha(raw), 'audit_sha256': inv.sha(audit_path.read_bytes()), 'validator_sha256': inv.sha(Path(__file__).read_bytes()),
              'game_executed': False, 'graphics_qa': 'NOT_RUN', 'full_native_classification': 'NOT_RUN'}
    (candidate / 'independent_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'new_fields': len(checked), 'inherited_fields_preserved': len(original_fields)}))


if __name__ == '__main__':
    main()
