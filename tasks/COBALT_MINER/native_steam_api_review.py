"""Steam SDK 공통 함수의 실제 Ghidra 소비 경계로 식별자와 개발 로그를 묶어 판정합니다."""
import ast
import collections
import json
import re
import struct
from pathlib import Path
import pefile
import native_inventory as inv


def main():
    input_path = inv.OUT / 'native_inventory_v7.jsonl'
    evidence_path = inv.OUT / 'rea_steam_api_consumers.json'
    rows = [json.loads(x) for x in input_path.read_text(encoding='utf-8').split('\n') if x]
    records = json.loads(evidence_path.read_text(encoding='utf-8'))['records']
    data = (inv.BASE / 'Modules/steam_api.dll').read_bytes()
    pe = pefile.PE(data=data)
    relocations = {pe.get_offset_from_rva(x.rva) for b in pe.DIRECTORY_ENTRY_BASERELOC for x in b.entries if x.type == 3}
    reasons = {
        '0x3b4061d0': 'SteamClient 가상함수로 요청하고 반환 포인터를 인터페이스 표에 저장하는 버전 식별자',
        '0x3b4051b0': 'GetProcAddress가 조회하는 콜백 함수 이름. 반환값을 함수 포인터 필드에 저장함',
        '0x3b406140': 'stricmp 입력 비교 후 HKEY 정수를 돌려주는 레지스트리 루트 식별자',
        '0x3b405ee0': 'RegOpenKeyExA/RegQueryValueExA로 Steam 설치 라이브러리를 찾는 레지스트리 키/값 식별자',
        '0x3b406430': '모듈 경로를 조립하여 GetModuleHandleA 및 LoadLibraryExW/A 경계에 전달하는 경로 서식',
        'SteamAPI_RestartAppIfNecessary': 'Steam 재시작을 위해 환경 변수·appid 파일·레지스트리·실행 URI/경로로 소비하는 식별자와 서식',
        '0x3b4069a0': '미니덤프 함수명을 GetProcAddress로 조회하거나 고정 stderr FILE 스트림으로 개발 진단을 출력함',
        '0x3b406b60': '고정 stderr FILE 스트림으로 미니덤프 SteamID 설정 과정을 출력하는 개발 로그',
        'SteamAPI_SetBreakpadAppID': '고정 stderr FILE 스트림으로 미니덤프 초기화 과정을 출력하는 개발 로그',
        'SteamAPI_UseBreakpadCrashHandler': 'stderr 개발 로그 또는 충돌 덤프의 빌드 시각을 숫자로 조립하는 서식',
        '0x3b406560': 'Steam 인터페이스 식별자·환경 변수명 또는 OutputDebugStringA 전용 초기화 진단',
        '0x3b406780': 'CreateInterface 함수 조회 또는 OutputDebugStringA 전용 초기화 실패 진단',
    }
    # Ghidra가 반환한 FILE 표의 실제 32바이트 레코드에서 표준 입출력 번호 0/1/2를 확인합니다.
    stream_start = pe.get_offset_from_rva(0x2a140)
    assert [struct.unpack_from('<I', data, stream_start + i * 32 + 16)[0] for i in range(3)] == [0, 1, 2]
    key_proofs = collections.defaultdict(list)
    for record in records:
        procedure = record['parameters'].get('procedure')
        if record['operation'] != 'procedure_pseudo_code' or procedure not in reasons:
            continue
        assert record['provider']['id'] == 'ghidra' and record['subject']['digest']['sha256'] == inv.sha(data)
        for token in re.findall(r'"(?:[^"\\]|\\.)*"', record['normalized_result']):
            value = ast.literal_eval(token)
            if len(value) >= 4:
                key_proofs[value].append({'evidence_id': record['evidence_id'], 'procedure': procedure, 'reason': reasons[procedure]})
    changes = []
    for row in rows:
        if row['file'] != 'Modules/steam_api.dll' or row['classification'] != 'UNKNOWN':
            continue
        key = row['source']
        prefix_proof = None
        if key not in key_proofs and key.endswith('Steam_BGetCallback'):
            prefix = len(key) - len('Steam_BGetCallback')
            at = row['file_offset'] + prefix - 4
            address = struct.unpack_from('<I', data, at)[0]
            target = pe.get_section_by_rva(address - pe.OPTIONAL_HEADER.ImageBase)
            assert at in relocations and target is not None and target.Characteristics & 0x20000000
            prefix_proof = {'pointer_word_offset': at, 'pointer_va': address, 'literal_offset': row['file_offset'] + prefix}
            key = 'Steam_BGetCallback'
        if key not in key_proofs:
            continue
        assert inv.sha(data[row['file_offset']:row['file_offset'] + row['bytes']]) == row['source_bytes_sha256']
        details = key_proofs[key]
        row.update(classification='INTERNAL', reason=details[0]['reason'], additional_evidence={
            'path': str(evidence_path.relative_to(inv.ROOT)), 'sha256': inv.sha(evidence_path.read_bytes()),
            'consumers': details, 'actual_literal': key, 'adjacent_pointer_prefix': prefix_proof,
            'stderr_structure': {'start': stream_start, 'record_size': 32, 'file_descriptors': [0, 1, 2]}})
        changes.append(row)
    inv.save('native_inventory_v8.jsonl', rows)
    inv.save('steam_api_classification.json', {'input_sha256': inv.sha(input_path.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'output_sha256': inv.sha((inv.OUT / 'native_inventory_v8.jsonl').read_bytes()),
               'full_native_classification': 'NOT_RUN', 'native_candidate_03_content_affected': False}
    inv.save('summary_v8.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
