"""Ghidra가 확인한 언어 비교·EDIF 자료형 비교·JSON 키 조회를 위치별로 적용합니다."""
import collections
import json
import re
from pathlib import Path
import native_inventory as inv


def main():
    input_path = inv.OUT / 'native_inventory_v4.jsonl'
    evidence_path = inv.OUT / 'rea_steamworks_consumers.json'
    rows = [json.loads(x) for x in input_path.read_text(encoding='utf-8').split('\n') if x]
    records = json.loads(evidence_path.read_text(encoding='utf-8'))['records']
    proof = {x['parameters'].get('procedure'): x for x in records if x['operation'] == 'procedure_pseudo_code'}
    rules = [
        ('0x1000bf60', 395644, 396000, r'_strcmp\(param_1,"([^"]+)"\)', 'Steam 언어명을 국가/언어 코드로 바꾸는 strcmp 입력 비교 키. 표시 문구가 아님'),
        ('0x100186e4', 397968, 398270, r'__strn?icmp\(param_1,"([^"]+)"', 'EDIF 매개변수 종류를 숫자 형식 번호로 바꾸는 stricmp/strnicmp 비교 키. 번역하면 확장 명령 해석이 깨짐'),
        ('0x10017437', 398444, 398560, r'FUN_10004a34\([^;\n]*,"([^"]+)"\)', '확장 명령/조건/표현식의 JSON 사전에서 찾는 속성 이름. 출력 문자열이 아닌 자료 접근 키'),
    ]
    data = (inv.BASE / 'Modules/Steamworks.mfx').read_bytes()
    changes = []
    for procedure, start, end, pattern, reason in rules:
        record = proof[procedure]
        assert record['provider']['id'] == 'ghidra' and record['subject']['digest']['sha256'] == inv.sha(data)
        keys = set(re.findall(pattern, record['normalized_result']))
        assert keys
        for row in rows:
            if row['file'] != 'Modules/Steamworks.mfx' or row['classification'] != 'UNKNOWN' or not start <= row['file_offset'] < end or row['source'] not in keys:
                continue
            assert inv.sha(data[row['file_offset']:row['file_offset'] + row['bytes']]) == row['source_bytes_sha256']
            row.update(classification='INTERNAL', reason=reason, additional_evidence={
                'path': str(evidence_path.relative_to(inv.ROOT)), 'sha256': inv.sha(evidence_path.read_bytes()),
                'evidence_id': record['evidence_id'], 'procedure': procedure, 'matched_key': row['source']})
            changes.append(row)
    inv.save('native_inventory_v5.jsonl', rows)
    inv.save('steam_key_classification.json', {'input_sha256': inv.sha(input_path.read_bytes()), 'changes': changes,
                                             'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'basis': '실제 Ghidra 비교/사전조회 응답과 원본의 위치별 바이트 해시'})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v5.jsonl').read_bytes()), 'native_candidate_03_content_affected': False}
    inv.save('summary_v5.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
