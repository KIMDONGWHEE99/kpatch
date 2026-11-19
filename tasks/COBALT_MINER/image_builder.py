"""이미 생성한 광고판 11장과 기능명 표지를 Cobalt의 zlib/BGR 이미지 묶음에 반영합니다."""
from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tasks/THE_HORDE_OF_GORAK'))
from dat_container import DatFile, sha, u32

SOURCE = ROOT / 'source_original/COBALT_MINER/steam_24347666/COBALT MINER.dat'
SOURCE_SHA256 = '01733d5907692df4cfa462dc709cb3c96180dba056f6249a1abf334fd2bb70e7'
EXTRACTED = ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01'
MANIFEST = ROOT / 'working_private/COBALT_MINER/media_ko_01/manifest.json'
BILLBOARD_HANDLES = {1374, 1486, 1491, 1492, 1498, 1499, 1500, 1501, 1503, 1504, 1513}
ALLOWED_HANDLES = BILLBOARD_HANDLES | {1123}
REGION = (234, 99, 375, 166)
REGIONS = {handle: REGION for handle in BILLBOARD_HANDLES} | {1123: (47, 197, 187, 236)}


@dataclass
class ImageRecord:
    handle: int
    offset: int
    raw: bytes
    body: bytes
    replacement: bytes | None = None

    @property
    def dimensions(self):
        return struct.unpack_from('<HH', self.body, 12)

    def rgba(self):
        width, height = self.dimensions
        if self.body[16] != 4 or self.body[17] not in (0, 16):
            raise ValueError('검증 범위 밖 이미지 형식')
        stride = (width + width % 2) * 3
        color_size = stride * height
        image = Image.frombytes('RGB', (width, height), self.body[32:32 + color_size], 'raw', 'BGR', stride)
        rgba = bytearray(image.convert('RGBA').tobytes())
        if self.body[17] == 16:
            alpha_stride = (width + 3) // 4 * 4
            if len(self.body) != 32 + color_size + alpha_stride * height:
                raise ValueError('알파 채널 크기 불일치')
            alpha = self.body[32 + color_size:]
            for y in range(height):
                rgba[(y * width) * 4 + 3:(y + 1) * width * 4:4] = alpha[y * alpha_stride:y * alpha_stride + width]
        else:
            if len(self.body) != 32 + color_size:
                raise ValueError('이미지 색상 자료 크기 불일치')
            # 저장 헤더의 투명색은 RGB 순서이고 픽셀 본문은 BGR 순서입니다.
            key = self.body[28:31]
            for p in range(0, len(rgba), 4):
                if rgba[p:p + 3] == key:
                    rgba[p + 3] = 0
        return bytes(rgba)

    def serialize(self):
        if self.replacement is None or self.replacement == self.body:
            return self.raw
        compressed = zlib.compress(self.replacement, 9)
        return self.raw[:4] + struct.pack('<II', len(self.replacement), len(compressed)) + compressed


class ImageBank:
    def __init__(self, dat):
        self.dat = dat
        self.bank = dat.one(0x6666)
        self.table = dat.one(0x5555)
        self.records = []
        data = self.bank.decoded
        position = 4
        for _ in range(u32(data)):
            stored_handle, decoded_size, compressed_size = struct.unpack_from('<III', data, position)
            end = position + 12 + compressed_size
            if end > len(data):
                raise ValueError('이미지 압축 레코드 경계 오류')
            raw = data[position:end]
            decoder = zlib.decompressobj()
            body = decoder.decompress(raw[12:]) + decoder.flush()
            if not decoder.eof or decoder.unused_data or len(body) != decoded_size or len(body) < 32 or u32(body, 8) != len(body) - 32:
                raise ValueError('이미지 압축 해제 경계 오류')
            handle = stored_handle - 1
            if handle * 4 + 4 > len(self.table.decoded) or u32(self.table.decoded, handle * 4) != position + 260:
                raise ValueError('이미지 위치표와 원본 레코드 불일치')
            record = ImageRecord(handle, position, raw, body)
            width, height = record.dimensions
            color_size = (width + width % 2) * 3 * height
            alpha_size = ((width + 3) // 4 * 4 * height) if body[17] == 16 else 0
            if body[16] != 4 or body[17] not in (0, 16) or len(body) != 32 + color_size + alpha_size:
                raise ValueError('원본 이미지 저장 형식 또는 자료 크기 불일치')
            self.records.append(record)
            position = end
        if position != len(data):
            raise ValueError('이미지 묶음 후미 자료')
        self.by_handle = {record.handle: record for record in self.records}
        if len(self.by_handle) != len(self.records):
            raise ValueError('중복 이미지 핸들')

    def replace_png(self, handle, path, region=REGION):
        if handle not in ALLOWED_HANDLES or tuple(region) != REGIONS[handle]:
            raise ValueError('허용된 간판 영역 외 수정 금지')
        record = self.by_handle[handle]
        if record.body[17] != 0:
            raise ValueError('교체 대상은 원본의 색상키 투명 방식만 지원')
        with Image.open(path) as image:
            if image.size != record.dimensions or image.mode != 'RGBA':
                raise ValueError('PNG 크기 또는 모드 불일치')
            rgba = image.tobytes()
        before = record.rgba()
        if rgba[3::4] != before[3::4]:
            raise ValueError('원본 알파 변경 금지')
        width, height = record.dimensions
        stride = (width + width % 2) * 3
        body = bytearray(record.body)
        changed = 0
        for pixel in range(width * height):
            pos = pixel * 4
            if rgba[pos:pos + 4] == before[pos:pos + 4]:
                continue
            x, y = pixel % width, pixel // width
            if not (region[0] <= x < region[2] and region[1] <= y < region[3]):
                raise ValueError(f'허용 영역 밖 픽셀 변경: {handle}/{x},{y}')
            if rgba[pos + 3] != 255:
                raise ValueError('투명 픽셀의 숨은 색상 변경 금지')
            r, g, b = rgba[pos:pos + 3]
            out = 32 + y * stride + x * 3
            body[out:out + 3] = bytes((b, g, r))
            changed += 1
        if not changed:
            raise ValueError('교체 이미지가 원본과 같음')
        record.replacement = bytes(body)
        return {'handle': handle, 'png_sha256': sha(Path(path).read_bytes()), 'rgba_sha256': sha(rgba),
                'changed_pixels': changed, 'outside_region': 'PASS', 'alpha_unchanged': 'PASS'}

    def apply(self):
        bank = bytearray(struct.pack('<I', len(self.records)))
        table = bytearray(self.table.decoded)
        for record in self.records:
            struct.pack_into('<I', table, record.handle * 4, len(bank) + 260)
            bank.extend(record.serialize())
        self.bank.replacement = bytes(bank)
        self.table.replacement = bytes(table)


def load_plan(manifest_path=MANIFEST):
    manifest_path = Path(manifest_path)
    plan = json.loads(manifest_path.read_text(encoding='utf-8'))
    handles = {row['handle'] for row in plan['files']}
    if handles not in (BILLBOARD_HANDLES, ALLOWED_HANDLES) or len(plan['files']) != len(handles):
        raise ValueError('교체 대상 목록 불일치')
    for row in plan['files']:
        if tuple(row['allowed_region']) != REGIONS[row['handle']]:
            raise ValueError('허용 영역 불일치')
        path = manifest_path.parent / f"{row['handle']:05d}.png"
        original = EXTRACTED / f"images/{row['handle']:05d}.png"
        if sha(path.read_bytes()) != row['output_sha256'] or sha(original.read_bytes()) != row['source_sha256']:
            raise ValueError('원본 또는 교체 PNG 지문 변경')
        row['path'] = path
    return plan


def apply_images(dat, manifest_path=MANIFEST):
    """텍스트·글꼴 후보에도 적용할 수 있지만 원본 이미지 묶음의 동일성을 먼저 검사합니다."""
    source = DatFile.load(SOURCE)
    if sha(source.original) != SOURCE_SHA256:
        raise ValueError('지원 원본 DAT 지문 불일치')
    if any(source.one(key).decoded != dat.one(key).decoded for key in (0x6666, 0x5555)):
        raise ValueError('미디어 입력은 원본 이미지 묶음이어야 함')
    bank = ImageBank(dat)
    changes = [bank.replace_png(row['handle'], row['path'], row['allowed_region']) for row in load_plan(manifest_path)['files']]
    bank.apply()
    return changes


def verify_replacement(source, output, manifest_path=MANIFEST):
    before, after = ImageBank(source), ImageBank(output)
    if [r.handle for r in before.records] != [r.handle for r in after.records]:
        raise ValueError('이미지 순서/개수 변경')
    plan = load_plan(manifest_path)
    expected_handles = {row['handle'] for row in plan['files']}
    changed = []
    for a, b in zip(before.records, after.records):
        if a.body[:32] != b.body[:32]:
            raise ValueError('이미지 메타데이터 변경')
        if a.raw != b.raw:
            changed.append(a.handle)
        if a.handle not in expected_handles and a.raw != b.raw:
            raise ValueError('비대상 이미지 원시 바이트 변경')
    if set(changed) != expected_handles:
        raise ValueError('실제 변경 이미지 집합 불일치')
    for row in plan['files']:
        with Image.open(row['path']) as image:
            expected = image.tobytes()
        actual = after.by_handle[row['handle']].rgba()
        if actual != expected:
            raise ValueError('다시 읽은 교체 픽셀 불일치')
        a = before.by_handle[row['handle']].rgba()
        if a[3::4] != actual[3::4]:
            raise ValueError('다시 읽은 알파 불일치')
        w, h = after.by_handle[row['handle']].dimensions
        region = REGIONS[row['handle']]
        for y in range(h):
            for x in range(w):
                if region[0] <= x < region[2] and region[1] <= y < region[3]:
                    continue
                p = (y * w + x) * 4
                if a[p:p + 4] != actual[p:p + 4]:
                    raise ValueError('다시 읽은 영역 밖 픽셀 불일치')
    if source.header != output.header or len(source.chunks) != len(output.chunks):
        raise ValueError('DAT 헤더/청크 개수 변경')
    for a, b in zip(source.chunks, output.chunks):
        if a.location != b.location or a.chunk_id != b.chunk_id or (a.decoded != b.decoded and a.chunk_id not in (0x6666, 0x5555)):
            raise ValueError('미디어 영역 밖 DAT 변경')
    if output.integrity_summary()['status'] != 'PASS':
        raise ValueError('DAT 무결성 검사 실패')
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, default=ROOT / 'build_candidate/COBALT_MINER/media_smoke_01/COBALT MINER.dat')
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    args = parser.parse_args()
    target = args.output.resolve()
    if not any(target.is_relative_to(ROOT / area / 'COBALT_MINER') for area in ('working_private', 'build_candidate')) or target == args.source.resolve():
        raise ValueError('원본과 다른 게임 비공개 후보 경로만 허용')
    source = DatFile.load(args.source)
    dat = DatFile.load(args.source)
    if dat.serialize() != dat.original:
        raise ValueError('변경 없는 DAT 왕복 실패')
    changes = apply_images(dat, args.manifest)
    data = dat.serialize()
    result = DatFile(data)
    changed = verify_replacement(source, result, args.manifest)
    if result.serialize() != data:
        raise ValueError('수정 DAT 왕복 실패')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != data:
        raise ValueError('다른 기존 후보 덮어쓰기 금지')
    target.write_bytes(data)
    report = {'source_sha256': sha(source.original), 'candidate_sha256': sha(data),
              'builder_sha256': sha(Path(__file__).read_bytes()), 'manifest_sha256': sha(args.manifest.read_bytes()),
              'changes': changes, 'changed_handles': changed, 'non_target_records_unchanged': 'PASS',
              'target_metadata_unchanged': 'PASS', 'outside_region_and_alpha_unchanged': 'PASS',
              'pixel_reread': 'PASS', 'independent_nebula_reextract': 'NOT_RUN', 'runtime_qa': 'NOT_RUN'}
    target.with_suffix('.dat.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'changes'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
