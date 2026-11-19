from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


TOKEN_PATTERN = re.compile(r"<[^>]+>|\{[^{}]+\}|\[[^\[\]]+\]")
DATA_RELATIVE = Path("Pibcremental_Data/data.unity3d")
DEFAULT_FONT_RELATIVE = Path("Pibcremental_Data/Resources/unity default resources")
AA_RELATIVE = Path("Pibcremental_Data/StreamingAssets/aa/StandaloneWindows64")
ENGLISH_BUNDLE = "localization-string-tables-english(en)_assets_all.bundle"
GERMAN_BUNDLE = "localization-string-tables-german(de)_assets_all.bundle"
LOCALES_BUNDLE = "localization-locales_assets_all.bundle"
VISIBLE_SERIALIZED_FIELDS = {
    "UpgradeData": {"displayName", "description"},
    "PrestigeUpgradeData": {"displayName", "description"},
    "ResourceData": {"displayName", "description"},
    "JuiceData": {"displayName", "description"},
    "RelicData": {"displayName", "description"},
    "BuildingData": {"displayName", "description"},
    "CostumeData": {"displayName", "description"},
    "TreeLevelData": {"displayName", "description"},
    "CS_MakeAWishEvent": {"tierName"},
    "CS_SilkwormRunEvent": {"tierName"},
    "CS_SapBlobEvent": {"tierName"},
    "TooltipTrigger": {"content"},
    "CS_AchievementData": {"displayName", "description"},
    "CS_DemoPrestigeGatekeepTooltip": {"toolTipText"},
    "CS_GraphicsSettingsPanel": {"windowedLabel", "fullscreenLabel"},
    "CS_SettingStepper": {"unlimitedLabel", "scientificLabel", "dictionaryLabel"},
    "CS_PrestigeManager": {"_currencyDisplayName"},
    "CS_PrestigePanel": {"_cappedLabel"},
    "CS_PrestigeXpTooltip": {"_cappedText"},
    "CS_ScrapDigEvent": {"tierName"},
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_localization_map(directory: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(directory.glob("localization_ko_part*.json")):
        part: dict[str, str] = load_json(path)
        duplicate = set(result) & set(part)
        if duplicate:
            raise RuntimeError(f"번역 키가 중복되었습니다: {path.name}: {sorted(duplicate)[:3]}")
        result.update(part)
    if not result:
        raise RuntimeError("StringTable 번역 파일을 찾지 못했습니다.")
    return result


def check_tokens(source: str, target: str, label: str) -> None:
    if Counter(TOKEN_PATTERN.findall(source)) != Counter(TOKEN_PATTERN.findall(target)):
        raise RuntimeError(f"태그·자리표시자 불일치: {label}: {source!r} -> {target!r}")
    if source.count("\n") != target.count("\n"):
        raise RuntimeError(f"줄바꿈 개수 불일치: {label}: {source!r} -> {target!r}")
    if source.count("\u2028") != target.count("\u2028"):
        raise RuntimeError(f"줄 구분자 개수 불일치: {label}: {source!r} -> {target!r}")


def script_class(obj: Any) -> str:
    try:
        head = obj.parse_monobehaviour_head()
        return str(head.m_Script.deref_parse_as_object().m_ClassName)
    except Exception:
        return ""


def save_environment(env: Any) -> bytes:
    try:
        return env.file.save(packer="original")
    except TypeError:
        return env.file.save()


def aligned_string_blob(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded + b"\x00" * ((-len(encoded)) % 4)


def patch_visible_fields(
    tree: dict[str, Any],
    fields: set[str],
    localization_map: dict[str, str],
    label: str,
) -> int:
    changed = 0

    def walk(value: Any, path: list[str]) -> None:
        nonlocal changed
        if isinstance(value, dict):
            for field, child in value.items():
                current_path = [*path, str(field)]
                if field in fields and isinstance(child, str) and child in localization_map:
                    target_text = localization_map[child]
                    check_tokens(child, target_text, f"{label}:{'.'.join(current_path)}")
                    value[field] = target_text
                    changed += 1
                else:
                    walk(child, current_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, [*path, str(index)])

    walk(tree, [])
    return changed


def patch_failed_visible_object(
    obj: Any,
    localization_map: dict[str, str],
    label: str,
) -> int:
    raw = obj.get_raw_data()
    changed = 0
    for source_text, target_text in localization_map.items():
        old = aligned_string_blob(source_text)
        occurrences = raw.count(old)
        if occurrences == 0:
            continue
        check_tokens(source_text, target_text, label)
        raw = raw.replace(old, aligned_string_blob(target_text))
        changed += occurrences
    if changed:
        obj.set_raw_data(raw)
    return changed


def write_output(
    source: Path,
    relative: Path,
    output_root: Path,
    output_bytes: bytes,
    changes: dict[str, int],
) -> dict[str, Any]:
    output = output_root / relative
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(output_bytes)
    source_bytes = source.read_bytes()
    return {
        "file": relative.as_posix(),
        "source_size": len(source_bytes),
        "source_sha256": sha256(source_bytes),
        "output_size": len(output_bytes),
        "output_sha256": sha256(output_bytes),
        "changes": changes,
    }


def locale_code(tree: dict[str, Any]) -> str:
    value = tree.get("m_LocaleId", tree.get("m_Identifier", {}))
    return str(value.get("m_Code", "")) if isinstance(value, dict) else str(value)


def patch_data_bundle(
    source: Path,
    output_root: Path,
    direct_map: dict[str, str],
    localization_map: dict[str, str],
    generator: TypeTreeGenerator,
) -> tuple[dict[str, Any], Counter[str]]:
    env = UnityPy.load(str(source))
    env.typetree_generator = generator
    counts: Counter[str] = Counter()
    errors: list[str] = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        class_name = script_class(obj)
        if class_name not in {
            "TextMeshPro",
            "TextMeshProUGUI",
            "Text",
            "TMP_FontAsset",
            *VISIBLE_SERIALIZED_FIELDS.keys(),
        }:
            continue
        try:
            tree = obj.read_typetree()
            changed = False
            if class_name in {"TextMeshPro", "TextMeshProUGUI"}:
                source_text = str(tree.get("m_text", ""))
                if source_text in direct_map:
                    target_text = direct_map[source_text]
                    check_tokens(source_text, target_text, f"{obj.assets_file.name}:{obj.path_id}")
                    tree["m_text"] = target_text
                    counts["direct_text"] += 1
                    changed = True
            elif class_name == "Text":
                source_text = str(tree.get("m_Text", ""))
                if source_text in direct_map:
                    target_text = direct_map[source_text]
                    check_tokens(source_text, target_text, f"{obj.assets_file.name}:{obj.path_id}")
                    tree["m_Text"] = target_text
                    counts["direct_text"] += 1
                    changed = True
            elif class_name in VISIBLE_SERIALIZED_FIELDS:
                changed_fields = patch_visible_fields(
                    tree,
                    VISIBLE_SERIALIZED_FIELDS[class_name],
                    localization_map,
                    f"{obj.assets_file.name}:{obj.path_id}",
                )
                if changed_fields:
                    counts["serialized_visible_text"] += changed_fields
                    changed = True
            if changed:
                obj.save_typetree(tree)
        except Exception as exc:
            if class_name in VISIBLE_SERIALIZED_FIELDS:
                changed_fields = patch_failed_visible_object(
                    obj,
                    localization_map,
                    f"{obj.assets_file.name}:{obj.path_id}",
                )
                if changed_fields:
                    counts["serialized_visible_text_raw"] += changed_fields
                    continue
            errors.append(f"{obj.assets_file.name}:{obj.path_id} {class_name}: {type(exc).__name__}: {exc}")
    if errors:
        raise RuntimeError("data.unity3d 패치 오류:\n" + "\n".join(errors[:20]))
    output_bytes = save_environment(env)
    row = write_output(source, DATA_RELATIVE, output_root, output_bytes, dict(counts))
    return row, counts


def patch_default_font(source: Path, output_root: Path, font_data: bytes) -> dict[str, Any]:
    env = UnityPy.load(str(source))
    target = None
    for obj in env.objects:
        if obj.type.name == "Font" and int(obj.path_id) == 10102:
            target = obj
            break
    if target is None:
        raise RuntimeError("LegacyRuntime 글꼴 자산을 찾지 못했습니다.")
    tree = target.read_typetree()
    if str(tree.get("m_Name", "")) != "LegacyRuntime":
        raise RuntimeError(f"기본 글꼴 이름이 예상과 다릅니다: {tree.get('m_Name')}")
    tree["m_FontData"] = list(font_data)
    tree["m_FontNames"] = ["Noto Sans KR"]
    target.save_typetree(tree)
    output_bytes = save_environment(env)
    return write_output(
        source,
        DEFAULT_FONT_RELATIVE,
        output_root,
        output_bytes,
        {"legacy_font_data": 1, "font_bytes": len(font_data)},
    )


def find_string_table(env: Any, expected_locale: str) -> tuple[Any, dict[str, Any]]:
    found: list[tuple[Any, dict[str, Any]]] = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if "m_TableData" in tree and locale_code(tree) == expected_locale:
            found.append((obj, tree))
    if len(found) != 1:
        raise RuntimeError(f"{expected_locale} StringTable 수가 예상과 다릅니다: {len(found)}")
    return found[0]


def patch_localization_bundles(
    game_root: Path,
    output_root: Path,
    localization_map: dict[str, str],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    english_relative = AA_RELATIVE / ENGLISH_BUNDLE
    english_source = game_root / english_relative
    english_env = UnityPy.load(str(english_source))
    english_obj, english_tree = find_string_table(english_env, "en")
    english_data = english_tree.get("m_TableData", [])
    if len(english_data) != 2093:
        raise RuntimeError(f"영어 StringTable 항목 수가 예상과 다릅니다: {len(english_data)}")
    translated_entries: list[dict[str, Any]] = []
    for index, entry in enumerate(english_data):
        source_text = str(entry.get("m_Localized", ""))
        if source_text not in localization_map:
            raise RuntimeError(f"StringTable 번역 누락: {index}: {source_text!r}")
        target_text = localization_map[source_text]
        check_tokens(source_text, target_text, f"StringTable:en:{entry.get('m_Id')}")
        entry["m_Localized"] = target_text
        translated_entries.append(copy.deepcopy(entry))
        counts["string_table_en"] += 1
    english_obj.save_typetree(english_tree)
    rows.append(
        write_output(
            english_source,
            english_relative,
            output_root,
            save_environment(english_env),
            {"string_table_en": counts["string_table_en"]},
        )
    )

    german_relative = AA_RELATIVE / GERMAN_BUNDLE
    german_source = game_root / german_relative
    german_env = UnityPy.load(str(german_source))
    german_obj, german_tree = find_string_table(german_env, "de")
    old_german_count = len(german_tree.get("m_TableData", []))
    german_tree["m_TableData"] = copy.deepcopy(translated_entries)
    german_obj.save_typetree(german_tree)
    counts["string_table_de"] = len(translated_entries)
    rows.append(
        write_output(
            german_source,
            german_relative,
            output_root,
            save_environment(german_env),
            {
                "string_table_de_old": old_german_count,
                "string_table_de_new": len(translated_entries),
            },
        )
    )

    locales_relative = AA_RELATIVE / LOCALES_BUNDLE
    locales_source = game_root / locales_relative
    locales_env = UnityPy.load(str(locales_source))
    locale_names = {"en": "한국어 (영어)", "de": "한국어 (독일어)"}
    changed_locales = 0
    for obj in locales_env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        code = locale_code(tree)
        if code not in locale_names:
            continue
        tree["m_Name"] = locale_names[code]
        tree["m_LocaleName"] = locale_names[code]
        obj.save_typetree(tree)
        changed_locales += 1
    if changed_locales != 2:
        raise RuntimeError(f"로케일 표시 이름 적용 수가 예상과 다릅니다: {changed_locales}/2")
    counts["locale_names"] = changed_locales
    rows.append(
        write_output(
            locales_source,
            locales_relative,
            output_root,
            save_environment(locales_env),
            {"locale_names": changed_locales},
        )
    )
    return rows, counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Pibcremental Demo 한글 자산 빌드")
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--direct-inventory", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--overlay-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--unity-version", default="6000.4.0f1")
    args = parser.parse_args()

    localization_map = load_localization_map(args.translations_dir)
    direct_map: dict[str, str] = load_json(args.translations_dir / "direct_text_ko.json")
    serialized_map = dict(localization_map)
    serialized_map.update(direct_map)
    serialized_map.update(load_json(args.translations_dir / "assembly_ko.json"))
    serialized_map.update(load_json(args.translations_dir / "serialized_text_ko.json"))
    direct_entries = load_json(args.direct_inventory)
    expected_direct = sum(1 for row in direct_entries if str(row["source"]) in direct_map)
    if len(localization_map) != 1183:
        raise RuntimeError(f"StringTable 고유 번역 수가 예상과 다릅니다: {len(localization_map)}/1183")
    for source_text, target_text in direct_map.items():
        check_tokens(source_text, target_text, f"direct:{source_text}")

    managed_dir = args.game_root / "Pibcremental_Data/Managed"
    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(managed_dir))
    report_rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()

    data_row, data_counts = patch_data_bundle(
        args.game_root / DATA_RELATIVE,
        args.overlay_root,
        direct_map,
        serialized_map,
        generator,
    )
    report_rows.append(data_row)
    totals.update(data_counts)
    if totals["direct_text"] != expected_direct:
        raise RuntimeError(f"직접 문구 적용 수 불일치: {totals['direct_text']}/{expected_direct}")

    font_data = args.font.read_bytes()
    font_row = patch_default_font(
        args.game_root / DEFAULT_FONT_RELATIVE,
        args.overlay_root,
        font_data,
    )
    report_rows.append(font_row)
    totals["legacy_font_data"] = 1
    totals["font_bytes"] = len(font_data)

    localization_rows, localization_counts = patch_localization_bundles(
        args.game_root,
        args.overlay_root,
        localization_map,
    )
    report_rows.extend(localization_rows)
    totals.update(localization_counts)

    report = {
        "schema_version": 1,
        "files": report_rows,
        "summary": {
            "modified_files": len(report_rows),
            "localization_unique": len(localization_map),
            "direct_unique": len(direct_map),
            "expected_direct_occurrences": expected_direct,
            **dict(totals),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
