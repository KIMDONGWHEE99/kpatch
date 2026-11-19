from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy


TOKEN_PATTERN = re.compile(r"%[A-Za-z0-9_.]+%?")
TAG_PATTERN = re.compile(r"<[^>]+>")
NEWLINE_PATTERN = re.compile(r"\r\n|\r|\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_string_table(path: Path) -> tuple[Any, Any, dict[str, Any]]:
    """영문 StringTable 번들과 직렬화 트리를 읽는다."""
    env = UnityPy.load(str(path))
    candidates = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        if "m_TableData" in tree and "m_LocaleId" in tree:
            candidates.append((obj, tree))
    if len(candidates) != 1:
        raise RuntimeError(f"StringTable 개체가 1개가 아닙니다: {len(candidates)}")
    obj, tree = candidates[0]
    return env, obj, tree


def load_shared_keys(path: Path) -> dict[int, str]:
    """SharedTableData에서 숫자 ID와 문자열 키를 연결한다."""
    env = UnityPy.load(str(path))
    candidates = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        if "m_Entries" in tree:
            candidates.append(tree)
    if len(candidates) != 1:
        raise RuntimeError(f"SharedTableData 개체가 1개가 아닙니다: {len(candidates)}")
    mapping: dict[int, str] = {}
    for entry in candidates[0]["m_Entries"]:
        mapping[int(entry["m_Id"])] = str(entry["m_Key"])
    return mapping


def control_signature(text: str) -> dict[str, Any]:
    """번역 과정에서 반드시 보존할 서식·제어 코드를 추출한다."""
    return {
        "tokens": TOKEN_PATTERN.findall(text),
        "tags": TAG_PATTERN.findall(text),
        "newlines": NEWLINE_PATTERN.findall(text),
        "bold_markers": text.count("**"),
    }


def extract_entries(bundle: Path, shared: Path) -> list[dict[str, Any]]:
    _, _, tree = load_string_table(bundle)
    keys = load_shared_keys(shared)
    rows = []
    for entry in tree["m_TableData"]:
        item_id = int(entry["m_Id"])
        source = str(entry["m_Localized"])
        rows.append(
            {
                "id": item_id,
                "key": keys.get(item_id, ""),
                "source": source,
                "translation": "",
            }
        )
    return rows


def validate_rows(rows: list[dict[str, Any]], source_tree: dict[str, Any]) -> list[str]:
    """ID, 태그, 아이콘 토큰, 줄바꿈, 유니코드 정규화를 검사한다."""
    errors: list[str] = []
    source_by_id = {
        int(item["m_Id"]): str(item["m_Localized"])
        for item in source_tree["m_TableData"]
    }
    row_ids = [int(row["id"]) for row in rows]
    duplicates = [item_id for item_id, count in Counter(row_ids).items() if count > 1]
    if duplicates:
        errors.append(f"중복 ID: {duplicates}")
    missing = sorted(set(source_by_id) - set(row_ids))
    extra = sorted(set(row_ids) - set(source_by_id))
    if missing:
        errors.append(f"누락 ID: {missing}")
    if extra:
        errors.append(f"원문에 없는 ID: {extra}")

    for row in rows:
        item_id = int(row["id"])
        if item_id not in source_by_id:
            continue
        source = source_by_id[item_id]
        translated = str(row.get("translation", ""))
        if not translated:
            errors.append(f"{item_id}: 번역문이 비어 있습니다.")
            continue
        if "�" in translated or "□" in translated:
            errors.append(f"{item_id}: 깨진 문자 후보가 있습니다.")
        if unicodedata.normalize("NFC", translated) != translated:
            errors.append(f"{item_id}: NFC 정규화가 아닙니다.")
        if control_signature(source) != control_signature(translated):
            errors.append(
                f"{item_id}: 제어 코드 불일치 "
                f"source={control_signature(source)!r} "
                f"translation={control_signature(translated)!r}"
            )
        if source == "-" and translated != "-":
            errors.append(f"{item_id}: 구분자 '-'가 변경되었습니다.")
    return errors


def object_signatures(path: Path) -> list[dict[str, Any]]:
    """번들 내부 개체의 논리적 동일성을 비교하기 위한 서명을 만든다."""
    env = UnityPy.load(str(path))
    rows = []
    for obj in env.objects:
        raw = bytes(obj.get_raw_data())
        rows.append(
            {
                "path_id": int(obj.path_id),
                "type": obj.type.name,
                "size": len(raw),
                "sha256": sha256_bytes(raw),
            }
        )
    return sorted(rows, key=lambda row: (row["path_id"], row["type"]))


def read_7bit_string(data: bytes, position: int) -> tuple[str, int]:
    value = 0
    shift = 0
    while True:
        current = data[position]
        position += 1
        value |= (current & 0x7F) << shift
        if current < 0x80:
            break
        shift += 7
    end = position + value
    return data[position:end].decode("utf-8"), end


def write_7bit_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    size = len(raw)
    prefix = bytearray()
    while size >= 0x80:
        prefix.append((size & 0x7F) | 0x80)
        size >>= 7
    prefix.append(size)
    return bytes(prefix) + raw


def decode_extra_records(encoded: str) -> list[dict[str, Any]]:
    data = base64.b64decode(encoded)
    position = 0
    records = []
    while position < len(data):
        marker = data[position]
        position += 1
        assembly, position = read_7bit_string(data, position)
        class_name, position = read_7bit_string(data, position)
        size = struct.unpack_from("<I", data, position)[0]
        position += 4
        payload = data[position : position + size]
        position += size
        records.append(
            {
                "marker": marker,
                "assembly": assembly,
                "class_name": class_name,
                "payload": payload,
            }
        )
    if position != len(data):
        raise RuntimeError("Addressables 추가 데이터 경계를 정확히 읽지 못했습니다.")
    return records


def encode_extra_records(records: list[dict[str, Any]]) -> str:
    output = bytearray()
    for record in records:
        payload = bytes(record["payload"])
        output.append(int(record["marker"]))
        output.extend(write_7bit_string(str(record["assembly"])))
        output.extend(write_7bit_string(str(record["class_name"])))
        output.extend(struct.pack("<I", len(payload)))
        output.extend(payload)
    return base64.b64encode(bytes(output)).decode("ascii")


def update_catalog(
    source: Path,
    output: Path,
    bundle_name: str,
    bundle_size: int,
) -> dict[str, Any]:
    """수정 번들을 허용하도록 해당 로컬 번들의 CRC 검사를 비활성화한다."""
    catalog = json.loads(source.read_text(encoding="utf-8"))
    records = decode_extra_records(catalog["m_ExtraDataString"])
    matches = 0
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    for record in records:
        options = json.loads(record["payload"].decode("utf-16le"))
        if options.get("m_BundleName") != bundle_name:
            continue
        matches += 1
        before = dict(options)
        options["m_Crc"] = 0
        options["m_BundleSize"] = int(bundle_size)
        after = dict(options)
        compact = json.dumps(options, ensure_ascii=False, separators=(",", ":"))
        record["payload"] = compact.encode("utf-16le")
    if matches != 1:
        raise RuntimeError(f"카탈로그 대상 번들 레코드가 1개가 아닙니다: {matches}")
    catalog["m_ExtraDataString"] = encode_extra_records(records)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
        newline="",
    )
    return {"before": before, "after": after}


def command_extract(args: argparse.Namespace) -> None:
    rows = extract_entries(args.bundle, args.shared)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"entries": len(rows), "output": str(args.output)}, ensure_ascii=False))


def command_noop(args: argparse.Namespace) -> None:
    env = UnityPy.load(str(args.bundle))
    repacked = bytes(env.file.save(packer="original"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(repacked)
    original_objects = object_signatures(args.bundle)
    repacked_objects = object_signatures(args.output)
    report = {
        "original_sha256": sha256_file(args.bundle),
        "repacked_sha256": sha256_file(args.output),
        "byte_identical": args.bundle.read_bytes() == args.output.read_bytes(),
        "logical_objects_identical": original_objects == repacked_objects,
        "original_size": args.bundle.stat().st_size,
        "repacked_size": args.output.stat().st_size,
        "object_count": len(original_objects),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["logical_objects_identical"]:
        raise SystemExit(2)


def command_build(args: argparse.Namespace) -> None:
    rows = json.loads(args.translations.read_text(encoding="utf-8"))
    env, obj, tree = load_string_table(args.bundle)
    errors = validate_rows(rows, tree)
    if errors:
        print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    translated_by_id = {int(row["id"]): str(row["translation"]) for row in rows}
    for entry in tree["m_TableData"]:
        entry["m_Localized"] = translated_by_id[int(entry["m_Id"])]
    obj.save_typetree(tree)
    output_data = bytes(env.file.save(packer="original"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_data)

    _, _, built_tree = load_string_table(args.output)
    built_rows = [
        {
            "id": int(item["m_Id"]),
            "translation": str(item["m_Localized"]),
        }
        for item in built_tree["m_TableData"]
    ]
    post_errors = validate_rows(built_rows, load_string_table(args.bundle)[2])
    report = {
        "entries": len(rows),
        "source_sha256": sha256_file(args.bundle),
        "output_sha256": sha256_file(args.output),
        "source_size": args.bundle.stat().st_size,
        "output_size": args.output.stat().st_size,
        "post_build_errors": post_errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if post_errors:
        raise SystemExit(3)


def command_catalog(args: argparse.Namespace) -> None:
    report = update_catalog(
        args.catalog,
        args.output,
        args.bundle_name,
        args.bundle.stat().st_size,
    )
    report.update(
        {
            "source_sha256": sha256_file(args.catalog),
            "output_sha256": sha256_file(args.output),
            "bundle_sha256": sha256_file(args.bundle),
        }
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PROFITS2167 번역 번들 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--bundle", type=Path, required=True)
    extract_parser.add_argument("--shared", type=Path, required=True)
    extract_parser.add_argument("--output", type=Path, required=True)
    extract_parser.set_defaults(func=command_extract)

    noop_parser = subparsers.add_parser("noop")
    noop_parser.add_argument("--bundle", type=Path, required=True)
    noop_parser.add_argument("--output", type=Path, required=True)
    noop_parser.set_defaults(func=command_noop)

    build_parser_command = subparsers.add_parser("build")
    build_parser_command.add_argument("--bundle", type=Path, required=True)
    build_parser_command.add_argument("--translations", type=Path, required=True)
    build_parser_command.add_argument("--output", type=Path, required=True)
    build_parser_command.set_defaults(func=command_build)

    catalog_parser = subparsers.add_parser("catalog")
    catalog_parser.add_argument("--catalog", type=Path, required=True)
    catalog_parser.add_argument("--bundle", type=Path, required=True)
    catalog_parser.add_argument("--bundle-name", required=True)
    catalog_parser.add_argument("--output", type=Path, required=True)
    catalog_parser.set_defaults(func=command_catalog)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
