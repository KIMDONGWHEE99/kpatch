from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def collect(root: Path, exclude_prefixes: tuple[str, ...]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file())):
        relative_path = path.relative_to(root).as_posix()
        if any(
            relative_path == prefix or relative_path.startswith(prefix + "/")
            for prefix in exclude_prefixes
        ):
            continue
        rows.append(
            {
                "relative_path": relative_path,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 원본 기준선 해시 기록 및 복사본 대조")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--copy", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--exclude-prefix", action="append", default=[])
    args = parser.parse_args()

    exclude_prefixes = tuple(str(value).replace("\\", "/").strip("/") for value in args.exclude_prefix)
    source_rows = collect(args.source, exclude_prefixes)
    copy_rows = collect(args.copy, exclude_prefixes)
    source_map = {str(row["relative_path"]): row for row in source_rows}
    copy_map = {str(row["relative_path"]): row for row in copy_rows}
    all_paths = sorted(set(source_map) | set(copy_map))
    mismatches: list[dict[str, object]] = []
    for relative_path in all_paths:
        source_row = source_map.get(relative_path)
        copy_row = copy_map.get(relative_path)
        if source_row != copy_row:
            mismatches.append(
                {
                    "relative_path": relative_path,
                    "source": source_row,
                    "copy": copy_row,
                }
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("baseline_source_files.csv", source_rows), ("baseline_copy_files.csv", copy_rows)):
        with (args.output_dir / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("relative_path", "size", "sha256"))
            writer.writeheader()
            writer.writerows(rows)

    report = {
        "source_root": str(args.source.resolve()),
        "copy_root": str(args.copy.resolve()),
        "exclude_prefixes": list(exclude_prefixes),
        "source_files": len(source_rows),
        "copy_files": len(copy_rows),
        "source_bytes": sum(int(row["size"]) for row in source_rows),
        "copy_bytes": sum(int(row["size"]) for row in copy_rows),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "passed": not mismatches,
    }
    (args.output_dir / "baseline_comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
