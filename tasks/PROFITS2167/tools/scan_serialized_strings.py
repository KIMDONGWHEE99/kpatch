from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import UnityPy


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Unity 직렬화 문자열 후보 검색")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--path-id", type=int, action="append", required=True)
    args = parser.parse_args()

    wanted = set(args.path_id)
    env = UnityPy.load(str(args.source))
    results = []
    for obj in env.objects:
        if int(obj.path_id) not in wanted:
            continue
        raw = bytes(obj.get_raw_data())
        strings = []
        for offset in range(0, max(0, len(raw) - 4), 4):
            length = struct.unpack_from("<I", raw, offset)[0]
            if length == 0 or length > 2000 or offset + 4 + length > len(raw):
                continue
            payload = raw[offset + 4 : offset + 4 + length]
            try:
                value = payload.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if not value.isprintable() or not any(character.isalpha() for character in value):
                continue
            strings.append({"offset": offset, "length": length, "value": value})
        results.append(
            {
                "path_id": int(obj.path_id),
                "type": obj.type.name,
                "name": str(obj.peek_name()),
                "object_size": len(raw),
                "strings": strings,
            }
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
