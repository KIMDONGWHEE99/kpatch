"""후보를 독립적으로 열어 기대 위치와 이전 189필드의 보존 경계를 검사합니다."""
import json
from pathlib import Path
import pefile
import native_inventory as inv


def read_wide(raw, at):
    end = at
    while raw[end:end + 2] != bytes(2):
        end += 2
    return raw[at:end].decode('utf-16le')


def main():
    previous = inv.ROOT / 'working_private/COBALT_MINER/native_candidate_03'
    candidate = inv.ROOT / 'working_private/COBALT_MINER/native_candidate_04'
    old_work = json.loads((inv.OUT / 'native_visible_worklist_v4.json').read_text(encoding='utf-8'))
    work_path = inv.OUT / 'native_visible_worklist_v5.json'
    work = json.loads(work_path.read_text(encoding='utf-8'))
    assert work[:189] == old_work and len(work) == 192
    before = (previous / 'COBALT MINER.exe').read_bytes()
    raw = (candidate / 'COBALT MINER.exe').read_bytes()
    old_pe, new_pe = pefile.PE(data=before), pefile.PE(data=raw)
    assert len(raw) == len(before) and old_pe.write()[:0x400] == new_pe.write()[:0x400]
    assert all(a.get_data() == b.get_data() for a, b in zip(old_pe.sections, new_pe.sections) if a.Name.rstrip(b'\0') != b'.rdata')
    allowed, checks = [], []
    for row in work[189:]:
        at, size = row['file_offset'], row['bytes'] + 2
        assert read_wide(before, at) == row['source']
        actual = read_wide(raw, at)
        assert actual == row['translation'] and actual != row['source'] and actual
        assert not any(raw[at + len(actual.encode('utf-16le')):at + size])
        allowed.append((at, at + size))
        check = {'offset': at, 'expected': row['translation'], 'actual': actual, 'status': 'PASS'}
        if ' bit' in row['source']:
            # 원본 Ghidra가 확인한 복사 경계: 8 WCHAR 복사 뒤 8번에 t, 9번에 NUL.
            rendered = bytearray(raw[at:at + 16]) + 't\0'.encode('utf-16le')
            assert read_wide(rendered, 0) == actual and len(actual) == 7
            check['original_inline_copy_result'] = read_wide(rendered, 0)
            check['source_terminator_within_first_8_wchars'] = True
        checks.append(check)
    assert all(any(a <= index < b for a, b in allowed) for index, (x, y) in enumerate(zip(before, raw)) if x != y)
    expected_files = {row['file'] for row in work}
    for name in expected_files - {'COBALT MINER.exe'}:
        assert (candidate / name).read_bytes() == (previous / name).read_bytes()
    for row in old_work:
        if row['file'] != 'COBALT MINER.exe':
            continue
        at = row.get('candidate_file_offset', row['file_offset'])
        assert not any(a <= at < b for a, b in allowed)
        assert raw[at:at + row['bytes']] == before[at:at + row['bytes']]
    report = {'status': 'PASS', 'new_fields': 3, 'inherited_fields_preserved': 189, 'new_field_checks': checks,
              'non_allowed_changes': 0, 'pe_layout_and_executable_code': 'PASS', 'relocations_preserved': 'PASS',
              'candidate_exe_sha256': inv.sha(raw), 'worklist_sha256': inv.sha(work_path.read_bytes()),
              'parent_validation_sha256': inv.sha((previous / 'independent_validation.json').read_bytes()),
              'graphics_qa': 'NOT_RUN', 'tool_sha256': inv.sha(Path(__file__).read_bytes())}
    (candidate / 'independent_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'new_field_checks'}))


if __name__ == '__main__':
    main()
