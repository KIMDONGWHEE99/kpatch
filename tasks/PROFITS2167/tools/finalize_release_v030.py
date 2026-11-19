from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path


PACKAGE_NAME = "PROFITS2167_Korean_Patch_v0.3.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="0.3.0 배포 체크섬과 ZIP 최종 갱신")
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    args = parser.parse_args()
    release = args.release.resolve()
    outputs = args.outputs.resolve()
    sums_path = release / "SHA256SUMS.txt"
    sums = []
    for path in sorted(item for item in release.rglob("*") if item.is_file() and item != sums_path):
        sums.append(f"{sha256_file(path)}  {path.relative_to(release).as_posix()}")
    sums_path.write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")

    zip_path = outputs / f"{PACKAGE_NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in release.rglob("*") if item.is_file()):
            archive.write(path, (Path(PACKAGE_NAME) / path.relative_to(release)).as_posix())

    with zipfile.ZipFile(zip_path, "r") as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"ZIP CRC 검증 실패: {bad}")
    print(f"{zip_path}\n{zip_path.stat().st_size}\n{sha256_file(zip_path)}")


if __name__ == "__main__":
    main()
