#!/usr/bin/env python3
"""0.4.0용 메타데이터 및 공용 TMP 번역 입력을 만든다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inventory_metadata_strings import collect_known
from direct_tmp_text import validate_rows


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root

    metadata = load(root / "metadata_translation_overrides.json")
    metadata.update(load(root / "metadata_translation_additions_v040.json"))
    metadata_output = root / "metadata_translation_overrides_v040.json"
    write(metadata_output, metadata)

    display_mapping = collect_known(root)
    display_mapping.update(metadata)
    display_mapping.update(load(root / "resource_tmp_overrides_v040.json"))
    rows = load(root / "direct_text_resources_v040.json")
    changed = 0
    for row in rows:
        source = str(row["source"])
        translation = display_mapping.get(source, source)
        row["translation"] = translation
        changed += translation != source
    errors = validate_rows(rows)
    if errors:
        raise RuntimeError("\n".join(errors))
    resource_output = root / "direct_text_resources_v040_ko.json"
    write(resource_output, rows)

    literals = load(
        root.parent / "tools" / "Unity_Font_Replacer_v1.2.8" / "Il2CppDumper" / "stringliteral.json"
    )
    literal_values = {row["value"] for row in literals}
    missing = sorted(source for source in metadata if source not in literal_values)
    if missing:
        raise RuntimeError(f"메타데이터 원문을 찾지 못했습니다: {missing}")

    print(
        json.dumps(
            {
                "metadata_translations": len(metadata),
                "resource_tmp_entries": len(rows),
                "resource_tmp_changed": changed,
                "metadata_output": str(metadata_output),
                "resource_output": str(resource_output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
