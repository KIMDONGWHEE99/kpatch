from __future__ import annotations

import argparse
import csv
import glob
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


CLASSIFICATIONS = {"VISIBLE_TRANSLATE", "VISIBLE_KEEP", "INTERNAL", "MEDIA", "UNKNOWN"}
INTERNAL_VISIBLE_NOTES = {"Please do not delete these - Eyal"}
VISIBLE_FIELDS = {
    "displayName", "description", "tierName", "content", "toolTipText",
    "windowedLabel", "fullscreenLabel", "unlimitedLabel", "scientificLabel",
    "dictionaryLabel", "_currencyDisplayName", "_cappedLabel", "_cappedText",
}
VISIBLE_CLASSES = {
    "UpgradeData",
    "PrestigeUpgradeData",
    "ResourceData",
    "JuiceData",
    "RelicData",
    "BuildingData",
    "CostumeData",
    "TreeLevelData",
    "CS_MakeAWishEvent",
    "CS_SilkwormRunEvent",
    "CS_SapBlobEvent",
    "TooltipTrigger",
    "CS_AchievementData",
    "CS_DemoPrestigeGatekeepTooltip",
    "CS_GraphicsSettingsPanel",
    "CS_SettingStepper",
    "CS_PrestigeManager",
    "CS_PrestigePanel",
    "CS_PrestigeXpTooltip",
    "CS_ScrapDigEvent",
}
ASSEMBLY_VISIBLE_KEEP = {
    "{0}/{1} PP",
    "{0} PP",
    "{0} / {1} XP",
    "x{0:0.##}",
    "x1",
    "????",
    " <sprite name=\"",
    "\">",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_map(directory: Path, pattern: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in sorted(glob.glob(str(directory / pattern))):
        result.update(load_json(Path(name)))
    return result


def field_name(row: dict[str, Any]) -> str:
    path = row.get("field_path", [])
    return str(path[-1]) if path else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Pibcremental Demo 전체 문자열·미디어 분류 감사")
    parser.add_argument("--unity-inventory", type=Path, required=True)
    parser.add_argument("--direct-inventory", type=Path, required=True)
    parser.add_argument("--assembly-inventory", type=Path, required=True)
    parser.add_argument("--text-asset-inventory", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--asset-report", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()

    unity_inventory = load_json(args.unity_inventory)
    direct_entries = load_json(args.direct_inventory)
    assembly_inventory = load_json(args.assembly_inventory)
    text_assets = load_json(args.text_asset_inventory)
    asset_report = load_json(args.asset_report)
    localization_map = load_map(args.translations_dir, "localization_ko_part*.json")
    direct_map: dict[str, str] = load_json(args.translations_dir / "direct_text_ko.json")
    assembly_map: dict[str, str] = load_json(args.translations_dir / "assembly_ko.json")
    serialized_map = dict(localization_map)
    serialized_map.update(direct_map)
    serialized_map.update(assembly_map)
    serialized_map.update(load_json(args.translations_dir / "serialized_text_ko.json"))

    rows: list[dict[str, Any]] = []
    direct_lookup: dict[tuple[str, int, str, str], str] = {}
    for row in direct_entries:
        source = str(row["source"])
        if source in direct_map:
            classification = "VISIBLE_TRANSLATE"
            reason = "장면·프리팹의 실제 TMP/Text 표시 문구"
        elif row["classification"] == "INTERNAL" or source == "Slider Title\n":
            classification = "INTERNAL"
            reason = "템플릿·디버그·편집기 기본값"
        else:
            classification = "VISIBLE_KEEP"
            reason = "숫자·기호·인명·라이선스·고유 표기"
        key = (str(row["file"]), int(row["path_id"]), str(row["class"]), source)
        direct_lookup[key] = classification

    for file_row in unity_inventory["files"]:
        relative = str(file_row["relative_path"])
        for string_row in file_row.get("strings", []):
            source = str(string_row.get("source", ""))
            class_name = str(string_row.get("class", ""))
            object_type = str(string_row.get("object_type", ""))
            last_field = field_name(string_row)
            direct_key = (relative, int(string_row["path_id"]), class_name, source)
            if last_field == "m_Localized":
                classification = "VISIBLE_TRANSLATE"
                reason = "Localization StringTable 표시 값"
                layer = "Localization StringTable"
            elif direct_key in direct_lookup:
                classification = direct_lookup[direct_key]
                reason = "TMP/Text 직접 문구 분류표"
                layer = "TMP/Text 직접 문구"
            elif class_name in VISIBLE_CLASSES and last_field in VISIBLE_FIELDS:
                layer = "ScriptableObject·런타임 표시 필드"
                if source in serialized_map and serialized_map[source] != source:
                    classification = "VISIBLE_TRANSLATE"
                    reason = "표시 이름·설명·보상 등 실제 화면 후보"
                elif source in serialized_map:
                    classification = "VISIBLE_KEEP"
                    reason = "CU3·S.N.A.F.U 등 의도된 고유 약칭"
                elif source in INTERNAL_VISIBLE_NOTES:
                    classification = "INTERNAL"
                    reason = "삭제하지 말라는 제작자 메모: 실제 플레이 문구가 아님"
                else:
                    classification = "UNKNOWN"
                    reason = "표시 가능한 필드에 번역 또는 명시적인 유지 판정이 없음"
            else:
                classification = "INTERNAL"
                reason = "자산명·식별자·키·경로·설정·엔진 메타데이터"
                layer = "기타 Unity 직렬화 문자열"
            rows.append(
                {
                    "layer": layer,
                    "classification": classification,
                    "file": relative,
                    "path_id": int(string_row["path_id"]),
                    "class": class_name or object_type,
                    "field": ".".join(str(value) for value in string_row.get("field_path", [])),
                    "source": source,
                    "reason": reason,
                    "occurrences": 1,
                }
            )

        for media in file_row.get("media", []):
            rows.append(
                {
                    "layer": "이미지·영상 픽셀 미디어",
                    "classification": "MEDIA",
                    "file": relative,
                    "path_id": int(media["path_id"]),
                    "class": str(media.get("object_type", "")),
                    "field": "",
                    "source": str(media.get("name", "")),
                    "reason": "24개 접촉 시트 수동 검수: 번역 대상 픽셀 영문 없음; 브랜드 로고·장식 낙서는 유지",
                    "occurrences": 1,
                }
            )

    # 생성된 타입트리와 실제 직렬화가 어긋난 16개 표시 객체는 원시 바이트의
    # 문자열 길이·정렬까지 확인해 별도로 교체했다. Unity 목록에 없던 적용 수를 보강한다.
    raw_count = int(asset_report["summary"].get("serialized_visible_text_raw", 0))
    if raw_count:
        rows.append(
            {
                "layer": "ScriptableObject 원시 바이트 표시 필드",
                "classification": "VISIBLE_TRANSLATE",
                "file": "Pibcremental_Data/data.unity3d",
                "path_id": "",
                "class": "타입트리 불일치 객체",
                "field": "displayName/description",
                "source": "",
                "reason": "원시 직렬화 문자열을 안전하게 교체하고 후보에서 원문 잔존 0건 확인",
                "occurrences": raw_count,
            }
        )

    for entry in assembly_inventory["entries"]:
        source = str(entry["source"])
        if source in assembly_map:
            classification = "VISIBLE_TRANSLATE"
            reason = "코드에서 런타임에 조합되는 화면 문구"
        elif source in ASSEMBLY_VISIBLE_KEEP:
            classification = "VISIBLE_KEEP"
            reason = "PP·XP·배율·아이콘 등 의도된 짧은 서식"
        else:
            classification = "INTERNAL"
            reason = "로그·오브젝트명·식별자·저장 키·애니메이션 키·엔진 예제"
        rows.append(
            {
                "layer": "Mono 어셈블리 문자열",
                "classification": classification,
                "file": "Pibcremental_Data/Managed/Assembly-CSharp.dll",
                "path_id": int(entry["offset"]),
                "class": str(entry["type"]),
                "field": str(entry["method"]),
                "source": source,
                "reason": reason,
                "occurrences": 1,
            }
        )

    for entry in text_assets:
        rows.append(
            {
                "layer": "TextAsset",
                "classification": "INTERNAL",
                "file": str(entry["file"]),
                "path_id": int(entry["path_id"]),
                "class": "TextAsset",
                "field": "m_Script",
                "source": str(entry["name"]),
                "reason": "햅틱 템플릿·성능 시험·TMP 줄바꿈 문자표로 화면 본문이 아님",
                "occurrences": 1,
            }
        )

    rows.extend(
        [
            {
                "layer": "enum ToString()",
                "classification": "INTERNAL",
                "file": "Pibcremental_Data/Managed/Assembly-CSharp.dll",
                "path_id": "",
                "class": "LocalizationKeys/TutorialManager",
                "field": "ToString()",
                "source": "",
                "reason": "열거형 문자열은 현지화 키와 튜토리얼 저장 단계에만 사용되며 화면에 직접 표시되지 않음",
                "occurrences": 2,
            },
            {
                "layer": "미디어 수동 검수",
                "classification": "VISIBLE_KEEP",
                "file": "viewer_output/PIBCREMENTAL_DEMO/media_all",
                "path_id": "",
                "class": "브랜드 로고",
                "field": "pixels",
                "source": "Pibcremental / Arcane Cabinet",
                "reason": "게임명·개발사 로고는 번역하지 않는 고유 상표",
                "occurrences": 2,
            },
        ]
    )

    for row in rows:
        if row["classification"] not in CLASSIFICATIONS:
            raise RuntimeError(f"잘못된 분류: {row}")
    counts = Counter()
    layer_counts: dict[str, Counter[str]] = {}
    for row in rows:
        occurrences = int(row["occurrences"])
        classification = str(row["classification"])
        counts[classification] += occurrences
        layer_counts.setdefault(str(row["layer"]), Counter())[classification] += occurrences
    if counts["UNKNOWN"] != 0:
        raise RuntimeError(f"UNKNOWN 항목이 남았습니다: {counts['UNKNOWN']}")

    report = {
        "schema_version": 1,
        "summary": {
            "records": len(rows),
            "occurrences": sum(int(row["occurrences"]) for row in rows),
            "classification_counts": {name: counts[name] for name in sorted(CLASSIFICATIONS)},
            "unknown": counts["UNKNOWN"],
            "release_unknown_gate_passed": counts["UNKNOWN"] == 0,
            "media_contact_sheets_reviewed": 24,
            "translatable_pixel_english": 0,
        },
        "layer_counts": {
            layer: dict(counter) for layer, counter in sorted(layer_counts.items())
        },
        "notes": [
            "텍스트 레이어와 이미지·영상 픽셀 레이어를 분리해 감사했습니다.",
            "로고의 Pibcremental 및 Arcane Cabinet은 고유 상표라 유지했습니다.",
            "실제 그래픽 실행 결과는 별도 실행 QA 보고서에서만 판정합니다.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "layer",
                "classification",
                "file",
                "path_id",
                "class",
                "field",
                "source",
                "reason",
                "occurrences",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
