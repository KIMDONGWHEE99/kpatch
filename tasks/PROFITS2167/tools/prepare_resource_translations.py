from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def is_player_facing(row: dict) -> bool:
    field_path = ".".join(str(part) for part in row["field_path"])
    class_name = row["class"]
    if class_name == "UpgradeData" and field_path == "_displayName":
        return True
    if class_name == "TechData" and field_path in {"displayTitle", "displayDescription"}:
        return True
    if class_name == "UpgradePack" and field_path == "displayName":
        return True
    if class_name == "StatDefinition" and field_path in {
        "_displayName",
        "_obsoleteTooltipContent",
    }:
        return True
    if class_name == "MapMetaDataContainer" and (
        field_path.endswith(".displayName") or field_path.endswith(".displayDescription")
    ):
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="resources.assets 표시 문자열 번역 준비")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--entries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    mapping: dict[str, str] = {}
    for row in read_json(args.root / "translation_entries.json"):
        mapping[str(row["source"])] = str(row["translation"])
    for path in sorted(args.root.glob("resource_translation_overrides_*.json")):
        mapping.update(read_json(path))

    selected = [row for row in read_json(args.entries) if is_player_facing(row)]
    missing = sorted({str(row["source"]) for row in selected if str(row["source"]) not in mapping})
    if missing:
        raise RuntimeError(f"플레이어 표시 문자열 번역 누락: {missing}")
    changed = 0
    for row in selected:
        row["translation"] = mapping[str(row["source"])]
        if row["translation"] != row["source"]:
            changed += 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(selected, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {"entries": len(selected), "changed": changed, "output": str(args.output)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
