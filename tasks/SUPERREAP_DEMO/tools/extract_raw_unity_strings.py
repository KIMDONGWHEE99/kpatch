#!/usr/bin/env python3
"""형식 트리가 깨진 Unity 객체에서 길이 접두 UTF-8 문자열 후보를 추출한다."""

from __future__ import annotations

import argparse
import json
import struct
import sys
import unicodedata
from pathlib import Path

import UnityPy


def is_readable(text: str) -> bool:
    if not text or len(text) > 4096:
        return False
    if any(character not in "\r\n\t" and not character.isprintable() for character in text):
        return False
    return any(unicodedata.category(character)[0] in {"L", "N"} for character in text)


def scan_strings(data: bytes) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for offset in range(0, max(0, len(data) - 4), 4):
        size = struct.unpack_from("<I", data, offset)[0]
        if size == 0 or size > 4096 or offset + 4 + size > len(data):
            continue
        raw = data[offset + 4:offset + 4 + size]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not is_readable(text):
            continue
        found.append({"offset": offset, "byte_length": size, "text": text})
    return found


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--dependency", type=Path, action="append", default=[])
    parser.add_argument("--path-id", type=int, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    env = UnityPy.load(str(args.file), *[str(path) for path in args.dependency])
    primary_name = args.file.name.lower()
    selected_ids = set(args.path_id)
    rows = []
    for obj in env.objects:
        assets_name = Path(str(getattr(obj.assets_file, "name", ""))).name.lower()
        if assets_name != primary_name or int(obj.path_id) not in selected_ids:
            continue
        raw = obj.get_raw_data()
        rows.append(
            {
                "file": str(args.file),
                "path_id": int(obj.path_id),
                "object_type": obj.type.name,
                "raw_size": len(raw),
                "strings": scan_strings(raw),
            }
        )
    missing = sorted(selected_ids - {row["path_id"] for row in rows})
    report = {"objects": rows, "missing_path_ids": missing}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"objects": len(rows), "missing": missing, "strings": sum(len(row["strings"]) for row in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
