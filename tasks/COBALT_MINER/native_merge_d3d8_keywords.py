"""D3D8 상태·값·타입 표를 별도로 읽어 독립 제안의 정확한 위치만 반영합니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv


def main():
    source = inv.OUT / 'native_inventory_v15.jsonl'
    folder = inv.OUT / 'media_keyword_review_02'
    proposal_path, structure_path = folder / 'classification_proposals.json', folder / 'structures.json'
    proposal = inv.read(proposal_path)
    structures = inv.read(structure_path)
    deps = proposal['dependencies']
    assert inv.sha(source.read_bytes()) == deps['inventory_sha256']
    evidence_path = inv.ROOT / deps['rea_evidence']
    assert inv.sha(evidence_path.read_bytes()) == deps['rea_evidence_sha256']
    data = (inv.BASE / deps['source_file']).read_bytes()
    assert inv.sha(data) == deps['source_sha256']
    pe = pefile.PE(data=data)
    records = {r['parameters']['procedure']: r for r in inv.read(evidence_path)['records'] if r['operation'] == 'procedure_pseudo_code'}
    required = {'0x10011db1': ['__stricmp', 'ppuVar3 + 5'],
                '0x10011870': ['__stricmp', 'piVar11 + 2', 'local_8 | piVar11[1]'],
                '0x10011d53': ['__stricmp', 'ppuVar3 + 2']}
    for address, tokens in required.items():
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

    assert len(structures['descriptors']) == 134
    for descriptor in structures['descriptors']:
        at = descriptor['record_offset']
        assert inv.sha(data[at:at + 20]) == descriptor['raw_sha256']
        assert list(struct.unpack_from('<5I', data, at)) == descriptor['dwords']
        check_name(descriptor['name'], descriptor['id'])
    terminal = structures['descriptor_terminator']['file_offset']
    assert data[terminal:terminal + 20] == bytes(20)
    for table in structures['name_value_tables']:
        assert inv.sha(data[table['start']:table['end']]) == table['raw_sha256']
        assert data[table['end'] - 8:table['end']] == bytes(8)
        for entry in table['entries']:
            check_name(entry, table['id'])
            assert struct.unpack_from('<I', data, entry['pointer_field'] + 4)[0] == entry['value']
    rows = [json.loads(x) for x in source.read_text(encoding='utf-8').split('\n') if x]
    positions = {(r['file'], r['file_offset'], r['encoding']): r for r in rows}
    changes = []
    for candidate in proposal['proposals']:
        row = positions[candidate['file'], candidate['file_offset'], candidate['encoding']]
        assert row['classification'] == 'UNKNOWN' and row['file_sha256'] == inv.sha(data)
        assert row['source_bytes_sha256'] == candidate['source_bytes_sha256']
        at = row['file_offset']
        assert inv.sha(data[at:at + row['bytes']]) == row['source_bytes_sha256']
        assert set(candidate['keyword_evidence_ids']) <= literals[at]
        row.update(classification='INTERNAL', reason='D3D8 FX 구문 해석의 상태·값·타입 이름. 실제 Ghidra 함수에서 이름 비교 후 정수 값으로 변환하는 표의 식별자로 소비됨', additional_evidence={
            'proposal_path': str(proposal_path.relative_to(inv.ROOT)), 'proposal_sha256': inv.sha(proposal_path.read_bytes()),
            'structure_path': str(structure_path.relative_to(inv.ROOT)), 'structure_sha256': inv.sha(structure_path.read_bytes()),
            'keyword_evidence_ids': candidate['keyword_evidence_ids'], 'keyword_roles': candidate['keyword_roles'],
            'independent_check': '134개 상태와 값·타입 표의 포인터/이름/수치/종료값을 다시 읽어 검증. 자연어 진단은 포함하지 않음'})
        changes.append(row)
    inv.save('native_inventory_v16.jsonl', rows)
    inv.save('keyword_merge_v16.json', {'input_sha256': inv.sha(source.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v16.jsonl').read_bytes()), 'native_candidate_04_content_affected': False}
    inv.save('summary_v16.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
