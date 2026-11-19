#!/usr/bin/env python3
"""Pibcremental Demo 한글 패치용 VCDIFF 배포본을 만들고 왕복 검증합니다."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def relative_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def run_xdelta(executable: Path, arguments: list[str]) -> None:
    completed = subprocess.run(
        [str(executable), *arguments],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"xdelta 실패({completed.returncode}): {' '.join(arguments)}\n{completed.stdout}"
        )


def create_and_verify_delta(
    executable: Path,
    source: Path,
    target: Path,
    delta: Path,
    expected_target_hash: str,
    roundtrip_root: Path,
) -> dict[str, Any]:
    delta.parent.mkdir(parents=True, exist_ok=True)
    run_xdelta(executable, ["-e", "-f", "-s", str(source), str(target), str(delta)])
    rebuilt = roundtrip_root / f"{delta.parent.name}_{delta.stem}.rebuilt"
    run_xdelta(executable, ["-d", "-f", "-s", str(source), str(delta), str(rebuilt)])
    rebuilt_hash = sha256(rebuilt)
    if rebuilt_hash != expected_target_hash:
        raise RuntimeError(
            f"xdelta 왕복 SHA-256 불일치: {delta} / {rebuilt_hash} / {expected_target_hash}"
        )
    rebuilt.unlink()
    return {
        "delta_size": delta.stat().st_size,
        "delta_sha256": sha256(delta),
        "roundtrip_sha256": rebuilt_hash,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--patch-version", default="1.0.0")
    parser.add_argument("--xdelta", type=Path, required=True)
    parser.add_argument("--xdelta-license", type=Path, required=True)
    parser.add_argument("--release-template", type=Path, required=True)
    parser.add_argument("--out-release", type=Path, required=True)
    parser.add_argument("--validation-out", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve()
    candidate = args.candidate.resolve()
    overlay = args.overlay.resolve()
    xdelta = args.xdelta.resolve()
    release = args.out_release.resolve()
    if release.exists():
        raise RuntimeError(f"배포 폴더가 이미 존재합니다: {release}")

    source_files = relative_files(source)
    candidate_files = relative_files(candidate)
    overlay_files = relative_files(overlay)
    if set(source_files) != set(candidate_files):
        missing = sorted(set(source_files) - set(candidate_files))
        extra = sorted(set(candidate_files) - set(source_files))
        raise RuntimeError(f"후보 파일 구성 불일치: missing={missing[:5]}, extra={extra[:5]}")

    source_hashes = {relative: sha256(path) for relative, path in source_files.items()}
    candidate_hashes = {relative: sha256(path) for relative, path in candidate_files.items()}
    changed = {
        relative
        for relative in source_files
        if source_hashes[relative] != candidate_hashes[relative]
    }
    if changed != set(overlay_files):
        raise RuntimeError(
            "후보 변경 파일과 작업 오버레이가 일치하지 않습니다: "
            f"변경만={sorted(changed - set(overlay_files))[:5]}, "
            f"오버레이만={sorted(set(overlay_files) - changed)[:5]}"
        )
    for relative, overlay_path in overlay_files.items():
        if sha256(overlay_path) != candidate_hashes[relative]:
            raise RuntimeError(f"후보와 오버레이 SHA-256 불일치: {relative}")

    release.mkdir(parents=True)
    (release / "tools").mkdir()
    shutil.copy2(xdelta, release / "tools/xdelta3.exe")
    shutil.copy2(args.xdelta_license.resolve(), release / "tools/LICENSE-APACHE-2.0.txt")

    manifest_files: list[dict[str, Any]] = []
    validation_files: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="pibcremental_xdelta_", dir=release.parent) as temp_name:
        roundtrip_root = Path(temp_name)
        for index, relative in enumerate(sorted(changed), start=1):
            original = source_files[relative]
            patched = candidate_files[relative]
            file_id = f"{index:03d}"
            forward_relative = f"patches/forward/{file_id}.vcdiff"
            reverse_relative = f"patches/reverse/{file_id}.vcdiff"
            forward = create_and_verify_delta(
                xdelta,
                original,
                patched,
                release / forward_relative,
                candidate_hashes[relative],
                roundtrip_root,
            )
            reverse = create_and_verify_delta(
                xdelta,
                patched,
                original,
                release / reverse_relative,
                source_hashes[relative],
                roundtrip_root,
            )
            manifest_files.append(
                {
                    "path": relative,
                    "patched_sha256": candidate_hashes[relative],
                    "patched_size": patched.stat().st_size,
                    "accepted_sources": [
                        {
                            "kind": "original",
                            "sha256": source_hashes[relative],
                            "size": original.stat().st_size,
                            "patch": forward_relative,
                            "patch_sha256": forward["delta_sha256"],
                        }
                    ],
                    "reverse_patch": reverse_relative,
                    "reverse_patch_sha256": reverse["delta_sha256"],
                    "original_sha256": source_hashes[relative],
                    "original_size": original.stat().st_size,
                }
            )
            validation_files.append(
                {
                    "path": relative,
                    "original_sha256": source_hashes[relative],
                    "patched_sha256": candidate_hashes[relative],
                    "forward": forward,
                    "reverse": reverse,
                }
            )
            print(f"[{index:02d}/{len(changed):02d}] 정·역방향 왕복 검증 완료: {relative}", flush=True)

    manifest = {
        "schema_version": 1,
        "patch": {
            "name": "Pibcremental Demo 한국어 패치",
            "version": args.patch_version,
            "steam_app_id": 4780080,
            "steam_build_id": 25008003,
            "unity_version": "6000.4.0f1",
            "game_executable": "Pibcremental.exe",
            "xdelta_sha256": sha256(xdelta),
        },
        "files": manifest_files,
        "guard_files": [
            {
                "path": relative,
                "sha256": source_hashes[relative],
                "size": source_files[relative].stat().st_size,
            }
            for relative in sorted(set(source_files) - changed)
        ],
    }
    (release / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    template_root = args.release_template.resolve()
    for template_file in sorted(template_root.rglob("*")):
        if not template_file.is_file():
            continue
        relative = template_file.relative_to(template_root)
        destination = release / relative
        if destination.exists():
            raise RuntimeError(f"배포 템플릿 파일이 생성 파일과 충돌합니다: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_file, destination)

    release_files = relative_files(release)
    source_hash_set = set(source_hashes.values())
    identical_payloads = [
        relative for relative, path in release_files.items() if sha256(path) in source_hash_set
    ]
    if identical_payloads:
        raise RuntimeError(f"배포본에 원본과 동일한 파일이 포함되었습니다: {identical_payloads}")

    validation = {
        "schema_version": 1,
        "passed": True,
        "source_files": len(source_files),
        "candidate_files": len(candidate_files),
        "changed_files": len(changed),
        "unchanged_files": len(source_files) - len(changed),
        "xdelta_sha256": sha256(xdelta),
        "release_files_at_build": len(release_files),
        "release_bytes_at_build": sum(path.stat().st_size for path in release_files.values()),
        "original_identical_payloads": [],
        "files": validation_files,
    }
    args.validation_out.parent.mkdir(parents=True, exist_ok=True)
    args.validation_out.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in validation.items() if key != "files"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
