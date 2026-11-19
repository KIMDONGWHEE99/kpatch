"""프로필·명령·레지스터 표와 어휘 분석기의 실제 문자열 위치를 다시 대조합니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv


def main():
    source = inv.OUT / 'native_inventory_v17.jsonl'
    folder = inv.OUT / 'media_keyword_review_03'
    proposal_path, structure_path = folder / 'classification_proposals.json', folder / 'structures.json'
    proposals, structures = inv.read(proposal_path), inv.read(structure_path)
    deps = proposals['dependencies']
    assert inv.sha((inv.ROOT / deps['inventory']).read_bytes()) == deps['inventory_sha256']
    evidence_path = inv.ROOT / deps['rea_evidence']
    assert inv.sha(evidence_path.read_bytes()) == deps['rea_evidence_sha256']
    data = (inv.BASE / deps['source_file']).read_bytes()
    assert inv.sha(data) == deps['source_sha256']
    pe = pefile.PE(data=data)
    records = {r['parameters']['procedure']: r for r in inv.read(evidence_path)['records'] if r['operation'] == 'procedure_pseudo_code'}
    checks = {'0x1002118e': ['"template"', '"virtual"', 'return 0x151;'],
              '0x1004cadd': ['local_8 = 0x2c;', 'uVar3 * 0xc'],
              '0x1005fa5a': ['uVar3 + 0x44', 'uVar3 < 0x1650'],
              '0x10061a4d': ['uVar2 + 0x48', 'uVar2 < 0x5e8']}
    for address, tokens in checks.items():
        record = records[address]
        assert record['provider']['id'] == 'ghidra' and record['subject']['digest']['sha256'] == inv.sha(data)
        assert all(t in record['normalized_result'] for t in tokens)
    literals = collections.defaultdict(set)

    def check_name(name, identity):
        start, end = name['start'], name['end']
        assert data[start:end].decode('ascii') == name['source'] and data[end] == 0
        assert inv.sha(data[start:end]) == name['source_bytes_sha256']
        assert struct.unpack_from('<I', data, name['pointer_field'])[0] == pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(start)
        literals[start].add(identity)

    for table in structures['tables']:
        assert inv.sha(data[table['start']:table['end']]) == table['raw_sha256']
        assert len(table['entries']) == table['count']
        assert table['end'] - table['start'] == table['count'] * table['stride']
        for entry in table['entries']:
            at = entry['record_offset']
            raw = data[at:at + table['stride']]
            assert inv.sha(raw) == entry['raw_sha256']
            assert list(struct.unpack('<' + 'I' * (table['stride'] // 4), raw)) == entry['dwords']
            check_name(entry['name'], table['id'])
    lexer = records['0x1002118e']['normalized_result']
    for item in structures['lexer']:
        check_name(item['name'], item['id'])
        assert '"' + item['name']['source'] + '"' in lexer
        at = item['name']['pointer_field'] - 1
        assert data[at:at + 5].hex() == item['instruction_prefix_hex']
        assert data[at] in range(0xb8, 0xc0) or data[at] == 0x68
    rows = [json.loads(x) for x in source.read_text(encoding='utf-8').split('\n') if x]
    positions = {(x['file'], x['file_offset'], x['encoding']): x for x in rows}
    changes = []
    for proposal in proposals['proposals']:
        row = positions[proposal['file'], proposal['file_offset'], proposal['encoding']]
        assert row['classification'] == 'UNKNOWN' and row['file_sha256'] == inv.sha(data)
        assert row['source_bytes_sha256'] == proposal['source_bytes_sha256']
        at = row['file_offset']
        assert inv.sha(data[at:at + row['bytes']]) == row['source_bytes_sha256']
        assert set(proposal['keyword_evidence_ids']) <= literals[at]
        row.update(classification='INTERNAL', reason=proposal['reason'], additional_evidence={
            'proposal_path': str(proposal_path.relative_to(inv.ROOT)), 'proposal_sha256': inv.sha(proposal_path.read_bytes()),
            'structure_path': str(structure_path.relative_to(inv.ROOT)), 'structure_sha256': inv.sha(structure_path.read_bytes()),
            'keyword_evidence_ids': proposal['keyword_evidence_ids'], 'keyword_roles': proposal['keyword_roles'],
            'independent_check': '프로필44개·일반명령84개·조건명령2개·레지스터21개와 어휘 분석기 참조35개의 원본 포인터·문자·코드를 다시 확인'})
        changes.append(row)
    inv.save('native_inventory_v18.jsonl', rows)
    inv.save('keyword_merge_v18.json', {'input_sha256': inv.sha(source.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v18.jsonl').read_bytes()), 'native_candidate_04_content_affected': False}
    inv.save('summary_v18.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
