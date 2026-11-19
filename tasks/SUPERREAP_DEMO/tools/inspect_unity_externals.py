#!/usr/bin/env python3
"""Unity 컨테이너의 내부 파일과 외부 참조 번호를 점검한다."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import UnityPy


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--path-id", type=int, action="append")
    parser.add_argument("--dependency", type=Path)
    args = parser.parse_args()

    output = []
    for path in args.files:
        inputs = [str(path)]
        if args.dependency is not None:
            inputs.append(str(args.dependency))
        env = UnityPy.load(*inputs)
        selected = []
        if args.path_id is not None:
            selected_ids = set(args.path_id)
            for obj in env.objects:
                if int(obj.path_id) not in selected_ids:
                    continue
                details = {
                    "assets_file": str(getattr(obj.assets_file, "name", "")),
                    "object_type": obj.type.name,
                    "raw_size": len(obj.get_raw_data()),
                }
                if obj.type.name == "MonoBehaviour" and details["raw_size"] >= 28:
                    raw = obj.get_raw_data()
                    script_file_id, script_path_id = struct.unpack_from("<iq", raw, 16)
                    details["raw_script_ptr"] = {
                        "file_id": script_file_id,
                        "path_id": script_path_id,
                    }
                    source_assets = obj.assets_file
                    if script_file_id == 0:
                        script_assets_name = str(getattr(source_assets, "name", ""))
                    else:
                        externals = list(getattr(source_assets, "externals", []))
                        script_assets_name = (
                            Path(str(externals[script_file_id - 1].path)).name
                            if 0 < script_file_id <= len(externals)
                            else ""
                        )
                    for candidate in env.objects:
                        if int(candidate.path_id) != script_path_id:
                            continue
                        candidate_name = Path(str(getattr(candidate.assets_file, "name", ""))).name
                        if candidate_name.lower() != script_assets_name.lower():
                            continue
                        try:
                            script = candidate.read()
                            details["raw_script_name"] = str(getattr(script, "m_Name", ""))
                            details["raw_script_class"] = str(getattr(script, "m_ClassName", ""))
                            details["raw_script_namespace"] = str(getattr(script, "m_Namespace", ""))
                            details["raw_script_assembly"] = str(getattr(script, "m_AssemblyName", ""))
                        except Exception as exc:
                            details["raw_script_error"] = f"{type(exc).__name__}: {exc}"
                        break
                try:
                    value = obj.read()
                    script_ptr = getattr(value, "m_Script", None)
                    if script_ptr is not None:
                        details["script_ptr"] = {
                            "file_id": int(getattr(script_ptr, "file_id", 0)),
                            "path_id": int(getattr(script_ptr, "path_id", 0)),
                        }
                        try:
                            script = script_ptr.read()
                            details["script_name"] = str(getattr(script, "m_Name", ""))
                            details["script_class"] = str(getattr(script, "m_ClassName", ""))
                            details["script_namespace"] = str(getattr(script, "m_Namespace", ""))
                            details["script_assembly"] = str(getattr(script, "m_AssemblyName", ""))
                        except Exception as exc:
                            details["script_error"] = f"{type(exc).__name__}: {exc}"
                except Exception as exc:
                    details["read_error"] = f"{type(exc).__name__}: {exc}"
                try:
                    details["tree"] = obj.read_typetree()
                except Exception as exc:
                    details["typetree_error"] = f"{type(exc).__name__}: {exc}"
                selected.append(details)
        serialized = {}
        for obj in env.objects:
            assets_file = obj.assets_file
            name = str(getattr(assets_file, "name", ""))
            if name in serialized:
                continue
            serialized[name] = [
                {"file_id": index, "path": str(external.path)}
                for index, external in enumerate(getattr(assets_file, "externals", []), 1)
            ]
        output.append({"file": str(path), "serialized_files": serialized, "selected": selected})
    print(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            default=lambda value: f"<bytes {len(value)}>" if isinstance(value, bytes) else str(value),
        )
    )


if __name__ == "__main__":
    main()
