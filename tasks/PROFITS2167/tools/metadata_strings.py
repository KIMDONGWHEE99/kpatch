from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import unicodedata
from pathlib import Path


TOKEN_PATTERN = re.compile(r"%[A-Za-z0-9_.]+%?")
TAG_PATTERN = re.compile(
    r"</?(?:align|allcaps|alpha|b|br|color|cspace|font|font-weight|gradient|i|indent|"
    r"line-height|line-indent|link|lowercase|margin|margin-left|margin-right|mark|material|"
    r"mspace|nobr|noparse|page|pos|rotate|s|size|smallcaps|space|sprite|strikethrough|"
    r"style|sub|sup|u|uppercase|voffset|width)(?:=[^>]*)?>",
    re.IGNORECASE,
)
BRACE_PATTERN = re.compile(r"\{[^{}]+\}")
NEWLINE_PATTERN = re.compile(r"\r\n|\r|\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def control_signature(text: str) -> dict[str, list[str]]:
    return {
        # 한국어 어순에 맞춰 토큰 위치가 바뀔 수 있으므로 종류와 개수만 비교한다.
        "tokens": sorted(TOKEN_PATTERN.findall(text)),
        "tags": TAG_PATTERN.findall(text),
        "braces": BRACE_PATTERN.findall(text),
        "newlines": NEWLINE_PATTERN.findall(text),
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
        rows.append(
            {
                "index": index,
                "length": length,
                "data_index": data_index,
                "source": raw.decode("utf-8"),
            }
        )
    return rows


def command_extract(args: argparse.Namespace) -> None:
    data = args.source.read_bytes()
    rows = extract_literals(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"entries": len(rows), "output": str(args.output)}, ensure_ascii=False))


def command_build(args: argparse.Namespace) -> None:
    original = args.source.read_bytes()
    version, literal_offset, literal_size, data_offset, old_data_size = metadata_layout(original)
    rows = extract_literals(original)
    mapping: dict[str, str] = json.loads(args.mapping.read_text(encoding="utf-8"))

    sources = {str(row["source"]) for row in rows}
    missing = sorted(set(mapping) - sources)
    if missing:
        raise RuntimeError(f"원본에서 찾지 못한 번역 키: {missing}")

    validation_errors: list[str] = []
    for source, translation in mapping.items():
        if not translation:
            validation_errors.append(f"빈 번역문: {source!r}")
        if unicodedata.normalize("NFC", translation) != translation:
            validation_errors.append(f"NFC 정규화 오류: {source!r}")
        if control_signature(source) != control_signature(translation):
            validation_errors.append(f"제어 문자 구조 불일치: {source!r}")
    if validation_errors:
        print(json.dumps({"errors": validation_errors}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    table = bytearray(literal_size)
    new_blob = bytearray()
    changed = 0
    for row in rows:
        index = int(row["index"])
        source = str(row["source"])
        if int(row["length"]) == 0:
            struct.pack_into("<II", table, index * 8, 0, 0)
            continue
        translation = mapping.get(source, source)
        encoded = translation.encode("utf-8")
        struct.pack_into("<II", table, index * 8, len(encoded), len(new_blob))
        new_blob.extend(encoded)
        if translation != source:
            changed += 1
    new_blob.append(0)

    prefix = bytearray(original[:data_offset])
    prefix[literal_offset : literal_offset + literal_size] = table
    old_data_end = data_offset + old_data_size
    delta = len(new_blob) - old_data_size

    header_size = literal_offset
    if (header_size - 8) % 8:
        raise ValueError("메타데이터 머리말 크기를 해석할 수 없습니다.")
    pair_count = (header_size - 8) // 8
    for pair_index in range(pair_count):
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
    counts: dict[str, int] = {}
    for row in verified:
        text = str(row["source"])
        counts[text] = counts.get(text, 0) + 1
    post_errors = [
        source for source, translation in mapping.items() if counts.get(translation, 0) == 0
    ]
    report = {
        "metadata_version": version,
        "entries": len(rows),
        "mapping_entries": len(mapping),
        "changed_literals": changed,
        "old_string_data_size": old_data_size,
        "new_string_data_size": len(new_blob),
        "file_size_delta": delta,
        "source_sha256": sha256_file(args.source),
        "output_sha256": sha256_file(args.output),
        "post_build_errors": post_errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if post_errors:
        raise SystemExit(3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IL2CPP global-metadata 문자열 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--source", type=Path, required=True)
    extract_parser.add_argument("--output", type=Path, required=True)
    extract_parser.set_defaults(func=command_extract)

    build_parser_command = subparsers.add_parser("build")
    build_parser_command.add_argument("--source", type=Path, required=True)
    build_parser_command.add_argument("--mapping", type=Path, required=True)
    build_parser_command.add_argument("--output", type=Path, required=True)
    build_parser_command.set_defaults(func=command_build)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
