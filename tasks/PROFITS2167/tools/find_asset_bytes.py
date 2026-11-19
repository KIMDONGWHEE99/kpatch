from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import UnityPy


def safe_name(obj: object) -> str:
    try:
        return str(obj.peek_name())
    except Exception:
        return ""


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Unity 자산의 원시 바이트 검색")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--needle", action="append", required=True)
    args = parser.parse_args()

    needles = [(item, item.encode("utf-8")) for item in args.needle]
    env = UnityPy.load(str(args.source))
    matches: list[dict[str, object]] = []
    for obj in env.objects:
        try:
            raw = bytes(obj.get_raw_data())
        except Exception:
            continue
        for label, needle in needles:
            offset = raw.lower().find(needle.lower())
            if offset < 0:
                continue
            start = max(0, offset - 160)
            end = min(len(raw), offset + len(needle) + 320)
            matches.append(
                {
                    "needle": label,
                    "path_id": int(obj.path_id),
                    "type": obj.type.name,
                    "name": safe_name(obj),
                    "object_size": len(raw),
                    "offset": offset,
                    "context": raw[start:end].decode("utf-8", errors="replace"),
                }
            )
    print(json.dumps(matches, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
