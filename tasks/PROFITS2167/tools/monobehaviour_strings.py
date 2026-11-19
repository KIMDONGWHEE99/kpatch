from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


ROOT_METADATA_FIELDS = {
    "m_Name",
    "m_EditorClassIdentifier",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def make_generator(unity_version: str, managed_dir: Path) -> TypeTreeGenerator:
    generator = TypeTreeGenerator(unity_version)
    generator.load_local_dll_folder(str(managed_dir))
    return generator


def load_environment(path: Path, generator: TypeTreeGenerator) -> Any:
    env = UnityPy.load(str(path))
    env.typetree_generator = generator
    return env


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


def iter_strings(value: Any, path: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], str]]:
    if isinstance(value, str):
        if value.strip():
            yield path, value
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not path and key in ROOT_METADATA_FIELDS:
                continue
            yield from iter_strings(child, path + (key,))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_strings(child, path + (index,))


def get_at_path(tree: Any, path: list[Any]) -> Any:
    current = tree
    for part in path:
        current = current[part]
    return current


def set_at_path(tree: Any, path: list[Any], value: str) -> None:
    if not path:
        raise ValueError("빈 필드 경로는 수정할 수 없습니다.")
    current = tree
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value


def extract_rows(path: Path, generator: TypeTreeGenerator) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    env = load_environment(path, generator)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        class_name, namespace, assembly = script_details(obj)
        try:
            tree = obj.read_typetree()
        except Exception as exc:
            errors.append(
                {
                    "path_id": int(obj.path_id),
                    "class": class_name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        for field_path, source in iter_strings(tree):
            rows.append(
                {
                    "path_id": int(obj.path_id),
                    "class": class_name,
                    "namespace": namespace,
                    "assembly": assembly,
                    "game_object": game_object_name(obj),
                    "field_path": list(field_path),
                    "source": source,
                    "translation": "",
                }
            )
    rows.sort(key=lambda row: (int(row["path_id"]), json.dumps(row["field_path"], ensure_ascii=False)))
    return rows, errors


def validate_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    keys: set[tuple[int, str]] = set()
    for row in rows:
        path_id = int(row["path_id"])
        field_path = list(row["field_path"])
        key = (path_id, json.dumps(field_path, ensure_ascii=False))
        if key in keys:
            errors.append(f"중복 대상: {path_id} {field_path}")
        keys.add(key)
        translation = str(row.get("translation", ""))
        if not translation:
            errors.append(f"번역문 누락: {path_id} {field_path}")
        elif unicodedata.normalize("NFC", translation) != translation:
            errors.append(f"NFC 정규화 오류: {path_id} {field_path}")
    return errors


def command_extract(args: argparse.Namespace) -> None:
    generator = make_generator(args.unity_version, args.managed_dir)
    rows, errors = extract_rows(args.source, generator)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    report = {
        "entries": len(rows),
        "objects_with_errors": len(errors),
        "errors": errors,
        "output": str(args.output),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def command_build(args: argparse.Namespace) -> None:
    rows = json.loads(args.translations.read_text(encoding="utf-8"))
    errors = validate_rows(rows)
    if errors:
        print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    generator = make_generator(args.unity_version, args.managed_dir)
    env = load_environment(args.source, generator)
    objects = {int(obj.path_id): obj for obj in env.objects if obj.type.name == "MonoBehaviour"}
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["path_id"]), []).append(row)

    changed = 0
    for path_id, object_rows in grouped.items():
        if path_id not in objects:
            raise RuntimeError(f"대상 MonoBehaviour를 찾지 못했습니다: {path_id}")
        obj = objects[path_id]
        tree = obj.read_typetree()
        object_changed = False
        for row in object_rows:
            field_path = list(row["field_path"])
            current = str(get_at_path(tree, field_path))
            source = str(row["source"])
            if current != source:
                raise RuntimeError(f"원문 기준선 불일치: {path_id} {field_path}")
            translation = str(row["translation"])
            if translation != source:
                set_at_path(tree, field_path, translation)
                changed += 1
                object_changed = True
        if object_changed:
            obj.save_typetree(tree)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(env.file.save(packer="original")))

    verify_generator = make_generator(args.unity_version, args.managed_dir)
    verify_env = load_environment(args.output, verify_generator)
    verify_objects = {
        int(obj.path_id): obj for obj in verify_env.objects if obj.type.name == "MonoBehaviour"
    }
    post_errors: list[str] = []
    for row in rows:
        path_id = int(row["path_id"])
        try:
            tree = verify_objects[path_id].read_typetree()
            actual = str(get_at_path(tree, list(row["field_path"])))
        except Exception as exc:
            post_errors.append(f"검증 실패: {path_id} {row['field_path']} ({exc})")
            continue
        if actual != str(row["translation"]):
            post_errors.append(f"저장 후 불일치: {path_id} {row['field_path']}")

    report = {
        "entries": len(rows),
        "changed": changed,
        "source_sha256": sha256_file(args.source),
        "output_sha256": sha256_file(args.output),
        "source_size": args.source.stat().st_size,
        "output_size": args.output.stat().st_size,
        "post_build_errors": post_errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if post_errors:
        raise SystemExit(3)


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--unity-version", default="2022.3.62f3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PROFITS2167 MonoBehaviour 문자열 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract")
    add_common_arguments(extract_parser)
    extract_parser.add_argument("--output", type=Path, required=True)
    extract_parser.set_defaults(func=command_extract)

    build_parser_command = subparsers.add_parser("build")
    add_common_arguments(build_parser_command)
    build_parser_command.add_argument("--translations", type=Path, required=True)
    build_parser_command.add_argument("--output", type=Path, required=True)
    build_parser_command.set_defaults(func=command_build)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
