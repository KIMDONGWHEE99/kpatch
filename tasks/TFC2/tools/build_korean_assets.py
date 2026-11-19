from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TOKEN_PATTERN = re.compile(r"<[^>]+>|\{[^{}]+\}|\[[A-Z0-9_+\-]+\]")
AA_RELATIVE = Path("TFC2_Data/StreamingAssets/aa/StandaloneWindows64")
ENGLISH_BUNDLE = "localization-string-tables-english(en)_assets_all.bundle"
LOCALES_BUNDLE = "localization-locales_assets_all.bundle"
DIRECT_CLASSES = {"TextMeshProUGUI", "TextMeshPro", "Text"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def pptr(file_id: int, path_id: int) -> dict[str, int]:
    return {"m_FileID": int(file_id), "m_PathID": int(path_id)}


def check_text(source: str, target: str, label: str) -> None:
    if unicodedata.normalize("NFC", target) != target:
        raise RuntimeError(f"NFC 정규화 오류: {label}: {target!r}")
    if Counter(TOKEN_PATTERN.findall(source)) != Counter(TOKEN_PATTERN.findall(target)):
        raise RuntimeError(f"태그·자리표시자 불일치: {label}: {source!r} -> {target!r}")
    if source.count("\n") != target.count("\n") or source.count("\r") != target.count("\r"):
        raise RuntimeError(f"줄바꿈 불일치: {label}: {source!r} -> {target!r}")
    if source.count("\u2028") != target.count("\u2028"):
        raise RuntimeError(f"줄 구분자 불일치: {label}: {source!r} -> {target!r}")


def load_localization_map(inventory_path: Path, translations_dir: Path) -> dict[str, str]:
    inventory = load_json(inventory_path)
    sources = {int(row["index"]): str(row["source"]) for row in inventory["english_unique"]}
    translations: dict[int, str] = {}
    for path in sorted(translations_dir.glob("localization_ko_part*.json")):
        part = load_json(path)
        for raw_index, target in part.items():
            index = int(raw_index)
            if index in translations:
                raise RuntimeError(f"StringTable 번역 번호 중복: {index}")
            translations[index] = str(target)
    if set(sources) != set(translations):
        missing = sorted(set(sources) - set(translations))
        extra = sorted(set(translations) - set(sources))
        raise RuntimeError(f"StringTable 번역 번호 불일치: 누락 {missing[:5]}, 추가 {extra[:5]}")
    result: dict[str, str] = {}
    for index, source in sources.items():
        target = translations[index]
        if not target:
            raise RuntimeError(f"빈 StringTable 번역: {index}: {source!r}")
        check_text(source, target, f"StringTable 고유 문구 {index}")
        result[source] = target
    if len(result) != 1238:
        raise RuntimeError(f"StringTable 고유 번역 수 불일치: {len(result)}/1238")
    return result


def script_class(obj: Any) -> str:
    try:
        head = obj.parse_monobehaviour_head()
        return str(head.m_Script.deref_parse_as_object().m_ClassName)
    except Exception:
        return ""


def locale_code(tree: dict[str, Any]) -> str:
    value = tree.get("m_LocaleId", tree.get("m_Identifier", {}))
    return str(value.get("m_Code", "")) if isinstance(value, dict) else str(value)


def save_environment(env: Any) -> bytes:
    try:
        return env.file.save(packer="original")
    except TypeError:
        return env.file.save()


def write_output(
    source: Path,
    relative: Path,
    output_root: Path,
    output_bytes: bytes,
    changes: Counter[str],
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
        "changes": dict(changes),
    }


def patch_localization(
    game_root: Path,
    overlay_root: Path,
    localization_map: dict[str, str],
    UnityPy: Any,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()

    english_relative = AA_RELATIVE / ENGLISH_BUNDLE
    english_source = game_root / english_relative
    env = UnityPy.load(str(english_source))
    counts: Counter[str] = Counter()
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if locale_code(tree) != "en" or "m_TableData" not in tree:
            continue
        for entry in tree.get("m_TableData", []):
            source = str(entry.get("m_Localized", ""))
            if source not in localization_map:
                raise RuntimeError(f"StringTable 번역 누락: {obj.path_id}: {source!r}")
            target = localization_map[source]
            check_text(source, target, f"StringTable:{obj.path_id}:{entry.get('m_Id')}")
            entry["m_Localized"] = target
            counts["string_table_entries"] += 1
        obj.save_typetree(tree)
        counts["string_tables"] += 1
    if counts["string_tables"] != 37 or counts["string_table_entries"] != 1376:
        raise RuntimeError(
            f"영어 StringTable 수 불일치: 표 {counts['string_tables']}/37, "
            f"항목 {counts['string_table_entries']}/1376"
        )
    rows.append(write_output(english_source, english_relative, overlay_root, save_environment(env), counts))
    totals.update(counts)

    locales_relative = AA_RELATIVE / LOCALES_BUNDLE
    locales_source = game_root / locales_relative
    env = UnityPy.load(str(locales_source))
    counts = Counter()
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if locale_code(tree) != "en":
            continue
        tree["m_Name"] = "한국어 (en)"
        tree["m_LocaleName"] = "한국어"
        obj.save_typetree(tree)
        counts["locale_names"] += 1
    if counts["locale_names"] != 1:
        raise RuntimeError(f"영어 로케일 표시 이름 변경 수 불일치: {counts['locale_names']}/1")
    rows.append(write_output(locales_source, locales_relative, overlay_root, save_environment(env), counts))
    totals.update(counts)
    return rows, totals


def append_fallback(tree: dict[str, Any], reference: dict[str, int]) -> bool:
    values = tree.get("m_FallbackFontAssetTable")
    if not isinstance(values, list):
        raise RuntimeError("TMP FontAsset의 폴백 배열을 찾지 못했습니다.")
    if reference in values:
        return False
    values.append(reference)
    return True


def patch_shared0_fonts(obj: Any, tree: dict[str, Any], font_data: bytes, counts: Counter[str]) -> bool:
    path_id = int(obj.path_id)
    if obj.type.name == "Font" and path_id == 658:
        tree["m_FontData"] = list(font_data)
        tree["m_FontNames"] = ["Noto Sans KR"]
        obj.save_typetree(tree)
        counts["source_font_replaced"] += 1
        counts["source_font_bytes"] += len(font_data)
        return True
    if obj.type.name != "MonoBehaviour" or script_class(obj) != "TMP_FontAsset":
        return False
    changed = False
    if path_id in {8620, 8621, 8625, 8626}:
        changed = append_fallback(tree, pptr(0, 8630)) or changed
        if changed:
            counts["tmp_primary_fallbacks"] += 1
    if path_id == 8630:
        if int(tree.get("m_AtlasPopulationMode", -1)) != 1:
            tree["m_AtlasPopulationMode"] = 1
            changed = True
        if tree.get("m_SourceFontFile") != pptr(0, 658):
            tree["m_SourceFontFile"] = pptr(0, 658)
            changed = True
        if int(tree.get("m_IsMultiAtlasTexturesEnabled", 0)) != 1:
            tree["m_IsMultiAtlasTexturesEnabled"] = 1
            changed = True
        counts["tmp_dynamic_korean_fonts"] += 1
    if changed:
        obj.save_typetree(tree)
    return changed


def patch_shared1_fonts(obj: Any, tree: dict[str, Any], counts: Counter[str]) -> bool:
    if obj.type.name != "MonoBehaviour" or script_class(obj) != "TMP_FontAsset":
        return False
    if int(obj.path_id) not in {2336, 2337, 2338, 2339}:
        return False
    changed = append_fallback(tree, pptr(5, 8630))
    if changed:
        obj.save_typetree(tree)
        counts["tmp_shared1_fallbacks"] += 1
    return changed


def shared0_external_index(assets_file: Any) -> int:
    matches = []
    for index, external in enumerate(getattr(assets_file, "externals", []), 1):
        name = str(external.path).replace("\\", "/").rsplit("/", 1)[-1].casefold()
        if name == "sharedassets0.assets":
            matches.append(index)
    if len(matches) != 1:
        raise RuntimeError(f"sharedassets0.assets 외부 참조 수가 예상과 다릅니다: {matches}")
    return matches[0]


def patch_data_files(
    game_root: Path,
    overlay_root: Path,
    direct_inventory: dict[str, Any],
    font_data: bytes,
    media_path: Path,
    report_dir: Path,
    UnityPy: Any,
    generator: Any,
    Image: Any,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    targets: dict[tuple[str, int], dict[str, Any]] = {}
    for row in direct_inventory["records"]:
        if row["classification"] != "VISIBLE_TRANSLATE":
            continue
        target = row.get("translation")
        if not isinstance(target, str) or not target:
            raise RuntimeError(f"직접 문구 번역 누락: {row['file']}:{row['path_id']}")
        check_text(str(row["source"]), target, f"직접 문구:{row['file']}:{row['path_id']}")
        key = (str(row["file"]), int(row["path_id"]))
        if key in targets:
            raise RuntimeError(f"직접 문구 대상 중복: {key}")
        targets[key] = row
    if len(targets) != 731:
        raise RuntimeError(f"직접 문구 대상 수 불일치: {len(targets)}/731")

    by_file: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for (file_name, path_id), row in targets.items():
        by_file[file_name][path_id] = row
    target_files = set(by_file) | {"sharedassets0.assets", "sharedassets1.assets", "sharedassets4.assets"}

    prepared_media = report_dir / "hattusa_1200_bc_ko_2048x1152.png"
    prepared_media.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(media_path) as image:
        image.convert("RGBA").resize((2048, 1152), Image.Resampling.LANCZOS).save(prepared_media)

    rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    patched_direct_keys: set[tuple[str, int]] = set()
    for file_name in sorted(target_files, key=str.casefold):
        relative = Path("TFC2_Data") / file_name
        source = game_root / relative
        env = UnityPy.load(str(source))
        env.typetree_generator = generator
        counts: Counter[str] = Counter()
        errors: list[str] = []

        if file_name == "sharedassets1.assets":
            assets_file = env.objects[0].assets_file
            if shared0_external_index(assets_file) != 5:
                raise RuntimeError("sharedassets1.assets의 sharedassets0 외부 참조 번호가 5가 아닙니다.")

        for obj in env.objects:
            path_id = int(obj.path_id)
            row = by_file.get(file_name, {}).get(path_id)
            if row is not None:
                class_name = script_class(obj)
                if obj.type.name != "MonoBehaviour" or class_name not in DIRECT_CLASSES:
                    errors.append(f"{path_id}: 직접 문구 대상 형식 불일치: {obj.type.name}/{class_name}")
                elif class_name != row["class"]:
                    errors.append(f"{path_id}: 직접 문구 클래스 불일치: {class_name}/{row['class']}")
                else:
                    try:
                        tree = obj.read_typetree()
                        field = str(row["field"])
                        source_text = str(row["source"])
                        if str(tree.get(field, "")) != source_text:
                            raise RuntimeError(
                                f"원문 불일치: {tree.get(field)!r} / {source_text!r}"
                            )
                        tree[field] = str(row["translation"])
                        if class_name == "Text":
                            external_index = shared0_external_index(obj.assets_file)
                            legacy_font_data = tree.get("m_FontData")
                            if not isinstance(legacy_font_data, dict) or "m_Font" not in legacy_font_data:
                                raise RuntimeError("Unity UI Text의 m_FontData.m_Font 필드를 찾지 못했습니다.")
                            legacy_font_data["m_Font"] = pptr(external_index, 658)
                            counts["legacy_text_font_refs"] += 1
                        obj.save_typetree(tree)
                        counts["direct_text"] += 1
                        patched_direct_keys.add((file_name, path_id))
                    except Exception as exc:
                        errors.append(f"{path_id} {class_name}: {type(exc).__name__}: {exc}")
                continue

            if file_name == "sharedassets0.assets" and (
                (obj.type.name == "Font" and path_id == 658)
                or (obj.type.name == "MonoBehaviour" and path_id in {8620, 8621, 8625, 8626, 8630})
            ):
                try:
                    patch_shared0_fonts(obj, obj.read_typetree(), font_data, counts)
                except Exception as exc:
                    errors.append(f"{path_id} font: {type(exc).__name__}: {exc}")
                continue

            if file_name == "sharedassets1.assets" and obj.type.name == "MonoBehaviour" and path_id in {2336, 2337, 2338, 2339}:
                try:
                    patch_shared1_fonts(obj, obj.read_typetree(), counts)
                except Exception as exc:
                    errors.append(f"{path_id} font: {type(exc).__name__}: {exc}")
                continue

            if file_name == "sharedassets4.assets" and obj.type.name == "Texture2D" and path_id == 13:
                try:
                    value = obj.read()
                    if (int(value.m_Width), int(value.m_Height)) != (2048, 1152):
                        raise RuntimeError(f"원본 이미지 크기 불일치: {value.m_Width}x{value.m_Height}")
                    texture_format = int(value.m_TextureFormat)
                    mip_count = max(1, int(getattr(value, "m_MipCount", 1) or 1))
                    value.set_image(str(prepared_media), target_format=texture_format, mipmap_count=mip_count)
                    value.save()
                    counts["localized_textures"] += 1
                    counts["localized_texture_format"] = texture_format
                    counts["localized_texture_mips"] = mip_count
                except Exception as exc:
                    errors.append(f"{path_id} Texture2D: {type(exc).__name__}: {exc}")

        if errors:
            raise RuntimeError(f"{file_name} 패치 오류:\n" + "\n".join(errors[:30]))
        output_bytes = save_environment(env)
        rows.append(write_output(source, relative, overlay_root, output_bytes, counts))
        totals.update(counts)

    missing_direct = sorted(set(targets) - patched_direct_keys)
    if missing_direct:
        raise RuntimeError(f"직접 문구 미적용 대상: {missing_direct[:10]}")
    expected = {
        "direct_text": 731,
        "legacy_text_font_refs": 18,
        "source_font_replaced": 1,
        "tmp_primary_fallbacks": 4,
        "tmp_dynamic_korean_fonts": 1,
        "tmp_shared1_fallbacks": 4,
        "localized_textures": 1,
    }
    for key, value in expected.items():
        if totals[key] != value:
            raise RuntimeError(f"{key} 적용 수 불일치: {totals[key]}/{value}")
    return rows, totals


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 한국어 Unity 자산 빌드")
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--localization-inventory", type=Path, required=True)
    parser.add_argument("--direct-inventory", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--unitypy-root", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--overlay-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--unity-version", default="6000.2.9f1")
    args = parser.parse_args()

    sys.path.insert(0, str(args.unitypy_root.resolve()))
    import UnityPy  # type: ignore
    from PIL import Image  # type: ignore
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator  # type: ignore

    localization_map = load_localization_map(args.localization_inventory, args.translations_dir)
    direct_inventory = load_json(args.direct_inventory)
    if direct_inventory.get("unknown_unique_count") != 0 or direct_inventory.get("error_count") != 0:
        raise RuntimeError("직접 문구 조사에 UNKNOWN 또는 오류가 남아 있습니다.")
    font_data = args.font.read_bytes()
    if sha256(font_data).upper() != "194018E6B2B293A7964F037B25C0249CE1418BC9AB3C971060A03AA57861E252":
        raise RuntimeError("Noto Sans KR 글꼴 SHA-256이 예상과 다릅니다.")

    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))
    report_rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()

    localization_rows, localization_counts = patch_localization(
        args.game_root, args.overlay_root, localization_map, UnityPy
    )
    report_rows.extend(localization_rows)
    totals.update(localization_counts)
    data_rows, data_counts = patch_data_files(
        args.game_root,
        args.overlay_root,
        direct_inventory,
        font_data,
        args.media,
        args.report.parent,
        UnityPy,
        generator,
        Image,
    )
    report_rows.extend(data_rows)
    totals.update(data_counts)

    report = {
        "schema_version": 1,
        "passed": True,
        "files": report_rows,
        "summary": {
            "modified_files": len(report_rows),
            "localization_unique": len(localization_map),
            **dict(totals),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
