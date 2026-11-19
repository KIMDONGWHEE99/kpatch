"""분류 제안 생성기와 별도로 현재 원본의 이름 표를 다시 읽어 위치를 확인합니다."""
import hashlib
import json
import struct
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
OUT = BASE / 'media_keyword_review_01'


def main():
    proposal_file = OUT / 'classification_proposals.json'
    proposals = json.loads(proposal_file.read_text(encoding='utf-8'))['proposals']
    original = ROOT / 'source_original/COBALT_MINER/steam_24347666/Modules/mmf2d3d9.dll'
    data = original.read_bytes()
    pe = pefile.PE(data=data)
    names, visited = set(), set()
    state_count = 0
    # 제안 생성기가 저장한 구조·개수는 사용하지 않고 널 이름을 만날 때까지 읽습니다.
    while True:
        cursor = 0xe01b8 + state_count*28
        values = struct.unpack_from('<7I', data, cursor)
        if not values[0]:
            break
        state_count += 1
        names.add(pe.get_offset_from_rva(values[0]-pe.OPTIONAL_HEADER.ImageBase))
        if not values[6]:
            continue
        enum = pe.get_offset_from_rva(values[6]-pe.OPTIONAL_HEADER.ImageBase)
        if enum in visited:
            continue
        visited.add(enum)
        index = 0
        while True:
            pointer = struct.unpack_from('<I', data, enum+index*8)[0]
            if not pointer:
                break
            names.add(pe.get_offset_from_rva(pointer-pe.OPTIONAL_HEADER.ImageBase))
            index += 1
    for row in proposals:
        start = row['file_offset']
        end = start+row['bytes']
        assert start in names
        assert data[start:end].decode('ascii') == row['source'] and data[end] == 0
        assert hashlib.sha256(data[start:end]).hexdigest() == row['source_bytes_sha256']
        assert hashlib.sha256(data).hexdigest() == row['file_sha256']
    assert len(proposals) == len({row['file_offset'] for row in proposals})
    current_file = BASE / 'native_inventory_v14.jsonl'
    current_rows = [json.loads(line) for line in current_file.read_text(encoding='utf-8').splitlines()]
    current = {(row['file'], row['file_offset'], row['encoding']): row for row in current_rows}
    classes = {current[(row['file'], row['file_offset'], row['encoding'])]['classification'] for row in proposals}
    report = {'status': 'PASS', 'proposal_locations': len(proposals), 'actual_state_count': state_count,
              'actual_enum_tables': len(visited), 'all_source_text_and_hash_match': True,
              'v14_target_classes': sorted(classes), 'v14_input_sha256': hashlib.sha256(current_file.read_bytes()).hexdigest(),
              'proposals_sha256': hashlib.sha256(proposal_file.read_bytes()).hexdigest(),
              'verification_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': '제안 결과에서 위치만 가져와 별도로 읽은 원시 표·문자열·종결 NUL과 비교. 공유 분류표 미수정.'}
    (OUT/'independent_location_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
