from __future__ import annotations

import argparse
import gc
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy

from inventory_structure import is_unity_container


ASCII_RUN = re.compile(rb"[\x20-\x7E]{3,}")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 직렬화 객체의 원시 영문 문자열 전수 스캔")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

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
    output_path = args.output_dir / "raw_serialized_strings.jsonl"
    object_counts: Counter[str] = Counter()
    unique_strings: Counter[str] = Counter()
    record_count = 0
    errors: list[dict[str, Any]] = []

    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for file_index, path in enumerate(candidates, 1):
            relative_path = path.relative_to(args.data_root).as_posix()
            print(f"[{file_index}/{len(candidates)}] {relative_path}", flush=True)
            try:
                env = UnityPy.load(str(path))
            except Exception as exc:
                errors.append({"file": relative_path, "stage": "load", "error": f"{type(exc).__name__}: {exc}"})
                continue
            for obj in env.objects:
                if obj.type.name not in {"MonoBehaviour", "TextAsset"}:
                    continue
                if obj.type.name == "MonoBehaviour":
                    class_name, namespace, assembly, game_object = mono_identity(obj)
                else:
                    class_name, namespace, assembly, game_object = "TextAsset", "UnityEngine", "UnityEngine", ""
                object_counts[f"{namespace}.{class_name}|{assembly}"] += 1
                try:
                    raw = bytes(obj.get_raw_data())
                except Exception as exc:
                    errors.append(
                        {
                            "file": relative_path,
                            "path_id": int(obj.path_id),
                            "stage": "raw",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                seen: set[str] = set()
                for match in ASCII_RUN.finditer(raw):
                    source = match.group().decode("ascii", errors="strict").strip()
                    if source in seen or not re.search(r"[A-Za-z]", source):
                        continue
                    seen.add(source)
                    unique_strings[source] += 1
                    row = {
                        "file": relative_path,
                        "path_id": int(obj.path_id),
                        "object_type": obj.type.name,
                        "class": class_name,
                        "namespace": namespace,
                        "assembly": assembly,
                        "game_object": game_object,
                        "byte_offset": match.start(),
                        "source": source,
                    }
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    record_count += 1
            stream.flush()
            del env
            gc.collect()

    summary = {
        "schema_version": 1,
        "data_root": str(args.data_root.resolve()),
        "candidate_files": len(candidates),
        "scanned_objects": sum(object_counts.values()),
        "record_count": record_count,
        "unique_string_count": len(unique_strings),
        "error_count": len(errors),
        "object_counts": dict(sorted(object_counts.items())),
        "frequent_strings": [
            {"source": source, "occurrences": count}
            for source, count in unique_strings.most_common(500)
        ],
        "errors": errors,
    }
    (args.output_dir / "raw_serialized_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in summary.items() if key not in {"object_counts", "frequent_strings", "errors"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

