"""JSON 오류 22필드를 UTF-8로 저장하고 해당 메시지 호출 하나만 Unicode로 변환합니다."""
import json
import re
import shutil
import struct
from pathlib import Path
import pefile
import native_inventory as inv

TARGETS = [
    'JSON 해석 오류', '문자열이 중간에 끝남 (%d:%d)', '잘못된 문자 `%c` (%d:%d)',
    '%d:%d: 블록 주석이 중간에 끝남', '%d:%d: 주석을 쓸 수 없는 위치', '%d:%d: 입력이 중간에 끝남',
    '%d:%d: 주석 시작에 잘못된 `%c`', '%d:%d: 뒤에 불필요한 문자 `%c`', '%d:%d: 잘못된 ]',
    '%d:%d: %c 앞에 , 필요', '%d:%d: %c 앞에 : 필요', '%d:%d: 값 위치에 잘못된 %c',
    '%d:%d: " 앞에 , 필요', '%d:%d: 객체 안에 잘못된 `%c`', '%d:%d: `%c` 앞에 잘못된 `0`',
    '%d:%d: `.` 앞에 숫자 필요', '%d:%d: `.` 뒤에 숫자 필요', '%d:%d: `e` 뒤에 숫자 필요',
    '%d:%d: 알 수 없는 값', '메모리 할당 실패', '%d:%d: 입력이 너무 김 (범위 초과)', '알 수 없는 오류',
]


def align(value, unit):
    return (value + unit - 1) & -unit


def make_wrapper(rva, convert_rva, message_rva):
    code = bytearray.fromhex('55 8bec 53 56 57 81ec 00030000')
    # 호출 시점 주소에서 현재 모듈 기준 주소를 구합니다. 추가 재배치가 필요 없습니다.
    code += b'\xe8\0\0\0\0\x5b\x81\xeb' + struct.pack('<I', rva + len(code) + 5)
    # 본문: 256 WCHAR. 제목: 128 WCHAR. 원본 오류 본문은 최대 128바이트입니다.
    for capacity, displacement, argument in [(256, -0x20c, 0x0c), (128, -0x30c, 0x10)]:
        code += b'\x68' + struct.pack('<I', capacity)
        code += b'\x8d\x85' + struct.pack('<i', displacement) + b'\x50\x6a\xff\xff\x75' + bytes([argument])
        code += b'\x6a\x00\x68\xe9\xfd\x00\x00\xff\x93' + struct.pack('<I', convert_rva)
    code += b'\xff\x75\x14\x8d\x85' + struct.pack('<i', -0x30c) + b'\x50\x8d\x85' + struct.pack('<i', -0x20c)
    code += b'\x50\xff\x75\x08\xff\x93' + struct.pack('<I', message_rva)
    code += bytes.fromhex('81c4 00030000 5f5e5b c9 c21000')
    return bytes(code)


def main():
    previous = inv.ROOT / 'working_private/COBALT_MINER/native_candidate_02'
    output = inv.ROOT / 'working_private/COBALT_MINER/native_candidate_03'
    if output.exists():
        raise ValueError('기존 후보를 덮어쓰지 않습니다.')
    old_audit = json.loads((previous / 'independent_validation.json').read_text(encoding='utf-8'))
    assert old_audit['status'] == 'PASS' and old_audit['checked_fields'] == 167
    rows_path = inv.OUT / 'native_new_visible_v4.json'
    rows = sorted(json.loads(rows_path.read_text(encoding='utf-8')), key=lambda x: x['file_offset'])
    assert len(rows) == len(TARGETS) == 22
    source_path = previous / 'Modules/Steamworks.mfx'
    old = source_path.read_bytes()
    pe = pefile.PE(data=old)
    data = bytearray(old)
    imports = {x.name.decode(): x.address - pe.OPTIONAL_HEADER.ImageBase for module in pe.DIRECTORY_ENTRY_IMPORT for x in module.imports if x.name}
    relocations = {pe.get_offset_from_rva(x.rva): x for block in pe.DIRECTORY_ENTRY_BASERELOC for x in block.entries if x.type == 3}
    section_rva = align(pe.sections[-1].VirtualAddress + max(pe.sections[-1].Misc_VirtualSize, pe.sections[-1].SizeOfRawData), pe.OPTIONAL_HEADER.SectionAlignment)
    section_raw = align(len(old), pe.OPTIONAL_HEADER.FileAlignment)
    wrapper = make_wrapper(section_rva, imports['MultiByteToWideChar'], imports['MessageBoxW'])
    payload = bytearray(wrapper)
    payload += b'\0' * (align(len(payload), 16) - len(payload))
    patches, translations = [], []
    for row, target in zip(rows, TARGETS):
        assert re.findall(r'%[dc]', row['source']) == re.findall(r'%[dc]', target)
        assert target and len(target.encode('utf-8')) + 20 < 128
        raw = old[row['file_offset']:row['file_offset'] + row['bytes']]
        assert inv.sha(raw) == row['source_bytes_sha256']
        at = section_rva + len(payload)
        payload += target.encode('utf-8') + b'\0'
        expected_pointer = pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(row['file_offset'])
        references = [offset for item in row['static_references'] for offset in item['pointer_offsets'] if item['target_offset'] == row['file_offset']]
        assert references
        for offset in references:
            assert offset in relocations and struct.unpack_from('<I', old, offset)[0] == expected_pointer
            replacement = struct.pack('<I', pe.OPTIONAL_HEADER.ImageBase + at)
            data[offset:offset + 4] = replacement
            patches.append({'kind': 'translation_pointer', 'offset': offset, 'before': old[offset:offset + 4].hex(), 'after': replacement.hex()})
        translations.append({**row, 'translation': target, 'encoding': 'utf-8', 'candidate_rva': at, 'candidate_file_offset': section_raw + at - section_rva, 'pointer_offsets': references})
    call_rva = 0x184ad
    call_offset = pe.get_offset_from_rva(call_rva)
    assert old[call_offset:call_offset + 6] == b'\xff\x15' + struct.pack('<I', pe.OPTIONAL_HEADER.ImageBase + imports['MessageBoxA'])
    replacement = b'\xe8' + struct.pack('<i', section_rva - call_rva - 5) + b'\x90'
    data[call_offset:call_offset + 6] = replacement
    patches.append({'kind': 'messagebox_call', 'offset': call_offset, 'before': old[call_offset:call_offset + 6].hex(), 'after': replacement.hex()})
    # 간접 절대주소 호출이 상대주소 호출로 바뀌었으므로 기존 재배치 하나를 ABSOLUTE로 바꿉니다.
    relocation = relocations[call_offset + 2]
    at = relocation.struct.get_file_offset()
    replacement = struct.pack('<H', relocation.struct.Data & 0xfff)
    data[at:at + 2] = replacement
    patches.append({'kind': 'disable_obsolete_relocation', 'offset': at, 'before': old[at:at + 2].hex(), 'after': replacement.hex()})
    header_offset = pe.sections[-1].get_file_offset() + 40
    assert header_offset + 40 <= pe.OPTIONAL_HEADER.SizeOfHeaders and not any(old[header_offset:header_offset + 40])
    raw_size = align(len(payload), pe.OPTIONAL_HEADER.FileAlignment)
    data[header_offset:header_offset + 40] = struct.pack('<8sIIIIIIHHI', b'.kjson\0\0', len(payload), section_rva, raw_size, section_raw, 0, 0, 0, 0, 0x60000020)
    struct.pack_into('<H', data, pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'), len(pe.sections) + 1)
    struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'), align(section_rva + len(payload), pe.OPTIONAL_HEADER.SectionAlignment))
    struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfCode'), pe.OPTIONAL_HEADER.SizeOfCode + raw_size)
    data += b'\0' * (section_raw - len(data)) + payload + b'\0' * (raw_size - len(payload))
    checksum_offset = pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum')
    if pe.OPTIONAL_HEADER.CheckSum:
        struct.pack_into('<I', data, checksum_offset, pefile.PE(data=data).generate_checksum())
    output.mkdir()
    for item in old_audit['candidate_files']:
        name = item['file']
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (previous / name).read_bytes()
        assert inv.sha(raw) == item['candidate_sha256']
        path.write_bytes(bytes(data) if name == 'Modules/Steamworks.mfx' else raw)
    headers = [[header_offset, header_offset + 40], [pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'), pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections') + 2]]
    headers += [[pe.OPTIONAL_HEADER.get_field_absolute_offset(x), pe.OPTIONAL_HEADER.get_field_absolute_offset(x) + 4] for x in ['SizeOfImage', 'SizeOfCode', 'CheckSum']]
    audit = {'status': 'NOT_RUN', 'candidate': str(output.relative_to(inv.ROOT)), 'parent_candidate': str(previous.relative_to(inv.ROOT)),
             'parent_validation_sha256': inv.sha((previous / 'independent_validation.json').read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()),
             'input_rows_sha256': inv.sha(rows_path.read_bytes()), 'file': 'Modules/Steamworks.mfx', 'source_sha256': inv.sha(old), 'candidate_sha256': inv.sha(data),
             'patches': patches, 'header_ranges': headers, 'new_section': {'rva': section_rva, 'file_offset': section_raw, 'size': len(payload), 'raw_size': raw_size},
             'wrapper': {'rva': section_rva, 'bytes': wrapper.hex(), 'size': len(wrapper), 'convert_iat_rva': imports['MultiByteToWideChar'], 'message_iat_rva': imports['MessageBoxW']},
             'translations': translations, 'inherited_fields': 167, 'added_fields': 22, 'graphics_qa': 'NOT_RUN', 'full_native_classification': 'NOT_RUN'}
    (output / 'native_json_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'candidate': str(output), 'fields': 189, 'patches': len(patches), 'wrapper_bytes': len(wrapper)}))


if __name__ == '__main__':
    main()
