#!/usr/bin/env python3
"""Sprite/Texture2D가 어떤 Unity 객체에서 참조되는지 전수 조사한다."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SuperReap Demo 미디어 참조 감사")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--python-packages", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--media-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unity-version", default="2022.3.62f3")
    return parser.parse_args()


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").lower()


def basename(value: str) -> str:
    return PurePosixPath(normalize_path(value)).name


def iter_pptrs(
    value: Any, field_path: tuple[Any, ...] = ()
) -> Iterable[tuple[tuple[Any, ...], int, int]]:
    if isinstance(value, dict):
        file_id = value.get("m_FileID")
        path_id = value.get("m_PathID")
        if isinstance(file_id, int) and isinstance(path_id, int) and path_id:
            yield field_path, file_id, path_id
        for key, child in value.items():
            yield from iter_pptrs(child, field_path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_pptrs(child, field_path + (index,))


def script_details(obj: Any) -> tuple[str, str, str]:
    if obj.type.name != "MonoBehaviour":
        return "", "", ""
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


def component_details(obj: Any) -> tuple[str, bool | None, bool | None]:
    """구성요소가 속한 GameObject 이름/활성 상태와 구성요소 활성 상태를 읽는다."""
    try:
        data = obj.read()
        game_object_ptr = getattr(data, "m_GameObject", None)
        if game_object_ptr is None:
            return "", None, None
        game_object = game_object_ptr.read()
        component_enabled_value = getattr(data, "m_Enabled", None)
        component_enabled = (
            bool(component_enabled_value)
            if component_enabled_value is not None
            else None
        )
        return (
            str(game_object.m_Name),
            bool(game_object.m_IsActive),
            component_enabled,
        )
    except Exception:
        return "", None, None


def is_structural_reference(object_type: str, field_path: tuple[Any, ...]) -> bool:
    # Sprite가 자신의 Texture2D를 가리키는 관계나 아틀라스 내부 묶음은
    # 화면에서 실제로 사용된다는 증거와 구분한다.
    if object_type in {
        "AssetBundle",
        "PreloadData",
        "ResourceManager",
        "Sprite",
        "SpriteAtlas",
        "Texture2D",
    }:
        return True
    joined = ".".join(str(part) for part in field_path).lower()
    return "spriterenderdata" in joined or "atlas" in joined and object_type == "AssetBundle"


def main() -> None:
    args = parse_args()
    sys.path.insert(0, str(args.python_packages.resolve()))
    import UnityPy  # type: ignore
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator  # type: ignore

    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    media_index = json.loads(args.media_index.read_text(encoding="utf-8-sig"))

    target_rows: list[dict[str, Any]] = []
    target_by_container_path: dict[tuple[str, int], list[int]] = defaultdict(list)
    containers_by_basename: dict[str, set[str]] = defaultdict(set)
    for item in media_index["items"]:
        for reference_index, reference in enumerate(item["references"]):
            row = {
                "target_id": len(target_rows),
                "image_index": int(item["index"]),
                "image_sha256": item["sha256"],
                "width": int(item["width"]),
                "height": int(item["height"]),
                "preview": item["preview"],
                "reference_index": reference_index,
                "file": normalize_path(reference["file"]),
                "path_id": int(reference["path_id"]),
                "object_type": reference["object_type"],
                "name": reference["name"],
                "serialized_file": "",
                "consumer_references": [],
                "structural_references": [],
            }
            target_rows.append(row)
            key = (row["file"], row["path_id"])
            target_by_container_path[key].append(row["target_id"])
            containers_by_basename[basename(row["file"])].add(row["file"])

    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))

    errors: list[dict[str, Any]] = []
    scanned_objects = 0
    pptr_count = 0
    matched_pptrs = 0
    target_object_mismatches: list[dict[str, Any]] = []
    candidate_files = [row["relative_path"] for row in inventory["files"]]

    # 번들 외부 참조는 물리 파일명 대신 내부 CAB(SerializedFile) 이름을 쓴다.
    # 먼저 모든 미디어 대상의 CAB 이름을 확보해야 다른 번들의 프리팹 참조를
    # 정확히 연결할 수 있다.
    containers_by_serialized_file: dict[str, set[str]] = defaultdict(set)
    for relative in candidate_files:
        relative_normalized = normalize_path(relative)
        source_path = args.data_root / Path(relative)
        try:
            env = UnityPy.load(str(source_path))
            env.typetree_generator = generator
        except Exception:
            continue
        for obj in env.objects:
            key = (relative_normalized, int(obj.path_id))
            for target_id in target_by_container_path.get(key, []):
                target = target_rows[target_id]
                if obj.type.name != target["object_type"]:
                    continue
                serialized_file = str(getattr(obj.assets_file, "name", ""))
                target["serialized_file"] = serialized_file
                containers_by_serialized_file[basename(serialized_file)].add(
                    relative_normalized
                )

    for file_number, relative in enumerate(candidate_files, start=1):
        relative_normalized = normalize_path(relative)
        source_path = args.data_root / Path(relative)
        try:
            env = UnityPy.load(str(source_path))
            env.typetree_generator = generator
        except Exception as exc:
            errors.append(
                {
                    "file": relative_normalized,
                    "stage": "load",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        for obj in env.objects:
            scanned_objects += 1
            try:
                tree = obj.read_typetree()
            except Exception as exc:
                errors.append(
                    {
                        "file": relative_normalized,
                        "stage": "typetree",
                        "path_id": int(obj.path_id),
                        "object_type": obj.type.name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            object_name = str(tree.get("m_Name", "")) if isinstance(tree, dict) else ""
            class_name, namespace, assembly = script_details(obj)
            go_name, go_active, component_enabled = component_details(obj)
            serialized_file = str(getattr(obj.assets_file, "name", ""))

            for field_path, file_id, path_id in iter_pptrs(tree):
                pptr_count += 1
                candidate_containers: set[str] = set()
                external_path = ""
                if file_id == 0:
                    candidate_containers.add(relative_normalized)
                else:
                    externals = getattr(obj.assets_file, "externals", [])
                    if 0 < file_id <= len(externals):
                        external_path = str(externals[file_id - 1].path)
                        external_name = basename(external_path)
                        if normalize_path(external_path).startswith("archive:/"):
                            candidate_containers.update(
                                containers_by_serialized_file.get(external_name, set())
                            )
                        else:
                            candidate_containers.update(
                                containers_by_basename.get(external_name, set())
                            )

                target_ids: set[int] = set()
                for container in candidate_containers:
                    target_ids.update(target_by_container_path.get((container, path_id), []))
                if not target_ids:
                    continue

                matched_pptrs += 1
                for target_id in sorted(target_ids):
                    target = target_rows[target_id]
                    # 같은 PathID가 다른 내부 파일에 우연히 겹칠 때의 오탐을 제거한다.
                    target_sf = str(target.get("serialized_file", ""))
                    if file_id == 0 and target_sf and serialized_file and target_sf != serialized_file:
                        continue
                    if int(obj.path_id) == path_id and relative_normalized == target["file"]:
                        continue
                    reference = {
                        "file": relative_normalized,
                        "serialized_file": serialized_file,
                        "path_id": int(obj.path_id),
                        "object_type": obj.type.name,
                        "object_name": object_name,
                        "class": class_name,
                        "namespace": namespace,
                        "assembly": assembly,
                        "game_object": go_name,
                        "game_object_active": go_active,
                        "component_enabled": component_enabled,
                        "field_path": list(field_path),
                        "file_id": file_id,
                        "external_path": external_path,
                    }
                    bucket = (
                        "structural_references"
                        if is_structural_reference(obj.type.name, field_path)
                        else "consumer_references"
                    )
                    target[bucket].append(reference)

        print(
            f"[{file_number}/{len(candidate_files)}] {relative_normalized}",
            file=sys.stderr,
            flush=True,
        )

    for target in target_rows:
        if not target["serialized_file"]:
            target_object_mismatches.append(
                {
                    "file": target["file"],
                    "path_id": target["path_id"],
                    "object_type": target["object_type"],
                    "name": target["name"],
                }
            )
        target["consumer_reference_count"] = len(target["consumer_references"])
        target["structural_reference_count"] = len(target["structural_references"])

    image_rollup: dict[int, dict[str, Any]] = {}
    for target in target_rows:
        index = target["image_index"]
        row = image_rollup.setdefault(
            index,
            {
                "image_index": index,
                "image_sha256": target["image_sha256"],
                "width": target["width"],
                "height": target["height"],
                "preview": target["preview"],
                "target_ids": [],
                "consumer_reference_count": 0,
                "structural_reference_count": 0,
            },
        )
        row["target_ids"].append(target["target_id"])
        row["consumer_reference_count"] += target["consumer_reference_count"]
        row["structural_reference_count"] += target["structural_reference_count"]

    consumer_types = Counter()
    for target in target_rows:
        for reference in target["consumer_references"]:
            consumer_types[reference["object_type"]] += 1

    report = {
        "schema_version": 1,
        "data_root": str(args.data_root),
        "candidate_files": len(candidate_files),
        "scanned_objects": scanned_objects,
        "pptrs": pptr_count,
        "matched_pptrs": matched_pptrs,
        "target_objects": len(target_rows),
        "images": len(image_rollup),
        "images_with_consumers": sum(
            row["consumer_reference_count"] > 0 for row in image_rollup.values()
        ),
        "target_objects_with_consumers": sum(
            row["consumer_reference_count"] > 0 for row in target_rows
        ),
        "consumer_types": dict(consumer_types.most_common()),
        "target_object_mismatches": target_object_mismatches,
        "errors": errors,
        "image_rollup": sorted(image_rollup.values(), key=lambda row: row["image_index"]),
        "targets": target_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "candidate_files": report["candidate_files"],
                "scanned_objects": report["scanned_objects"],
                "pptrs": report["pptrs"],
                "matched_pptrs": report["matched_pptrs"],
                "images": report["images"],
                "images_with_consumers": report["images_with_consumers"],
                "target_objects_with_consumers": report["target_objects_with_consumers"],
                "target_object_mismatches": len(target_object_mismatches),
                "errors": len(errors),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
