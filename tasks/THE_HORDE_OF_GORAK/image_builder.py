"""확인된 4개 이미지의 PNG 픽셀만 바꾸는 Fusion 296 이미지 묶음 작성기."""
from __future__ import annotations

import argparse
import json
import struct
from dataclasses import dataclass
from pathlib import Path

import lz4.block
from PIL import Image

from dat_container import DatFile, sha, u32

ALLOWED_HANDLES = {215, 980, 1512, 1820}


@dataclass
class ImageRecord:
    handle: int
    offset: int
    raw: bytes
    pixels: bytes
    replacement: bytes | None = None

    @property
    def dimensions(self):
        return struct.unpack_from("<HH", self.raw, 20)

    def rgba(self):
        if self.raw[24] != 8 or not self.raw[25] & 128:
            raise ValueError("지원 범위 밖 이미지 색상 형식")
        # 4개 대상은 알파 0/255뿐이므로 미리 곱한 알파를 정확히 되돌릴 수 있다.
        if any(alpha not in (0, 255) for alpha in self.pixels[3::4]):
            raise ValueError("이번 원본의 수정 대상 범위를 벗어난 반투명 이미지")
        image = Image.frombytes("RGBA", self.dimensions, self.pixels, "raw", "BGRA")
        value = bytearray(image.tobytes())
        for start in range(0, len(value), 4):
            if not value[start + 3]:
                value[start:start + 3] = b"\0\0\0"
        return bytes(value)

    def serialize(self):
        if self.replacement is None or self.replacement == self.pixels:
            return self.raw
        compressed = lz4.block.compress(self.replacement, mode="high_compression", compression=12, store_size=False)
        header = bytearray(self.raw[:44])
        struct.pack_into("<I", header, 16, len(compressed) + 4)
        struct.pack_into("<I", header, 40, len(self.replacement))
        return bytes(header) + compressed


class ImageBank:
    def __init__(self, dat):
        self.dat = dat
        self.bank = dat.one(0x6666)
        self.table = dat.one(0x5555)
        self.records = []
        data = self.bank.decoded
        position = 4
        for index in range(u32(data)):
            size = u32(data, position + 16)
            if size < 4 or position + 40 + size > len(data):
                raise ValueError("이미지 LZ4 레코드 경계 오류")
            raw = data[position:position + 40 + size]
            handle = u32(raw) - 1
            pixels = lz4.block.decompress(raw[44:], uncompressed_size=u32(raw, 40))
            width, height = struct.unpack_from("<HH", raw, 20)
            if len(pixels) != width * height * 4 or raw[24] != 8 or raw[25] not in (0x88, 0x98):
                raise ValueError("검증하지 않은 이미지 저장 방식")
            if handle * 4 + 4 > len(self.table.decoded) or u32(self.table.decoded, handle * 4) != position + 260:
                raise ValueError("이미지 위치표의 원본 관계 불일치")
            self.records.append(ImageRecord(handle, position, raw, pixels))
            position += len(raw)
        if position != len(data):
            raise ValueError("이미지 묶음 후미 잔여 자료")
        self.by_handle = {record.handle: record for record in self.records}
        if len(self.by_handle) != len(self.records):
            raise ValueError("이미지 핸들 중복")

    def replace_png(self, handle, path):
        if handle not in ALLOWED_HANDLES:
            raise ValueError("승인한 네 이미지 외 수정 금지")
        record = self.by_handle[handle]
        with Image.open(path) as image:
            if image.size != record.dimensions or image.mode != "RGBA":
                raise ValueError("PNG는 원본 크기의 RGBA여야 함")
            rgba = image.tobytes()
        if any(alpha not in (0, 255) for alpha in rgba[3::4]):
            raise ValueError("현재 네 대상의 원래 알파 0/255 범위만 지원")
        if any(rgba[i + 3] == 0 and any(rgba[i:i + 3]) for i in range(0, len(rgba), 4)):
            raise ValueError("완전 투명 픽셀의 RGB는 0이어야 PNG 정확 왕복 가능")
        before = record.rgba()
        # 안 바뀐 픽셀은 숨은 색상값까지 원래 그대로 보존한다.
        pixels = bytearray(record.pixels)
        changed = 0
        for start in range(0, len(rgba), 4):
            if rgba[start:start + 4] != before[start:start + 4]:
                r, g, b, a = rgba[start:start + 4]
                pixels[start:start + 4] = bytes((b, g, r, a))
                changed += 1
        record.replacement = bytes(pixels)
        return {"handle": handle, "png_sha256": sha(Path(path).read_bytes()), "rgba_sha256": sha(rgba), "changed_pixels": changed}

    def apply(self):
        bank = bytearray(struct.pack("<I", len(self.records)))
        table = bytearray(self.table.decoded)
        for record in self.records:
            struct.pack_into("<I", table, record.handle * 4, len(bank) + 260)
            bank += record.serialize()
        self.bank.replacement = bytes(bank)
        self.table.replacement = bytes(table)


def verify_replacement(source, output, expected):
    before, after = ImageBank(source), ImageBank(output)
    assert len(before.records) == len(after.records)
    changed = []
    for a, b in zip(before.records, after.records):
        assert a.handle == b.handle
        # 길이 필드 외 40바이트 메타데이터와 압축 해제 크기를 전부 보존한다.
        assert a.raw[:16] + a.raw[20:44] == b.raw[:16] + b.raw[20:44]
        if a.raw != b.raw:
            changed.append(a.handle)
        if a.handle not in expected:
            assert a.raw == b.raw
    for handle, rgba in expected.items():
        assert after.by_handle[handle].rgba() == rgba
    assert set(changed) <= set(expected)
    assert source.header == output.header
    assert output.integrity_summary()["status"] == "PASS"
    assert {a.chunk_id for a, b in zip(source.chunks, output.chunks) if a.decoded != b.decoded} <= {0x6666, 0x5555}
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--plan", required=True, type=Path, help="handle 문자열을 RGBA PNG 경로에 연결하는 JSON")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    target = args.output.resolve()
    if not any(target.is_relative_to(root / area / "THE_HORDE_OF_GORAK") for area in ("working_private", "build_candidate")):
        raise ValueError("게임 후보는 해당 게임 비공개 영역에만 작성")
    if target == args.source.resolve():
        raise ValueError("원본 덮어쓰기 금지")
    source = DatFile.load(args.source)
    dat = DatFile.load(args.source)
    bank = ImageBank(dat)
    expected, changes = {}, []
    for key, path in json.loads(args.plan.read_text(encoding="utf-8")).items():
        handle = int(key)
        changes.append(bank.replace_png(handle, Path(path)))
        with Image.open(path) as image:
            expected[handle] = image.tobytes()
    bank.apply()
    data = dat.serialize()
    result = DatFile(data)
    changed = verify_replacement(source, result, expected)
    assert result.serialize() == data
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != data:
        raise ValueError("서로 다른 기존 후보 덮어쓰기 금지")
    target.write_bytes(data)
    report = {"source_sha256": sha(source.original), "candidate_sha256": sha(data), "changes": changes,
              "changed_handles": changed, "metadata_and_other_images": "PASS", "rgba_reread": "PASS", "runtime_qa": "NOT_RUN"}
    target.with_suffix(target.suffix + ".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
