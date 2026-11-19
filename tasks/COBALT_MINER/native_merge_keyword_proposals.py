"""FX 문법 표의 포인터·값·이름 바이트를 독립적으로 확인해 제안을 병합합니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv


def main():
    source = inv.OUT / 'native_inventory_v14.jsonl'
    folder = inv.OUT / 'media_keyword_review_01'
    proposal_path, structure_path = folder / 'classification_proposals.json', folder / 'structures.json'
    proposals = json.loads(proposal_path.read_text(encoding='utf-8'))
    structures = json.loads(structure_path.read_text(encoding='utf-8'))
    deps = proposals['dependencies']
    assert inv.sha((inv.ROOT / deps['inventory']).read_bytes()) == deps['inventory_sha256']
    assert inv.sha((inv.ROOT / deps['rea_evidence']).read_bytes()) == deps['rea_evidence_sha256']
    data = (inv.BASE / deps['source_file']).read_bytes()
    assert inv.sha(data) == deps['source_sha256']
    pe = pefile.PE(data=data)
    literals = collections.defaultdict(set)

    def check_name(name, identity):
        start, end = name['start'], name['end']
        assert data[start:end].decode('ascii') == name['source'] and data[end] == 0
        assert inv.sha(data[start:end]) == name['source_bytes_sha256']
        assert struct.unpack_from('<I', data, name['pointer_field'])[0] == pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(start)
        literals[start].add(identity)

    for descriptor in structures['descriptors']:
        at = descriptor['record_offset']
        assert inv.sha(data[at:at + 28]) == descriptor['raw_sha256']
        assert list(struct.unpack_from('<7I', data, at)) == descriptor['dwords']
        check_name(descriptor['name'], descriptor['id'])
        check_name(descriptor['duplicate_name'], descriptor['id'])
        duplicate = descriptor['duplicate_record_offset']
        assert data[at + 4:at + 24] == data[duplicate + 4:duplicate + 24]
    for table in structures['enum_tables']:
        assert inv.sha(data[table['start']:table['end']]) == table['raw_sha256']
        assert data[table['end'] - 8:table['end']] == bytes(8)
        for entry in table['entries']:
            check_name(entry, table['id'])
            assert struct.unpack_from('<I', data, entry['pointer_field'] + 4)[0] == entry['value']
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
            'independent_check': '명령182개·이름과값 표28개 및 복제본의 실제 포인터/이름/수치/원시해시를 재검증'})
        changes.append(row)
    inv.save('native_inventory_v15.jsonl', rows)
    inv.save('keyword_merge_v15.json', {'input_sha256': inv.sha(source.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v15.jsonl').read_bytes()), 'native_candidate_04_content_affected': False}
    inv.save('summary_v15.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
