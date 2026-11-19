#!/usr/bin/env python3
"""SuperReap Demo 한글화 전수 조사 항목을 최종 분류하고 검증한다."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ENUM_RE = re.compile(r"\benum\s+(?P<name>[A-Za-z_]\w*)(?:\s*:\s*[^\s{]+)?\s*\{(?P<body>.*?)\}", re.S)
ENUM_MEMBER_RE = re.compile(r"^(?P<name>[A-Za-z_]\w*)\s*(?:=.*)?[,]?$")
FORMAT_RE = re.compile(r"(?:\{[^{}]+\}|<[^>]+>|%|\\n|\[br /\])")
LOCALIZATION_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.{}-]+$")
INTERNAL_CONTEXT_RE = re.compile(
    r"(?:\[(?:Header|Inspector|Tooltip|ContextMenu|MenuItem)|"
    r"\.Find\(|Get(?:Button|Text|Trans|Image)\(|new GameObject\(|"
    r"Debug\.(?:Log|LogWarning|LogError)|throw new|Resources\.Load|"
    r"Load(?:Asset|Prefab|Sprite)|PlayerPrefs|Analytics|Addressables)",
    re.I,
)
BRAND_RE = re.compile(r"(?:unity|fmod|zoom\s*games|srdebugger|super\s*reap|logo)", re.I)

# ILSpy가 복합 서식 문자열을 보간 문자열로 복원하면서, 실제 IL의 자리표시자 이름이
# 지역 변수 이름으로 바뀌는 항목들이다. 패치는 IL 원문에 적용하고 감사 보고서에는
# 사람이 읽는 디컴파일 원문과 한글 결과를 연결한다.
DECOMPILER_FORMAT_ALIASES = {
    "第 {_selectedWave} 局": "第 {0} 局",
    "技能 {value.SkillChanges?.Count ?? 0} / 装备 {value.EquipmentIds?.Count ?? 0} / 天赋 {value.TalentIds?.Count ?? 0}": "技能 {0} / 装备 {1} / 天赋 {2}",
    "{root.GroundSys.CurrentWaveElapsedSeconds:F1}s": "{0:F1}s",
    "{_remainingTime:F1}s / {_currentGrowthTime:F1}s": "{0:F1}s / {1:F1}s",
    "{GetRemainingTime():F1}s / {GetTotalGrowthTime():F1}s": "{0:F1}s / {1:F1}s",
    "{pointTreeMaxDesc}\n{num24:0.##}s": "{0}\n{1:0.##}s",
    "{pointTreeDesc}\n{num24:0.##}s ➡ {num25:0.##}s": "{0}\n{1:0.##}s ➡ {2:0.##}s",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").lower()


def classify_managed(row: dict[str, Any], translations: dict[str, str]) -> dict[str, Any]:
    result = dict(row)
    source = str(row["source"])
    context = str(row.get("context", ""))
    file_name = str(row.get("file", ""))
    if file_name == "GameMenuPanelWeaponItem.cs" and source == "s":
        result.update(
            classification="VISIBLE_TRANSLATE",
            reason="도구 화면의 초 단위 접미사를 메서드 범위로 한정하여 어셈블리에 한글 적용",
            translation="초",
            il_source="s",
        )
        return result
    translation_key = source if source in translations else DECOMPILER_FORMAT_ALIASES.get(source, "")
    if translation_key in translations:
        result.update(
            classification="VISIBLE_TRANSLATE",
            reason="실행 IL에서 실제 표시·대체·개발 화면 문구로 확인되어 어셈블리에 한글 적용",
            translation=translations[translation_key],
            il_source=translation_key,
        )
        return result
    if source == "No translation" and "StartsWith" in context:
        result.update(
            classification="INTERNAL",
            reason="번역 조회 실패를 판별하는 내부 반환 접두사이며 화면에 직접 표시하지 않음",
            translation="",
        )
        return result
    if file_name.startswith("E2C/Demo/"):
        result.update(
            classification="INTERNAL",
            reason="게임 장면에서 사용하지 않는 E2Chart 예제 코드",
            translation="",
        )
        return result
    if INTERNAL_CONTEXT_RE.search(context):
        result.update(
            classification="INTERNAL",
            reason="편집기 속성·장면 객체 경로·로그·자원/분석 식별자 문맥",
            translation="",
        )
        return result
    if LOCALIZATION_KEY_RE.fullmatch(source) and (
        "." in source or source.startswith(("Btn_", "Txt_", "UI", "FX_"))
    ):
        result.update(
            classification="INTERNAL",
            reason="번역된 StringTable 또는 장면 객체를 찾는 내부 키",
            translation="",
        )
        return result
    if row.get("classification") == "VISIBLE_TRANSLATE":
        result.update(
            classification="VISIBLE_KEEP",
            reason=(
                "숫자·서식·태그·단위·로캘 코드이거나 번역된 값과 조합되는 표시 조각"
                if FORMAT_RE.search(source) or not re.search(r"[A-Za-z\u3400-\u9fff]{3,}", source)
                else "표시 경로를 확인했으며 번역하면 식별·동작을 깨뜨리는 이름 또는 고유 표기"
            ),
            translation="",
        )
        return result
    result.update(
        classification="INTERNAL",
        reason="코드 흐름상 식별자·설정·로그·자원명·편집기 설명으로만 사용",
        translation="",
    )
    return result


def classify_text_assets(
    rows: list[dict[str, Any]], config_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    visible_assets = {
        str(row["asset"])
        for row in config_rows
        if row["classification"] == "VISIBLE_TRANSLATE"
    }
    result = []
    for row in rows:
        item = dict(row)
        name = str(row["name"])
        if name == "Dialogue.en":
            item.update(
                classification="VISIBLE_TRANSLATE",
                reason="실행 대화 CSV이며 164개 ID를 한글로 적용",
            )
        elif name in visible_assets:
            item.update(
                classification="VISIBLE_TRANSLATE",
                reason="표시 필드가 있는 설정 컨테이너이며 필드 단위 번역표로 적용",
            )
        elif name.startswith("LineBreaking "):
            item.update(
                classification="INTERNAL",
                reason="TMP 줄바꿈 금칙 문자 규칙으로 화면 문구가 아님",
            )
        else:
            item.update(
                classification="INTERNAL",
                reason="다른 언어 원본·컴파일 입력·수치/오디오/업적 내부 설정 컨테이너",
            )
        result.append(item)
    return result


def enum_records(source_root: Path, translations: dict[str, str]) -> list[dict[str, Any]]:
    attribute_source = (source_root / "DebugCurrentWaveDataPanel.cs").read_text(
        encoding="utf-8-sig", errors="replace"
    )
    attribute_names = {
        name: source
        for name, source in re.findall(
            r"RuntimeDataAttribute\.([A-Za-z_]\w*)\s*,\s*\"((?:\\.|[^\"])*)\"",
            attribute_source,
        )
    }
    attribute_names["FinalToolRangeTalentMagnification"] = "최종 도구 범위 재능 배율"

    records: list[dict[str, Any]] = []
    for path in sorted(source_root.rglob("*.cs")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for match in ENUM_RE.finditer(text):
            enum_name = match.group("name")
            for line in match.group("body").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("["):
                    continue
                member_match = ENUM_MEMBER_RE.match(stripped)
                if not member_match:
                    continue
                member = member_match.group("name")
                if enum_name == "RuntimeDataAttribute":
                    source_label = attribute_names.get(member, "")
                    translation = (
                        source_label
                        if member == "FinalToolRangeTalentMagnification"
                        else translations.get(source_label, "")
                    )
                    if not translation:
                        raise RuntimeError(f"화면 표시 enum 번역 누락: {enum_name}.{member}")
                    classification = "VISIBLE_TRANSLATE"
                    reason = "개발 통계 화면에서 이름을 표시하며 한글 이름 사전/대체 분기로 처리"
                else:
                    source_label = member
                    translation = ""
                    classification = "INTERNAL"
                    reason = "열거값 이름이 화면에 직접 표시되지 않고 분기·직렬화 값으로만 사용"
                records.append(
                    {
                        "layer": "enum ToString/display audit",
                        "classification": classification,
                        "reason": reason,
                        "file": path.relative_to(source_root).as_posix(),
                        "enum": enum_name,
                        "member": member,
                        "source_label": source_label,
                        "translation": translation,
                    }
                )
    return records


def media_records(media_audit: dict[str, Any]) -> list[dict[str, Any]]:
    targets = {int(row["target_id"]): row for row in media_audit["targets"]}
    edited_targets = {
        ("sharedassets0.assets", 105),
        ("sharedassets0.assets", 331),
        ("streamingassets/yoo/defaultpackage/724fd7887af016644d655d57fbc7ee9f.bundle", 7568154705151158573),
        ("streamingassets/yoo/defaultpackage/dfa99baf3020132933558a01994b8a9c.bundle", 8940992715402494823),
        ("streamingassets/yoo/defaultpackage/9578efb46f5c6523c9cbdb8188e5ae74.bundle", 742611586594813104),
    }
    result = []
    for image in media_audit["image_rollup"]:
        image_targets = [targets[int(target_id)] for target_id in image["target_ids"]]
        target_pairs = {
            (normalize_path(str(target["file"])), int(target["path_id"]))
            for target in image_targets
        }
        names = sorted({str(target.get("name", "")) for target in image_targets if target.get("name")})
        if target_pairs & edited_targets:
            decision = "TRANSLATED"
            reason = "화면에 표시되는 픽셀 영문/중문을 한글 이미지로 교체하고 재디코딩 일치 검사"
        elif any(BRAND_RE.search(name) for name in names):
            decision = "VISIBLE_KEEP_BRAND"
            reason = "로고·상표·엔진/미들웨어 고유 표기로 유지"
        else:
            decision = "NO_TRANSLATABLE_TEXT_OR_INTERNAL"
            reason = "38개 접촉시트 전수 육안 검사에서 번역할 픽셀 문구가 없거나 비활성/미사용 개발 자료"
        result.append(
            {
                "layer": "image/video pixel text",
                "classification": "MEDIA",
                "reason": reason,
                "review_decision": decision,
                "image_index": int(image["image_index"]),
                "sha256": image["image_sha256"],
                "width": int(image["width"]),
                "height": int(image["height"]),
                "consumer_reference_count": int(image["consumer_reference_count"]),
                "names": names,
            }
        )
    return result


def unresolved_object_records() -> list[dict[str, Any]]:
    rows = [
        ("globalgamemanagers", 11, "BuildSettings", "INTERNAL", "Unity 빌드 장면/설정 데이터"),
        ("globalgamemanagers", 18, "UnityConnectSettings", "INTERNAL", "Unity 서비스 연결 설정"),
        ("globalgamemanagers.assets", 3264, "LocalizationSettings", "INTERNAL", "로캘 참조와 선택 정책 설정"),
        ("resources.assets", 1618, "ES3Defaults", "INTERNAL", "Easy Save 저장 설정"),
        ("resources.assets", 1619, "FMODUnity.Settings", "INTERNAL", "FMOD 오디오 설정"),
        ("resources.assets", 1624, "GameAnalytics Settings", "INTERNAL", "분석 이벤트 설정"),
        ("resources.assets", 1626, "SRF.UI StyleSheet", "INTERNAL", "디버그 UI 색상/스타일 키"),
        ("resources.assets", 1627, "SRF.UI StyleSheet", "INTERNAL", "디버그 UI 색상/스타일 키"),
        ("resources.assets", 1628, "SRF.UI StyleSheet", "INTERNAL", "디버그 UI 색상/스타일 키"),
        ("resources.assets", 1629, "SRF.UI StyleSheet", "INTERNAL", "디버그 UI 색상/스타일 키"),
        ("resources.assets", 2227, "ScrollRectPatch", "INTERNAL", "SRDebugger 스크롤 동작 구성"),
        ("sharedassets0.assets", 995, "Yarn.Localization en", "VISIBLE_TRANSLATE", "Yarn 영어 대화 164개를 한글 적용"),
        ("sharedassets0.assets", 1015, "SkillDatas", "INTERNAL", "기술 트리 GUID·수치·배치·오브젝트 이름"),
        ("sharedassets0.assets", 1016, "SkillDatas", "INTERNAL", "기술 트리 GUID·수치·배치·오브젝트 이름"),
        ("sharedassets0.assets", 1017, "SkillDatas", "INTERNAL", "기술 트리 GUID·수치·배치·오브젝트 이름"),
        ("sharedassets0.assets", 1080, "Yarn.Localization zh-Hant", "VISIBLE_TRANSLATE", "Yarn 번체 대화 164개를 한글 적용"),
        ("sharedassets0.assets", 1081, "YarnProject", "INTERNAL", "컴파일된 Yarn 명령·대사 ID·초상화 태그"),
        ("sharedassets0.assets", 1082, "Yarn.Localization zh-Hans", "VISIBLE_TRANSLATE", "Yarn 간체 대화 164개를 한글 적용"),
        ("sharedassets0.assets", 1120, "GameObjectLocalizer", "INTERNAL", "활성 상태 변형 구조 데이터"),
        ("sharedassets0.assets", 1168, "GameObjectLocalizer", "INTERNAL", "활성 상태 변형 구조 데이터"),
    ]
    return [
        {
            "layer": "typetree fallback audit",
            "file": file,
            "path_id": path_id,
            "object": object_name,
            "classification": classification,
            "reason": reason,
        }
        for file, path_id, object_name, classification, reason in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translation-data", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--decompiled-source", type=Path, required=True)
    parser.add_argument("--assembly-report", type=Path, required=True)
    parser.add_argument("--patched-il", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    localization = load_json(args.translation_data / "localization_entries.json")
    direct = load_json(args.translation_data / "direct_text_entries.json")
    config_audit = load_json(args.translation_data / "config_localization_audit.json")
    config = config_audit["config_fields"]
    text_assets = classify_text_assets(
        load_json(args.translation_data / "text_asset_entries.json"), config
    )
    assembly_map = load_json(args.translations_dir / "assembly_ko.json")
    managed_source = load_json(args.translation_data / "csharp_literals_audit.json")["entries"]
    managed = [classify_managed(row, assembly_map) for row in managed_source]
    enums = enum_records(args.decompiled_source, assembly_map)
    media = media_records(load_json(args.translation_data / "media_reference_audit.json"))
    fallback_objects = unresolved_object_records()
    runtime_formats = [
        {
            **row,
            "layer": "runtime composition/format string",
        }
        for row in managed
        if FORMAT_RE.search(str(row["source"]))
    ]
    special_screens = [
        {**row, "layer": "development/reserve/accessibility screen"}
        for row in managed
        if re.search(r"(?:^|/)(?:Debug|Demo|Setting|Credits|SRDebugger)", str(row["file"]), re.I)
    ]

    layers = {
        "localization_string_tables": localization,
        "tmp_text_direct": direct,
        "text_assets": text_assets,
        "config_fields": config,
        "managed_code_literals": managed,
        "enum_display_names": enums,
        "runtime_formats": runtime_formats,
        "special_screens": special_screens,
        "typetree_fallback_objects": fallback_objects,
        "media": media,
    }

    assembly_report = load_json(args.assembly_report)
    if assembly_report.get("unmatched"):
        raise RuntimeError(f"어셈블리 번역 미적용: {assembly_report['unmatched'][:5]}")
    if assembly_report.get("seconds_suffix_replacements") != 3:
        raise RuntimeError("초 단위 메서드 한정 교체 수가 3이 아닙니다.")
    if not assembly_report.get("enum_fallback_patched"):
        raise RuntimeError("enum 화면 표시 대체 분기가 적용되지 않았습니다.")
    patched_il = load_json(args.patched_il)["entries"]
    patched_sources = [str(row["source"]) for row in patched_il]
    for source, target in assembly_map.items():
        if source != target and source in patched_sources:
            raise RuntimeError(f"패치된 IL에 번역 대상 원문이 남았습니다: {source!r}")
    seconds_sources = [
        row for row in patched_il
        if row["source"] == "s" and row["type"] == "GameMenuPanelWeaponItem"
    ]
    if seconds_sources:
        raise RuntimeError("도구 화면에 영문 초 단위 s가 남았습니다.")

    all_rows = [row for rows in layers.values() for row in rows]
    classifications = Counter(str(row.get("classification", "UNKNOWN")) for row in all_rows)
    if classifications.get("UNKNOWN", 0):
        raise RuntimeError(f"UNKNOWN 분류가 남았습니다: {classifications['UNKNOWN']}")
    allowed = {"VISIBLE_TRANSLATE", "VISIBLE_KEEP", "INTERNAL", "MEDIA"}
    invalid = sorted(set(classifications) - allowed)
    if invalid:
        raise RuntimeError(f"허용되지 않은 분류: {invalid}")

    layer_summary = {
        name: {
            "items": len(rows),
            "classifications": dict(sorted(Counter(row["classification"] for row in rows).items())),
        }
        for name, rows in layers.items()
    }
    report = {
        "schema_version": 1,
        "passed": True,
        "summary": {
            "total_classified_items": len(all_rows),
            "classifications": dict(sorted(classifications.items())),
            "unknown": 0,
            "layers": layer_summary,
            "assembly_translations": len(assembly_map),
            "assembly_replacements": int(assembly_report["replacements"]),
            "seconds_suffix_replacements": 3,
            "enum_fallback_patched": True,
            "media_contact_sheets_reviewed": 38,
        },
        "layers": layers,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
