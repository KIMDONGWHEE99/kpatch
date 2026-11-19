"""Fusion 296 DAT의 원본 보존식 해석·선택 수정 도구.

지원 범위는 이 게임에서 확인한 wwww/PAMU, 청크 0/1/2/3,
프레임 청크, 객체 속성 및 글꼴 묶음이다. 바꾸지 않은 압축 자료는
재압축하지 않는다. 구조별 의미 해석은 별도의 Nebula 추출과 대조한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def u32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def integrity_checksum(data: bytes) -> int:
    """실행기의 0x2242 검증값: LE32마다 1비트 회전 후 덧셈한다."""
    value = 0
    aligned_size = len(data) // 4 * 4
    for (word,) in struct.iter_unpack("<I", memoryview(data)[:aligned_size]):
        value = (((value << 1) | (value >> 31)) + word) & 0xFFFFFFFF
    for byte in data[aligned_size:]:
        value = (((value << 1) | (value >> 31)) + byte) & 0xFFFFFFFF
    return value ^ 0x0D


def utf16z(data: bytes, offset: int = 0) -> tuple[str, int]:
    end = offset
    while end + 2 <= len(data):
        if data[end:end + 2] == b"\0\0":
            return data[offset:end].decode("utf-16le"), end + 2
        end += 2
    raise ValueError(f"종료 없는 UTF-16 문자열: {offset}")


def inflate(data: bytes) -> bytes:
    mode = 15 if len(data) >= 2 and data[0] == 0x78 and data[1] in (1, 0x5E, 0x9C, 0xDA) else -15
    obj = zlib.decompressobj(mode)
    result = obj.decompress(data) + obj.flush()
    if not obj.eof or obj.unused_data or obj.unconsumed_tail:
        raise ValueError("압축 블록의 끝 또는 잔여 데이터 불일치")
    return result


def encode_block(data: bytes) -> bytes:
    compressed = zlib.compress(data, 9)
    return struct.pack("<II", len(data), len(compressed)) + compressed


def decode_block(data: bytes) -> bytes:
    size, compressed_size = struct.unpack_from("<II", data)
    if len(data) != 8 + compressed_size:
        raise ValueError("압축 길이 불일치")
    result = inflate(data[8:])
    if len(result) != size:
        raise ValueError("압축 해제 길이 불일치")
    return result


class Cipher:
    """Nebula의 Fusion 청크 키와 대칭 변환을 재현한다."""
    def __init__(self, parts: list[str]):
        key = bytes(v for s in parts for v in s.encode("utf-16le") if v)
        length = len(key)
        checksum = sum(key) & 255
        key = bytearray(key[:128].ljust(256, b"\0"))
        if length < 255:
            key[length + 1] = (checksum * 2) & 255
        table = list(range(256))
        second = position = 0
        for first in range(256):
            if key[position] == 0:
                position = 0
            second = (second + key[position] + table[first]) & 255
            position = (position + 1) & 255
            table[second], table[first] = table[first], table[second]
        self.table = table

    def transform(self, value: bytes) -> bytes:
        table = self.table.copy()
        first = second = 0
        out = bytearray(value)
        for index in range(len(out)):
            first = (first + 1) & 255
            second = (second + table[first]) & 255
            table[first], table[second] = table[second], table[first]
            out[index] ^= table[(table[first] + table[second]) & 255]
        return bytes(out)


@dataclass
class Chunk:
    chunk_id: int
    flag: int
    raw: bytes
    decoded: bytes
    location: str
    offset: int
    cipher: Cipher | None = None
    children: list[Chunk] = field(default_factory=list)
    replacement: bytes | None = None

    def payload(self) -> bytes:
        if self.children:
            current = b"".join(c.serialize() for c in self.children)
        else:
            current = self.decoded if self.replacement is None else self.replacement
        if current == self.decoded:
            return self.raw
        if self.flag == 0:
            return current
        if self.flag == 1:
            return encode_block(current)
        if self.cipher is None:
            raise ValueError("암호 키 없음")
        if self.flag == 2:
            return self.cipher.transform(current)
        compressed = zlib.compress(current, 9)
        encrypted = bytearray(self.cipher.transform(struct.pack("<I", len(compressed)) + compressed))
        if self.chunk_id & 1:
            encrypted[0] ^= ((self.chunk_id & 255) ^ (self.chunk_id >> 8)) & 255
        return struct.pack("<I", len(current)) + encrypted

    def serialize(self) -> bytes:
        payload = self.payload()
        return struct.pack("<HHI", self.chunk_id, self.flag, len(payload)) + payload

    def all_chunks(self):
        yield self
        for child in self.children:
            yield from child.all_chunks()


def parse_chunks(data: bytes, prefix: str, cipher: Cipher | None = None) -> list[Chunk]:
    result = []
    position = 0
    names = {0x2224: "", 0x223B: "", 0x222E: ""}
    while position < len(data):
        if position + 8 > len(data):
            raise ValueError(f"청크 헤더 손상: {prefix}+{position}")
        ident, flag, size = struct.unpack_from("<HHI", data, position)
        if flag not in (0, 1, 2, 3) or position + 8 + size > len(data):
            raise ValueError(f"청크 크기·플래그 오류: {prefix}+{position}")
        raw = data[position + 8:position + 8 + size]
        if size == 0:
            decoded = b""
        elif flag == 0:
            decoded = raw
        elif flag == 1:
            decoded = decode_block(raw)
        elif cipher is None:
            raise ValueError(f"암호 키 생성 전 암호 청크: {ident:04x}")
        elif flag == 2:
            decoded = cipher.transform(raw)
        else:
            encrypted = bytearray(raw[4:])
            if ident & 1:
                encrypted[0] ^= ((ident & 255) ^ (ident >> 8)) & 255
            transformed = cipher.transform(encrypted)
            decoded = decode_block(raw[:4] + transformed)
        location = f"{prefix}/{len(result):03d}:{ident:04x}"
        chunk = Chunk(ident, flag, raw, decoded, location, position, cipher)
        if ident in names:
            names[ident] = utf16z(decoded)[0]
        if ident == 0x222E:
            cipher = Cipher([names[0x2224], names[0x223B], names[0x222E]])
        if ident == 0x3333:
            chunk.children = parse_chunks(decoded, location, cipher)
        result.append(chunk)
        position += 8 + size
    return result


@dataclass
class Block:
    index: int
    offset: int
    raw: bytes
    decoded: bytes
    handle: int | None = None
    replacement: bytes | None = None

    def serialize(self) -> bytes:
        if self.replacement is None or self.replacement == self.decoded:
            return self.raw
        return encode_block(self.replacement)


class DatFile:
    def __init__(self, data: bytes):
        self.original = data
        if data[:4] != b"wwww" or u32(data, 28) != 0 or data[32:36] != b"PAMU":
            raise ValueError("지원하지 않는 DAT 헤더·내장 PackFile")
        if u32(data, 44) != 296:
            raise ValueError("검증 범위 밖 Fusion 빌드")
        self.header = data[:48]
        self.chunks = parse_chunks(data[48:], "top")
        self.by_location = {c.location: c for top in self.chunks for c in top.all_chunks()}
        self.objects = self._blocks(self.one(0x2256).decoded)
        self.fonts = self._blocks(self.one(0x6667).decoded, fonts=True)
        self._check_offset_tables()

    @staticmethod
    def load(path: str | Path) -> DatFile:
        return DatFile(Path(path).read_bytes())

    def one(self, ident: int) -> Chunk:
        candidates = [c for c in self.chunks if c.chunk_id == ident]
        if len(candidates) != 1:
            raise ValueError(f"단일 청크 예상 불일치: {ident:04x}")
        return candidates[0]

    @staticmethod
    def _blocks(data: bytes, fonts: bool = False) -> list[Block]:
        position = 4 if fonts else 0
        result = []
        expected_count = u32(data) if fonts else None
        while position < len(data):
            start = position
            handle = u32(data, position) if fonts else None
            position += 4 if fonts else 0
            end = position + 8 + u32(data, position + 4)
            if end > len(data):
                raise ValueError("개별 압축 블록 경계 오류")
            raw = data[position:end]
            result.append(Block(len(result), start, raw, decode_block(raw), handle))
            position = end
        if fonts and expected_count != len(result):
            raise ValueError("글꼴 수 불일치")
        return result

    def _check_offset_tables(self):
        offsets = self.one(0x2257).decoded
        if len(offsets) != len(self.objects) * 4:
            raise ValueError("객체 위치표 수 불일치")
        for block in self.objects:
            if u32(offsets, block.index * 4) != block.offset:
                raise ValueError("객체 위치표 값 불일치")
        self.font_offsets = self.one(0x5556).decoded
        self.font_offset_bias = {}
        for block in self.fonts:
            if not block.handle or block.handle * 4 > len(self.font_offsets):
                raise ValueError("글꼴 핸들 위치표 경계 오류")
            self.font_offset_bias[block.handle] = u32(self.font_offsets, (block.handle - 1) * 4) - block.offset
        if set(self.font_offset_bias.values()) != {260}:
            raise ValueError("검증한 글꼴 위치표 상대 기준과 다름")

    def serialize(self) -> bytes:
        if any(b.replacement is not None for b in self.objects):
            bank = bytearray()
            offsets = bytearray()
            for block in self.objects:
                offsets += struct.pack("<I", len(bank))
                bank += block.serialize()
            self.one(0x2256).replacement = bytes(bank)
            self.one(0x2257).replacement = bytes(offsets)
        if any(b.replacement is not None for b in self.fonts):
            bank = bytearray(struct.pack("<I", len(self.fonts)))
            offsets = bytearray(self.font_offsets)
            for block in self.fonts:
                struct.pack_into("<I", offsets, (block.handle - 1) * 4, len(bank) + self.font_offset_bias[block.handle])
                bank += struct.pack("<I", block.handle) + block.serialize()
            self.one(0x6667).replacement = bytes(bank)
            self.one(0x5556).replacement = bytes(offsets)
        encoded = [c.serialize() for c in self.chunks]
        start = self.chunks.index(self.one(0x222F))
        end = self.chunks.index(self.one(0x2242))
        if start >= end or len(self.one(0x2242).decoded) != 4:
            raise ValueError("파일 검증값 범위 또는 크기 불일치")
        # 실제 저장 바이트를 검사하므로 재압축·위치표 갱신을 마친 뒤 계산한다.
        self.one(0x2242).replacement = struct.pack("<I", integrity_checksum(b"".join(encoded[start:end])))
        encoded[end] = self.one(0x2242).serialize()
        return self.header + b"".join(encoded)

    def integrity_summary(self):
        """입력 파일의 검증값을 재조립과 별개로 확인한다."""
        start = len(self.header) + self.one(0x222F).offset
        end = len(self.header) + self.one(0x2242).offset
        expected = integrity_checksum(self.original[start:end])
        stored = u32(self.one(0x2242).decoded)
        return {"status": "PASS" if expected == stored else "FAIL", "start": start, "end": end,
                "expected": expected, "stored": stored}

    def get_target(self, target: str) -> tuple[object, bytes]:
        if target.startswith("object:"):
            obj = self.objects[int(target.split(":")[1])]
        elif target.startswith("font:"):
            obj = next(b for b in self.fonts if b.handle == int(target.split(":")[1]))
        else:
            obj = self.by_location[target]
            if obj.children:
                raise ValueError("부모 청크 직접 수정은 지원하지 않음")
        return obj, obj.decoded if obj.replacement is None else obj.replacement

    def patch(self, target: str, offset: int, expected: bytes, replacement: bytes):
        """개별 슬롯 길이를 보존하고 원문까지 일치할 때만 바꾼다."""
        obj, data = self.get_target(target)
        if len(expected) != len(replacement):
            raise ValueError("가변 길이 수정은 구조별 구현 없이 허용하지 않음")
        if offset < 0 or data[offset:offset + len(expected)] != expected:
            raise ValueError(f"기대 원본 불일치: {target}@{offset}")
        obj.replacement = data[:offset] + replacement + data[offset + len(expected):]

    def patch_utf16(self, target: str, offset: int, source: str, translated: str, slot_bytes: int | None = None):
        original = source.encode("utf-16le") + b"\0\0"
        encoded = translated.encode("utf-16le") + b"\0\0"
        capacity = slot_bytes or len(original)
        if capacity % 2 or len(encoded) > capacity or len(original) > capacity:
            raise ValueError("UTF-16 슬롯 용량 초과")
        self.patch(target, offset, original.ljust(capacity, b"\0"), encoded.ljust(capacity, b"\0"))

    def font_summary(self):
        return [{"handle": b.handle, "name": utf16z(b.decoded, 40)[0],
                 "height": struct.unpack_from("<i", b.decoded, 12)[0],
                 "charset": b.decoded[35], "sha256": sha(b.decoded)} for b in self.fonts]

    def inventory(self):
        return {"source_sha256": sha(self.original), "source_bytes": len(self.original),
                "integrity": self.integrity_summary(),
                "top_chunks": len(self.chunks), "frames": sum(c.chunk_id == 0x3333 for c in self.chunks),
                "object_blocks": len(self.objects), "fonts": self.font_summary(),
                "font_offset_bias": sorted(set(self.font_offset_bias.values())),
                "chunks": [{"location": c.location, "id": f"0x{c.chunk_id:04x}", "flag": c.flag,
                            "raw_bytes": len(c.raw), "decoded_bytes": len(c.decoded),
                            "raw_sha256": sha(c.raw), "decoded_sha256": sha(c.decoded)}
                           for top in self.chunks for c in top.all_chunks()]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    target = args.output.resolve()
    allowed = [root / area / "THE_HORDE_OF_GORAK" for area in ("working_private", "build_candidate", "extracted_private")]
    if not any(target.is_relative_to(base) for base in allowed):
        raise ValueError("게임 파생 자료 출력은 해당 게임의 비공개 영역만 허용")
    if target == args.source.resolve():
        raise ValueError("입력 덮어쓰기 금지")
    dat = DatFile.load(args.source)
    report = dat.inventory()
    report["unmodified_roundtrip"] = "PASS" if dat.serialize() == dat.original else "FAIL"
    if report["unmodified_roundtrip"] != "PASS":
        raise ValueError("무변경 왕복 실패")
    changes = json.loads(args.plan.read_text(encoding="utf-8")) if args.plan else []
    for change in changes:
        dat.patch_utf16(**change)
    output = dat.serialize()
    check = DatFile(output)
    if check.serialize() != output:
        raise ValueError("재추출 왕복 실패")
    for change in changes:
        _, data = check.get_target(change["target"])
        if utf16z(data, change["offset"])[0] != change["translated"]:
            raise ValueError("위치별 기대 번역 불일치")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != output:
        raise ValueError("기존 결과와 다른 내용 덮어쓰기 금지: 새 출력 경로를 사용")
    if not args.output.exists():
        args.output.write_bytes(output)
    report.update({"output_sha256": sha(output), "output_bytes": len(output), "applied_changes": changes,
                   "reread_roundtrip": "PASS", "location_comparison": "PASS"})
    args.output.with_suffix(args.output.suffix + ".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("top_chunks", "frames", "object_blocks", "unmodified_roundtrip", "reread_roundtrip", "output_sha256")}))


if __name__ == "__main__":
    main()
