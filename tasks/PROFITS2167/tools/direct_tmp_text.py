from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


TOKEN_PATTERN = re.compile(r"%[A-Za-z0-9_.]+%?")
TAG_PATTERN = re.compile(r"<[^>]+>")
BRACE_PATTERN = re.compile(r"\{[^{}]+\}")
NEWLINE_PATTERN = re.compile(r"\r\n|\r|\n")
TMP_CLASSES = {"TextMeshPro", "TextMeshProUGUI"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_generator(unity_version: str, managed_dir: Path) -> TypeTreeGenerator:
    """IL2CPP에서 만든 더미 DLL로 MonoBehaviour 구조를 복원한다."""
    generator = TypeTreeGenerator(unity_version)
    generator.load_local_dll_folder(str(managed_dir))
    return generator


def load_environment(path: Path, generator: TypeTreeGenerator) -> Any:
    env = UnityPy.load(str(path))
    env.typetree_generator = generator
    return env


def pptr_values(value: Any) -> tuple[int, int]:
    if not isinstance(value, dict):
        return 0, 0
    return int(value.get("m_FileID", 0)), int(value.get("m_PathID", 0))


def read_game_object_name(obj: Any) -> str:
    try:
        head = obj.parse_monobehaviour_head()
        game_object = head.m_GameObject.deref_parse_as_object()
        return str(game_object.m_Name)
    except Exception:
        return ""


def iter_tmp_objects(env: Any) -> list[tuple[Any, dict[str, Any], str]]:
    rows: list[tuple[Any, dict[str, Any], str]] = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            head = obj.parse_monobehaviour_head()
            script = head.m_Script.deref_parse_as_object()
            class_name = str(script.m_ClassName)
            if class_name not in TMP_CLASSES or str(script.m_Namespace) != "TMPro":
                continue
            tree = obj.read_typetree()
            rows.append((obj, tree, class_name))
        except Exception:
            continue
    return rows


def extract_rows(path: Path, generator: TypeTreeGenerator) -> list[dict[str, Any]]:
    env = load_environment(path, generator)
    rows: list[dict[str, Any]] = []
    for obj, tree, class_name in iter_tmp_objects(env):
        text = str(tree.get("m_text", ""))
        if not text.strip():
            continue
        font_file_id, font_path_id = pptr_values(tree.get("m_fontAsset"))
        rows.append(
            {
                "path_id": int(obj.path_id),
                "class": class_name,
                "game_object": read_game_object_name(obj),
                "font_file_id": font_file_id,
                "font_path_id": font_path_id,
                "source": text,
                "translation": "",
            }
        )
    return sorted(rows, key=lambda row: int(row["path_id"]))


def control_signature(text: str) -> dict[str, Any]:
    """번역 중 보존해야 할 표시용 제어 문자를 기록한다."""
    return {
        "tokens": TOKEN_PATTERN.findall(text),
        "tags": TAG_PATTERN.findall(text),
        "braces": BRACE_PATTERN.findall(text),
        "newlines": NEWLINE_PATTERN.findall(text),
    }


def validate_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    path_ids = [int(row["path_id"]) for row in rows]
    if len(path_ids) != len(set(path_ids)):
        errors.append("중복 path_id가 있습니다.")
    for row in rows:
        path_id = int(row["path_id"])
        source = str(row["source"])
        translation = str(row.get("translation", ""))
        if not translation:
            errors.append(f"{path_id}: 번역문이 비어 있습니다.")
            continue
        if unicodedata.normalize("NFC", translation) != translation:
            errors.append(f"{path_id}: NFC 정규화가 아닙니다.")
        if control_signature(source) != control_signature(translation):
            errors.append(f"{path_id}: 태그·토큰·줄바꿈 구조가 다릅니다.")
    return errors


def command_extract(args: argparse.Namespace) -> None:
    generator = make_generator(args.unity_version, args.managed_dir)
    rows = extract_rows(args.source, generator)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"entries": len(rows), "output": str(args.output)}, ensure_ascii=False))


def command_merge(args: argparse.Namespace) -> None:
    rows = json.loads(args.entries.read_text(encoding="utf-8"))
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    row_ids = {str(int(row["path_id"])) for row in rows}
    mapping_ids = set(mapping)
    missing = sorted(row_ids - mapping_ids)
    extra = sorted(mapping_ids - row_ids)
    if missing or extra:
        raise RuntimeError(f"path_id 불일치: missing={missing}, extra={extra}")
    for row in rows:
        row["translation"] = str(mapping[str(int(row["path_id"]))])
    errors = validate_rows(rows)
    if errors:
        print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"entries": len(rows), "output": str(args.output)}, ensure_ascii=False))


def command_build(args: argparse.Namespace) -> None:
    rows = json.loads(args.translations.read_text(encoding="utf-8"))
    errors = validate_rows(rows)
    if errors:
        print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    generator = make_generator(args.unity_version, args.managed_dir)
    env = load_environment(args.source, generator)
    objects = {int(obj.path_id): (obj, tree) for obj, tree, _ in iter_tmp_objects(env)}
    changed = 0
    for row in rows:
        path_id = int(row["path_id"])
        if path_id not in objects:
            raise RuntimeError(f"대상 TMP 개체를 찾지 못했습니다: {path_id}")
        obj, tree = objects[path_id]
        if str(tree.get("m_text", "")) != str(row["source"]):
            raise RuntimeError(f"원문 기준선이 다릅니다: {path_id}")
        translation = str(row["translation"])
        if translation != str(row["source"]):
            tree["m_text"] = translation
            obj.save_typetree(tree)
            changed += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(env.file.save(packer="original")))

    verify_generator = make_generator(args.unity_version, args.managed_dir)
    built_rows = extract_rows(args.output, verify_generator)
    built_by_id = {int(row["path_id"]): str(row["source"]) for row in built_rows}
    post_errors = []
    for row in rows:
        if built_by_id.get(int(row["path_id"])) != str(row["translation"]):
            post_errors.append(f"{row['path_id']}: 저장 후 번역문이 일치하지 않습니다.")
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
    parser = argparse.ArgumentParser(description="PROFITS2167 직접 TMP 텍스트 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract")
    add_common_arguments(extract_parser)
    extract_parser.add_argument("--output", type=Path, required=True)
    extract_parser.set_defaults(func=command_extract)

    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--entries", type=Path, required=True)
    merge_parser.add_argument("--mapping", type=Path, required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    merge_parser.set_defaults(func=command_merge)

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
