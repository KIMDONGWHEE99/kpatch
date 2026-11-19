from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy
from fontTools.ttLib import TTFont
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


TOKEN_PATTERN = re.compile(r"<[^>]+>|\{[^{}]+\}|\[[^\[\]]+\]")
DATA_RELATIVE = Path("Pibcremental_Data/data.unity3d")
DEFAULT_FONT_RELATIVE = Path("Pibcremental_Data/Resources/unity default resources")
AA_RELATIVE = Path("Pibcremental_Data/StreamingAssets/aa/StandaloneWindows64")
ENGLISH_BUNDLE = "localization-string-tables-english(en)_assets_all.bundle"
GERMAN_BUNDLE = "localization-string-tables-german(de)_assets_all.bundle"
LOCALES_BUNDLE = "localization-locales_assets_all.bundle"
CATALOG_RELATIVE = Path("Pibcremental_Data/StreamingAssets/aa/catalog.bin")
ASSEMBLY_RELATIVE = Path("Pibcremental_Data/Managed/Assembly-CSharp.dll")
TMP_FONT_EXPECTED = {
    ("sharedassets0.assets", 940): (0, 0, 0, 0),
    ("sharedassets1.assets", 7057): (0, 0, 0, 0),
    ("sharedassets1.assets", 7058): (0, 0, 0, 0),
    ("resources.assets", 1568): (1, 0, 0, 120),
    ("resources.assets", 1569): (1, 0, 0, 117),
    ("resources.assets", 1570): (1, 0, 0, 119),
    ("resources.assets", 1571): (1, 0, 0, 122),
    ("resources.assets", 1572): (1, 0, 0, 116),
    ("resources.assets", 1573): (0, 0, 0, 0),
    ("resources.assets", 1579): (1, 1, 0, 123),
    ("resources.assets", 1580): (0, 0, 0, 0),
    ("resources.assets", 1584): (0, 0, 0, 0),
}
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_map(translations_dir: Path, pattern: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in sorted(glob.glob(str(translations_dir / pattern))):
        part: dict[str, str] = load_json(Path(name))
        duplicate = set(result) & set(part)
        if duplicate:
            raise RuntimeError(f"번역 키 중복: {sorted(duplicate)[:3]}")
        result.update(part)
    return result


def check_tokens(source: str, target: str, label: str) -> None:
    if Counter(TOKEN_PATTERN.findall(source)) != Counter(TOKEN_PATTERN.findall(target)):
        raise RuntimeError(f"태그·자리표시자 불일치: {label}")
    if source.count("\n") != target.count("\n"):
        raise RuntimeError(f"줄바꿈 불일치: {label}")
    if source.count("\u2028") != target.count("\u2028"):
        raise RuntimeError(f"줄 구분자 불일치: {label}")


def script_class(obj: Any) -> str:
    try:
        head = obj.parse_monobehaviour_head()
        return str(head.m_Script.deref_parse_as_object().m_ClassName)
    except Exception:
        return ""


def locale_code(tree: dict[str, Any]) -> str:
    value = tree.get("m_LocaleId", tree.get("m_Identifier", {}))
    return str(value.get("m_Code", "")) if isinstance(value, dict) else str(value)


def find_table(path: Path, code: str) -> list[dict[str, Any]]:
    env = UnityPy.load(str(path))
    found: list[list[dict[str, Any]]] = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if "m_TableData" in tree and locale_code(tree) == code:
            found.append(tree["m_TableData"])
    if len(found) != 1:
        raise RuntimeError(f"{code} StringTable 수가 예상과 다릅니다: {len(found)}")
    return found[0]


def aligned_string_blob(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded + b"\x00" * ((-len(encoded)) % 4)


def collect_visible_values(value: Any, fields: set[str], result: list[str]) -> None:
    if isinstance(value, dict):
        for field, child in value.items():
            if field in fields and isinstance(child, str):
                result.append(child)
            else:
                collect_visible_values(child, fields, result)
    elif isinstance(value, list):
        for child in value:
            collect_visible_values(child, fields, result)


def load_baseline(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            relative = str(row["RelativePath"]).replace("\\", "/")
            rows[relative] = {"size": int(row["Length"]), "sha256": str(row["SHA256"]).lower()}
    return rows


def inventory_files(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.relative_to(root).as_posix(): {"size": path.stat().st_size, "sha256": sha256_file(path)}
        for path in root.rglob("*")
        if path.is_file()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pibcremental Demo 한글 후보 정적 검증")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--source-original", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--addressables-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unity-version", default="6000.4.0f1")
    args = parser.parse_args()

    localization_map = load_map(args.translations_dir, "localization_ko_part*.json")
    direct_map: dict[str, str] = load_json(args.translations_dir / "direct_text_ko.json")
    assembly_map: dict[str, str] = load_json(args.translations_dir / "assembly_ko.json")
    serialized_map = dict(localization_map)
    serialized_map.update(direct_map)
    serialized_map.update(assembly_map)
    serialized_map.update(load_json(args.translations_dir / "serialized_text_ko.json"))
    for map_name, mapping in {
        "localization": localization_map,
        "direct": direct_map,
        "assembly": assembly_map,
        "serialized": serialized_map,
    }.items():
        for source, target in mapping.items():
            check_tokens(source, target, f"{map_name}:{source}")

    baseline = load_baseline(args.baseline)
    source_files = inventory_files(args.source_original)
    candidate_files = inventory_files(args.candidate)
    overlay_files = inventory_files(args.overlay)
    source_differences = sorted(
        relative
        for relative in set(baseline) | set(source_files)
        if baseline.get(relative) != source_files.get(relative)
    )
    candidate_path_difference = sorted(set(baseline) ^ set(candidate_files))
    changed_files = sorted(
        relative
        for relative in set(baseline) & set(candidate_files)
        if baseline[relative] != candidate_files[relative]
    )
    overlay_mismatch = sorted(
        relative
        for relative, value in overlay_files.items()
        if candidate_files.get(relative) != value
    )
    if source_differences:
        raise RuntimeError(f"격리 원본 무결성 차이: {source_differences[:5]}")
    if candidate_path_difference:
        raise RuntimeError(f"후보 파일 경로 차이: {candidate_path_difference[:5]}")
    if sorted(changed_files) != sorted(overlay_files):
        raise RuntimeError(
            f"후보 변경 파일이 오버레이와 다릅니다: 변경 {changed_files}, 오버레이 {sorted(overlay_files)}"
        )
    if overlay_mismatch:
        raise RuntimeError(f"후보와 오버레이 해시 불일치: {overlay_mismatch}")

    managed_dir = args.candidate / "Pibcremental_Data/Managed"
    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(managed_dir))
    data_env = UnityPy.load(str(args.candidate / DATA_RELATIVE))
    data_env.typetree_generator = generator
    direct_source_remaining: list[dict[str, Any]] = []
    direct_target_occurrences = 0
    serialized_source_remaining: list[dict[str, Any]] = []
    tmp_fonts: list[dict[str, Any]] = []
    failed_visible_objects = 0
    for obj in data_env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        class_name = script_class(obj)
        if class_name in {"TextMeshPro", "TextMeshProUGUI", "Text"}:
            tree = obj.read_typetree()
            field = "m_Text" if class_name == "Text" else "m_text"
            text = str(tree.get(field, ""))
            if text in direct_map:
                direct_source_remaining.append(
                    {"file": obj.assets_file.name, "path_id": int(obj.path_id), "source": text}
                )
            if text in direct_map.values():
                direct_target_occurrences += 1
        if class_name == "TMP_FontAsset":
            key = (str(obj.assets_file.name), int(obj.path_id))
            if key not in TMP_FONT_EXPECTED:
                continue
            tree = obj.read_typetree()
            source_ref = tree.get("m_SourceFontFile", {})
            actual_ref = (int(source_ref.get("m_FileID", 0)), int(source_ref.get("m_PathID", 0)))
            actual = (
                int(tree.get("m_AtlasPopulationMode", -1)),
                int(tree.get("m_IsMultiAtlasTexturesEnabled", 0)),
                actual_ref[0],
                actual_ref[1],
            )
            expected = TMP_FONT_EXPECTED[key]
            tmp_fonts.append(
                {
                    "file": key[0],
                    "path_id": key[1],
                    "name": str(tree.get("m_Name", "")),
                    "actual": list(actual),
                    "expected": list(expected),
                    "preserved": actual == expected,
                }
            )
        if class_name in VISIBLE_SERIALIZED_FIELDS:
            try:
                tree = obj.read_typetree()
                values: list[str] = []
                collect_visible_values(tree, VISIBLE_SERIALIZED_FIELDS[class_name], values)
                for value in values:
                    if value in serialized_map and serialized_map[value] != value:
                        serialized_source_remaining.append(
                            {
                                "file": obj.assets_file.name,
                                "path_id": int(obj.path_id),
                                "class": class_name,
                                "source": value,
                            }
                        )
            except Exception:
                failed_visible_objects += 1
                raw = obj.get_raw_data()
                for source, target in serialized_map.items():
                    if source != target and aligned_string_blob(source) in raw:
                        serialized_source_remaining.append(
                            {
                                "file": obj.assets_file.name,
                                "path_id": int(obj.path_id),
                                "class": class_name,
                                "source": source,
                            }
                        )
    if direct_source_remaining:
        raise RuntimeError(f"TMP/Text 대상 원문 잔존: {direct_source_remaining[:5]}")
    if serialized_source_remaining:
        raise RuntimeError(f"직렬화 표시 필드 원문 잔존: {serialized_source_remaining[:5]}")
    if len(tmp_fonts) != len(TMP_FONT_EXPECTED):
        raise RuntimeError(f"TMP 글꼴 자산 수 불일치: {len(tmp_fonts)}/{len(TMP_FONT_EXPECTED)}")
    invalid_fonts = [row for row in tmp_fonts if not row["preserved"]]
    if invalid_fonts:
        raise RuntimeError(f"원본 TMP 글꼴 설정 보존 오류: {invalid_fonts[:3]}")

    font_env = UnityPy.load(str(args.candidate / DEFAULT_FONT_RELATIVE))
    font_objects = [obj for obj in font_env.objects if obj.type.name == "Font" and int(obj.path_id) == 10102]
    if len(font_objects) != 1:
        raise RuntimeError(f"LegacyRuntime 글꼴 수 불일치: {len(font_objects)}")
    font_tree = font_objects[0].read_typetree()
    embedded_font = bytes(font_tree.get("m_FontData", []))
    font_file_data = args.font.read_bytes()
    if embedded_font != font_file_data:
        raise RuntimeError("후보에 삽입된 한글 글꼴이 준비한 글꼴과 다릅니다.")
    font = TTFont(args.font)
    cmap: set[int] = set()
    for table in font["cmap"].tables:
        cmap.update(int(codepoint) for codepoint in table.cmap)
    required_text = "".join(
        [*localization_map.values(), *direct_map.values(), *assembly_map.values(), *serialized_map.values(), "한국어 (영어)한국어 (독일어)"]
    )
    required_codepoints = {
        ord(character)
        for character in required_text
        if not character.isspace() and ord(character) >= 0x20
    }
    missing_glyphs = sorted(required_codepoints - cmap)
    if missing_glyphs:
        raise RuntimeError(f"한글 글꼴 누락 문자: {[hex(value) for value in missing_glyphs[:20]]}")

    source_english = find_table(args.source_original / AA_RELATIVE / ENGLISH_BUNDLE, "en")
    candidate_english = find_table(args.candidate / AA_RELATIVE / ENGLISH_BUNDLE, "en")
    candidate_german = find_table(args.candidate / AA_RELATIVE / GERMAN_BUNDLE, "de")
    expected_entries = []
    for entry in source_english:
        source = str(entry.get("m_Localized", ""))
        if source not in localization_map:
            raise RuntimeError(f"원본 StringTable 번역 누락: {source!r}")
        expected_entries.append((int(entry.get("m_Id", 0)), localization_map[source]))
    actual_english = [(int(entry.get("m_Id", 0)), str(entry.get("m_Localized", ""))) for entry in candidate_english]
    actual_german = [(int(entry.get("m_Id", 0)), str(entry.get("m_Localized", ""))) for entry in candidate_german]
    if actual_english != expected_entries:
        raise RuntimeError("영어 슬롯 StringTable이 기대 번역과 다릅니다.")
    if actual_german != expected_entries:
        raise RuntimeError("독일어 슬롯 StringTable이 기대 번역과 다릅니다.")

    locales_env = UnityPy.load(str(args.candidate / AA_RELATIVE / LOCALES_BUNDLE))
    locale_names: dict[str, str] = {}
    for obj in locales_env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        code = locale_code(tree)
        if code in {"en", "de"}:
            locale_names[code] = str(tree.get("m_LocaleName", ""))
    if locale_names != {"en": "한국어 (영어)", "de": "한국어 (독일어)"}:
        raise RuntimeError(f"로케일 표시 이름 오류: {locale_names}")

    addressables_report = load_json(args.addressables_report)
    catalog_data = (args.candidate / CATALOG_RELATIVE).read_bytes()
    catalog_checks: list[dict[str, Any]] = []
    for row in addressables_report["modified_bundles"]:
        position = int(row["option_offset"]) + 12
        crc = struct.unpack_from("<I", catalog_data, position - 4)[0]
        size = struct.unpack_from("<I", catalog_data, position)[0]
        actual_size = (args.candidate / AA_RELATIVE / str(row["file"])).stat().st_size
        valid = crc == 0 and size == actual_size
        catalog_checks.append({"file": row["file"], "crc": crc, "catalog_size": size, "actual_size": actual_size, "valid": valid})
    if not all(row["valid"] for row in catalog_checks):
        raise RuntimeError(f"Addressables 카탈로그 불일치: {catalog_checks}")

    report = {
        "schema_version": 1,
        "summary": {
            "baseline_files": len(baseline),
            "source_original_files": len(source_files),
            "candidate_files": len(candidate_files),
            "source_original_differences": len(source_differences),
            "candidate_path_differences": len(candidate_path_difference),
            "modified_files": len(changed_files),
            "overlay_mismatches": len(overlay_mismatch),
            "localization_unique": len(localization_map),
            "string_table_entries_per_locale": len(expected_entries),
            "direct_unique": len(direct_map),
            "direct_source_remaining": len(direct_source_remaining),
            "direct_target_occurrences": direct_target_occurrences,
            "serialized_source_remaining": len(serialized_source_remaining),
            "visible_typetree_error_objects_checked_raw": failed_visible_objects,
            "tmp_font_assets_preserved": len(tmp_fonts),
            "embedded_font_bytes": len(embedded_font),
            "required_glyphs": len(required_codepoints),
            "missing_glyphs": len(missing_glyphs),
            "addressables_catalog_checks": len(catalog_checks),
            "all_static_gates_passed": True,
        },
        "changed_files": changed_files,
        "tmp_fonts": tmp_fonts,
        "locale_names": locale_names,
        "catalog_checks": catalog_checks,
        "candidate_hashes": {relative: candidate_files[relative] for relative in changed_files},
        "assembly": {
            "file": ASSEMBLY_RELATIVE.as_posix(),
            "sha256": candidate_files[ASSEMBLY_RELATIVE.as_posix()]["sha256"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
