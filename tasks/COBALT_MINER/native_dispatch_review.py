"""네이티브 표현식 사용 경계와 독립 수치표 제안을 원본 바이트로 대조합니다."""
import ast
import collections
import json
import re
import struct
from pathlib import Path
import pefile
import native_inventory as inv


def main():
    input_path = inv.OUT / 'native_inventory_v8.jsonl'
    rows = [json.loads(x) for x in input_path.read_text(encoding='utf-8').split('\n') if x]
    data = (inv.BASE / 'Modules/Steamworks.mfx').read_bytes()
    pe = pefile.PE(data=data)
    path = inv.OUT / 'rea_steamworks_dispatch.json'
    evidence = json.loads(path.read_text(encoding='utf-8'))['records']
    proofs = {x['parameters']['procedure']: x for x in evidence}
    assert all(x['provider']['id'] == 'ghidra' and x['subject']['digest']['sha256'] == inv.sha(data) for x in evidence)
    registration = proofs['0x10015eea']
    dispatcher = proofs['0x10017e19']
    assert '+ 0x4c) + 0x68) = &LAB_10008614;' in registration['normalized_result']
    assert 'pcVar3 = *(code **)(*(int *)(DAT_1007be1c + 0x4c) + iVar2 * 4);' in dispatcher['normalized_result']
    probe_path = inv.OUT / 'steam_status_probe.json'
    probe = json.loads(probe_path.read_text(encoding='utf-8'))
    assert probe['module_sha256'] == inv.sha(data) and probe['expression_index'] == 26 and probe['expression_title'] == 'SteamLastError$('
    frames_path = inv.OUT.parent / 'classification/raw_frames.json'
    frames = json.loads(frames_path.read_text(encoding='utf-8'))
    summary_path = inv.OUT.parent / 'classification/summary.json'
    source_dat_hash = inv.sha((inv.BASE / 'COBALT MINER.dat').read_bytes())
    assert json.loads(summary_path.read_text(encoding='utf-8'))['source_sha256'] == source_dat_hash
    uses = []

    def walk(value):
        if isinstance(value, dict):
            if value.get('type') == 36:
                uses.append(value)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(frames)
    assert len(frames) == 17 and len(uses) == 16
    assert {(x.get('kind'), x.get('num'), x.get('handle')) for x in uses} == {('Actions', 102, 640)}
    switch = pe.get_offset_from_rva(0x8614)
    assert data[switch:switch + 25].hex() == '8b818402000083c0fc83f83b0f876f010000ff24859c870010'
    switch_targets = struct.unpack_from('<60I', data, pe.get_offset_from_rva(0x879c))
    returned_offsets = set()
    return_operands = set()
    for target in switch_targets:
        at = pe.get_offset_from_rva(target - pe.OPTIONAL_HEADER.ImageBase)
        assert data[at] == 0xb8 and data[at + 5] == 0xc3
        va = struct.unpack_from('<I', data, at + 1)[0]
        returned_offsets.add(pe.get_offset_from_rva(va - pe.OPTIONAL_HEADER.ImageBase))
        return_operands.add(at + 1)
    assert len(returned_offsets) == 60
    relocated_pointers = [(pe.get_offset_from_rva(x.rva), struct.unpack_from('<I', data, pe.get_offset_from_rva(x.rva))[0])
                          for block in pe.DIRECTORY_ENTRY_BASERELOC for x in block.entries if x.type == 3]
    common = {'path': str(path.relative_to(inv.ROOT)), 'sha256': inv.sha(path.read_bytes())}
    changes = []
    reason_rules = {
        'GetRunObjectInfos': 'EDIF의 개수·확장 식별자를 조회하는 사전 키. 사용자 출력값과 구분됨',
        '0x1001929d': 'EDIF 사전 키 또는 확장 종속 파일 목록을 구성하는 json 확장자',
        '0x10004dd3': '결제 응답 JSON에서 success/token/error 속성을 조회하는 키. 조회 결과와 키 자체를 구분함',
        '0x10018541': 'Separator와 비교하여 글자 없는 메뉴 구분선으로 변환하는 제어 토큰',
        '0x1000c900': 'GetTempPathW/GetModuleFileNameW/tmpnam으로 조립하는 임시 파일 경로 서식',
    }
    keys = collections.defaultdict(list)
    for procedure, reason in reason_rules.items():
        record = proofs[procedure]
        for token in re.findall(r'"(?:[^"\\]|\\.)*"', record['normalized_result']):
            value = ast.literal_eval(token)
            if len(value) >= 4:
                keys[value].append({'evidence_id': record['evidence_id'], 'procedure': procedure, 'reason': reason})
    for row in rows:
        if row['classification'] != 'UNKNOWN' or row['file'] != 'Modules/Steamworks.mfx':
            continue
        assert inv.sha(data[row['file_offset']:row['file_offset'] + row['bytes']]) == row['source_bytes_sha256']
        if row['file_offset'] in returned_offsets:
            assert row['source'].startswith('statusError') and row['encoding'] == 'utf-16le'
            string_va = pe.OPTIONAL_HEADER.ImageBase + pe.get_rva_from_offset(row['file_offset'])
            uses_of_literal = [at for at, va in relocated_pointers if string_va <= va < string_va + row['bytes']]
            assert len(uses_of_literal) == 1 and uses_of_literal[0] in return_operands
            row.update(classification='INTERNAL', reason='상태 번호 4~63을 반환 문자열로 바꾸는 SteamLastError$( 표현식 26번. 현재 Cobalt DAT 전체 17프레임은 이 확장의 조건·표현식을 사용하지 않음',
                       additional_evidence={**common, 'registration_evidence_id': registration['evidence_id'],
                                            'dispatcher_evidence_id': dispatcher['evidence_id'],
                                            'switch_va': '0x10008614', 'switch_table_va': '0x1000879c',
                                            'return_instruction_count': 60, 'expression_index': 26,
                                            'probe_path': str(probe_path.relative_to(inv.ROOT)), 'probe_sha256': inv.sha(probe_path.read_bytes()),
                                            'game_usage': {'path': str(frames_path.relative_to(inv.ROOT)), 'sha256': inv.sha(frames_path.read_bytes()),
                                                           'original_dat_sha256': source_dat_hash, 'frames': 17, 'actions_102': 16, 'conditions': 0, 'expressions': 0},
                                            'limit': '이 게임 빌드의 DAT 사용 범위 판정. 다른 게임 또는 DAT 변경 시 재검증 필요'})
            changes.append(row)
        elif row['source'] in keys:
            details = keys[row['source']]
            row.update(classification='INTERNAL', reason=details[0]['reason'], additional_evidence={**common, 'consumers': details})
            changes.append(row)
    # 독립 숫자 검토의 표 전체 지문·행 경계를 다시 대조하고 제안된 위치만 적용합니다.
    media_path = inv.OUT / 'media_numeric_review_01/classification_proposals.json'
    structure_path = media_path.with_name('structures.json')
    media = json.loads(media_path.read_text(encoding='utf-8'))
    assert media['dependencies']['input_sha256'] == inv.sha(input_path.read_bytes())
    structures = {x['id']: x for x in json.loads(structure_path.read_text(encoding='utf-8'))['structures']}
    images = {}
    for entry in structures.values():
        raw = images.setdefault(entry['file'], (inv.BASE / entry['file']).read_bytes())
        assert inv.sha(raw) == entry['file_sha256']
        assert inv.sha(raw[entry['start']:entry['end']]) == entry['raw_sha256']
    positions = {(x['file'], x['file_offset'], x['encoding']): x for x in rows}
    for proposal in media['proposals']:
        row = positions[proposal['file'], proposal['file_offset'], proposal['encoding']]
        assert row['classification'] == 'UNKNOWN' and row['source_bytes_sha256'] == proposal['source_bytes_sha256']
        raw = images[row['file']]
        assert inv.sha(raw[row['file_offset']:row['file_offset'] + row['bytes']]) == row['source_bytes_sha256']
        for structure_id in proposal['numeric_evidence_ids']:
            structure = structures[structure_id]
            assert structure['start'] <= row['file_offset'] and row['file_offset'] + row['bytes'] <= structure['end']
        row.update(classification='INTERNAL', reason=proposal['reason'], additional_evidence={
            'path': str(media_path.relative_to(inv.ROOT)), 'sha256': inv.sha(media_path.read_bytes()),
            'structure_path': str(structure_path.relative_to(inv.ROOT)), 'structure_sha256': inv.sha(structure_path.read_bytes()),
            'structure_ids': proposal['numeric_evidence_ids'], 'review_scope': '구조 전체와 행 원시 바이트를 다시 검증한 독립 숫자 검토'})
        changes.append(row)
    inv.save('native_inventory_v9.jsonl', rows)
    inv.save('dispatch_classification.json', {'input_sha256': inv.sha(input_path.read_bytes()), 'tool_sha256': inv.sha(Path(__file__).read_bytes()), 'changes': changes})
    summary = {'records': len(rows), 'classifications': dict(collections.Counter(x['classification'] for x in rows)),
               'additional_internal': len(changes), 'full_native_classification': 'NOT_RUN',
               'output_sha256': inv.sha((inv.OUT / 'native_inventory_v9.jsonl').read_bytes()), 'native_candidate_03_content_affected': False}
    inv.save('summary_v9.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
