"""실제 엔진 제목·CRT 숫자 출력·DLL 로딩 경계의 근거를 분류표에 적용합니다."""
import collections
import json
import re
import struct
from pathlib import Path
import pefile
import native_inventory as inv
from native_inspect import disassemble


def main():
    input_path = inv.OUT / 'native_inventory_v11.jsonl'
    rows = [json.loads(x) for x in input_path.read_text(encoding='utf-8').split('\n') if x]
    evidence_path = inv.OUT / 'rea_exe_engine_strings.json'
    records = json.loads(evidence_path.read_text(encoding='utf-8'))['records']
    proofs = {x['parameters'].get('procedure'): x for x in records if x['operation'] == 'procedure_pseudo_code'}
    images = {file: (inv.BASE / file).read_bytes() for file in sorted({x['file'] for x in rows})}
    exe = images['COBALT MINER.exe']
    assert all(x['provider']['id'] == 'ghidra' and x['subject']['digest']['sha256'] == inv.sha(exe) for x in proofs.values())
    shared = {'evidence_path': str(evidence_path.relative_to(inv.ROOT)), 'evidence_sha256': inv.sha(evidence_path.read_bytes())}
    changes, structures, code_matches = [], [], []
    translations = {'Untitled': '제목 없음', ' - 24 bit': ' - 24비트', ' - 32 bit': ' - 32비트'}
    keep_titles = {' - D3D8', ' - D3D9', ' - D3D11', ' - DLL #%d', '%s - %s'}
    effects = {'Invert', 'Mono', 'Blend'}
    for row in rows:
        if row['file'] != 'COBALT MINER.exe' or row['classification'] != 'UNKNOWN':
            continue
        source = row['source']
        if source in translations:
            row.update(classification='VISIBLE_TRANSLATE', translation=translations[source],
                       reason='실제 Ghidra 함수가 SetWindowTextW 창 제목으로 전달하는 기본 제목 또는 색상 깊이 문구',
                       additional_evidence={**shared, 'consumers': [proofs['0x407ff4']['evidence_id'], proofs['0x40762d']['evidence_id']],
                                            'literal_copy_limit': 'bit 문구는 앞8 WCHAR 복사 뒤 코드에서 t/NUL을 씀. 번역은7 WCHAR 뒤 NUL이므로 뒤 t가 출력되지 않도록 독립 검증 필요'})
        elif source in keep_titles:
            row.update(classification='VISIBLE_KEEP', reason='그래픽 API·DLL의 기술 식별자 또는 제목 값 두 개 사이의 서식·구분 기호. 임의로 한글화하지 않음',
                       additional_evidence={**shared, 'consumer': proofs['0x40762d' if source != '%s - %s' else '0x407ff4']['evidence_id']})
        elif source in effects:
            row.update(classification='INTERNAL', reason='wcsicmp 비교 후 효과 종류 정수로 변환하는 엔진 효과 선택 키',
                       additional_evidence={**shared, 'consumer': proofs['0x44e309']['evidence_id']})
        elif source == 'Button':
            row.update(classification='INTERNAL', reason='GetClassNameW의 반환값과 비교하여 버튼 창의 입력 처리 함수를 지정하는 클래스 식별자',
                       additional_evidence={**shared, 'consumer': proofs['0x45b62c']['evidence_id']})
        else:
            continue
        changes.append(row)
    # 대표 함수의 제어 코드를 전체 비교합니다. 재배치 주소와 외부 call 목적지만 정규화합니다.
    float_record = proofs['0x475a77']
    assert '__acrt_fp_classify' in float_record['normalized_result'] and '_strcpy_s(pcVar17,param_6,_Src)' in float_record['normalized_result']
    special_tokens = {'1#INF', '1#QNAN', '1#SNAN', '1#IND'}
    normalized_reference = None
    float_source = Path('C:/Program Files (x86)/Windows Kits/10/Source/10.0.22621.0/ucrt/convert/cfout.cpp')
    for row in [x for x in rows if x['source'] == '1#INF' and x['classification'] == 'UNKNOWN']:
        file, raw = row['file'], images[row['file']]
        pe = pefile.PE(data=raw)
        start = row['static_references'][0]['pointer_offsets'][0] - 1 - 0x1353
        if start < 0:
            continue
        length = 0x139c
        address = pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(start)
        code = disassemble(inv.BASE / file, address, length)
        if sum(len(bytes.fromhex(x['bytes'])) for x in code) != length:
            continue
        normalized = bytearray(raw[start:start + length])
        relocations = []
        for block in pe.DIRECTORY_ENTRY_BASERELOC:
            for item in block.entries:
                at = pe.get_offset_from_rva(item.rva)
                if item.type == 3 and start <= at <= start + length - 4:
                    normalized[at - start:at - start + 4] = bytes(4)
                    relocations.append(at)
        calls = []
        for instruction in code:
            if instruction['bytes'].startswith('e8') and len(instruction['bytes']) == 10:
                at = int(instruction['address'], 16) - address
                normalized[at + 1:at + 5] = bytes(4)
                calls.append(instruction)
        if file == 'COBALT MINER.exe':
            normalized_reference = bytes(normalized)
        if normalized_reference is None or normalized != normalized_reference:
            continue
        selected = [x for x in rows if x['file'] == file and x['classification'] == 'UNKNOWN' and x['source'] in special_tokens]
        assert len(selected) == 4
        assert all(len(x['static_references']) == 1 and len(x['static_references'][0]['pointer_offsets']) == 1 and start <= x['static_references'][0]['pointer_offsets'][0] < start + length for x in selected)
        proof = {'file': file, 'file_sha256': inv.sha(raw), 'start': start, 'end': start + length,
                 'code_sha256': inv.sha(raw[start:start + length]), 'normalized_code_sha256': inv.sha(normalized),
                 'instructions': len(code), 'relocation_operands': relocations, 'direct_calls': calls,
                 'representative_evidence_id': float_record['evidence_id'],
                 'source_path': str(float_source), 'source_sha256': inv.sha(float_source.read_bytes()),
                 'scope': '5020바이트 전체 제어 코드 일치. 절대 재배치 주소와 E8 call 상대 목적지만 제외하고 분기·수치 상수·명령은 보존'}
        code_matches.append(proof)
        for item in selected:
            item.update(classification='VISIBLE_KEEP', reason='부동소수 숫자 변환기가 비유한 수를 나타내는 고정 숫자 표기(INF/NaN/IND). 자연어 오류 본문과 구분하여 원래 숫자 문법을 유지함',
                        additional_evidence={**shared, 'numeric_type': 'CRT_NONFINITE_NUMBER_FORMAT', 'function_match': proof})
            changes.append(item)
    # 각 파일에서 20항 DLL 이름 표와 실제 LoadLibraryExW 호출 명령을 다시 확인합니다.
    reference_pe = pefile.PE(data=exe)
    reference_table = 0x86f58

    def wide(raw, at):
        end = at
        while raw[end:end + 2] != bytes(2):
            end += 2
        return raw[at:end].decode('utf-16le')

    names = [wide(exe, reference_pe.get_offset_from_rva(struct.unpack_from('<I', exe, reference_table + i * 4)[0] - 0x400000)) for i in range(20)]
    assert 'LoadLibraryExW(lpLibFileName' in proofs['0x473ebd']['normalized_result']
    for file, raw in images.items():
        if not file.endswith(('.exe', '.dll', '.mfx', '.sft')):
            continue
        pe = pefile.PE(data=raw)
        needle = names[0].encode('utf-16le') + bytes(2)
        first = raw.find(needle)
        if first < 0:
            continue
        first_va = pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(first)
        candidates = [at for at in range(max(0, first - 96), first, 4) if struct.unpack_from('<I', raw, at)[0] == first_va]
        for table in candidates:
            offsets = []
            try:
                for i, expected in enumerate(names):
                    at = pe.get_offset_from_rva(struct.unpack_from('<I', raw, table + i * 4)[0] - pe.OPTIONAL_HEADER.ImageBase)
                    assert wide(raw, at) == expected
                    offsets.append(at)
            except (AssertionError, pefile.PEFormatError, UnicodeDecodeError):
                continue
            table_va = pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(table)
            pattern = b'\x8b\x1c\x85' + struct.pack('<I', table_va) + bytes.fromhex('5668000800006a0053ff15')
            code_at = raw.find(pattern)
            if code_at < 0:
                continue
            iat = struct.unpack_from('<I', raw, code_at + len(pattern))[0]
            imports = {x.address: x.name for module in pe.DIRECTORY_ENTRY_IMPORT for x in module.imports}
            assert imports.get(iat) == b'LoadLibraryExW'
            relocated = {pe.get_offset_from_rva(x.rva) for block in pe.DIRECTORY_ENTRY_BASERELOC for x in block.entries if x.type == 3}
            assert all(table + i * 4 in relocated for i in range(20))
            proof = {'file': file, 'file_sha256': inv.sha(raw), 'table_start': table, 'table_end': table + 80,
                     'table_sha256': inv.sha(raw[table:table + 80]), 'names': names, 'literal_offsets': offsets,
                     'consumer_offset': code_at, 'consumer_bytes': raw[code_at:code_at + len(pattern) + 4].hex(),
                     'representative_evidence_id': proofs['0x473ebd']['evidence_id']}
            structures.append(proof)
            for item in rows:
                if item['file'] != file or item['classification'] != 'UNKNOWN':
                    continue
                at = item['file_offset']
                exact = at in offsets
                prefix = at + 2 == first and first == table + 80 and at - 2 in relocated
                if exact or prefix:
                    item.update(classification='INTERNAL', reason='20항 UTF16 DLL 이름 표의 구성원으로 인덱스 조회 후 LoadLibraryExW의 파일명 인수로 전달됨. 행 앞의 인접 포인터 상위2바이트가 붙은 경우도 원시 구조로 분리 확인',
                                additional_evidence={**shared, 'loader_table': proof, 'adjacent_pointer_prefix': prefix})
                    changes.append(item)
    inv.save('native_inventory_v12.jsonl', rows)
    previous = json.loads((inv.OUT / 'native_visible_worklist_v4.json').read_text(encoding='utf-8'))
    additional = [x for x in changes if x['classification'] == 'VISIBLE_TRANSLATE']
    assert len(additional) == 3
    inv.save('native_visible_worklist_v5.json', previous + additional)
    inv.save('engine_classification.json', {'input_sha256': inv.sha(input_path.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()),
             'changes': changes, 'loader_structures': structures, 'float_function_matches': code_matches})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'resolved': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v12.jsonl').read_bytes()), 'native_candidate_03_content_affected': False,
               'new_candidate_required': 'native_candidate_04', 'new_translation_fields': 3}
    inv.save('summary_v12.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
