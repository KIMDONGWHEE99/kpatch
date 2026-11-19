"""실제 Steam 설치본 전체가 검증된 후보와 동일한지 확인합니다."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "build_candidate/PIBCREMENTAL_DEMO"
INSTALLED = Path("D:/steam/steamapps/common/Pibcremental Demo")
VALIDATION = ROOT / "validation/PIBCREMENTAL_DEMO"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def inventory(root: Path) -> dict[str, dict]:
    return {
        path.relative_to(root).as_posix(): {"size": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def main() -> None:
    expected = inventory(CANDIDATE)
    actual = inventory(INSTALLED)
    differences = [
        {"path": name, "expected": expected.get(name), "actual": actual.get(name)}
        for name in sorted(set(expected) | set(actual))
        if expected.get(name) != actual.get(name)
    ]
    if differences:
        raise RuntimeError(f"실제 설치본과 후보가 다릅니다: {differences}")
    report = {
        "schema_version": 1,
        "passed": True,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "installed_root": str(INSTALLED),
        "candidate_root": str(CANDIDATE),
        "installed_files": len(actual),
        "candidate_files": len(expected),
        "file_size_or_hash_differences": differences,
        "extra_temporary_files": [],
        "files": actual,
    }
    (VALIDATION / "installed_verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
