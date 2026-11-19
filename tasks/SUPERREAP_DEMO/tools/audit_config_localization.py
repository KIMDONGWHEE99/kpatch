#!/usr/bin/env python3
"""게임 설정의 표시 문자열과 StringTable 키를 대조한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TABLE_KEY_BUILDERS = {
    "tbweaponcfg": {
        "name": ("weapon.{id}.name", "skillTree.weapon.{id}.name"),
    },
    "tbweaponlvcfg": {
        "name": ("weaponLv.{id}.name",),
        "desc": ("weaponLv.{id}.desc",),
    },
    "gain_tbequipmentcfg": {
        "name": ("equipment.{id}.name",),
        "desc": ("equipment.{id}.desc",),
        "comment": ("equipment.{id}.comment",),
    },
    "gain_tbtalentcfg": {
        "name": ("talent.{id}.name",),
        "desc": ("talent.{id}.desc",),
        # comnent는 오탈자가 포함된 원본 설정 필드이며 화면 표시에는 사용되지 않는다.
        "comnent": (),
    },
    "gain_tbpointtreecfg": {
        "name": ("skillTree.pointTree.{id}.name",),
        "desc": ("skillTree.pointTree.{id}.desc",),
        "maxdesc": ("skillTree.pointTree.{id}.maxdesc",),
    },
    "tbcropcfg": {
        "name": ("farm.crop.{id}.name", "skillTree.crop.{id}.name"),
    },
    "tbfarmcfg": {
        # 일반 농장 화면은 tbcropcfg 이름을 사용하지만 개발 화면은 이 이름을 직접 표시한다.
        "name": (),
    },
    "tbstagecfg": {
        # 현재 빌드에서는 장면 선택용 내부 데이터지만 사람이 읽을 수 있는 필드라 별도 기록한다.
        "stageName": (),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translation-data", type=Path, required=True)
    parser.add_argument("--unity-inventory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_text_assets(data: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in data if item.get("decoded")}


def main() -> None:
    args = parse_args()
    localization = load_json(args.translation_data / "localization_entries.json")
    text_assets = iter_text_assets(load_json(args.translation_data / "text_asset_entries.json"))
    inventory = load_json(args.unity_inventory)

    game_ui_rows = [row for row in localization if row.get("table") == "gameUI"]
    localized_keys = {row["key"] for row in game_ui_rows}

    shared_game_ui: dict[str, Any] | None = None
    for file_info in inventory["files"]:
        for table in file_info.get("shared_tables", []):
            if table.get("table_collection_name") == "gameUI":
                shared_game_ui = table
                break
        if shared_game_ui:
            break
    if shared_game_ui is None:
        raise RuntimeError("gameUI Shared Data를 찾지 못했습니다.")

    shared_keys = {entry["m_Key"] for entry in shared_game_ui["entries"]}
    field_rows: list[dict[str, Any]] = []
    missing_required_keys: list[dict[str, Any]] = []

    for asset_name, field_map in TABLE_KEY_BUILDERS.items():
        asset = text_assets.get(asset_name)
        if not asset:
            raise RuntimeError(f"설정 TextAsset 누락: {asset_name}")
        records = json.loads(asset["text"].lstrip("\ufeff"))
        if not isinstance(records, list):
            records = [records]
        for index, record in enumerate(records):
            record_id = record.get("id", record.get("stageID", index))
            for field, templates in field_map.items():
                value = record.get(field)
                if not isinstance(value, str) or not value:
                    continue
                expected_keys = [template.format(id=record_id) for template in templates]
                present_keys = [key for key in expected_keys if key in localized_keys]
                missing_keys = [key for key in expected_keys if key not in localized_keys]
                classification = "VISIBLE_TRANSLATE"
                reason = "일반 화면 또는 개발 화면에서 실제 표시되는 설정 필드"
                if asset_name == "tbstagecfg":
                    classification = "INTERNAL"
                    reason = "현재 코드에서 장면 로딩 식별 정보로만 사용"
                row = {
                    "layer": "MonoBehaviour/ScriptableObject config TextAsset",
                    "classification": classification,
                    "asset": asset_name,
                    "record_index": index,
                    "id": record_id,
                    "field": field,
                    "source": value,
                    "expected_localization_keys": expected_keys,
                    "present_localization_keys": present_keys,
                    "missing_localization_keys": missing_keys,
                    "reason": reason,
                    "translation": "",
                }
                field_rows.append(row)
                for key in missing_keys:
                    missing_required_keys.append(
                        {
                            "asset": asset_name,
                            "id": record_id,
                            "field": field,
                            "source": value,
                            "key": key,
                        }
                    )

    report = {
        "summary": {
            "game_ui_localized_rows": len(game_ui_rows),
            "game_ui_localized_unique_keys": len(localized_keys),
            "game_ui_shared_keys": len(shared_keys),
            "shared_keys_missing_from_english_table": len(shared_keys - localized_keys),
            "english_keys_missing_from_shared_data": len(localized_keys - shared_keys),
            "config_display_fields": len(field_rows),
            "config_fields_with_missing_required_keys": sum(
                1 for row in field_rows if row["missing_localization_keys"]
            ),
            "missing_required_key_instances": len(missing_required_keys),
        },
        "shared_keys_missing_from_english_table": sorted(shared_keys - localized_keys),
        "english_keys_missing_from_shared_data": sorted(localized_keys - shared_keys),
        "missing_required_keys": missing_required_keys,
        "config_fields": field_rows,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
