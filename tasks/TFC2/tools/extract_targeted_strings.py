from __future__ import annotations

import argparse
import gc
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

from inventory_structure import is_unity_container


VISIBLE_UI_CLASSES = {
    "TextMeshProUGUI",
    "TextMeshPro",
    "Text",
    "TMP_Dropdown",
    "TMP_InputField",
    "Dropdown",
}

HEAVY_INTERNAL_CLASSES = {
    "AnimationAtlas",
    "AtlasAnimator",
    "AtlasAnimatorLoadingScene",
    "PathfindingManager",
    "PathfindingUnit",
}


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


def mono_identity(obj: Any) -> tuple[str, str, str, str]:
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


def selected(class_name: str, namespace: str, assembly: str) -> bool:
    if class_name in HEAVY_INTERNAL_CLASSES or namespace.startswith("WieldGames.Animations"):
        return False
    return (
        assembly == "Assembly-CSharp"
        or namespace.startswith("WieldGames")
        or class_name in VISIBLE_UI_CLASSES
        or class_name in {"TMP_FontAsset", "TMP_Settings", "TMP_SpriteAsset"}
        or (assembly == "Unity.Localization" and class_name == "LocalizeStringEvent")
    )


def is_candidate_text(source: str) -> bool:
    return bool(re.search(r"[A-Za-z\u00C0-\u024F]", source)) or "\n" in source


def compact_pointer(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {key: value.get(key) for key in ("m_FileID", "m_PathID") if key in value}


def compact_font(tree: dict[str, Any]) -> dict[str, Any]:
    character_table = tree.get("m_CharacterTable", [])
    glyph_table = tree.get("m_GlyphTable", [])
    atlas_textures = tree.get("m_AtlasTextures", [])
    fallbacks = tree.get("m_FallbackFontAssetTable", [])
    return {
        "name": str(tree.get("m_Name", "")),
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


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 표시 가능 직렬화 문자열과 TMP 글꼴 추출")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--unity-version", default="6000.2.9f1")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))
    candidates = sorted(
        (
            path
            for path in args.data_root.rglob("*")
            if path.is_file()
            and is_unity_container(path)
            and "StreamingAssets/aa/" not in path.relative_to(args.data_root).as_posix()
        ),
        key=lambda item: item.relative_to(args.data_root).as_posix().lower(),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    strings_path = args.output_dir / "targeted_strings.jsonl"
    fonts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    selected_objects = 0
    string_records = 0
    candidate_records = 0

    with strings_path.open("w", encoding="utf-8", newline="\n") as strings_stream:
        for file_index, path in enumerate(candidates, 1):
            relative_path = path.relative_to(args.data_root).as_posix()
            print(f"[{file_index}/{len(candidates)}] {relative_path}", flush=True)
            try:
                env = UnityPy.load(str(path))
                env.typetree_generator = generator
            except Exception as exc:
                errors.append({"file": relative_path, "stage": "load", "error": f"{type(exc).__name__}: {exc}"})
                continue

            for obj in env.objects:
                if obj.type.name != "MonoBehaviour":
                    continue
                try:
                    class_name, namespace, assembly, game_object = mono_identity(obj)
                except Exception as exc:
                    errors.append(
                        {
                            "file": relative_path,
                            "path_id": int(obj.path_id),
                            "stage": "identity",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                if not selected(class_name, namespace, assembly):
                    continue
                selected_objects += 1
                class_counts[f"{namespace}.{class_name}|{assembly}"] += 1
                try:
                    tree = obj.read_typetree()
                except Exception as exc:
                    errors.append(
                        {
                            "file": relative_path,
                            "path_id": int(obj.path_id),
                            "stage": "typetree",
                            "class": class_name,
                            "namespace": namespace,
                            "assembly": assembly,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue

                object_name = str(tree.get("m_Name", ""))
                for field_path, source in iter_strings(tree):
                    row = {
                        "file": relative_path,
                        "path_id": int(obj.path_id),
                        "class": class_name,
                        "namespace": namespace,
                        "assembly": assembly,
                        "game_object": game_object,
                        "object_name": object_name,
                        "field_path": list(field_path),
                        "source": source,
                        "candidate_text": is_candidate_text(source),
                    }
                    strings_stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    string_records += 1
                    candidate_records += int(row["candidate_text"])

                if class_name == "TMP_FontAsset":
                    fonts.append(
                        {
                            "file": relative_path,
                            "path_id": int(obj.path_id),
                            "class": class_name,
                            "namespace": namespace,
                            "assembly": assembly,
                            **compact_font(tree),
                        }
                    )
                del tree
                if selected_objects % 100 == 0:
                    strings_stream.flush()
                    gc.collect()
            del env
            gc.collect()

    report = {
        "schema_version": 1,
        "unity_version": args.unity_version,
        "data_root": str(args.data_root.resolve()),
        "candidate_files": len(candidates),
        "selected_objects": selected_objects,
        "string_records": string_records,
        "candidate_text_records": candidate_records,
        "font_assets": len(fonts),
        "error_count": len(errors),
        "class_counts": dict(sorted(class_counts.items())),
        "fonts": fonts,
        "errors": errors,
    }
    (args.output_dir / "targeted_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in report.items() if key not in {"fonts", "errors", "class_counts"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
