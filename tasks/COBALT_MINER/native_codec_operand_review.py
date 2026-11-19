"""코드 원시4바이트 일치가 명령 경계를 가로지르는지 보조 판독합니다."""
import collections
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native/media_codec_review_01'
SOURCE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
INSPECTOR = ROOT / 'tasks/THE_HORDE_OF_GORAK/native_inspect.py'
spec = importlib.util.spec_from_file_location('codec_aux_disassembler', INSPECTOR)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    report = json.loads((BASE/'structures.json').read_text(encoding='utf-8'))
    results = []
    for region in report['results']:
        path = SOURCE/region['file']
        data = path.read_bytes()
        pe = pefile.PE(data=data)
        assert hashlib.sha256(data).hexdigest() == region['file_sha256']
        for kind, candidates in region['raw_code_coordinate_candidates'].items():
            for item in candidates:
                position = item['word_offset']
                lower = max(0, position-0x10000)
                starts = []
                for pattern in (b'\x8b\xff\x55\x8b\xec', b'\x55\x8b\xec'):
                    start = data.rfind(pattern, lower, position)
                    if start >= 0:
                        starts.append(start)
                decoded = None
                for start in sorted(set(starts), reverse=True):
                    va = pe.OPTIONAL_HEADER.ImageBase+pe.get_rva_from_offset(start)
                    instructions = module.disassemble(path, va, position+20-start)
                    selected = []
                    for index, instruction in enumerate(instructions):
                        instruction_start = pe.get_offset_from_rva(int(instruction['address'],16)-pe.OPTIONAL_HEADER.ImageBase)
                        instruction_end = instruction_start+len(bytes.fromhex(instruction['bytes']))
                        if instruction_start < position+4 and position < instruction_end:
                            selected.append({**instruction, 'instruction_start': instruction_start,
                                             'instruction_end': instruction_end})
                    if selected and selected[-1]['instruction_end'] >= position+4:
                        decoded = {'linear_sweep_start': start, 'instructions': selected}
                        break
                status = 'DECODE_NOT_REACHED'
                if decoded:
                    if len(decoded['instructions']) > 1:
                        status = 'WORD_CROSSES_INSTRUCTION_BOUNDARIES'
                    else:
                        instruction = decoded['instructions'][0]['instruction']
                        if instruction.startswith(('call ', 'jmp ', 'je ', 'jne ', 'ja ', 'jae ', 'jb ', 'jbe ', 'jg ', 'jge ', 'jl ', 'jle ')):
                            status = 'RELATIVE_CONTROL_FLOW_ENCODING'
                        elif int(item['value'],16) not in [int(value,16) for value in re.findall(r'0x[0-9a-f]+', instruction)]:
                            status = 'WORD_CROSSES_INSTRUCTION_ENCODING_FIELDS'
                        elif kind == 'file_offset' and int(item['value'],16) == 0xf0000:
                            status = 'SDK_WRITE_MASK_VALUE_NOT_A_RUNTIME_VA_OR_RVA'
                        elif instruction.startswith(('and ', 'or ', 'xor ', 'test ')):
                            status = 'BIT_OPERATION_REQUIRES_CONTEXT'
                        else:
                            status = 'SINGLE_INSTRUCTION_REQUIRES_CONTEXT'
                results.append({'file': region['file'], 'coordinate': kind, **item, 'auxiliary_status': status, 'decoded': decoded})
    # 유일하게 선형 해독이 닿지 않은 VA 일치는 switch의 바이트 인덱스 표 내부입니다.
    source9 = SOURCE/'Modules/mmf2d3d9.dll'
    bytes9 = source9.read_bytes()
    byte_index_data = bytes9[0x1e4a4:0x1e4a4+90]
    assert bytes9[0x1e4b2:0x1e4b6] == bytes.fromhex('0d0e0f10')
    assert len(byte_index_data) == 90 and max(byte_index_data) == 59
    index_instructions = module.disassemble(source9, 0x1001de3f, 0x23)
    assert any(i['instruction'] == 'cmp eax, 0x59' for i in index_instructions)
    assert any(i['instruction'] == 'movzx eax, byte ptr [eax + 0x1001f0a4]' for i in index_instructions)
    assert any(i['instruction'] == 'jmp dword ptr [eax*4 + 0x1001efb4]' for i in index_instructions)
    for result in results:
        if result['file'] == 'Modules/mmf2d3d9.dll' and result['word_offset'] == 0x1e4b2:
            result['auxiliary_status'] = 'FOUR_SWITCH_INDEX_BYTES_NOT_A_POINTER'
            result['switch_index_evidence'] = {'table_offset': 0x1e4a4, 'element_size': 1, 'elements': 90,
                                                'raw_sha256': hashlib.sha256(byte_index_data).hexdigest(),
                                                'consumer_instructions': index_instructions}
    sdk = Path('C:/Program Files (x86)/Windows Kits/10/Include/10.0.22621.0/shared/d3d9types.h')
    assert re.search(r'#define\s+D3DSP_WRITEMASK_ALL\s+0x000F0000', sdk.read_text(encoding='utf-8-sig'))
    summary = {'status': 'AUXILIARY_ONLY', 'candidate_count': len(results),
               'by_status': dict(collections.Counter(r['auxiliary_status'] for r in results)),
               'input_sha256': hashlib.sha256((BASE/'structures.json').read_bytes()).hexdigest(),
               'inspector_sha256': hashlib.sha256(INSPECTOR.read_bytes()).hexdigest(),
               'capstone_sha256': hashlib.sha256(module.CAPSTONE.read_bytes()).hexdigest(),
               'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'sdk_write_mask_reference': {'path': str(sdk), 'sha256': hashlib.sha256(sdk.read_bytes()).hexdigest(),
                                           'identifier': 'D3DSP_WRITEMASK_ALL', 'value': 0xf0000},
               'limitations': '로컬 x86 보조 판독기이며 Ghidra 응답이 아님. 검색한 함수 시작 패턴에서 선형 해독했으므로 도달성 또는 완전한 함수 경계 증명으로 사용하지 않음. UNKNOWN 분류는 변경하지 않음.'}
    (BASE/'operand_review_02.json').write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
