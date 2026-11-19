from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="장면별 TMP 번역 파일 생성")
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    root = args.root
    mapping: dict[str, str] = {}
    for row in read_json(root / "translation_entries.json"):
        mapping[str(row["source"])] = str(row["translation"])
    for row in read_json(root / "direct_text_level0_ko.json"):
        mapping[str(row["source"])] = str(row["translation"])
    mapping.update(read_json(root / "scene_translation_overrides.json"))

    reports = []
    for level in range(1, 7):
        input_path = root / f"direct_text_level{level}.json"
        output_path = root / f"direct_text_level{level}_ko.json"
        rows = read_json(input_path)
        changed = 0
        for row in rows:
            source = str(row["source"])
            translation = mapping.get(source, source)
            row["translation"] = translation
            if translation != source:
                changed += 1
        output_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        reports.append(
            {
                "level": level,
                "entries": len(rows),
                "changed": changed,
                "output": str(output_path),
            }
        )
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
