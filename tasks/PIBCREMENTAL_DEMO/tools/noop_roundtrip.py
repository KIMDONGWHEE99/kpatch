from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import UnityPy


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Unity 컨테이너 무변경 재포장 검사")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for source in args.files:
        source_bytes = source.read_bytes()
        environment = UnityPy.load(str(source))
        output_bytes = environment.file.save(packer="original")
        output = args.output_dir / source.name
        output.write_bytes(output_bytes)
        reopened = UnityPy.load(str(output))
        source_objects = {
            (obj.assets_file.name, int(obj.path_id), obj.type.name): sha256(obj.get_raw_data())
            for obj in environment.objects
        }
        output_objects = {
            (obj.assets_file.name, int(obj.path_id), obj.type.name): sha256(obj.get_raw_data())
            for obj in reopened.objects
        }
        changed_keys = sorted(
            set(source_objects) | set(output_objects),
            key=lambda item: (str(item[0]), int(item[1]), str(item[2])),
        )
        changed_keys = [
            key for key in changed_keys if source_objects.get(key) != output_objects.get(key)
        ]
        rows.append(
            {
                "file": source.as_posix(),
                "source_size": len(source_bytes),
                "output_size": len(output_bytes),
                "byte_identical": source_bytes == output_bytes,
                "source_objects": len(environment.objects),
                "output_objects": len(reopened.objects),
                "changed_object_count": len(changed_keys),
                "changed_object_samples": [list(key) for key in changed_keys[:20]],
                "source_sha256": sha256(source_bytes),
                "output_sha256": sha256(output_bytes),
            }
        )

    report = {"schema_version": 1, "files": rows}
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
