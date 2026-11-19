"""SDK의 FOURCC 열거형과 DDPIXELFORMAT 레코드 전체가 일치하는 오탐만 제안합니다."""
import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'working_private/COBALT_MINER/investigation_20261101/native'
SOURCE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
OUT = NATIVE / 'media_numeric_review_04'
PREVIOUS = NATIVE / 'media_numeric_review_03/remaining_unknown.json'
INCLUDE = Path('C:/Program Files (x86)/Windows Kits/10/Include/10.0.22621.0')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    rows = json.loads(PREVIOUS.read_text(encoding='utf-8'))['rows']
    enum_path = INCLUDE / 'shared/d3d9types.h'
    structure_path = INCLUDE / 'um/ddraw.h'
    enum_source = enum_path.read_text(encoding='utf-8-sig')
    structure_source = structure_path.read_text(encoding='utf-8-sig')
    if not all(field in structure_source for field in ('dwSize;', 'dwFlags;', 'dwFourCC;', 'dwRGBBitCount;', 'dwRBitMask;', 'dwGBitMask;', 'dwBBitMask;', 'dwRGBAlphaBitMask;')):
        raise ValueError('DDPIXELFORMAT SDK 정의 누락')
    flag = re.search(r'#define\s+DDPF_FOURCC\s+(0x[0-9A-Fa-f]+)', structure_source)
    if not flag or int(flag[1], 16) != 4:
        raise ValueError('SDK FOURCC 플래그 정의 변경')
    formats = {}
    for name in ('YUY2', 'DXT1', 'DXT2', 'DXT3', 'DXT4', 'DXT5'):
        line = next(line for line in enum_source.splitlines() if f'D3DFMT_{name}' in line and 'MAKEFOURCC' in line)
        characters = re.findall(r"'(.)'", line)
        if len(characters) != 4:
            raise ValueError('SDK FOURCC 상수 읽기 실패')
        formats[name] = int.from_bytes(''.join(characters).encode('ascii'), 'little')
    structures = []
    for file in ('Modules/mmf2d3d8.dll', 'Modules/mmf2d3d9.dll'):
        data = (SOURCE/file).read_bytes()
        for name, value in formats.items():
            # D3DFORMAT 한 필드 뒤에 SDK의 32바이트 DDPIXELFORMAT이 이어집니다.
            expected = struct.pack('<9I', value, 32, 4, value, 0, 0, 0, 0, 0)
            cursor = 0
            while True:
                start = data.find(expected, cursor)
                if start < 0:
                    break
                cursor = start+len(expected)
                structures.append({'id': f'DDPIXELFORMAT:{file}:{start:x}', 'type': 'DDPIXELFORMAT_FOURCC_RECORD',
                                   'file': file, 'file_sha256': sha(data), 'start': start, 'end': cursor,
                                   'raw_sha256': sha(expected), 'format_symbol': 'D3DFMT_'+name,
                                   'record_dwords': list(struct.unpack('<9I', expected)),
                                   'reason': 'SDK의 D3DFORMAT FOURCC 값과 32바이트 DDPIXELFORMAT(size32, FOURCC플래그4, 동일 코드, 나머지0)의 전체36바이트 레코드가 일치. 텍스트처럼 읽힌 FOURCC+크기 바이트는 파일 형식 정수 필드.',
                                   'source_enum': str(enum_path), 'source_enum_sha256': sha(enum_path.read_bytes()),
                                   'source_structure': str(structure_path), 'source_structure_sha256': sha(structure_path.read_bytes())})
    proposals, remaining = [], []
    for row in rows:
        evidence = next((s for s in structures if s['file']==row['file'] and s['start']<=row['file_offset'] and row['file_offset']+row['bytes']<=s['end']), None)
        if evidence:
            data = (SOURCE/row['file']).read_bytes()
            if sha(data) != row['file_sha256'] or sha(data[row['file_offset']:row['file_offset']+row['bytes']]) != row['source_bytes_sha256']:
                raise ValueError('원본 위치 지문 불일치')
            proposals.append({**row, 'classification': 'INTERNAL', 'reason': evidence['reason'], 'proposal_only': True,
                              'numeric_evidence_ids': [evidence['id']], 'numeric_review_evidence': str((OUT/'structures.json').relative_to(ROOT))})
        else:
            remaining.append(row)
    dependencies = {'previous_unknowns': str(PREVIOUS.relative_to(ROOT)), 'previous_unknowns_sha256': sha(PREVIOUS.read_bytes()),
                    'script_sha256': sha(Path(__file__).read_bytes()), 'scope': '6개 SDK 형식의 전체36바이트 레코드 일치만. 공유 분류표 미수정.'}
    for name, value in [('structures.json', {'dependencies': dependencies, 'structures': structures}),
                        ('classification_proposals.json', {'dependencies': dependencies, 'proposals': proposals}),
                        ('remaining_unknown.json', {'dependencies': dependencies, 'rows': remaining})]:
        (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {**dependencies, 'status': 'PROPOSAL_READY', 'targets': len(rows), 'proposed_internal': len(proposals),
               'remaining_unknown': len(remaining), 'proposal_sha256': sha((OUT/'classification_proposals.json').read_bytes()),
               'structures_sha256': sha((OUT/'structures.json').read_bytes()), 'shared_inventory_modified': False}
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
