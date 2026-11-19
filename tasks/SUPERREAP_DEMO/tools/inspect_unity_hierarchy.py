#!/usr/bin/env python3
"""Unity 구성요소가 속한 GameObject의 부모 경로와 활성 상태를 조사한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


def deref(pptr: Any) -> Any | None:
    try:
        return pptr.deref_parse_as_object()
    except Exception:
        return None


def game_object_path(component: Any) -> list[dict[str, Any]]:
    head = component.parse_monobehaviour_head()
    game_object = deref(head.m_GameObject)
    if game_object is None:
        return []
    output = []
    current = game_object
    visited: set[int] = set()
    while current is not None:
        reader = current.object_reader
        path_id = int(reader.path_id) if reader is not None else 0
        if path_id in visited:
            break
        visited.add(path_id)
        output.append(
            {
                "path_id": path_id,
                "name": str(getattr(current, "m_Name", "")),
                "active": bool(getattr(current, "m_IsActive", True)),
            }
        )
        transform = None
        for component_ref in getattr(current, "m_Component", []):
            candidate = deref(getattr(component_ref, "component", component_ref))
            if candidate is not None and candidate.__class__.__name__ in {"Transform", "RectTransform"}:
                transform = candidate
                break
        if transform is None:
            break
        father = deref(getattr(transform, "m_Father", None))
        current = deref(getattr(father, "m_GameObject", None)) if father is not None else None
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--path-id", type=int, nargs="+", required=True)
    parser.add_argument("--unity-version", default="2022.3.62f3")
    args = parser.parse_args()

    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))
    env = UnityPy.load(str(args.file))
    env.typetree_generator = generator
    wanted = set(args.path_id)
    rows = []
    for obj in env.objects:
        if int(obj.path_id) not in wanted or obj.type.name != "MonoBehaviour":
            continue
        try:
            head = obj.parse_monobehaviour_head()
            script = deref(head.m_Script)
            class_name = str(getattr(script, "m_ClassName", "")) if script is not None else ""
            rows.append(
                {
                    "serialized_file": str(getattr(obj.assets_file, "name", "")),
                    "path_id": int(obj.path_id),
                    "class": class_name,
                    "hierarchy": game_object_path(obj),
                }
            )
        except Exception as exc:
            rows.append({"path_id": int(obj.path_id), "error": f"{type(exc).__name__}: {exc}"})
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
