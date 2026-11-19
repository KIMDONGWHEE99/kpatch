"""이미 확보한 실제 어셈블러 함수에서 선언 의미 이름의 추가 위치만 연결합니다."""
import hashlib
import json
import struct
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
OUT = BASE / 'media_keyword_review_04'
INVENTORY = BASE / 'native_inventory_v15.jsonl'
EVIDENCE = BASE / 'media_keyword_review_03/rea_d3d9_shader_names.json'
PREVIOUS = BASE / 'media_keyword_review_03/classification_proposals.json'
FILE = 'Modules/mmf2d3d9.dll'
NAMES = set('volume position blendweight blendindices psize tangent binormal tessfactor positiont color depth'.split())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    data = (ROOT/'source_original/COBALT_MINER/steam_24347666'/FILE).read_bytes()
    pe = pefile.PE(data=data)
    inventory = INVENTORY.read_bytes()
    assert sha(inventory) == '121d5686d724478b458b8eaae0214b4a2b7e5a80456a728712667b8141631663'
    bundle = json.loads(EVIDENCE.read_text(encoding='utf-8'))
    record = next(r for r in bundle['records'] if r.get('operation') == 'procedure_pseudo_code' and r.get('parameters', {}).get('procedure') == '0x1005fa5a')
    assert record['provider']['id'] == 'ghidra' and record['subject']['digest']['sha256'] == sha(data)
    pseudo = record['normalized_result']
    assert 'FUN_1005f9a1' in pseudo and 'bVar10 = *pbVar4 == *pbVar9;' in pseudo
    references = {}
    for block in pe.DIRECTORY_ENTRY_BASERELOC:
        for relocation in block.entries:
            if relocation.type != 3 or not 0x5f9a1 <= relocation.rva < 0x6027f:
                continue
            field = pe.get_offset_from_rva(relocation.rva)
            pointer = struct.unpack_from('<I', data, field)[0]
            section = pe.get_section_by_rva(pointer-pe.OPTIONAL_HEADER.ImageBase)
            if section is None or section.IMAGE_SCN_MEM_EXECUTE:
                continue
            start = pe.get_offset_from_rva(pointer-pe.OPTIONAL_HEADER.ImageBase)
            try:
                end = data.index(b'\0', start, start+90)
                source = data[start:end].decode('ascii')
            except (ValueError, UnicodeDecodeError):
                continue
            if source in NAMES:
                assert '"'+source+'"' in pseudo and data[field-1] in (0xbf, 0x68)
                references.setdefault(start, []).append({'file_offset': field, 'va': hex(relocation.rva+pe.OPTIONAL_HEADER.ImageBase), 'bytes': data[field-1:field+4].hex()})
    prior = json.loads(PREVIOUS.read_text(encoding='utf-8'))['proposals']
    prior_keys = {(r['file'], r['file_offset']) for r in prior}
    proposals, proofs = [], []
    for row in [json.loads(line) for line in inventory.decode('utf-8').splitlines()]:
        if row['file'] != FILE or row['classification'] != 'UNKNOWN' or row['source'] not in NAMES:
            continue
        start = row['file_offset']
        assert start in references and (FILE, start) not in prior_keys
        assert row['file_sha256'] == sha(data)
        assert data[start:start+row['bytes']].decode('ascii') == row['source']
        assert sha(data[start:start+row['bytes']]) == row['source_bytes_sha256']
        position = pseudo.index('"'+row['source']+'"')
        proof_id = f'ASSEMBLER_SEMANTIC:{start:x}'
        proofs.append({'id': proof_id, 'source': row['source'], 'file_offset': start, 'source_bytes_sha256': row['source_bytes_sha256'],
                       'references': references[start], 'rea_evidence_id': record['evidence_id'],
                       'pseudocode_excerpt': pseudo[max(0,position-100):position+900]})
        reason = '실제 D3D9 어셈블러가 입력 선언의 의미 이름 또는 텍스처 차원 수식어와 바이트 단위로 비교해 선언 값으로 바꾸는 문법 식별자. 같은 함수의 자연어 오류 메시지는 분류 대상에서 제외함.'
        proposals.append({**row, 'classification': 'INTERNAL', 'proposal_only': True, 'reason': reason,
                          'keyword_evidence_ids': [proof_id], 'keyword_roles': ['SHADER_DECLARATION_SEMANTIC'],
                          'keyword_review_evidence': str((OUT/'structures.json').relative_to(ROOT))})
    assert {r['source'] for r in proposals} == NAMES
    dependencies = {'inventory': str(INVENTORY.relative_to(ROOT)), 'inventory_sha256': sha(inventory), 'source_sha256': sha(data),
                    'rea_evidence': str(EVIDENCE.relative_to(ROOT)), 'rea_evidence_sha256': sha(EVIDENCE.read_bytes()),
                    'previous_proposals_sha256': sha(PREVIOUS.read_bytes()), 'script_sha256': sha(Path(__file__).read_bytes())}
    for name, value in [('structures.json', {'dependencies': dependencies, 'proofs': proofs}), ('classification_proposals.json', {'dependencies': dependencies, 'proposals': proposals})]:
        (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {**dependencies, 'status': 'PROPOSAL_READY', 'proposed_internal': len(proposals), 'new_rea_calls': 0,
               'proposal_sha256': sha((OUT/'classification_proposals.json').read_bytes()), 'shared_inventory_modified': False}
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
