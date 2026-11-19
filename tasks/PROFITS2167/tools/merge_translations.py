from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="키 기반 한국어 번역 병합")
    parser.add_argument("--entries", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    args = parser.parse_args()

    entries = json.loads(args.entries.read_text(encoding="utf-8"))
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    keys = [str(entry["key"]) for entry in entries]
    missing = sorted(set(keys) - set(mapping))
    extra = sorted(set(mapping) - set(keys))
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if missing or extra or duplicates:
        raise RuntimeError(
            f"키 불일치: missing={missing}, extra={extra}, duplicates={duplicates}"
        )
    for entry in entries:
        entry["translation"] = mapping[str(entry["key"])]
    args.entries.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(f"병합 완료: {len(entries)}개")


if __name__ == "__main__":
    main()
