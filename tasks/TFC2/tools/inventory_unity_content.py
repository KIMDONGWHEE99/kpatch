from __future__ import annotations

import argparse
import gc
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


CORE_FILE_NAMES = {
    "globalgamemanagers",
    "globalgamemanagers.assets",
    "resources.assets",
    "unity default resources",
    "unity_builtin_extra",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def is_unity_container(path: Path) -> bool:
    name = path.name.lower()
    if path.suffix.lower() == ".bundle":
        return True
    if name in CORE_FILE_NAMES:
        return True
    if name.startswith("sharedassets") and path.suffix.lower() == ".assets":
        return True
    return name.startswith("level") and not path.suffix


def iter_strings(value: Any, path: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], str]]:
    if isinstance(value, str):
        if value.strip():
            yield path, value
        return
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_strings(child, path + (key,))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_strings(child, path + (index,))


def script_details(obj: Any) -> tuple[str, str, str, str]:
    try:
        head = obj.parse_monobehaviour_head()
        script = head.m_Script.deref_parse_as_object()
        game_object = ""
        try:
            game_object = str(head.m_GameObject.deref_parse_as_object().m_Name)
        except Exception:
            pass
        return (
            str(script.m_ClassName),
            str(script.m_Namespace),
            str(script.m_AssemblyName),
            game_object,
        )
    except Exception:
        return "", "", "", ""


def decode_text_asset(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, (bytes, bytearray)):
        return ""
    raw = bytes(value)
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text and "\x00" not in text[:200]:
            return text
    return ""


def compact_pointer(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {key: value.get(key) for key in ("m_FileID", "m_PathID") if key in value}


def compact_font_asset(tree: dict[str, Any]) -> dict[str, Any]:
    character_table = tree.get("m_CharacterTable", [])
    glyph_table = tree.get("m_GlyphTable", [])
    atlas_textures = tree.get("m_AtlasTextures", [])
    fallbacks = tree.get("m_FallbackFontAssetTable", [])
    return {
        "name": str(tree.get("m_Name", "")),
        "version": str(tree.get("m_Version", "")),
        "atlas_population_mode": tree.get("m_AtlasPopulationMode"),
        "source_font_file": compact_pointer(tree.get("m_SourceFontFile")),
        "source_font_file_guid": tree.get("m_SourceFontFileGUID"),
        "material": compact_pointer(tree.get("m_Material")),
        "atlas_textures": [compact_pointer(value) for value in atlas_textures],
        "fallback_font_assets": [compact_pointer(value) for value in fallbacks],
        "multi_atlas_enabled": tree.get("m_IsMultiAtlasTexturesEnabled"),
        "character_count": len(character_table) if isinstance(character_table, list) else None,
        "glyph_count": len(glyph_table) if isinstance(glyph_table, list) else None,
        "character_unicode": sorted(
            {
                int(row.get("m_Unicode", row.get("m_unicode", -1)))
                for row in character_table
                if isinstance(row, dict) and row.get("m_Unicode", row.get("m_unicode")) is not None
            }
        ),
    }


def inventory_file(path: Path, data_root: Path, generator: TypeTreeGenerator) -> dict[str, Any]:
    relative_path = path.relative_to(data_root).as_posix()
    result: dict[str, Any] = {
        "relative_path": relative_path,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "object_counts": {},
        "script_counts": {},
        "strings": [],
        "font_assets": [],
        "text_assets": [],
        "media": [],
        "errors": [],
    }
    try:
        env = UnityPy.load(str(path))
        env.typetree_generator = generator
    except Exception as exc:
        result["errors"].append({"stage": "load", "error": f"{type(exc).__name__}: {exc}"})
        return result

    object_counts: Counter[str] = Counter()
    script_counts: Counter[str] = Counter()
    for obj in env.objects:
        object_type = obj.type.name
        object_counts[object_type] += 1
        path_id = int(obj.path_id)
        if object_type == "MonoBehaviour":
            class_name, namespace, assembly, game_object = script_details(obj)
            script_key = f"{namespace}.{class_name}|{assembly}"
            script_counts[script_key] += 1
            try:
                tree = obj.read_typetree()
            except Exception as exc:
                result["errors"].append(
                    {
                        "stage": "typetree",
                        "path_id": path_id,
                        "class": class_name,
                        "namespace": namespace,
                        "assembly": assembly,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            object_name = str(tree.get("m_Name", ""))
            for field_path, source in iter_strings(tree):
                result["strings"].append(
                    {
                        "path_id": path_id,
                        "object_type": object_type,
                        "class": class_name,
                        "namespace": namespace,
                        "assembly": assembly,
                        "object_name": object_name,
                        "game_object": game_object,
                        "field_path": list(field_path),
                        "source": source,
                    }
                )
            if class_name in {"TMP_FontAsset", "TMP_SpriteAsset", "TMP_Settings"}:
                result["font_assets"].append(
                    {
                        "path_id": path_id,
                        "class": class_name,
                        "namespace": namespace,
                        "assembly": assembly,
                        **compact_font_asset(tree),
                    }
                )
        elif object_type == "TextAsset":
            try:
                value = obj.read()
                text = decode_text_asset(getattr(value, "m_Script", b""))
                result["text_assets"].append(
                    {
                        "path_id": path_id,
                        "name": str(getattr(value, "m_Name", "")),
                        "text": text,
                        "decoded": bool(text),
                    }
                )
            except Exception as exc:
                result["errors"].append(
                    {"stage": "text_asset", "path_id": path_id, "error": f"{type(exc).__name__}: {exc}"}
                )
        elif object_type in {"Texture2D", "Sprite", "VideoClip", "Font", "Material"}:
            try:
                name = str(obj.peek_name())
            except Exception:
                name = ""
            result["media"].append(
                {"path_id": path_id, "object_type": object_type, "name": name}
            )

    result["object_counts"] = dict(sorted(object_counts.items()))
    result["script_counts"] = dict(sorted(script_counts.items()))
    del env
    gc.collect()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 Unity 콘텐츠 저메모리 전수 인벤토리")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--unity-version", default="6000.2.9f1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))
    candidates = sorted(
        (path for path in args.data_root.rglob("*") if path.is_file() and is_unity_container(path)),
        key=lambda item: item.relative_to(args.data_root).as_posix().lower(),
    )
    files: list[dict[str, Any]] = []
    for index, path in enumerate(candidates, 1):
        print(f"[{index}/{len(candidates)}] {path.relative_to(args.data_root).as_posix()}", flush=True)
        files.append(inventory_file(path, args.data_root, generator))

    report = {
        "schema_version": 1,
        "unity_version": args.unity_version,
        "data_root": str(args.data_root.resolve()),
        "managed_dir": str(args.managed_dir.resolve()),
        "candidate_files": len(candidates),
        "files_with_errors": sum(bool(item["errors"]) for item in files),
        "error_count": sum(len(item["errors"]) for item in files),
        "string_records": sum(len(item["strings"]) for item in files),
        "font_assets": sum(len(item["font_assets"]) for item in files),
        "text_assets": sum(len(item["text_assets"]) for item in files),
        "media_objects": sum(len(item["media"]) for item in files),
        "files": files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

