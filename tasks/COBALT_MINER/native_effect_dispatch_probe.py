"""CEffectEx 검증 슬롯(+0x14)의 직접/레지스터 간접 호출 후보를 원본 코드에서 찾습니다."""
import json
import re
from pathlib import Path
import pefile
import native_inventory as inv
from native_api_boundary_review import Decoder


def main():
    data = (inv.BASE / 'COBALT MINER.exe').read_bytes()
    pe = pefile.PE(data=data)
    decoder = Decoder()
    guard_pointer = pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct.GuardCFCheckFunctionPointer
    direct, loaded = [], []
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        start, end = section.PointerToRawData, section.PointerToRawData + section.SizeOfRawData
        for at in range(start, end):
            if data[at] not in (0xff, 0x8b):
                continue
            code = decoder.read(data, at, pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(at), {})
            if not code:
                continue
            first = code[0]['instruction']
            if not re.search(r'\+ 0x14\]', first):
                continue
            if first.startswith(('call ', 'jmp ')):
                direct.append({'file_offset': at, 'instructions': code})
            elif first.startswith('mov '):
                register = first[4:].split(',')[0]
                destinations = {register}
                for instruction in code[1:]:
                    mnemonic, _, operands = instruction['instruction'].partition(' ')
                    if mnemonic in ('call', 'jmp'):
                        if mnemonic == 'call' and operands == f'dword ptr [{hex(guard_pointer)}]':
                            continue
                        if operands in destinations:
                            loaded.append({'file_offset': at, 'instructions': code[:code.index(instruction) + 1]})
                        break
                    if mnemonic.startswith('j') or mnemonic in ('ret', 'int3'):
                        break
                    if mnemonic == 'mov':
                        dest, source = operands.split(', ', 1)
                        if source in destinations:
                            destinations.add(dest)
                        elif dest in destinations:
                            destinations.remove(dest)
                    elif mnemonic in ('lea', 'xor', 'add', 'sub', 'and', 'or', 'pop'):
                        destinations.discard(operands.split(',')[0])
                    if not destinations:
                        break
    result = {'source_sha256': inv.sha(data), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'guard_check_pointer': hex(guard_pointer),
              'direct': direct, 'loaded_then_called': loaded,
              'limits': '전체 실행 절의 각 바이트에서 직접 call/jmp 및 mov 후 짧은 직선 구간 내 레지스터 호출을 조사. 포인터 저장·함수 간 전달·인덱스 계산을 완전한 값 흐름 분석으로 간주하지 않음.'}
    inv.save('effect_dispatch_probe.json', result)
    print(json.dumps({'direct': [(x['instructions'][0]['address'], x['instructions'][0]['instruction']) for x in direct],
                      'loaded_then_called': [(x['instructions'][0]['address'], x['instructions'][0]['instruction'], x['instructions'][-1]['instruction']) for x in loaded]}))


if __name__ == '__main__':
    main()
