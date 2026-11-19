"""빌더 결과를 사용하지 않고 Nebula 재추출과 예상 PNG를 전수 대조합니다."""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01'
BILLBOARD_HANDLES = {1374, 1486, 1491, 1492, 1498, 1499, 1500, 1501, 1503, 1504, 1513}
REGION = (234, 99, 375, 166)
REGIONS = {handle: REGION for handle in BILLBOARD_HANDLES} | {1123: (47, 197, 187, 236)}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def raw_containers(path):
    data = Path(path).read_bytes()
    pos, chunks = 48, {}
    while pos < len(data):
        ident, flags, size = struct.unpack_from('<HHI', data, pos)
        raw = data[pos + 8:pos + 8 + size]
        chunks.setdefault(ident, []).append((flags, raw))
        pos += 8 + size
    if pos != len(data):
        raise ValueError('독립 원시 DAT 순회 경계 오류')
    bank = chunks[0x6666][0][1]
    table_raw = chunks[0x5555][0][1]
    table = zlib.decompress(table_raw[8:])
    if len(table) != struct.unpack_from('<I', table_raw)[0] or len(table_raw) != 8 + struct.unpack_from('<I', table_raw, 4)[0]:
        raise ValueError('독립 위치표 경계 오류')
    records, pos = {}, 4
    for _ in range(struct.unpack_from('<I', bank)[0]):
        stored, unpacked, size = struct.unpack_from('<III', bank, pos)
        raw = bank[pos:pos + 12 + size]
        body = zlib.decompress(raw[12:])
        if len(body) != unpacked or struct.unpack_from('<I', table, (stored - 1) * 4)[0] != pos + 260:
            raise ValueError('독립 이미지 위치표/자료 길이 불일치')
        records[stored - 1] = (raw, body)
        pos += len(raw)
    if pos != len(bank):
        raise ValueError('독립 이미지 레코드 후미 경계 오류')
    return data[:48], chunks, records, list(struct.unpack('<' + 'I' * (len(table) // 4), table))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, default=ROOT / 'build_candidate/COBALT_MINER/media_smoke_01/COBALT MINER.dat')
    parser.add_argument('--extracted', type=Path, default=ROOT / 'extracted_private/COBALT_MINER/media_smoke_01/nebula_01')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'working_private/COBALT_MINER/media_ko_01/manifest.json')
    args = parser.parse_args()
    original = read_json(ORIGINAL / 'package.json')
    candidate = read_json(args.extracted / 'package.json')
    source_info = read_json(ORIGINAL / 'input.json')
    info = read_json(args.extracted / 'input.json')
    if info['sha256'] != digest(args.candidate):
        raise ValueError('재추출 입력 후보 지문 불일치')
    if read_json(args.extracted / 'errors.json'):
        raise ValueError('독립 추출 오류가 있음')
    plan = read_json(args.manifest)
    expected = {row['handle']: row for row in plan['files']}
    handles = set(expected)
    if handles not in (BILLBOARD_HANDLES, BILLBOARD_HANDLES | {1123}) or len(plan['files']) != len(handles):
        raise ValueError('기대 이미지 집합 불일치')
    before_header, before_chunks, before_records, before_offsets = raw_containers(source_info['input'])
    after_header, after_chunks, after_records, after_offsets = raw_containers(args.candidate)
    if before_header != after_header or before_chunks.keys() != after_chunks.keys() or before_records.keys() != after_records.keys():
        raise ValueError('원시 DAT 구조 또는 이미지 목록 변경')
    for key in before_chunks:
        if key not in (0x6666, 0x5555) and before_chunks[key] != after_chunks[key]:
            raise ValueError('이미지 청크 외 원시 자료 변경')
    for handle in before_records:
        a, b = before_records[handle], after_records[handle]
        if a[1][:32] != b[1][:32] or (handle not in handles and a != b):
            raise ValueError('이미지 메타데이터 또는 비대상 원시 레코드 변경')
    for value, offsets, chunks in ((original, before_offsets, before_chunks), (candidate, after_offsets, after_chunks)):
        if value['ImageOffsets']['Offsets'] != offsets or value['ImageOffsets']['SortedOffsets'] != sorted(n for n in offsets if n):
            raise ValueError('독립 원시 위치표와 Nebula 위치표 불일치')
        for name, ident in (('ImageBank', 0x6666), ('ImageOffsets', 0x5555)):
            if value[name]['ChunkSize'] != len(chunks[ident][0][1]):
                raise ValueError('재추출 압축 묶음 크기와 원시 자료 불일치')
    original_images = original['ImageBank']['Images']
    candidate_images = candidate['ImageBank']['Images']
    if original_images.keys() != candidate_images.keys():
        raise ValueError('재추출 이미지 키 목록 불일치')
    image_rows = []
    for key, metadata in original_images.items():
        handle = int(key)
        new_metadata = candidate_images[key]
        original_path = ORIGINAL / f'images/{handle:05d}.png'
        candidate_path = args.extracted / f'images/{handle:05d}.png'
        with Image.open(original_path) as im:
            size = im.size
            before = im.convert('RGBA').tobytes()
        with Image.open(candidate_path) as im:
            if im.size != size:
                raise ValueError('재추출 이미지 크기 변경')
            after = im.convert('RGBA').tobytes()
        if handle not in handles:
            if metadata != new_metadata or before != after:
                raise ValueError(f'비대상 이미지 변경: {handle}')
        else:
            row = expected[handle]
            region = REGIONS[handle]
            path = args.manifest.parent / f'{handle:05d}.png'
            if row['source_sha256'] != digest(original_path) or row['output_sha256'] != digest(path) or tuple(row['allowed_region']) != region:
                raise ValueError('기대 PNG 입력 지문/영역 불일치')
            with Image.open(path) as im:
                target = im.convert('RGBA').tobytes()
            if after != target or before == after or before[3::4] != after[3::4]:
                raise ValueError(f'교체 픽셀 또는 알파 불일치: {handle}')
            for field in metadata:
                if field != 'ImageData' and metadata[field] != new_metadata[field]:
                    raise ValueError(f'이미지 메타데이터 변경: {handle}/{field}')
            if metadata['ImageData']['byte_length'] != new_metadata['ImageData']['byte_length']:
                raise ValueError('원시 픽셀 자료 길이 변경')
            for y in range(size[1]):
                for x in range(size[0]):
                    if region[0] <= x < region[2] and region[1] <= y < region[3]:
                        continue
                    p = (y * size[0] + x) * 4
                    if before[p:p + 4] != after[p:p + 4]:
                        raise ValueError('허용 영역 밖 재추출 픽셀 변경')
        image_rows.append({'handle': handle, 'source_png_sha256': digest(original_path),
                           'candidate_png_sha256': digest(candidate_path), 'status': 'PASS'})
    for key in original:
        if key not in ('ImageOffsets', 'ImageBank') and original[key] != candidate[key]:
            raise ValueError(f'이미지 외 전체 의미 구조 변경: {key}')
    for key in original['ImageBank']:
        if key not in ('Images', 'ChunkSize') and original['ImageBank'][key] != candidate['ImageBank'][key]:
            raise ValueError(f'이미지 묶음 메타데이터 변경: {key}')
    for key in original['ImageOffsets']:
        if key not in ('Offsets', 'SortedOffsets', 'ChunkSize') and original['ImageOffsets'][key] != candidate['ImageOffsets'][key]:
            raise ValueError(f'이미지 위치표 메타데이터 변경: {key}')
    report = {'status': 'PASS', 'method': '독립 Nebula 전체 재추출 자료와 원본·기대 PNG 대조. 빌더 보고서나 성공 카운터를 입력으로 사용하지 않음',
              'source_dat_sha256': source_info['sha256'], 'candidate_dat_sha256': info['sha256'],
              'manifest_sha256': digest(args.manifest), 'verifier_sha256': digest(__file__),
              'original_package_sha256': digest(ORIGINAL / 'package.json'), 'candidate_package_sha256': digest(args.extracted / 'package.json'),
              'images_compared': len(image_rows), 'changed_handles': sorted(handles),
              'non_target_images': 'PASS', 'all_non_image_semantics': 'PASS', 'target_pixels': 'PASS',
              'metadata_alpha_outside_region': 'PASS', 'runtime_qa': 'NOT_RUN', 'images': image_rows}
    output = args.candidate.parent / 'independent_image_verification.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('images', 'method')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
