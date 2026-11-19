from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


CONTROL_PATTERN = re.compile(r"%[A-Za-z0-9_.]+%?|<[^>]+>|\{[^{}]+\}|\[[^\[\]]+\]")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def control_signature(text: str) -> dict[str, Any]:
    return {
        "tokens": Counter(CONTROL_PATTERN.findall(text)),
        "lf": text.count("\n"),
        "cr": text.count("\r"),
        "line_separator": text.count("\u2028"),
    }


def metadata_layout(data: bytes) -> tuple[int, int, int, int, int]:
    sanity, version = struct.unpack_from("<II", data, 0)
    if sanity != 0xFAB11BAF:
        raise ValueError(f"지원하지 않는 메타데이터 서명: 0x{sanity:08X}")
    literal_offset, literal_size, data_offset, data_size = struct.unpack_from("<IIII", data, 8)
    if literal_offset < 24 or literal_offset % 8 or literal_size % 8:
        raise ValueError("문자열 표 머리말이 올바르지 않습니다.")
    if data_offset != literal_offset + literal_size:
        raise ValueError("문자열 데이터가 문자열 표 바로 뒤에 있지 않습니다.")
    if data_offset + data_size > len(data):
        raise ValueError("문자열 데이터가 파일 범위를 벗어납니다.")
    return version, literal_offset, literal_size, data_offset, data_size


def extract_literals(data: bytes) -> list[dict[str, object]]:
    _, literal_offset, literal_size, data_offset, data_size = metadata_layout(data)
    rows: list[dict[str, object]] = []
    for index, table_position in enumerate(range(literal_offset, literal_offset + literal_size, 8)):
        length, data_index = struct.unpack_from("<II", data, table_position)
        if data_index + length > data_size:
            raise ValueError(f"문자열 {index}가 데이터 범위를 벗어납니다.")
        raw = data[data_offset + data_index : data_offset + data_index + length]
        rows.append({"index": index, "length": length, "data_index": data_index, "source": raw.decode("utf-8")})
    return rows


def load_mapping(path: Path) -> dict[str, str]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(value, dict) and isinstance(value.get("translations"), dict):
        value = value["translations"]
    if not isinstance(value, dict):
        raise ValueError("번역 매핑은 JSON 객체여야 합니다.")
    mapping: dict[str, str] = {}
    for source, target in value.items():
        if not isinstance(target, str):
            raise ValueError(f"문자열이 아닌 번역문: {source!r}")
        mapping[str(source)] = target
    return mapping


def command_extract(args: argparse.Namespace) -> None:
    rows = extract_literals(args.source.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"entries": len(rows), "output": str(args.output)}, ensure_ascii=False))


def command_build(args: argparse.Namespace) -> None:
    original = args.source.read_bytes()
    version, literal_offset, literal_size, data_offset, old_data_size = metadata_layout(original)
    rows = extract_literals(original)
    mapping = load_mapping(args.mapping)

    sources = {str(row["source"]) for row in rows}
    missing = sorted(set(mapping) - sources)
    if missing:
        raise RuntimeError(f"원본에서 찾지 못한 번역 키: {missing}")
    errors = []
    for source, target in mapping.items():
        if unicodedata.normalize("NFC", target) != target:
            errors.append(f"NFC 정규화 오류: {source!r}")
        if control_signature(source) != control_signature(target):
            errors.append(f"제어 문자 구조 불일치: {source!r}")
    if errors:
        raise RuntimeError("\n".join(errors))

    table = bytearray(literal_size)
    new_blob = bytearray()
    changed = 0
    changed_occurrences: Counter[str] = Counter()
    for row in rows:
        index = int(row["index"])
        source = str(row["source"])
        if int(row["length"]) == 0:
            struct.pack_into("<II", table, index * 8, 0, 0)
            continue
        target = mapping.get(source, source)
        encoded = target.encode("utf-8")
        struct.pack_into("<II", table, index * 8, len(encoded), len(new_blob))
        new_blob.extend(encoded)
        if target != source:
            changed += 1
            changed_occurrences[source] += 1
    new_blob.append(0)

    prefix = bytearray(original[:data_offset])
    prefix[literal_offset : literal_offset + literal_size] = table
    old_data_end = data_offset + old_data_size
    delta = len(new_blob) - old_data_size
    if (literal_offset - 8) % 8:
        raise ValueError("메타데이터 머리말 크기를 해석할 수 없습니다.")
    for pair_index in range((literal_offset - 8) // 8):
        field_position = 8 + pair_index * 8
        section_offset, section_size = struct.unpack_from("<II", prefix, field_position)
        if field_position == 16:
            struct.pack_into("<II", prefix, field_position, section_offset, len(new_blob))
        elif section_offset >= old_data_end:
            struct.pack_into("<II", prefix, field_position, section_offset + delta, section_size)

    output = bytes(prefix) + bytes(new_blob) + original[old_data_end:]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)

    verified = extract_literals(output)
    counts = Counter(str(row["source"]) for row in verified)
    post_errors = [source for source, target in mapping.items() if counts[target] == 0]
    unchanged_mapped = [source for source, target in mapping.items() if source != target and source and counts[source] > 0]
    report = {
        "schema_version": 1,
        "passed": not post_errors,
        "metadata_version": version,
        "entries": len(rows),
        "mapping_entries": len(mapping),
        "changed_literals": changed,
        "changed_occurrences": dict(changed_occurrences),
        "old_string_data_size": old_data_size,
        "new_string_data_size": len(new_blob),
        "file_size_delta": delta,
        "source_sha256": sha256_file(args.source),
        "output_sha256": sha256_file(args.output),
        "post_build_errors": post_errors,
        "mapped_source_literals_still_present": unchanged_mapped,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if post_errors:
        raise SystemExit(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 IL2CPP global-metadata 문자열 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--source", type=Path, required=True)
    extract_parser.add_argument("--output", type=Path, required=True)
    extract_parser.set_defaults(func=command_extract)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--source", type=Path, required=True)
    build_parser.add_argument("--mapping", type=Path, required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--report", type=Path)
    build_parser.set_defaults(func=command_build)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
