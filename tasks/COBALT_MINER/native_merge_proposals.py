"""분담 조사 제안을 현재 분류표와 원본 지문에 다시 맞추어 병합합니다."""
import argparse
import collections
import json
from pathlib import Path
import native_inventory as inv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-version', type=int, required=True)
    parser.add_argument('--output-version', type=int, required=True)
    parser.add_argument('folders', nargs='+')
    args = parser.parse_args()
    source = inv.OUT / ('native_inventory_v%d.jsonl' % args.input_version)
    rows = [json.loads(x) for x in source.read_text(encoding='utf-8').split('\n') if x]
    positions = {(x['file'], x['file_offset'], x['encoding']): x for x in rows if 'file_offset' in x}
    images, changes, dependencies = {}, [], []
    for folder in args.folders:
        proposals_path = inv.OUT / folder / 'classification_proposals.json'
        structures_path = proposals_path.with_name('structures.json')
        proposal_data = json.loads(proposals_path.read_text(encoding='utf-8'))
        structures = {x['id']: x for x in json.loads(structures_path.read_text(encoding='utf-8'))['structures']}
        source_dependencies = proposal_data['dependencies']
        if 'input_inventory' in source_dependencies:
            input_path = inv.ROOT / source_dependencies['input_inventory']
            assert inv.sha(input_path.read_bytes()) == source_dependencies['input_sha256']
        else:
            previous_path = inv.ROOT / source_dependencies['previous_unknowns']
            assert inv.sha(previous_path.read_bytes()) == source_dependencies['previous_unknowns_sha256']
        for key in ('rea_evidence', 'previous_proposals'):
            if key in source_dependencies:
                assert inv.sha((inv.ROOT / source_dependencies[key]).read_bytes()) == source_dependencies[key + '_sha256']
        dependency = {'proposal_path': str(proposals_path.relative_to(inv.ROOT)), 'proposal_sha256': inv.sha(proposals_path.read_bytes()),
                      'structure_path': str(structures_path.relative_to(inv.ROOT)), 'structure_sha256': inv.sha(structures_path.read_bytes())}
        dependencies.append(dependency)
        for structure in structures.values():
            raw = images.setdefault(structure['file'], (inv.BASE / structure['file']).read_bytes())
            assert inv.sha(raw) == structure['file_sha256']
            assert inv.sha(raw[structure['start']:structure['end']]) == structure['raw_sha256']
        for proposed in proposal_data['proposals']:
            row = positions[proposed['file'], proposed['file_offset'], proposed['encoding']]
            assert row['classification'] == 'UNKNOWN' and proposed['classification'] == 'INTERNAL'
            assert row['file_sha256'] == proposed['file_sha256'] and row['source_bytes_sha256'] == proposed['source_bytes_sha256']
            raw = images[row['file']]
            assert inv.sha(raw[row['file_offset']:row['file_offset'] + row['bytes']]) == row['source_bytes_sha256']
            for key in proposed['numeric_evidence_ids']:
                structure = structures[key]
                assert structure['start'] <= row['file_offset'] and row['file_offset'] + row['bytes'] <= structure['end']
            row.update(classification='INTERNAL', reason=proposed['reason'], additional_evidence={**dependency,
                'structure_ids': proposed['numeric_evidence_ids'], 'review_scope': '독립 조사 제안의 원본 파일·구조 전체·위치별 바이트를 재검증'})
            changes.append(row)
    output = 'native_inventory_v%d.jsonl' % args.output_version
    inv.save(output, rows)
    inv.save('proposal_merge_v%d.json' % args.output_version, {'input_sha256': inv.sha(source.read_bytes()),
             'dependencies': dependencies, 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / output).read_bytes()), 'native_candidate_03_content_affected': False}
    inv.save('summary_v%d.json' % args.output_version, summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
