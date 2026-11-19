#!/usr/bin/env python3
"""생성한 SuperReap Demo 한글 Unity 자산을 다시 열어 정적 검증한다."""

from __future__ import annotations

import argparse
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import UnityPy
from fontTools.ttLib import TTFont
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

from build_korean_assets import (
    FUSION_BUNDLE_FONT_PATH_ID,
    FUSION_BUNDLE_PATH_ID,
    FUSION_SHARED_FONT_PATH_ID,
    FUSION_SHARED_PATH_ID,
    YARN_LOCALIZATION_COPIES_PER_LOCALE,
    build_dialogue,
    decode_text_asset,
    fusion_pptr,
    is_fusion_font_asset,
    load_json,
    locale_code,
    parse_dialogue,
    parse_yarn_localization,
    script_class,
    table_collection,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patched-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--translation-data", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--font-inventory", type=Path, required=True)
    parser.add_argument("--patch-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--unity-version", default="2022.3.62f3")
    return parser.parse_args()


def pptr_tuple(value: Any) -> tuple[int, int]:
    if not isinstance(value, dict):
        return 0, 0
    return int(value.get("m_FileID", 0)), int(value.get("m_PathID", 0))


def main() -> None:
    args = parse_args()
    localization_rows = load_json(args.translation_data / "localization_entries.json")
    direct_rows = load_json(args.translation_data / "direct_text_entries.json")
    config_audit = load_json(args.translation_data / "config_localization_audit.json")
    localization_map: dict[str, str] = load_json(args.translations_dir / "localization_ko.json")
    direct_map: dict[str, str] = load_json(args.translations_dir / "direct_ko.json")
    dialogue_map: dict[str, str] = load_json(args.translations_dir / "dialogue_ko.json")
    assembly_map: dict[str, str] = load_json(args.translations_dir / "assembly_ko.json")
    font_inventory = load_json(args.font_inventory)
    patch_report = load_json(args.patch_report)

    merged = dict(localization_map)
    merged.update(direct_map)
    table_expected = {
        (str(row["table"]), int(row["id"])): localization_map[str(row["source"])]
        for row in localization_rows
    }
    key_expected = {
        str(row["key"]): localization_map[str(row["source"])] for row in localization_rows
    }
    direct_expected: dict[tuple[str, int], set[tuple[str, str]]] = defaultdict(set)
    direct_expected_count = 0
    for row in direct_rows:
        if row["classification"] != "VISIBLE_TRANSLATE":
            continue
        direct_expected[(str(row["file"]), int(row["path_id"]))].add(
            (str(row["class"]), merged[str(row["source"])])
        )
        direct_expected_count += 1

    config_expected: dict[str, dict[tuple[int, str], str]] = defaultdict(dict)
    for row in config_audit["config_fields"]:
        if row["classification"] != "VISIBLE_TRANSLATE" or row["field"] == "comnent":
            continue
        target = ""
        for key in row["present_localization_keys"]:
            target = key_expected.get(str(key), "")
            if target:
                break
        if not target and row["asset"] == "tbfarmcfg" and row["field"] == "name":
            target = key_expected[f"farm.crop.{row['id']}.name"]
        if not target:
            target = merged[str(row["source"])]
        config_expected[str(row["asset"])][(int(row["record_index"]), str(row["field"]))] = target

    font_files = {str(row["file"]) for row in font_inventory["tmp_text_usages"]}
    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))
    counts: Counter[str] = Counter()
    errors: list[str] = []
    required_chars = set(
        "".join(localization_map.values())
        + "".join(direct_map.values())
        + "".join(dialogue_map.values())
        + "".join(assembly_map.values())
        + "".join(value for rows in config_expected.values() for value in rows.values())
    )
    required_hangul = {char for char in required_chars if "가" <= char <= "힣"}
    legacy_font_codepoints: dict[int, set[int]] = {}
    fusion_font_codepoints: dict[int, set[int]] = {}

    validation_files = {
        *(str(file_row["file"]) for file_row in patch_report["files"]),
        *font_files,
    }
    for relative in sorted(validation_files, key=str.casefold):
        patched_path = args.patched_root / Path(relative)
        path = patched_path if patched_path.is_file() else args.source_root / Path(relative)
        if not path.is_file():
            errors.append(f"수정 파일 누락: {relative}")
            continue
        try:
            if path.suffix.lower() == ".bundle":
                env = UnityPy.load(str(path))
            else:
                # level/resources/shared 자산의 MonoBehaviour 형식 정보는
                # globalgamemanagers.assets에 있으므로 읽기 전용 의존 파일로 함께 연다.
                env = UnityPy.load(str(path), str(args.source_root / "globalgamemanagers.assets"))
            env.typetree_generator = generator
        except Exception as exc:
            errors.append(f"다시 열기 실패: {relative}: {type(exc).__name__}: {exc}")
            continue
        counts["reopened_files"] += 1
        for obj in env.objects:
            if str(getattr(obj.assets_file, "name", "")) == "globalgamemanagers.assets":
                continue
            object_type = obj.type.name
            class_name = script_class(obj) if object_type == "MonoBehaviour" else ""
            key = (relative, int(obj.path_id))
            if object_type == "MonoBehaviour" and class_name == "Localization":
                try:
                    locale_name, keys, values = parse_yarn_localization(obj.get_raw_data())
                    for value in values:
                        expected_value = dialogue_map.get(str(value["key"]))
                        if expected_value != str(value["text"]):
                            errors.append(
                                f"Yarn 대사 값 불일치: {locale_name}:{value['key']}"
                            )
                        else:
                            counts[f"yarn_localization_{locale_name}"] += 1
                    if set(keys) != set(dialogue_map):
                        errors.append(f"Yarn 대사 ID 집합 불일치: {locale_name}")
                except Exception as exc:
                    errors.append(f"Yarn 대사 다시 읽기 실패: {relative}:{obj.path_id}: {exc}")
                continue
            if object_type == "MonoBehaviour" and class_name in {"TextMeshPro", "TextMeshProUGUI", "Text"}:
                try:
                    tree = obj.read_typetree()
                except Exception as exc:
                    errors.append(f"텍스트 다시 읽기 실패: {relative}:{obj.path_id}: {exc}")
                    continue
                field = "m_Text" if class_name == "Text" else "m_text"
                target = str(tree.get(field, ""))
                if (class_name, target) in direct_expected.get(key, set()):
                    counts["direct_text"] += 1
                if class_name == "TextMeshPro" or class_name == "TextMeshProUGUI":
                    if relative in font_files:
                        expected_font = fusion_pptr(obj)
                        if expected_font is None or tree.get("m_fontAsset") != expected_font:
                            errors.append(f"TMP 한글 글꼴 불일치: {relative}:{obj.path_id}")
                        else:
                            counts["tmp_font_refs"] += 1
                elif relative == "resources.assets":
                    counts["legacy_text_objects"] += 1
                continue

            if object_type == "MonoBehaviour" and class_name == "StringTable":
                tree = obj.read_typetree()
                collection = table_collection(str(tree.get("m_Name", "")))
                locale = locale_code(tree.get("m_LocaleId")) or "unknown"
                for entry in tree.get("m_TableData", []):
                    expected = table_expected.get((collection, int(entry.get("m_Id", 0))))
                    if expected is None:
                        continue
                    if str(entry.get("m_Localized", "")) != expected:
                        errors.append(
                            f"StringTable 값 불일치: {relative}:{obj.path_id}:{entry.get('m_Id')}"
                        )
                    else:
                        counts[f"string_table_{locale}"] += 1
                continue

            if object_type == "MonoBehaviour" and class_name == "TMP_FontAsset":
                if not is_fusion_font_asset(obj):
                    continue
                try:
                    tree = obj.read_typetree()
                except Exception as exc:
                    errors.append(f"Fusion TMP 글꼴 다시 읽기 실패: {relative}:{obj.path_id}: {exc}")
                    continue
                if int(tree.get("m_AtlasPopulationMode", -1)) != 1:
                    errors.append(f"Fusion TMP 동적 글꼴 모드 불일치: {relative}:{obj.path_id}")
                if int(tree.get("m_IsMultiAtlasTexturesEnabled", 0)) != 1:
                    errors.append(f"Fusion TMP 다중 아틀라스 비활성: {relative}:{obj.path_id}")
                counts["tmp_fusion_multi_atlas"] += 1
                continue

            if object_type == "TextAsset":
                value = obj.read()
                name = str(getattr(value, "m_Name", ""))
                if name != "Dialogue.en" and name not in config_expected:
                    continue
                text, _ = decode_text_asset(getattr(value, "m_Script", ""))
                if name == "Dialogue.en":
                    _, rows = parse_dialogue(text)
                    for row in rows:
                        if dialogue_map.get(row[1]) != row[2]:
                            errors.append(f"대사 값 불일치: {row[1]}")
                        else:
                            counts["dialogue_rows"] += 1
                else:
                    records = json.loads(text.lstrip("\ufeff"))
                    record_list = [records] if isinstance(records, dict) else records
                    for (index, field), expected in config_expected[name].items():
                        if str(record_list[index][field]) != expected:
                            errors.append(f"설정 값 불일치: {name}:{index}:{field}")
                        else:
                            counts["config_fields"] += 1
                continue

            if object_type == "Font" and relative == "resources.assets" and int(obj.path_id) in {100, 101, 102, 103, 104}:
                value = obj.read()
                data = bytes(getattr(value, "m_FontData", b""))
                font = TTFont(io.BytesIO(data), lazy=True)
                points: set[int] = set()
                for table in font["cmap"].tables:
                    points.update(int(point) for point in table.cmap)
                font.close()
                legacy_font_codepoints[int(obj.path_id)] = points
                counts["legacy_font_data"] += 1

            if object_type == "Font" and int(obj.path_id) in {
                FUSION_SHARED_FONT_PATH_ID,
                FUSION_BUNDLE_FONT_PATH_ID,
            }:
                value = obj.read()
                data = bytes(getattr(value, "m_FontData", b""))
                font = TTFont(io.BytesIO(data), lazy=True)
                points: set[int] = set()
                for table in font["cmap"].tables:
                    points.update(int(point) for point in table.cmap)
                font.close()
                fusion_font_codepoints[int(obj.path_id)] = points
                counts["fusion_source_font_data"] += 1

    expected = {
        "reopened_files": len(validation_files),
        "direct_text": direct_expected_count,
        "dialogue_rows": len(dialogue_map),
        "yarn_localization_en": len(dialogue_map) * YARN_LOCALIZATION_COPIES_PER_LOCALE,
        "yarn_localization_zh-Hans": len(dialogue_map) * YARN_LOCALIZATION_COPIES_PER_LOCALE,
        "yarn_localization_zh-Hant": len(dialogue_map) * YARN_LOCALIZATION_COPIES_PER_LOCALE,
        "config_fields": sum(len(rows) for rows in config_expected.values()),
        "string_table_en": len(localization_rows),
        "string_table_zh-CN": len(localization_rows),
        "string_table_zh-Hant": len(localization_rows),
        "tmp_font_refs": len(font_inventory["tmp_text_usages"]),
        "tmp_fusion_multi_atlas": 2,
        "fusion_source_font_data": 2,
        "legacy_font_data": 5,
    }
    for name, value in expected.items():
        if counts[name] != value:
            errors.append(f"검증 수 불일치 {name}: {counts[name]} / {value}")
    for path_id in (100, 101, 102, 103, 104):
        points = legacy_font_codepoints.get(path_id, set())
        missing_legacy = sorted(char for char in required_hangul if ord(char) not in points)
        if missing_legacy:
            errors.append(
                f"구형 UI 글꼴 {path_id} 한글 글리프 누락: {''.join(missing_legacy[:30])}"
            )
    for path_id in (FUSION_SHARED_FONT_PATH_ID, FUSION_BUNDLE_FONT_PATH_ID):
        points = fusion_font_codepoints.get(path_id, set())
        missing_fusion = sorted(char for char in required_hangul if ord(char) not in points)
        if missing_fusion:
            errors.append(
                f"Fusion TMP 원본 글꼴 {path_id} 한글 글리프 누락: "
                f"{''.join(missing_fusion[:30])}"
            )
    if not any("글리프 누락" in error for error in errors):
        counts["required_hangul_glyphs"] = len(required_hangul)

    report = {
        "schema_version": 1,
        "passed": not errors,
        "summary": dict(counts),
        "expected": expected,
        "errors": errors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
