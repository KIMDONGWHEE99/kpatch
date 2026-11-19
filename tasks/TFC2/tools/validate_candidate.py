from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


AA_RELATIVE = Path("TFC2_Data/StreamingAssets/aa/StandaloneWindows64")
ENGLISH_BUNDLE = "localization-string-tables-english(en)_assets_all.bundle"
LOCALES_BUNDLE = "localization-locales_assets_all.bundle"
TOKEN_PATTERN = re.compile(r"%[A-Za-z0-9_.]+%?|<[^>]+>|\{[^{}]+\}|\[[^\[\]]+\]")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_localization_map(inventory_path: Path, translations_dir: Path) -> dict[str, str]:
    inventory = load_json(inventory_path)
    sources = {int(row["index"]): str(row["source"]) for row in inventory["english_unique"]}
    translations: dict[int, str] = {}
    for path in sorted(translations_dir.glob("localization_ko_part*.json")):
        translations.update({int(index): str(text) for index, text in load_json(path).items()})
    if set(sources) != set(translations):
        raise RuntimeError("StringTable 번역 번호 집합이 원본과 다릅니다.")
    return {source: translations[index] for index, source in sources.items()}


def locale_code(tree: dict[str, Any]) -> str:
    value = tree.get("m_LocaleId", tree.get("m_Identifier", {}))
    return str(value.get("m_Code", "")) if isinstance(value, dict) else str(value)


def script_class(obj: Any) -> str:
    try:
        head = obj.parse_monobehaviour_head()
        return str(head.m_Script.deref_parse_as_object().m_ClassName)
    except Exception:
        return ""


def pptr_tuple(value: Any) -> tuple[int, int]:
    if not isinstance(value, dict):
        return (0, 0)
    return (int(value.get("m_FileID", 0)), int(value.get("m_PathID", 0)))


def compare_tree(source: Path, candidate: Path) -> tuple[int, list[str], list[str]]:
    source_files = {path.relative_to(source).as_posix(): path for path in source.rglob("*") if path.is_file()}
    candidate_files = {path.relative_to(candidate).as_posix(): path for path in candidate.rglob("*") if path.is_file()}
    if set(source_files) != set(candidate_files):
        missing = sorted(set(source_files) - set(candidate_files))
        extra = sorted(set(candidate_files) - set(source_files))
        raise RuntimeError(f"후보 파일 집합 불일치: 누락 {missing[:5]}, 추가 {extra[:5]}")
    changed = []
    unchanged = []
    for relative, path in source_files.items():
        if sha256_file(path) == sha256_file(candidate_files[relative]):
            unchanged.append(relative)
        else:
            changed.append(relative)
    return len(source_files), sorted(changed), sorted(unchanged)


def validate_localization(
    candidate: Path,
    localization_map: dict[str, str],
    UnityPy: Any,
) -> dict[str, Any]:
    bundle = candidate / AA_RELATIVE / ENGLISH_BUNDLE
    env = UnityPy.load(str(bundle))
    table_count = 0
    entry_count = 0
    errors = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if locale_code(tree) != "en" or "m_TableData" not in tree:
            continue
        table_count += 1
        for entry in tree["m_TableData"]:
            entry_count += 1
            target = str(entry.get("m_Localized", ""))
            matches = [source for source, expected in localization_map.items() if expected == target]
            if not matches:
                errors.append({"path_id": int(obj.path_id), "id": int(entry.get("m_Id", 0)), "value": target})
    if table_count != 37 or entry_count != 1376 or errors:
        raise RuntimeError(f"StringTable 1차 검증 실패: 표 {table_count}, 항목 {entry_count}, 오류 {errors[:3]}")

    locales = candidate / AA_RELATIVE / LOCALES_BUNDLE
    locale_env = UnityPy.load(str(locales))
    names = []
    for obj in locale_env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if locale_code(tree) == "en":
            names.append((str(tree.get("m_Name", "")), str(tree.get("m_LocaleName", ""))))
    if names != [("한국어 (en)", "한국어")]:
        raise RuntimeError(f"한국어 로케일 이름 검증 실패: {names}")
    return {"tables": table_count, "entries": entry_count, "locale_names": names, "reopened": True}


def validate_localization_against_source(
    source: Path,
    candidate: Path,
    localization_map: dict[str, str],
    UnityPy: Any,
) -> dict[str, Any]:
    original_env = UnityPy.load(str(source / AA_RELATIVE / ENGLISH_BUNDLE))
    candidate_env = UnityPy.load(str(candidate / AA_RELATIVE / ENGLISH_BUNDLE))
    original_tables = {}
    candidate_tables = {}
    for env, output in ((original_env, original_tables), (candidate_env, candidate_tables)):
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tree = obj.read_typetree()
            except Exception:
                continue
            if locale_code(tree) == "en" and "m_TableData" in tree:
                output[int(obj.path_id)] = tree["m_TableData"]
    if set(original_tables) != set(candidate_tables):
        raise RuntimeError("StringTable 객체 집합이 바뀌었습니다.")
    checked = 0
    residual = []
    for path_id, original_entries in original_tables.items():
        candidate_entries = candidate_tables[path_id]
        if len(original_entries) != len(candidate_entries):
            raise RuntimeError(f"StringTable 항목 수 변경: {path_id}")
        for original, patched in zip(original_entries, candidate_entries):
            if int(original.get("m_Id", 0)) != int(patched.get("m_Id", 0)):
                raise RuntimeError(f"StringTable ID 순서 변경: {path_id}")
            source_text = str(original.get("m_Localized", ""))
            expected = localization_map[source_text]
            if str(patched.get("m_Localized", "")) != expected:
                residual.append({"path_id": path_id, "id": int(original.get("m_Id", 0)), "source": source_text})
            checked += 1
    if residual:
        raise RuntimeError(f"StringTable 원문 잔존 또는 오역 위치: {residual[:3]}")
    return {"checked_entries": checked, "target_mismatches": len(residual)}


def validate_direct(
    candidate: Path,
    direct_inventory: dict[str, Any],
    UnityPy: Any,
    generator: Any,
) -> dict[str, Any]:
    by_file: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in direct_inventory["records"]:
        if row["classification"] == "VISIBLE_TRANSLATE":
            by_file[str(row["file"])][int(row["path_id"])] = row
    checked = 0
    mismatches = []
    legacy_font_errors = []
    for file_name, targets in by_file.items():
        env = UnityPy.load(str(candidate / "TFC2_Data" / file_name))
        env.typetree_generator = generator
        objects = {int(obj.path_id): obj for obj in env.objects}
        for path_id, row in targets.items():
            obj = objects.get(path_id)
            if obj is None:
                mismatches.append({"file": file_name, "path_id": path_id, "error": "missing"})
                continue
            tree = obj.read_typetree()
            actual = str(tree.get(str(row["field"]), ""))
            if actual != str(row["translation"]):
                mismatches.append({"file": file_name, "path_id": path_id, "actual": actual})
            if row["class"] == "Text":
                font_data = tree.get("m_FontData", {})
                font_reference = font_data.get("m_Font") if isinstance(font_data, dict) else None
                if pptr_tuple(font_reference)[1] != 658:
                    legacy_font_errors.append(
                        {"file": file_name, "path_id": path_id, "font": font_reference}
                    )
            checked += 1
    if checked != 731 or mismatches or legacy_font_errors:
        raise RuntimeError(
            f"직접 문구 검증 실패: {checked}/731, 문구 {mismatches[:3]}, 글꼴 {legacy_font_errors[:3]}"
        )
    return {"checked": checked, "target_mismatches": 0, "legacy_font_errors": 0, "reopened_files": len(by_file)}


def validate_fonts(
    candidate: Path,
    font_path: Path,
    font_inventory: dict[str, Any],
    corpus: str,
    UnityPy: Any,
    generator: Any,
    TTFont: Any,
) -> dict[str, Any]:
    assets: dict[tuple[str, int], dict[str, Any]] = {}
    atlas_readable: dict[int, bool] = {}
    for file_name in ("sharedassets0.assets", "sharedassets1.assets"):
        env = UnityPy.load(str(candidate / "TFC2_Data" / file_name))
        env.typetree_generator = generator
        for obj in env.objects:
            if obj.type.name == "Font" and file_name == "sharedassets0.assets" and int(obj.path_id) == 658:
                tree = obj.read_typetree()
                embedded = bytes(tree["m_FontData"])
                if hashlib.sha256(embedded).digest() != hashlib.sha256(font_path.read_bytes()).digest():
                    raise RuntimeError("내장 Noto Sans KR 글꼴 데이터가 원본 글꼴과 다릅니다.")
            if obj.type.name == "Texture2D" and file_name == "sharedassets0.assets" and int(obj.path_id) == 598:
                atlas_readable[int(obj.path_id)] = bool(obj.read_typetree().get("m_IsReadable", False))
            if obj.type.name != "MonoBehaviour" or script_class(obj) != "TMP_FontAsset":
                continue
            tree = obj.read_typetree()
            assets[(file_name, int(obj.path_id))] = tree

    dynamic = {("sharedassets0.assets", 8630)}

    def resolve(current_file: str, reference: tuple[int, int]) -> tuple[str, int] | None:
        file_id, path_id = reference
        if not path_id:
            return None
        if file_id == 0:
            return (current_file, path_id)
        if current_file == "sharedassets1.assets" and file_id == 5:
            return ("sharedassets0.assets", path_id)
        return None

    def reaches_dynamic(node: tuple[str, int], visiting: set[tuple[str, int]]) -> bool:
        if node in dynamic:
            tree = assets[node]
            return (
                int(tree.get("m_AtlasPopulationMode", -1)) == 1
                and pptr_tuple(tree.get("m_SourceFontFile")) == (0, 658)
                and int(tree.get("m_IsMultiAtlasTexturesEnabled", 0)) == 1
            )
        if node in visiting or node not in assets:
            return False
        visiting.add(node)
        tree = assets[node]
        for reference in tree.get("m_FallbackFontAssetTable", []):
            next_node = resolve(node[0], pptr_tuple(reference))
            if next_node is not None and reaches_dynamic(next_node, visiting):
                return True
        return False

    expected_nodes = {(str(row["file"]), int(row["path_id"])) for row in font_inventory["tmp_font_assets"]}
    missing_nodes = sorted(expected_nodes - set(assets))
    unreachable = sorted(node for node in expected_nodes if not reaches_dynamic(node, set()))
    used_path_ids = {int(row["font_asset"]["path_id"]) for row in font_inventory["tmp_text_usages"]}
    known_path_ids = {path_id for _, path_id in expected_nodes}
    unknown_usage_fonts = sorted(used_path_ids - known_path_ids)
    unreadable_atlases = [] if atlas_readable.get(598, False) else [598]
    if missing_nodes or unreachable or unknown_usage_fonts or unreadable_atlases:
        raise RuntimeError(
            f"TMP 글꼴 연결 실패: 누락 {missing_nodes}, 폴백 불가 {unreachable}, "
            f"사용 미상 {unknown_usage_fonts}, 읽기 불가 아틀라스 {unreadable_atlases}"
        )

    cleaned = TOKEN_PATTERN.sub("", corpus)
    required = {ord(char) for char in cleaned if ord(char) >= 128 and not char.isspace()}
    cmap = TTFont(str(font_path)).getBestCmap()
    missing_glyphs = sorted(required - set(cmap))
    if missing_glyphs:
        raise RuntimeError(f"Noto Sans KR 누락 글리프: {[f'U+{value:04X}' for value in missing_glyphs]}")
    return {
        "tmp_font_assets": len(expected_nodes),
        "tmp_text_usages": len(font_inventory["tmp_text_usages"]),
        "all_usage_fonts_known": True,
        "all_font_chains_reach_korean_source": True,
        "dynamic_atlas_textures_readable": sorted(atlas_readable),
        "required_non_ascii_glyphs": len(required),
        "missing_glyphs": [],
        "embedded_source_font_sha256": sha256_file(font_path),
    }


def validate_media(candidate: Path, expected_path: Path, UnityPy: Any, Image: Any, ImageChops: Any, ImageStat: Any) -> dict[str, Any]:
    env = UnityPy.load(str(candidate / "TFC2_Data/sharedassets4.assets"))
    obj = next((obj for obj in env.objects if obj.type.name == "Texture2D" and int(obj.path_id) == 13), None)
    if obj is None:
        raise RuntimeError("하투사 한글 이미지 Texture2D를 찾지 못했습니다.")
    actual = obj.read().image.convert("RGBA")
    with Image.open(expected_path) as image:
        expected = image.convert("RGBA")
    if actual.size != (2048, 1152) or expected.size != actual.size:
        raise RuntimeError(f"하투사 한글 이미지 크기 불일치: {actual.size}/{expected.size}")
    mean_absolute_error = sum(ImageStat.Stat(ImageChops.difference(actual, expected)).mean) / 4.0
    if mean_absolute_error > 8.0:
        raise RuntimeError(f"하투사 이미지 재압축 오차가 큽니다: {mean_absolute_error}")
    return {"path_id": 13, "size": list(actual.size), "decoded": True, "mean_absolute_error": mean_absolute_error}


def validate_metadata(
    source: Path,
    candidate: Path,
    code_mapping_path: Path,
    enum_mapping_path: Path,
    enum_tool_path: Path,
) -> dict[str, Any]:
    from metadata_strings import extract_literals

    original_rows = extract_literals(source.read_bytes())
    patched_data = candidate.read_bytes()
    patched_rows = extract_literals(patched_data)
    if len(original_rows) != len(patched_rows):
        raise RuntimeError("메타데이터 문자열 항목 수가 바뀌었습니다.")
    mapping_data = load_json(code_mapping_path)
    mapping = {str(key): str(value) for key, value in mapping_data["translations"].items()}
    changed = 0
    errors = []
    for original, patched in zip(original_rows, patched_rows):
        source_text = str(original["source"])
        if source_text not in mapping:
            continue
        expected = mapping[source_text]
        if str(patched["source"]) != expected:
            errors.append({"index": original["index"], "source": source_text, "actual": patched["source"]})
        changed += 1
    if changed != 36 or errors:
        raise RuntimeError(f"IL2CPP 문구 검증 실패: {changed}/36, {errors[:3]}")

    spec = importlib.util.spec_from_file_location("metadata_enum_names", enum_tool_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("enum 검증 도구를 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    version, pairs = module.header_pairs(patched_data)
    field_start, field_count = module.find_type(patched_data, pairs, "", "RESOURCE_TYPE")
    heap_offset, heap_size = pairs[module.STRING_HEAP_PAIR]
    field_offset = pairs[module.FIELD_DEFINITIONS_PAIR][0]
    actual_names = []
    for local_index in range(field_count):
        position = field_offset + (field_start + local_index) * module.FIELD_DEFINITION_SIZE
        name_index = struct.unpack_from("<I", patched_data, position)[0]
        actual_names.append(module.read_heap_string(patched_data, heap_offset, heap_size, name_index))
    enum_mapping = {str(key): str(value) for key, value in load_json(enum_mapping_path).items()}
    missing_enum_targets = sorted(set(enum_mapping.values()) - set(actual_names))
    if version != 31 or field_count != 10 or missing_enum_targets:
        raise RuntimeError(f"RESOURCE_TYPE 검증 실패: v{version}, 필드 {field_count}, 누락 {missing_enum_targets}")
    return {
        "metadata_version": version,
        "literal_entries": len(patched_rows),
        "translated_literal_occurrences": changed,
        "literal_target_mismatches": 0,
        "resource_type_field_count": field_count,
        "resource_type_korean_names": list(enum_mapping.values()),
    }


def validate_catalog(source: Path, candidate: Path, report_path: Path) -> dict[str, Any]:
    report = load_json(report_path)
    source_data = source.read_bytes()
    candidate_data = candidate.read_bytes()
    if len(source_data) != len(candidate_data):
        raise RuntimeError("Addressables 카탈로그 크기가 바뀌었습니다.")
    for row in report["modified_bundles"]:
        position = int(row["option_offset"]) + 12
        crc = struct.unpack_from("<I", candidate_data, position - 4)[0]
        size = struct.unpack_from("<I", candidate_data, position)[0]
        if crc != 0 or size != int(row["new_size"]):
            raise RuntimeError(f"Addressables 옵션 검증 실패: {row['file']}")
    return {"size_preserved": True, "modified_bundles": len(report["modified_bundles"]), "reopened": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 한국어 실행 후보 정적 검증")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--localization-inventory", type=Path, required=True)
    parser.add_argument("--direct-inventory", type=Path, required=True)
    parser.add_argument("--font-inventory", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--expected-media", type=Path, required=True)
    parser.add_argument("--catalog-report", type=Path, required=True)
    parser.add_argument("--enum-tool", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--unitypy-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--unity-version", default="6000.2.9f1")
    args = parser.parse_args()

    sys.path.insert(0, str(args.unitypy_root.resolve()))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import UnityPy  # type: ignore
    from fontTools.ttLib import TTFont  # type: ignore
    from PIL import Image, ImageChops, ImageStat  # type: ignore
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator  # type: ignore

    localization_map = load_localization_map(args.localization_inventory, args.translations_dir)
    direct_inventory = load_json(args.direct_inventory)
    font_inventory = load_json(args.font_inventory)
    code_mapping = load_json(args.translations_dir / "code_literals_ko.json")["translations"]
    enum_mapping = load_json(args.translations_dir / "resource_type_enum_ko.json")
    corpus_parts = list(localization_map.values())
    corpus_parts.extend(
        str(row["translation"])
        for row in direct_inventory["records"]
        if row["classification"] == "VISIBLE_TRANSLATE"
    )
    corpus_parts.extend(str(value) for value in code_mapping.values())
    corpus_parts.extend(str(value) for value in enum_mapping.values())
    corpus_parts.extend(["한국어", "하투사", "기원전 1200년"])

    file_count, changed_files, unchanged_files = compare_tree(args.source_root, args.candidate_root)
    expected_changed = sorted(
        [
            "TFC2_Data/StreamingAssets/aa/catalog.bin",
            f"TFC2_Data/StreamingAssets/aa/StandaloneWindows64/{ENGLISH_BUNDLE}",
            f"TFC2_Data/StreamingAssets/aa/StandaloneWindows64/{LOCALES_BUNDLE}",
            "TFC2_Data/sharedassets0.assets",
            "TFC2_Data/sharedassets1.assets",
            "TFC2_Data/sharedassets4.assets",
            "TFC2_Data/level0",
            "TFC2_Data/level1",
            "TFC2_Data/level2",
            "TFC2_Data/level3",
            "TFC2_Data/level4",
            "TFC2_Data/il2cpp_data/Metadata/global-metadata.dat",
        ]
    )
    if changed_files != expected_changed:
        raise RuntimeError(f"예상 밖 후보 변경 파일: 실제 {changed_files}, 예상 {expected_changed}")

    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))
    localization = validate_localization(args.candidate_root, localization_map, UnityPy)
    localization_positions = validate_localization_against_source(
        args.source_root, args.candidate_root, localization_map, UnityPy
    )
    direct = validate_direct(args.candidate_root, direct_inventory, UnityPy, generator)
    fonts = validate_fonts(
        args.candidate_root,
        args.font,
        font_inventory,
        "\n".join(corpus_parts),
        UnityPy,
        generator,
        TTFont,
    )
    media = validate_media(args.candidate_root, args.expected_media, UnityPy, Image, ImageChops, ImageStat)
    metadata = validate_metadata(
        args.source_root / "TFC2_Data/il2cpp_data/Metadata/global-metadata.dat",
        args.candidate_root / "TFC2_Data/il2cpp_data/Metadata/global-metadata.dat",
        args.translations_dir / "code_literals_ko.json",
        args.translations_dir / "resource_type_enum_ko.json",
        args.enum_tool,
    )
    catalog = validate_catalog(
        args.source_root / "TFC2_Data/StreamingAssets/aa/catalog.bin",
        args.candidate_root / "TFC2_Data/StreamingAssets/aa/catalog.bin",
        args.catalog_report,
    )
    report = {
        "schema_version": 1,
        "passed": True,
        "file_tree": {
            "file_count": file_count,
            "changed_file_count": len(changed_files),
            "unchanged_file_count": len(unchanged_files),
            "changed_files": changed_files,
            "unexpected_changes": [],
        },
        "localization": localization,
        "localization_positions": localization_positions,
        "direct_text": direct,
        "fonts": fonts,
        "media": media,
        "metadata": metadata,
        "addressables_catalog": catalog,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
