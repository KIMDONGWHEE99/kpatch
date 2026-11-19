from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TOKEN_PATTERN = re.compile(r"{[^{}]+}|<[^>]+>|\\n|\[[A-Za-z0-9_]+\]")
TRANSLATABLE_PATTERN = re.compile(r"[A-Za-z]")


def locale_code(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("m_Code", ""))
    return str(value)


def control_signature(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text)


def is_keep_text(source: str, game_object: str) -> tuple[bool, str]:
    stripped = source.strip()
    if not stripped or not TRANSLATABLE_PATTERN.search(stripped):
        return True, "숫자·기호·서식 전용"
    if re.fullmatch(r"[A-Z]", stripped) or re.fullmatch(r"[XYZWASD]+", stripped):
        return True, "조작 키 표기"
    if re.search(r"https?://|creativecommons|incompetech\.com", source, re.I):
        return True, "URL·라이선스 원문"
    if game_object.startswith("Name") or game_object in {"VersionNumber"}:
        return True, "인명·버전"
    if stripped in {
        "Arcane Cabinet Team", "Grab The Games", "Discord", "Website",
        "Pib Rock", "XP", "FPS", "MAX",
    }:
        return True, "브랜드·서비스·고유명·게임 약어"
    return False, ""


def classify_direct(row: dict[str, Any]) -> tuple[str, str]:
    source = str(row["source"])
    game_object = str(row.get("game_object", ""))
    keep, reason = is_keep_text(source, game_object)
    if keep:
        return "VISIBLE_KEEP", reason
    if row.get("class") == "Text" and game_object in {
        "Text", "Value", "Title", "Float", "Int", "Increment", "AchievementTitle",
        "AchievementDescription",
    }:
        return "INTERNAL", "Unity 예제·디버그 UI 기본값"
    return "VISIBLE_TRANSLATE", "TMP/Text 직렬화 표시 필드"


def main() -> None:
    parser = argparse.ArgumentParser(description="Pibcremental Demo 번역 계층별 인벤토리")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--assembly", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.inventory.read_text(encoding="utf-8"))
    shared_maps: dict[str, dict[int, str]] = {}
    locale_tables: dict[tuple[str, str], dict[str, Any]] = {}
    for file_row in report["files"]:
        for table in file_row["shared_tables"]:
            collection = str(table["table_collection_name"])
            shared_maps[collection] = {
                int(entry["m_Id"]): str(entry["m_Key"])
                for entry in table["entries"]
            }
        for table in file_row["localization_tables"]:
            name = str(table["name"])
            collection = name.rsplit("_", 1)[0]
            locale_tables[(collection, locale_code(table["locale"]))] = {
                "file": file_row["relative_path"],
                **table,
            }

    localization_rows: list[dict[str, Any]] = []
    for (collection, code), table in sorted(locale_tables.items()):
        keys = shared_maps.get(collection, {})
        for index, entry in enumerate(table["entries"]):
            source = str(entry.get("m_Localized", ""))
            localization_rows.append(
                {
                    "layer": "Localization StringTable",
                    "classification": "VISIBLE_TRANSLATE" if source.strip() else "VISIBLE_KEEP",
                    "locale": code,
                    "table": collection,
                    "table_path_id": int(table["path_id"]),
                    "file": table["file"],
                    "entry_index": index,
                    "id": int(entry["m_Id"]),
                    "key": keys.get(int(entry["m_Id"]), ""),
                    "source": source,
                    "control_tokens": control_signature(source),
                    "translation": "",
                }
            )

    direct_rows: list[dict[str, Any]] = []
    for file_row in report["files"]:
        for row in file_row["strings"]:
            field_name = row["field_path"][-1] if row["field_path"] else ""
            if row["class"] not in {"TextMeshPro", "TextMeshProUGUI", "Text"}:
                continue
            if field_name not in {"m_text", "m_Text"}:
                continue
            classification, reason = classify_direct(row)
            direct_rows.append(
                {
                    "layer": "TMP/Text direct",
                    "classification": classification,
                    "reason": reason,
                    "file": file_row["relative_path"],
                    "asset_file": row.get("asset_file", ""),
                    "path_id": int(row["path_id"]),
                    "class": row["class"],
                    "game_object": row["game_object"],
                    "field_path": row["field_path"],
                    "source": row["source"],
                    "control_tokens": control_signature(str(row["source"])),
                    "translation": "",
                }
            )

    unique_direct: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in direct_rows:
        unique_direct[str(row["source"])].append(row)
    direct_unique_rows = [
        {
            "source": source,
            "classification": locations[0]["classification"],
            "reason": locations[0]["reason"],
            "occurrences": len(locations),
            "game_objects": sorted({str(item["game_object"]) for item in locations}),
            "translation": "",
        }
        for source, locations in sorted(unique_direct.items())
    ]

    assembly = json.loads(args.assembly.read_text(encoding="utf-8"))
    assembly_rows = []
    for row in assembly["entries"]:
        source = str(row["source"])
        assembly_rows.append(
            {
                **row,
                "layer": "Mono managed code literal",
                "classification": "INTERNAL",
                "reason": "코드 사용처 검토 전 기본 내부 분류",
                "control_tokens": control_signature(source),
                "translation": "",
            }
        )

    text_asset_rows = []
    for file_row in report["files"]:
        for item in file_row["text_assets"]:
            text_asset_rows.append(
                {
                    "layer": "TextAsset",
                    "classification": "INTERNAL",
                    "reason": "햅틱·성능시험·TMP 줄바꿈 제어 데이터",
                    "file": file_row["relative_path"],
                    "path_id": int(item["path_id"]),
                    "name": item["name"],
                    "decoded": bool(item["decoded"]),
                    "character_count": len(str(item["text"])),
                }
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "localization_entries.json": localization_rows,
        "direct_text_entries.json": direct_rows,
        "direct_text_unique.json": direct_unique_rows,
        "assembly_entries.json": assembly_rows,
        "text_asset_entries.json": text_asset_rows,
    }
    for name, rows in outputs.items():
        (args.output_dir / name).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    english_sources: dict[str, set[str]] = defaultdict(set)
    for row in localization_rows:
        if row["locale"] == "en":
            english_sources[str(row["source"])].add(str(row["key"]))
    english_unique = sorted(english_sources)
    (args.output_dir / "localization_unique.json").write_text(
        json.dumps(
            [
                {
                    "index": index,
                    "source": source,
                    "sample_keys": sorted(english_sources[source])[:8],
                    "translation": "",
                }
                for index, source in enumerate(english_unique, 1)
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "localization_entries": len(localization_rows),
        "localization_by_locale": dict(Counter(row["locale"] for row in localization_rows)),
        "english_unique": len(english_unique),
        "direct_locations": len(direct_rows),
        "direct_unique": len(direct_unique_rows),
        "direct_classifications": dict(Counter(row["classification"] for row in direct_rows)),
        "assembly_occurrences": len(assembly_rows),
        "text_assets": len(text_asset_rows),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
