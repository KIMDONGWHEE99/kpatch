#!/usr/bin/env python3
"""IL2CPP 메타데이터의 특정 enum 표시 이름을 안전하게 바꾼다.

PROFITS2167(Unity 6000.0.36f1, metadata v31)의 업그레이드 분류 화면은
별도 문구가 아니라 UpgradeTag enum의 이름을 그대로 표시한다. 숫자 값과
필드 순서는 유지하고 이름 인덱스만 새 UTF-8 문자열로 연결한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import unicodedata
from pathlib import Path


METADATA_MAGIC = 0xFAB11BAF
STRING_HEAP_PAIR = 2
FIELD_DEFINITIONS_PAIR = 11
TYPE_DEFINITIONS_PAIR = 19
FIELD_DEFINITION_SIZE = 12
TYPE_DEFINITION_SIZE = 88
TYPE_FIELD_START_OFFSET = 32
TYPE_FIELD_COUNT_OFFSET = 68


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def header_pairs(data: bytes) -> tuple[int, list[tuple[int, int]]]:
    sanity, version = struct.unpack_from("<II", data, 0)
    if sanity != METADATA_MAGIC:
        raise ValueError(f"지원하지 않는 메타데이터 서명: 0x{sanity:08X}")
    first_offset = struct.unpack_from("<I", data, 8)[0]
    if first_offset < 16 or (first_offset - 8) % 8:
        raise ValueError("메타데이터 머리말을 해석할 수 없습니다.")
    pairs = [
        struct.unpack_from("<II", data, 8 + index * 8)
        for index in range((first_offset - 8) // 8)
    ]
    if len(pairs) <= TYPE_DEFINITIONS_PAIR:
        raise ValueError("필요한 메타데이터 구역이 없습니다.")
    return version, pairs


def read_heap_string(data: bytes, heap_offset: int, heap_size: int, index: int) -> str:
    if not 0 <= index < heap_size:
        raise ValueError(f"문자열 인덱스가 범위를 벗어났습니다: {index}")
    start = heap_offset + index
    end = data.find(b"\0", start, heap_offset + heap_size)
    if end < 0:
        raise ValueError(f"문자열 끝을 찾지 못했습니다: {index}")
    return data[start:end].decode("utf-8")


def find_type(
    data: bytes,
    pairs: list[tuple[int, int]],
    namespace: str,
    type_name: str,
) -> tuple[int, int]:
    heap_offset, heap_size = pairs[STRING_HEAP_PAIR]
    type_offset, type_size = pairs[TYPE_DEFINITIONS_PAIR]
    if type_size % TYPE_DEFINITION_SIZE:
        raise ValueError("Il2CppTypeDefinition 크기가 v31 형식과 다릅니다.")
    matches: list[tuple[int, int]] = []
    for index in range(type_size // TYPE_DEFINITION_SIZE):
        position = type_offset + index * TYPE_DEFINITION_SIZE
        name_index, namespace_index = struct.unpack_from("<II", data, position)
        if (
            read_heap_string(data, heap_offset, heap_size, name_index) == type_name
            and read_heap_string(data, heap_offset, heap_size, namespace_index) == namespace
        ):
            field_start = struct.unpack_from("<I", data, position + TYPE_FIELD_START_OFFSET)[0]
            field_count = struct.unpack_from("<H", data, position + TYPE_FIELD_COUNT_OFFSET)[0]
            matches.append((field_start, field_count))
    if len(matches) != 1:
        raise RuntimeError(f"{namespace}.{type_name} 검색 결과가 {len(matches)}개입니다.")
    return matches[0]


def command_patch(args: argparse.Namespace) -> None:
    original = args.source.read_bytes()
    version, pairs = header_pairs(original)
    if version != 31:
        raise ValueError(f"지원하는 메타데이터 버전은 31이며 현재 버전은 {version}입니다.")
    mapping: dict[str, str] = json.loads(args.mapping.read_text(encoding="utf-8-sig"))
    for source, translation in mapping.items():
        if not source or not translation:
            raise ValueError("빈 enum 이름은 사용할 수 없습니다.")
        if unicodedata.normalize("NFC", translation) != translation:
            raise ValueError(f"NFC 정규화 오류: {source!r}")

    field_start, field_count = find_type(original, pairs, args.namespace, args.type_name)
    heap_offset, heap_size = pairs[STRING_HEAP_PAIR]
    field_offset, field_size = pairs[FIELD_DEFINITIONS_PAIR]
    if field_size % FIELD_DEFINITION_SIZE:
        raise ValueError("Il2CppFieldDefinition 크기가 v31 형식과 다릅니다.")
    if field_start + field_count > field_size // FIELD_DEFINITION_SIZE:
        raise ValueError("enum 필드 범위가 필드 정의 구역을 벗어납니다.")

    fields: dict[str, int] = {}
    for local_index in range(field_count):
        position = field_offset + (field_start + local_index) * FIELD_DEFINITION_SIZE
        name_index = struct.unpack_from("<I", original, position)[0]
        name = read_heap_string(original, heap_offset, heap_size, name_index)
        fields[name] = local_index
    missing = sorted(set(mapping) - set(fields))
    if missing:
        raise RuntimeError(f"enum에서 찾지 못한 필드: {missing}")

    new_heap = bytearray(original[heap_offset : heap_offset + heap_size])
    new_indices: dict[str, int] = {}
    for source, translation in mapping.items():
        new_indices[source] = len(new_heap)
        new_heap.extend(translation.encode("utf-8"))
        new_heap.append(0)
    old_heap_end = heap_offset + heap_size
    delta = len(new_heap) - heap_size
    output = bytearray(original[:heap_offset]) + new_heap + bytearray(original[old_heap_end:])

    shifted_pairs: list[tuple[int, int]] = []
    for index, (section_offset, section_size) in enumerate(pairs):
        if index == STRING_HEAP_PAIR:
            shifted_pairs.append((section_offset, len(new_heap)))
        elif section_offset >= old_heap_end:
            shifted_pairs.append((section_offset + delta, section_size))
        else:
            shifted_pairs.append((section_offset, section_size))
        struct.pack_into("<II", output, 8 + index * 8, *shifted_pairs[-1])

    shifted_field_offset = shifted_pairs[FIELD_DEFINITIONS_PAIR][0]
    for source, local_index in fields.items():
        if source not in new_indices:
            continue
        position = shifted_field_offset + (field_start + local_index) * FIELD_DEFINITION_SIZE
        struct.pack_into("<I", output, position, new_indices[source])

    verify_version, verify_pairs = header_pairs(output)
    verify_field_start, verify_field_count = find_type(
        output, verify_pairs, args.namespace, args.type_name
    )
    if (verify_version, verify_field_start, verify_field_count) != (version, field_start, field_count):
        raise RuntimeError("enum 형식 검증에 실패했습니다.")
    verify_heap_offset, verify_heap_size = verify_pairs[STRING_HEAP_PAIR]
    verify_field_offset = verify_pairs[FIELD_DEFINITIONS_PAIR][0]
    actual: dict[str, str] = {}
    for source, local_index in fields.items():
        if source not in mapping:
            continue
        position = verify_field_offset + (field_start + local_index) * FIELD_DEFINITION_SIZE
        name_index = struct.unpack_from("<I", output, position)[0]
        actual[source] = read_heap_string(output, verify_heap_offset, verify_heap_size, name_index)
    errors = {source: value for source, value in actual.items() if value != mapping[source]}
    if errors:
        raise RuntimeError(f"enum 이름 사후 검증 실패: {errors}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    print(json.dumps({
        "metadata_version": version,
        "type": f"{args.namespace}.{args.type_name}",
        "field_start": field_start,
        "field_count": field_count,
        "changed_names": actual,
        "file_size_delta": delta,
        "source_sha256": sha256_file(args.source),
        "output_sha256": sha256_file(args.output),
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--namespace", default="_TDGame.StatSystem")
    parser.add_argument("--type-name", default="UpgradeTag")
    parser.add_argument("--output", type=Path, required=True)
    command_patch(parser.parse_args())


if __name__ == "__main__":
    main()
