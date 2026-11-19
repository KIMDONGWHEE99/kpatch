"""선언 의미 이름의 실제 포인터 피연산자와 Ghidra 비교 코드를 대조합니다."""
import collections
import json
import struct
from pathlib import Path
import pefile
import native_inventory as inv


def main():
    folder = inv.OUT / 'media_keyword_review_04'
    proposal_path, structure_path = folder / 'classification_proposals.json', folder / 'structures.json'
    proposals, structures = inv.read(proposal_path), inv.read(structure_path)
    deps = proposals['dependencies']
    assert inv.sha((inv.ROOT / deps['inventory']).read_bytes()) == deps['inventory_sha256']
    evidence = inv.ROOT / deps['rea_evidence']
    assert inv.sha(evidence.read_bytes()) == deps['rea_evidence_sha256']
    records = {r['evidence_id']: r for r in inv.read(evidence)['records']}
    raw = (inv.BASE / 'Modules/mmf2d3d9.dll').read_bytes()
    assert inv.sha(raw) == deps['source_sha256']
    pe = pefile.PE(data=raw)
    proofs = {p['file_offset']: p for p in structures['proofs']}
    references = []
    for proof in proofs.values():
        name, at = proof['source'].encode(), proof['file_offset']
        assert raw[at:at + len(name) + 1] == name + b'\0'
        assert inv.sha(name) == proof['source_bytes_sha256']
        record = records[proof['rea_evidence_id']]
        assert record['provider']['id'] == 'ghidra'
        assert record['subject']['digest']['sha256'] == inv.sha(raw)
        assert proof['pseudocode_excerpt'] in record['normalized_result']
        for ref in proof['references']:
            # 제안의 주소는 명령 시작이 아닌 4바이트 주소 피연산자의 시작입니다.
            operand = ref['file_offset']
            instruction = bytes.fromhex(ref['bytes'])
            assert pe.get_offset_from_rva(int(ref['va'], 16) - pe.OPTIONAL_HEADER.ImageBase) == operand
            assert len(instruction) == 5 and 0xb8 <= instruction[0] <= 0xbf
            assert raw[operand - 1:operand + 4] == instruction
            assert struct.unpack_from('<I', raw, operand)[0] == pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(at)
            references.append(dict(source=proof['source'], operand_offset=operand, instruction_offset=operand - 1, bytes=instruction.hex()))
    source = inv.OUT / 'native_inventory_v19.jsonl'
    rows = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line]
    positions = {(r['file'], r['file_offset'], r['encoding']): r for r in rows}
    changes = []
    reused = []
    for proposal in proposals['proposals']:
        row = positions[proposal['file'], proposal['file_offset'], proposal['encoding']]
        proof = proofs[row['file_offset']]
        assert row['source_bytes_sha256'] == proof['source_bytes_sha256']
        if row['classification'] == 'INTERNAL':
            reused.append(row['source'])
            continue
        assert row['classification'] == 'UNKNOWN'
        row.update(classification='INTERNAL', reason=proposal['reason'], additional_evidence={
            'proposal_path': str(proposal_path.relative_to(inv.ROOT)), 'proposal_sha256': inv.sha(proposal_path.read_bytes()),
            'structure_path': str(structure_path.relative_to(inv.ROOT)), 'structure_sha256': inv.sha(structure_path.read_bytes()),
            'rea_evidence_id': proof['rea_evidence_id'],
            'independent_check': '셰이더 어휘 비교 코드와 실제 MOV 주소 피연산자·원문 바이트 재검증. 제안의 주소는 피연산자 시작으로 해석하며 명령 시작은 1바이트 앞임'})
        changes.append(row)
    if not changes:
        inv.save('semantic_existing_location_verification.json', dict(status='PASS', input_sha256=inv.sha(source.read_bytes()), tool_sha256=inv.sha(Path(__file__).read_bytes()), already_classified=reused, verified_references=references, new_classifications=0))
        print(dict(status='PASS', already_classified=len(reused), new_classifications=0))
        return
    assert not (inv.OUT / 'native_inventory_v20.jsonl').exists()
    inv.save('native_inventory_v20.jsonl', rows)
    inv.save('keyword_merge_v20.json', dict(input_sha256=inv.sha(source.read_bytes()), tool_sha256=inv.sha(Path(__file__).read_bytes()), changes=changes, verified_references=references))
    summary = dict(records=len(rows), classifications=dict(collections.Counter(r['classification'] for r in rows)), additional_internal=len(changes), full_native_classification='NOT_RUN', output_sha256=inv.sha((inv.OUT / 'native_inventory_v20.jsonl').read_bytes()))
    inv.save('summary_v20.json', summary)
    print(summary)


if __name__ == '__main__':
    main()
