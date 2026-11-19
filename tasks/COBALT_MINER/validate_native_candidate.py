"""후보 파일을 새로 읽고 Windows 리소스 로더로 기대 번역을 독립 대조합니다."""
import argparse
import collections
import ctypes
import hashlib
import json
import struct
from pathlib import Path
import pefile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
WORK = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def dialog_texts(raw):
    """빌더를 불러오지 않고 Windows 대화상자 템플릿을 다시 해석합니다."""
    extended = struct.unpack_from('<H', raw, 2)[0] == 0xffff
    style = struct.unpack_from('<I', raw, 12 if extended else 0)[0]
    count = struct.unpack_from('<H', raw, 16 if extended else 8)[0]
    cursor = 26 if extended else 18
    result = {}
    def field(role):
        nonlocal cursor
        first = struct.unpack_from('<H', raw, cursor)[0]
        if first == 0xffff:
            cursor += 4
            return
        words = []
        while True:
            word = struct.unpack_from('<H', raw, cursor)[0]
            cursor += 2
            if not word:
                break
            words.append(word)
        result[role] = struct.pack('<' + 'H' * len(words), *words).decode('utf-16le')
    for role in ['menu_name', 'window_class', 'dialog_title']:
        field(role)
    if style & 0x40:
        cursor += 6 if extended else 2
        field('font_name')
    for index in range(count):
        cursor = (cursor + 3) & -4
        identifier = struct.unpack_from('<I' if extended else '<H', raw, cursor + (20 if extended else 16))[0]
        cursor += 24 if extended else 18
        field(f'control:{index}:{identifier}:class')
        field(f'control:{index}:{identifier}:text')
        extra = struct.unpack_from('<H', raw, cursor)[0]
        cursor += extra if extra else 2
    if any(raw[cursor:]):
        raise ValueError('해석하지 않은 대화상자 후미')
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidate-id', default='native_candidate_02')
    ap.add_argument('--expected', type=Path)
    args = ap.parse_args()
    candidate = ROOT / 'working_private/COBALT_MINER' / args.candidate_id
    candidate = candidate.resolve()
    if not candidate.is_relative_to(ROOT / 'working_private/COBALT_MINER'):
        raise ValueError('허용 검수 경계 밖')
    expected_path = args.expected.resolve() if args.expected else WORK / 'native_visible_worklist.json'
    if not expected_path.resolve().is_relative_to(ROOT / 'working_private/COBALT_MINER'):
        raise ValueError('기대값은 비공개 작업 경계에 있어야 합니다.')
    expected = json.loads(expected_path.read_text(encoding='utf-8'))
    inventory_path = WORK / 'native_inventory.jsonl'
    positions = [json.loads(line) for line in inventory_path.read_text(encoding='utf-8').split('\n') if line]
    positions = [row for row in positions if row['classification'] == 'VISIBLE_TRANSLATE']
    identity = lambda row: (row['file'], row['kind'], row['file_offset'], row['source_bytes_sha256'], row.get('string_id'), row.get('role'))
    wanted_counts = collections.Counter(identity(row) for row in positions)
    actual_counts = collections.Counter(identity(row) for row in expected)
    if wanted_counts != actual_counts or any(value != 1 for value in actual_counts.values()):
        raise ValueError('기대값 위치 누락·중복·예상 밖 위치')
    audit = json.loads((candidate / 'native_patch_audit.json').read_text(encoding='utf-8'))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
    kernel.LoadLibraryExW.restype = ctypes.c_void_p
    kernel.FreeLibrary.argtypes = [ctypes.c_void_p]
    kernel.FindResourceExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint16]
    kernel.FindResourceExW.restype = ctypes.c_void_p
    kernel.LoadResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.LoadResource.restype = ctypes.c_void_p
    kernel.SizeofResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.SizeofResource.restype = ctypes.c_uint32
    kernel.LockResource.argtypes = [ctypes.c_void_p]
    kernel.LockResource.restype = ctypes.c_void_p
    user.LoadStringW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_int]
    user.LoadStringW.restype = ctypes.c_int
    loaded, resources, outputs, blobs, inputs = {}, {}, [], {}, []
    try:
        for entry in audit['files']:
            name = entry['file']
            original, raw = (BASE / name).read_bytes(), (candidate / name).read_bytes()
            assert digest(original) == entry['source_sha256'] and digest(raw) == entry['candidate_sha256']
            assert len(original) == len(raw)
            for index, (a, b) in enumerate(zip(original, raw)):
                if a != b and not any(start <= index < end for start, end in entry['allowed_ranges']):
                    raise ValueError('허용 경계 밖 변경')
            # 허용 범위와 별개로 실행 코드·참조 배치가 실제 동일한지 검사합니다.
            old_pe, new_pe = pefile.PE(data=original), pefile.PE(data=raw)
            for old, new in zip(old_pe.sections, new_pe.sections):
                assert old.Name == new.Name and old.VirtualAddress == new.VirtualAddress
                if old.Characteristics & 0x20000000:
                    assert old.get_data() == new.get_data()
            blobs[name] = raw
            inputs.append({'file': name, 'source_sha256': digest(original), 'candidate_sha256': digest(raw)})
        for row in expected:
            name, wanted = row['file'], row['translation']
            if row['kind'] == 'section_string':
                raw = blobs[name]
                offset, end = row['file_offset'], row['file_offset']
                while raw[end:end + 2] != b'\0\0':
                    end += 2
                    if end > offset + row['bytes']:
                        raise ValueError('문자열 종료 없음')
                actual = raw[offset:end].decode('utf-16le')
                identity = f'literal:{offset}'
            else:
                if name not in loaded:
                    # 데이터 전용 플래그: 게임 코드·DllMain을 실행하지 않습니다.
                    loaded[name] = kernel.LoadLibraryExW(str(candidate / name), None, 0x22)
                    assert loaded[name], (name, ctypes.get_last_error())
                if row['kind'] == 'RT_STRING':
                    buffer = ctypes.create_unicode_buffer(4096)
                    count = user.LoadStringW(loaded[name], row['string_id'], buffer, len(buffer))
                    actual = buffer.value
                    assert count == len(actual)
                    identity = f"RT_STRING:{row['string_id']}"
                else:
                    key = (name, row['resource_name']['id'], row['resource_language']['id'])
                    if key not in resources:
                        found = kernel.FindResourceExW(loaded[name], 5, key[1], key[2])
                        assert found
                        size = kernel.SizeofResource(loaded[name], found)
                        pointer = kernel.LockResource(kernel.LoadResource(loaded[name], found))
                        assert pointer and size
                        resources[key] = dialog_texts(ctypes.string_at(pointer, size))
                    actual = resources[key][row['role']]
                    identity = f'RT_DIALOG:{key[1]}:{key[2]}:{row["role"]}'
            assert actual == wanted, (name, identity, actual, wanted)
            outputs.append({'file': name, 'identity': identity, 'expected': wanted, 'actual': actual, 'status': 'PASS'})
    finally:
        for handle in loaded.values():
            kernel.FreeLibrary(handle)
    report = {'game_id': 'COBALT_MINER', 'build_id': args.candidate_id, 'status': 'PASS',
              'method': '새 파일 읽기·Windows 데이터전용 리소스 로더·별도 대화상자 파서',
              'records': outputs, 'checked_fields': len(outputs), 'candidate_files': inputs,
              'expected_sha256': digest(expected_path.read_bytes()), 'validator_sha256': digest(Path(__file__).read_bytes()),
              'game_executed': False, 'graphics_qa': 'NOT_RUN', 'full_native_classification': 'NOT_RUN'}
    report_path = expected_path.with_suffix('.validation.json') if args.expected else candidate / 'independent_validation.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'fields': len(outputs), 'files': len(inputs), 'game_executed': False}))

if __name__ == '__main__':
    main()
