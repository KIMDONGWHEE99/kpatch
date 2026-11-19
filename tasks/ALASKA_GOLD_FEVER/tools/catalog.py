"""Addressables v2 이진 목록을 위치 참조로 읽고 변경 묶음의 검사값만 갱신합니다."""
from __future__ import annotations

import hashlib
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

NULL = 0xFFFFFFFF


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def catalog_hash(data: bytes) -> str:
    """Unity 빌드 도구의 SpookyHash V2를 192바이트 이상 목록에 적용합니다.

    Bob Jenkins의 공개 알고리즘(퍼블릭 도메인)을 순환 인덱스로 구현했습니다.
    참조: https://burtleburtle.net/bob/c/SpookyV2.h 및 SpookyV2.cpp
    """
    if len(data) < 192:
        raise ValueError("목록 해시 함수는 192바이트 이상의 파일 전용입니다.")
    mask = (1 << 64) - 1
    state = [0, 0, 0xDEADBEEFDEADBEEF] * 4

    def rotate(value, amount):
        return ((value << amount) | (value >> (64 - amount))) & mask

    rotations = (11, 32, 43, 31, 17, 28, 39, 57, 55, 54, 22, 46)
    blocks = len(data) // 96
    for block in range(blocks):
        words = struct.unpack_from("<12Q", data, block * 96)
        for i, amount in enumerate(rotations):
            previous, following = (i + 11) % 12, (i + 1) % 12
            state[i] = (state[i] + words[i]) & mask
            state[(i + 2) % 12] ^= state[(i + 10) % 12]
            state[previous] ^= state[i]
            state[i] = rotate(state[i], amount)
            state[previous] = (state[previous] + state[following]) & mask
    remainder = data[blocks * 96:]
    last = bytearray(remainder + b"\0" * (96 - len(remainder)))
    last[95] = len(remainder)
    state = [(a + b) & mask for a, b in zip(state, struct.unpack("<12Q", last))]
    for _ in range(3):
        for i, amount in enumerate((44, 15, 34, 21, 38, 33, 10, 13, 38, 53, 42, 54)):
            previous, following = (i + 11) % 12, (i + 1) % 12
            state[previous] = (state[previous] + state[following]) & mask
            state[(i + 2) % 12] ^= state[previous]
            state[following] = rotate(state[following], amount)
    return struct.pack("<2Q", *state[:2]).hex()


def bundle_crc(data: bytes) -> int:
    """UnityFS의 비압축 데이터 전체 CRC를 계산합니다. 원본 목록 값과 먼저 대조합니다."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools/python_deps"))
    from UnityPy.files.BundleFile import BundleFile
    from UnityPy.streams import EndianBinaryReader

    class PayloadBundle(BundleFile):
        def read_files(self, reader, nodes):
            self.payload = reader.bytes

    bundle = PayloadBundle(EndianBinaryReader(data), None, name="crc-probe")
    return zlib.crc32(bundle.payload) & NULL


class Catalog:
    def __init__(self, data: bytes):
        self.data = data
        self.header = self.values(0, 8)
        if self.header[1] != 2:
            raise ValueError(f"지원하지 않는 목록 버전: {self.header[1]}")
        self.keys: list[dict[str, Any]] = []
        self.locations: dict[int, dict[str, Any]] = {}
        for key, location_set in self.array(self.header[2], 2):
            locs = [v[0] for v in self.array(location_set, 1)]
            self.keys.append({"key": self.object(key), "locations": locs})
            for offset in locs:
                self.location(offset)

    def values(self, offset: int, count: int) -> tuple[int, ...]:
        if offset < 0 or offset + count * 4 > len(self.data):
            raise ValueError(f"목록 범위 밖의 정수 참조: {offset}, {count}")
        return struct.unpack_from("<" + "I" * count, self.data, offset)

    def array(self, offset: int, width: int) -> list[tuple[int, ...]]:
        if offset == NULL:
            return []
        size = self.values(offset - 4, 1)[0]
        if size % (width * 4) or offset + size > len(self.data):
            raise ValueError(f"잘못된 배열 크기: {offset}, {size}")
        return [self.values(p, width) for p in range(offset, offset + size, width * 4)]

    def string(self, offset: int, separator: str = "") -> str | None:
        if offset == NULL:
            return None
        if offset & 0x40000000:
            if not separator:
                raise ValueError("분리된 문자열에 결합 문자가 없습니다.")
            parts, seen = [], set()
            while offset != NULL:
                ptr = offset & 0x3FFFFFFF
                if ptr in seen:
                    raise ValueError("분리된 문자열 참조에 순환이 있습니다.")
                seen.add(ptr)
                part, offset = self.values(ptr, 2)
                parts.append(self.string(part))
            return separator.join(reversed(parts))
        encoding = "utf-16-le" if offset & 0x80000000 else "ascii"
        offset &= 0x3FFFFFFF
        length = self.values(offset - 4, 1)[0]
        if offset + length > len(self.data):
            raise ValueError("문자열이 목록 파일 범위를 벗어납니다.")
        return self.data[offset:offset + length].decode(encoding)

    def typename(self, offset: int) -> tuple[str | None, str | None]:
        assembly, name = self.values(offset, 2)
        return self.string(assembly, "."), self.string(name, ".")

    def object(self, offset: int) -> Any:
        if offset == NULL:
            return None
        type_id, object_id = self.values(offset, 2)
        _, cls = self.typename(type_id)
        if cls == "System.String":
            ptr = self.values(object_id, 1)[0]
            separator = chr(struct.unpack_from("<H", self.data, object_id + 4)[0])
            return self.string(ptr, "" if separator == "\0" else separator)
        if cls == "System.Int32":
            return struct.unpack_from("<i", self.data, object_id)[0]
        return {"type": cls, "offset": object_id}

    def location(self, offset: int) -> None:
        if offset in self.locations:
            return
        key, internal, provider, deps, dep_hash, extra, typename = self.values(offset, 7)
        row = {
            "offset": offset, "key": self.string(key, "/"),
            "internal": self.string(internal, "/"), "provider": self.string(provider, "."),
            "dependencies": [v[0] for v in self.array(deps, 1)],
            "dependency_hash": dep_hash, "type": self.typename(typename), "extra": self.object(extra),
        }
        self.locations[offset] = row
        if isinstance(row["extra"], dict) and row["extra"]["type"].endswith("AssetBundleRequestOptions"):
            position = row["extra"]["offset"]
            hash_id, name_id, crc, size, common = self.values(position, 5)
            timeout, redirect, retry, flags = struct.unpack_from("<hBBI", self.data, common)
            if hash_id + 16 > len(self.data):
                raise ValueError("묶음 해시 참조가 범위를 벗어납니다.")
            row["options"] = {
                "offset": position, "hash_offset": hash_id,
                "hash_bytes": self.data[hash_id:hash_id + 16].hex(),
                "bundle_name": self.string(name_id, "_"), "crc": crc, "size": size,
                "timeout": timeout, "redirect": redirect, "retry": retry, "flags": flags,
            }
        for dependency in row["dependencies"]:
            self.location(dependency)

    def bundles(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for row in self.locations.values():
            if "options" in row:
                name = row["internal"].replace("\\", "/").rsplit("/", 1)[-1]
                result.setdefault(name, []).append(row)
        return result


def update_catalog(source: bytes, bundle_changes: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    """각 변경은 name, source_size, candidate_bytes, candidate_crc를 제공합니다."""
    original = Catalog(source)
    output = bytearray(source)
    bundles = original.bundles()
    expected: dict[int, dict[str, Any]] = {}
    allowed_offsets: set[int] = set()
    seen_names: set[str] = set()
    changes = []
    for change in bundle_changes:
        name = change["name"]
        if name in seen_names:
            raise ValueError(f"중복된 수정 묶음: {name}")
        seen_names.add(name)
        if name not in bundles:
            raise ValueError(f"목록에서 수정 묶음을 찾을 수 없습니다: {name}")
        candidate = change["candidate_bytes"]
        new_crc = int(change["candidate_crc"])
        if len(candidate) > NULL or not 0 <= new_crc <= NULL:
            raise ValueError("묶음 크기 또는 CRC가 저장 범위를 벗어납니다.")
        if new_crc != bundle_crc(candidate):
            raise ValueError(f"후보 묶음 CRC가 실제 압축 해제 데이터와 다릅니다: {name}")
        # 해시는 캐시의 새 버전을 식별합니다. 파일 무결성은 별도의 SHA-256으로 검증합니다.
        hash_bytes = bytes.fromhex(digest(candidate)[:32])
        hash_offset = len(output)
        output.extend(hash_bytes)
        for row in bundles[name]:
            old = row["options"]
            if old["size"] != change["source_size"]:
                raise ValueError(f"원본 묶음 크기가 목록과 다릅니다: {name}")
            position = old["offset"]
            new = dict(old, hash_offset=hash_offset, hash_bytes=hash_bytes.hex(), crc=new_crc, size=len(candidate))
            if position in expected and expected[position] != new:
                raise ValueError("서로 다른 수정 묶음이 같은 옵션을 공유합니다.")
            expected[position] = new
            struct.pack_into("<I", output, position, hash_offset)
            struct.pack_into("<II", output, position + 8, new_crc, len(candidate))
            allowed_offsets.update(range(position, position + 4))
            allowed_offsets.update(range(position + 8, position + 16))
            changes.append({"file": name, "location_offset": row["offset"], "before": old, "after": new, "candidate_sha256": digest(candidate)})
    result = bytes(output)
    reopened = Catalog(result)
    if original.header != reopened.header or original.keys != reopened.keys or set(original.locations) != set(reopened.locations):
        raise ValueError("목록의 헤더·키·위치 목록이 예상 밖으로 바뀌었습니다.")
    for offset, old_row in original.locations.items():
        new_row = reopened.locations[offset]
        if {k: v for k, v in old_row.items() if k != "options"} != {k: v for k, v in new_row.items() if k != "options"}:
            raise ValueError(f"목록의 경로·유형·의존 관계가 바뀌었습니다: {offset}")
        old_options = old_row.get("options")
        expected_options = expected.get(old_options["offset"], old_options) if old_options else None
        if new_row.get("options") != expected_options:
            raise ValueError(f"목록의 묶음 옵션이 기대값과 다릅니다: {offset}")
    unexpected = [i for i, (a, b) in enumerate(zip(source, result)) if a != b and i not in allowed_offsets]
    if unexpected or len(result) != len(source) + 16 * len(bundle_changes):
        raise ValueError(f"허용 범위 밖에서 목록이 변경되었습니다: {unexpected[:10]}")
    return result, {
        "status": "PASS", "scope": "카탈로그 정적 재열기와 변경 경계",
        "source_sha256": digest(source), "candidate_sha256": digest(result),
        "source_size": len(source), "candidate_size": len(result),
        "key_count": len(original.keys), "location_count": len(original.locations),
        "bundle_count": len(bundles), "changed_bundles": changes,
        "unexpected_byte_changes": unexpected,
        "runtime_loading": "NOT_RUN",
    }
