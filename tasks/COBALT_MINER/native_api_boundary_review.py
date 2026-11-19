"""주소 리터럴이 Windows API의 이름·경로 인수로 전달되는 짧은 직선 코드를 검증합니다."""
import collections
import ctypes
import json
import re
import struct
from pathlib import Path
import pefile
import native_inventory as inv
from native_inspect import CAPSTONE, Instruction


class Decoder:
    def __init__(self):
        self.library = ctypes.CDLL(str(CAPSTONE))
        self.library.cs_open.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
        self.library.cs_disasm.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_size_t, ctypes.POINTER(ctypes.POINTER(Instruction))]
        self.library.cs_disasm.restype = ctypes.c_size_t
        self.library.cs_free.argtypes = [ctypes.POINTER(Instruction), ctypes.c_size_t]
        self.handle = ctypes.c_size_t()
        assert self.library.cs_open(3, 4, ctypes.byref(self.handle)) == 0

    def read(self, data, start, address, imports):
        raw = data[start:start + 100]
        buffer = ctypes.create_string_buffer(raw)
        pointer = ctypes.POINTER(Instruction)()
        count = self.library.cs_disasm(self.handle.value, buffer, len(raw), address, 16, ctypes.byref(pointer))
        result = []
        for index in range(count):
            value = pointer[index]
            operand = value.op_str.decode()
            result.append({'address': hex(value.address), 'bytes': bytes(value.bytes[:value.size]).hex(),
                           'instruction': value.mnemonic.decode() + ' ' + operand,
                           'imports': [name for target, name in imports.items() if hex(target) in operand]})
        self.library.cs_free(pointer, count)
        return result

API_ARGUMENTS = {
    'GetProcAddress': (1, '함수 조회 이름'),
    'GetModuleHandleA': (0, '모듈 이름'), 'GetModuleHandleW': (0, '모듈 이름'),
    'LoadLibraryA': (0, '모듈 경로'), 'LoadLibraryW': (0, '모듈 경로'),
    'LoadLibraryExA': (0, '모듈 경로'), 'LoadLibraryExW': (0, '모듈 경로'),
    'GetClassInfoA': (1, '윈도 클래스 이름'), 'GetClassInfoW': (1, '윈도 클래스 이름'),
    'CreateWindowExA': (1, '윈도 클래스 이름'), 'CreateWindowExW': (1, '윈도 클래스 이름'),
    'FindFirstFileA': (0, '파일 검색 패턴'), 'FindFirstFileW': (0, '파일 검색 패턴'),
    'GetFileAttributesA': (0, '파일 경로'), 'GetFileAttributesW': (0, '파일 경로'),
    'CreateMutexA': (2, '프로세스 동기화 이름'), 'CreateMutexW': (2, '프로세스 동기화 이름'),
    'CreateEventA': (3, '프로세스 동기화 이름'), 'CreateEventW': (3, '프로세스 동기화 이름'),
    'RegisterWindowMessageA': (0, '프로그램 간 메시지 식별자'), 'RegisterWindowMessageW': (0, '프로그램 간 메시지 식별자'),
    'GetPropA': (1, '윈도 속성 키'), 'GetPropW': (1, '윈도 속성 키'),
    'SetPropA': (1, '윈도 속성 키'), 'SetPropW': (1, '윈도 속성 키'),
    'RemovePropA': (1, '윈도 속성 키'), 'RemovePropW': (1, '윈도 속성 키'),
}


def consume(decoder, imports, data, pe, pointer, literal_va):
    if data[pointer - 1] != 0x68 and not 0xb8 <= data[pointer - 1] <= 0xbf:
        return None
    start = pointer - 1
    rva = pe.get_rva_from_offset(start)
    section = pe.get_section_by_rva(rva)
    if section is None or not section.Characteristics & 0x20000000:
        return None
    address = pe.OPTIONAL_HEADER.ImageBase + rva
    code = decoder.read(data, start, address, imports)
    if not code or len(bytes.fromhex(code[0]['bytes'])) != 5:
        return None
    stack, registers, used = [], {}, []

    def value(operand):
        if re.fullmatch(r'0x[0-9a-f]+|\d+', operand):
            return int(operand, 0)
        return registers.get(operand)

    for instruction in code[:16]:
        text = instruction['instruction']
        mnemonic, _, operands = text.partition(' ')
        used.append(instruction)
        if mnemonic in ('jmp', 'ret', 'int3') or mnemonic.startswith('j'):
            return None
        if mnemonic == 'push':
            stack.insert(0, value(operands))
        elif mnemonic == 'pop':
            registers[operands] = stack.pop(0) if stack else None
        elif mnemonic == 'mov':
            destination, _, source = operands.partition(', ')
            if re.fullmatch(r'e[abcd]x|e[sd]i|ebp|esp', destination):
                registers[destination] = value(source)
            elif source == hex(literal_va):
                return None
        elif mnemonic in ('lea', 'xor', 'add', 'sub', 'and', 'or', 'inc', 'dec'):
            destination = operands.split(',')[0]
            if destination == 'esp':
                return None
            registers[destination] = None
        elif mnemonic == 'call':
            names = [x.split(':', 1)[1] for x in instruction['imports'] if ':' in x]
            if len(names) != 1 or names[0] not in API_ARGUMENTS:
                return None
            index, role = API_ARGUMENTS[names[0]]
            if len(stack) <= index or stack[index] != literal_va:
                return None
            return {'api': names[0], 'argument_index': index, 'role': role, 'instructions': used}
        elif mnemonic not in ('test', 'cmp', 'nop'):
            return None
    return None


def main():
    source = inv.OUT / 'native_inventory_v9.jsonl'
    rows = [json.loads(x) for x in source.read_text(encoding='utf-8').split('\n') if x]
    decoder = Decoder()
    images = {}
    changes = []
    for row in rows:
        if row['classification'] != 'UNKNOWN' or not row.get('static_references'):
            continue
        file = row['file']
        if file not in images:
            path = inv.BASE / file
            data = path.read_bytes()
            pe = pefile.PE(data=data)
            imports = {item.address: module.dll.decode() + ':' + item.name.decode()
                       for module in pe.DIRECTORY_ENTRY_IMPORT for item in module.imports if item.name}
            images[file] = (data, pe, imports)
        data, pe, imports = images[file]
        assert inv.sha(data) == row['file_sha256']
        assert inv.sha(data[row['file_offset']:row['file_offset'] + row['bytes']]) == row['source_bytes_sha256']
        results, complete = [], True
        for reference in row['static_references']:
            if reference['target_offset'] != row['file_offset']:
                complete = False
                break
            target = pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(reference['target_offset'])
            for pointer in reference['pointer_offsets']:
                assert struct.unpack_from('<I', data, pointer)[0] == target
                proof = consume(decoder, imports, data, pe, pointer, target)
                if proof is None:
                    complete = False
                    break
                results.append({'pointer_offset': pointer, **proof})
            if not complete:
                break
        if not complete or not results:
            continue
        row.update(classification='INTERNAL', reason='Windows API의 ' + '·'.join(sorted({x['role'] for x in results})) + ' 인수로 직접 소비됨. 표시 본문 인수와 구분하여 보존함',
                   additional_evidence={'method': '현재 원본의 PE 재배치 참조와 인수 스택을 분기 없는 명령 구간에서 검증',
                                        'all_recorded_literal_references_checked': True, 'consumers': results,
                                        'limitation': '표시 문자열을 인수로 받는 API는 허용하지 않으며 확인되지 않은 간접 경계는 미분류로 유지'})
        changes.append(row)
    inv.save('native_inventory_v10.jsonl', rows)
    inv.save('api_boundary_classification.json', {'input_sha256': inv.sha(source.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v10.jsonl').read_bytes()), 'native_candidate_03_content_affected': False}
    inv.save('summary_v10.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
