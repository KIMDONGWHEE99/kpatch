"""Ghidra가 확인한 세 구문 분석기의 int16 표와 실제 원본 바이트를 대조합니다."""
import collections
import hashlib
import json
import re
import struct
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
BASE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
OUT = NATIVE / 'media_numeric_review_03'
PREVIOUS = NATIVE / 'media_numeric_review_02/remaining_unknown.json'
EVIDENCE = NATIVE / 'media_numeric_review_02/rea_d3d9_parser_tables.json'
FILE = 'Modules/mmf2d3d9.dll'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    prior = json.loads(PREVIOUS.read_text(encoding='utf-8'))
    rows = prior['rows']
    data = (BASE / FILE).read_bytes()
    pe = pefile.PE(data=data)
    bundle = json.loads(EVIDENCE.read_text(encoding='utf-8'))
    # 16비트 자료 주소는 현재 PE 주소 매핑으로 변환합니다. 인접한 정렬 여백은 포함하지 않습니다.
    specs = [
        ('0x10011dd9', 0x172, [0x10108268, 0x101082c8, 0x10108328, 0x101083c8, 0x101083e8, 0x10108488, 0x10108528, 0x10108548, 0x10108830]),
        ('0x100245bd', 0xd89, [0x10108b18, 0x10108d68, 0x10108fb8, 0x10109380, 0x10109468, 0x10109830, 0x10109bf8, 0x10109ce0, 0x1010b7f8]),
        ('0x100624c9', 0x128, [0x1010ec58, 0x1010ecd8, 0x1010ed58, 0x1010ee60, 0x1010eea0, 0x1010efa8, 0x1010f0b0, 0x1010f0f0, 0x1010f340]),
    ]
    roles = ['rule_lhs', 'rule_length', 'default_reduction', 'default_goto', 'shift_base', 'reduction_base', 'goto_base', 'transition_value', 'transition_check']
    structures, functions = [], []
    for procedure, table_count, addresses in specs:
        record = next(r for r in bundle['records'] if r.get('operation') == 'procedure_pseudo_code' and r.get('parameters', {}).get('procedure') == procedure)
        if record['provider']['id'] != 'ghidra' or record['subject']['digest']['sha256'] != sha(data):
            raise ValueError('실제 Ghidra 응답/현재 DLL 지문 불일치')
        pseudo = record['normalized_result']
        if not all(f'{address:08x}' in pseudo.lower() for address in addresses):
            raise ValueError('구문 분석기 소비 주소 누락')
        if f'< 0x{table_count:x}' not in pseudo or '*(short *)' not in pseudo or 'syntax error' not in pseudo or 'yacc stack overflow' not in pseudo:
            raise ValueError('상태 표 폭·경계·구문 분석 문맥 불일치')
        offsets = [pe.get_offset_from_rva(address-pe.OPTIONAL_HEADER.ImageBase) for address in addresses]
        case_values = [int(value, 0) for value in re.findall(r'case (0x[\da-f]+|\d+):', pseudo)]
        rule_count = max(case_values) + 1
        lhs = struct.unpack_from('<' + 'h'*rule_count, data, offsets[0])
        rule_lengths = struct.unpack_from('<' + 'h'*rule_count, data, offsets[1])
        table = struct.unpack_from('<' + 'h'*table_count, data, offsets[7])
        checks = struct.unpack_from('<' + 'h'*table_count, data, offsets[8])
        nonterminal_count = max(lhs) + 1
        state_count = max(table) + 1
        counts = [rule_count, rule_count, state_count, nonterminal_count, state_count, state_count, nonterminal_count, table_count, table_count]
        if lhs[0] != -1 or any(x < 0 for x in lhs[1:]) or any(x < 0 for x in rule_lengths) or min(table) < 0 or min(checks) < -1:
            raise ValueError('문법 규칙·상태 표 값의 범위 불일치')
        if any(offsets[i]+counts[i]*2 > offsets[i+1] for i in range(len(offsets)-1)):
            raise ValueError('검증한 자료 표가 인접 표의 경계를 넘음')
        default_reductions = struct.unpack_from('<'+'h'*state_count, data, offsets[2])
        default_gotos = struct.unpack_from('<'+'h'*nonterminal_count, data, offsets[3])
        if not all(0 <= x < rule_count for x in default_reductions) or not all(0 <= x < state_count for x in default_gotos):
            raise ValueError('축약 규칙 또는 goto 상태 번호가 실제 표 범위 밖임')
        function = {'queried_address': procedure, 'name': re.search(r'FUN_[\da-f]+', pseudo)[0],
                    'evidence_id': record['evidence_id'], 'evidence_sha256': sha(EVIDENCE.read_bytes()),
                    'provider': record['provider'], 'rule_count': rule_count, 'state_count': state_count,
                    'nonterminal_count': nonterminal_count, 'table_count': table_count,
                    'count_basis': '규칙 switch의 최대 case+1, lhs 전체 최대값+1, shift/goto 테이블 값 최대+1, Ghidra의 명시적 전이 인덱스 상한',
                    'observed_use': '토큰과 16비트 check 값을 비교하여 shift/reduce/goto 상태 스택을 갱신. 별도 오류 문자열 출력은 이 분류 범위에 포함하지 않음.'}
        functions.append(function)
        for address, start, count, role in zip(addresses, offsets, counts, roles):
            end = start + count*2
            values = struct.unpack_from('<'+'h'*count, data, start)
            structures.append({'id': f'PARSER_INT16_TABLE:{address:x}', 'type': 'PARSER_INT16_TABLE',
                               'file': FILE, 'file_sha256': sha(data), 'preferred_va': hex(address), 'start': start, 'end': end,
                               'raw_sha256': sha(data[start:end]), 'element_type': 'int16 little endian', 'elements': count,
                               'min': min(values), 'max': max(values), 'role': role, 'function': function,
                               'reason': '실제 Ghidra 구문 분석 함수가 short 값으로 읽는 상태·규칙·전이 자료. 원본 전체 항목의 형식과 인접 경계, 규칙·상태 범위를 검증했으며 정렬 여백·실제 메시지는 제외함.'})
    proposals, remaining = [], []
    for row in rows:
        proofs = [s for s in structures if s['file'] == row['file'] and s['start'] <= row['file_offset'] and row['file_offset']+row['bytes'] <= s['end']]
        if proofs:
            if row['file_sha256'] != sha(data) or row['source_bytes_sha256'] != sha(data[row['file_offset']:row['file_offset']+row['bytes']]):
                raise ValueError('제안 대상 원본 바이트 지문 불일치')
            proposals.append({**row, 'classification': 'INTERNAL', 'reason': proofs[0]['reason'], 'proposal_only': True,
                              'numeric_evidence_ids': [s['id'] for s in proofs],
                              'numeric_review_evidence': str((OUT/'structures.json').relative_to(ROOT))})
        else:
            remaining.append(row)
    dependencies = {'previous_unknowns': str(PREVIOUS.relative_to(ROOT)), 'previous_unknowns_sha256': sha(PREVIOUS.read_bytes()),
                    'rea_evidence': str(EVIDENCE.relative_to(ROOT)), 'rea_evidence_sha256': sha(EVIDENCE.read_bytes()),
                    'script_sha256': sha(Path(__file__).read_bytes()), 'source_sha256': sha(data),
                    'scope': '숫자군 잔여 항목 중 27개 int16 표 내부에 완전히 들어가는 바이트만. 공유 분류표 미수정.'}
    outputs = {'structures.json': {'dependencies': dependencies, 'functions': functions, 'structures': structures},
               'classification_proposals.json': {'dependencies': dependencies, 'proposals': proposals},
               'remaining_unknown.json': {'dependencies': dependencies, 'rows': remaining}}
    for name, value in outputs.items():
        (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {**dependencies, 'status': 'PROPOSAL_READY', 'targets': len(rows), 'proposed_internal': len(proposals),
               'remaining_unknown': len(remaining), 'tables': len(structures), 'ghidra_functions': len(functions),
               'by_function': dict(collections.Counter(next(s['function']['name'] for s in structures if s['id'] == p['numeric_evidence_ids'][0]) for p in proposals)),
               'proposal_sha256': sha((OUT/'classification_proposals.json').read_bytes()),
               'structures_sha256': sha((OUT/'structures.json').read_bytes()), 'shared_inventory_modified': False}
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
