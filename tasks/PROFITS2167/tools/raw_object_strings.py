from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import UnityPy


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def serialized_string(value: str) -> bytes:
    payload = value.encode("utf-8")
    result = struct.pack("<I", len(payload)) + payload
    result += b"\0" * ((-len(result)) % 4)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Unity 개체의 길이 접두 문자열 수정")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = json.loads(args.translations.read_text(encoding="utf-8"))
    grouped: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(int(row["path_id"]), []).append(row)

    env = UnityPy.load(str(args.source))
    objects = {int(obj.path_id): obj for obj in env.objects}
    changed = 0
    for path_id, object_rows in grouped.items():
        if path_id not in objects:
            raise RuntimeError(f"대상 개체가 없습니다: {path_id}")
        obj = objects[path_id]
        raw = bytes(obj.get_raw_data())
        replacements = []
        for row in object_rows:
            source = str(row["source"])
            translation = str(row["translation"])
            needle = serialized_string(source)
            offset = raw.find(needle)
            if offset < 0:
                raise RuntimeError(f"원문을 찾지 못했습니다: {path_id} {source!r}")
            if raw.find(needle, offset + 1) >= 0:
                raise RuntimeError(f"원문이 중복됩니다: {path_id} {source!r}")
            replacements.append((offset, needle, serialized_string(translation)))
        for offset, needle, replacement in sorted(replacements, reverse=True):
            raw = raw[:offset] + replacement + raw[offset + len(needle) :]
            changed += 1
        obj.set_raw_data(raw)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(env.file.save(packer="original")))

    verify_env = UnityPy.load(str(args.output))
    verify_objects = {int(obj.path_id): obj for obj in verify_env.objects}
    post_errors = []
    for row in rows:
        raw = bytes(verify_objects[int(row["path_id"])].get_raw_data())
        if serialized_string(str(row["translation"])) not in raw:
            post_errors.append(f"{row['path_id']}: {row['translation']!r}")
    report = {
        "entries": len(rows),
        "changed": changed,
        "source_sha256": sha256_file(args.source),
        "output_sha256": sha256_file(args.output),
        "post_build_errors": post_errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if post_errors:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
