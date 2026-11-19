from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


CORE_FILE_NAMES = {
    "data.unity3d",
    "globalgamemanagers",
    "globalgamemanagers.assets",
    "resources.assets",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def is_unity_container(path: Path) -> bool:
    name = path.name.lower()
    if path.suffix.lower() == ".bundle":
        return True
    if name in CORE_FILE_NAMES:
        return True
    if name.startswith("sharedassets") and path.suffix.lower() == ".assets":
        return True
    if name.startswith("level") and not path.suffix:
        return True
    return False


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


def script_details(obj: Any) -> tuple[str, str, str]:
    try:
        head = obj.parse_monobehaviour_head()
        script = head.m_Script.deref_parse_as_object()
        return (
            str(script.m_ClassName),
            str(script.m_Namespace),
            str(script.m_AssemblyName),
        )
    except Exception:
        return "", "", ""


def game_object_name(obj: Any) -> str:
    try:
        head = obj.parse_monobehaviour_head()
        game_object = head.m_GameObject.deref_parse_as_object()
        return str(game_object.m_Name)
    except Exception:
        return ""


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


def safe_object_name(obj: Any) -> str:
    try:
        value = obj.read()
    except Exception:
        return ""
    return str(getattr(value, "m_Name", ""))


def inventory_file(
    path: Path,
    data_root: Path,
    generator: TypeTreeGenerator,
) -> dict[str, Any]:
    relative_path = path.relative_to(data_root).as_posix()
    result: dict[str, Any] = {
        "relative_path": relative_path,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "object_counts": {},
        "strings": [],
        "localization_tables": [],
        "shared_tables": [],
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

    counts: Counter[str] = Counter()
    for obj in env.objects:
        object_type = obj.type.name
        counts[object_type] += 1
        path_id = int(obj.path_id)
        if object_type == "MonoBehaviour":
            class_name, namespace, assembly = script_details(obj)
            try:
                tree = obj.read_typetree()
            except Exception as exc:
                result["errors"].append(
                    {
                        "stage": "typetree",
                        "path_id": path_id,
                        "class": class_name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            object_name = str(tree.get("m_Name", ""))
            game_object = game_object_name(obj)
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
            if "m_TableData" in tree and "m_LocaleId" in tree:
                result["localization_tables"].append(
                    {
                        "path_id": path_id,
                        "class": class_name,
                        "name": object_name,
                        "locale": tree.get("m_LocaleId"),
                        "shared_data": tree.get("m_SharedData"),
                        "entry_count": len(tree.get("m_TableData", [])),
                        "entries": tree.get("m_TableData", []),
                    }
                )
            if "m_Entries" in tree and "m_TableCollectionName" in tree:
                result["shared_tables"].append(
                    {
                        "path_id": path_id,
                        "name": object_name,
                        "table_collection_name": tree.get("m_TableCollectionName", ""),
                        "table_collection_name_guid": tree.get("m_TableCollectionNameGuid", ""),
                        "entry_count": len(tree.get("m_Entries", [])),
                        "entries": tree.get("m_Entries", []),
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
                    {
                        "stage": "text_asset",
                        "path_id": path_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        elif object_type in {"Texture2D", "Sprite", "VideoClip", "Font"}:
            row: dict[str, Any] = {
                "path_id": path_id,
                "object_type": object_type,
                "name": safe_object_name(obj),
            }
            if object_type == "Texture2D":
                try:
                    value = obj.read()
                    row["width"] = int(getattr(value, "m_Width", 0))
                    row["height"] = int(getattr(value, "m_Height", 0))
                    row["texture_format"] = str(getattr(value, "m_TextureFormat", ""))
                except Exception:
                    pass
            result["media"].append(row)

    result["object_counts"] = dict(sorted(counts.items()))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Pibcremental Demo Unity 콘텐츠 전수 인벤토리")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--unity-version", default="6000.4.0f1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))
    candidates = sorted(
        (path for path in args.data_root.rglob("*") if path.is_file() and is_unity_container(path)),
        key=lambda item: item.relative_to(args.data_root).as_posix().lower(),
    )
    files = [inventory_file(path, args.data_root, generator) for path in candidates]
    report = {
        "schema_version": 1,
        "unity_version": args.unity_version,
        "data_root": str(args.data_root),
        "managed_dir": str(args.managed_dir),
        "candidate_files": len(candidates),
        "files_with_errors": sum(bool(item["errors"]) for item in files),
        "string_records": sum(len(item["strings"]) for item in files),
        "localization_tables": sum(len(item["localization_tables"]) for item in files),
        "shared_tables": sum(len(item["shared_tables"]) for item in files),
        "text_assets": sum(len(item["text_assets"]) for item in files),
        "media_objects": sum(len(item["media"]) for item in files),
        "files": files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "files"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
