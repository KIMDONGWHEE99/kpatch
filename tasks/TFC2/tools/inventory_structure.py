from __future__ import annotations

import argparse
import gc
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy


CORE_FILE_NAMES = {
    "globalgamemanagers",
    "globalgamemanagers.assets",
    "resources.assets",
    "unity default resources",
    "unity_builtin_extra",
}


def is_unity_container(path: Path) -> bool:
    name = path.name.lower()
    return (
        path.suffix.lower() == ".bundle"
        or name in CORE_FILE_NAMES
        or (name.startswith("sharedassets") and path.suffix.lower() == ".assets")
        or (name.startswith("level") and not path.suffix)
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def safe_peek_name(obj: Any) -> str:
    try:
        return str(obj.peek_name())
    except Exception:
        return ""


def mono_identity(obj: Any) -> tuple[str, str, str, str]:
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


def inventory_file(path: Path, data_root: Path) -> dict[str, Any]:
    relative_path = path.relative_to(data_root).as_posix()
    result: dict[str, Any] = {
        "relative_path": relative_path,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "object_counts": {},
        "script_counts": {},
        "monobehaviours": [],
        "media": [],
        "errors": [],
    }
    try:
        env = UnityPy.load(str(path))
    except Exception as exc:
        result["errors"].append({"stage": "load", "error": f"{type(exc).__name__}: {exc}"})
        return result

    object_counts: Counter[str] = Counter()
    script_counts: Counter[str] = Counter()
    for obj in env.objects:
        object_type = obj.type.name
        object_counts[object_type] += 1
        if object_type == "MonoBehaviour":
            class_name, namespace, assembly, game_object = mono_identity(obj)
            script_key = f"{namespace}.{class_name}|{assembly}"
            script_counts[script_key] += 1
            result["monobehaviours"].append(
                {
                    "path_id": int(obj.path_id),
                    "class": class_name,
                    "namespace": namespace,
                    "assembly": assembly,
                    "game_object": game_object,
                    "name": safe_peek_name(obj),
                }
            )
        elif object_type in {"Texture2D", "Sprite", "VideoClip", "Font", "Material", "SpriteAtlas"}:
            result["media"].append(
                {
                    "path_id": int(obj.path_id),
                    "object_type": object_type,
                    "name": safe_peek_name(obj),
                }
            )
    result["object_counts"] = dict(sorted(object_counts.items()))
    result["script_counts"] = dict(sorted(script_counts.items()))
    del env
    gc.collect()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 Unity 객체·스크립트·미디어 구조 인벤토리")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidates = sorted(
        (path for path in args.data_root.rglob("*") if path.is_file() and is_unity_container(path)),
        key=lambda item: item.relative_to(args.data_root).as_posix().lower(),
    )
    files: list[dict[str, Any]] = []
    for index, path in enumerate(candidates, 1):
        print(f"[{index}/{len(candidates)}] {path.relative_to(args.data_root).as_posix()}", flush=True)
        files.append(inventory_file(path, args.data_root))
        partial = {
            "schema_version": 1,
            "data_root": str(args.data_root.resolve()),
            "candidate_files": len(candidates),
            "completed_files": len(files),
            "files": files,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(partial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "schema_version": 1,
        "data_root": str(args.data_root.resolve()),
        "candidate_files": len(candidates),
        "completed_files": len(files),
        "files_with_errors": sum(bool(item["errors"]) for item in files),
        "error_count": sum(len(item["errors"]) for item in files),
        "monobehaviour_count": sum(len(item["monobehaviours"]) for item in files),
        "media_object_count": sum(len(item["media"]) for item in files),
        "files": files,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

