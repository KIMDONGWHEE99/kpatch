from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TOKEN_PATTERN = re.compile(r"%[A-Za-z0-9_.]+%?|{[^{}]+\}|<[^>]+>")
TRANSLATABLE_PATTERN = re.compile(r"[A-Za-z\u3400-\u9fff]")
KEEP_EXACT = {
    "Bingo",
    "Codex",
    "Koko",
    "Locus",
    "OpenAI Codex",
    "Ruby",
    "Suno",
    "WeiWei",
    "Yuan",
    "yuan",
    "koko",
    "STEAMROUGE",
}
KEEP_CONTAINS = {
    "© 2026 ZoomGames Studio",
    "FMOD Studio by Firelight Technologies",
    "Fusion Pixel Font by TakWolf",
    "OpenAI Codex,Locus",
    "Suno",
}


def locale_code(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("m_Code", ""))
    return str(value)


def table_collection(name: str) -> str:
    for suffix in ("_zh-CN", "_zh-Hant", "_en"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def control_signature(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text)


def default_direct_classification(source: str) -> tuple[str, str]:
    stripped = source.strip()
    if not stripped:
        return "VISIBLE_KEEP", "빈 표시값"
    if not TRANSLATABLE_PATTERN.search(stripped):
        return "VISIBLE_KEEP", "숫자·기호·서식 전용"
    if stripped in KEEP_EXACT or any(item in source for item in KEEP_CONTAINS):
        return "VISIBLE_KEEP", "이름·상표·저작권 표기"
    if re.fullmatch(r"(?:LV|XP)\.?[0-9./:%kKmM+ -]*", stripped, re.IGNORECASE):
        return "VISIBLE_KEEP", "게임 수치 약어"
    return "VISIBLE_TRANSLATE", "TMP/Text 직렬화 표시 필드"


def main() -> None:
    parser = argparse.ArgumentParser(description="SuperReap Demo 번역 계층별 인벤토리 생성")
    parser.add_argument("--inventory", type=Path, required=True)
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
            collection = table_collection(str(table["name"]))
            locale_tables[(collection, locale_code(table["locale"]))] = {
                "file": file_row["relative_path"],
                **table,
            }

    localization_rows: list[dict[str, Any]] = []
    for (collection, code), table in sorted(locale_tables.items()):
        if code != "en" or table["class"] != "StringTable":
            continue
        translations: dict[str, dict[int, str]] = {}
        for target_code in ("zh-CN", "zh-Hant"):
            target = locale_tables.get((collection, target_code), {})
            translations[target_code] = {
                int(entry["m_Id"]): str(entry.get("m_Localized", ""))
                for entry in target.get("entries", [])
            }
        keys = shared_maps.get(collection, {})
        for index, entry in enumerate(table["entries"]):
            item_id = int(entry["m_Id"])
            source = str(entry.get("m_Localized", ""))
            classification = "VISIBLE_TRANSLATE" if source.strip() else "VISIBLE_KEEP"
            localization_rows.append(
                {
                    "layer": "Localization StringTable",
                    "classification": classification,
                    "table": collection,
                    "table_path_id": int(table["path_id"]),
                    "file": table["file"],
                    "entry_index": index,
                    "id": item_id,
                    "key": keys.get(item_id, ""),
                    "source": source,
                    "zh_cn": translations["zh-CN"].get(item_id, ""),
                    "zh_hant": translations["zh-Hant"].get(item_id, ""),
                    "control_tokens": control_signature(source),
                    "translation": "",
                }
            )

    direct_rows: list[dict[str, Any]] = []
    direct_classes = {"TextMeshPro", "TextMeshProUGUI", "Text"}
    for file_row in report["files"]:
        for row in file_row["strings"]:
            field_name = row["field_path"][-1] if row["field_path"] else ""
            if row["class"] not in direct_classes or field_name not in {"m_text", "m_Text"}:
                continue
            classification, reason = default_direct_classification(str(row["source"]))
            direct_rows.append(
                {
                    "layer": "TMP/Text direct",
                    "classification": classification,
                    "reason": reason,
                    "file": file_row["relative_path"],
                    "path_id": int(row["path_id"]),
                    "class": row["class"],
                    "game_object": row["game_object"],
                    "field_path": row["field_path"],
                    "source": row["source"],
                    "control_tokens": control_signature(str(row["source"])),
                    "translation": "",
                }
            )
    direct_rows.sort(key=lambda item: (item["file"], item["path_id"]))

    text_asset_rows: list[dict[str, Any]] = []
    for file_row in report["files"]:
        for item in file_row["text_assets"]:
            name = str(item["name"])
            if name == "Dialogue.en":
                classification = "VISIBLE_TRANSLATE"
                reason = "영문 대화 CSV"
            elif name in {"Content", "Dialogue.zh-Hant"}:
                classification = "INTERNAL"
                reason = "영문 실행 언어가 참조하지 않는 원본·타 언어 대화"
            else:
                classification = "UNKNOWN"
                reason = "표시 필드 사용처 코드 교차 확인 필요"
            text_asset_rows.append(
                {
                    "layer": "TextAsset",
                    "classification": classification,
                    "reason": reason,
                    "file": file_row["relative_path"],
                    "path_id": int(item["path_id"]),
                    "name": name,
                    "decoded": bool(item["decoded"]),
                    "character_count": len(str(item["text"])),
                    "text": item["text"],
                }
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "localization_entries.json": localization_rows,
        "direct_text_entries.json": direct_rows,
        "text_asset_entries.json": text_asset_rows,
    }
    for name, rows in outputs.items():
        (args.output_dir / name).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )

    unique_direct = defaultdict(list)
    for row in direct_rows:
        unique_direct[str(row["source"])].append(row)
    unique_rows = [
        {
            "source": source,
            "classification": locations[0]["classification"],
            "reason": locations[0]["reason"],
            "occurrences": len(locations),
            "locations": [
                {
                    "file": item["file"],
                    "path_id": item["path_id"],
                    "game_object": item["game_object"],
                }
                for item in locations
            ],
            "translation": "",
        }
        for source, locations in sorted(unique_direct.items(), key=lambda item: item[0])
    ]
    (args.output_dir / "direct_text_unique.json").write_text(
        json.dumps(unique_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    summary = {
        "localization_entries": len(localization_rows),
        "localization_classifications": dict(Counter(item["classification"] for item in localization_rows)),
        "direct_text_locations": len(direct_rows),
        "direct_text_unique": len(unique_rows),
        "direct_text_classifications": dict(Counter(item["classification"] for item in direct_rows)),
        "text_assets": len(text_asset_rows),
        "text_asset_classifications": dict(Counter(item["classification"] for item in text_asset_rows)),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
