from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def copy_to_root(source: Path, root: Path, relative: str) -> None:
    destination = root / Path(relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def run_ps1(script: Path, game_root: Path, expected_code: int = 0) -> str:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-GamePath",
            str(game_root),
        ],
        capture_output=True,
        check=False,
    )
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if result.returncode != expected_code:
        raise RuntimeError(
            f"PowerShell 종료 코드 불일치: {script.name} "
            f"expected={expected_code} actual={result.returncode}\n{output}"
        )
    return output


def assert_hashes(root: Path, manifest: dict, field: str) -> None:
    errors = []
    for entry in manifest["files"]:
        path = root / Path(entry["relative_path"])
        actual = sha256_file(path)
        expected = entry[field]
        if actual != expected:
            errors.append(f"{entry['relative_path']}: {actual} != {expected}")
    if errors:
        raise RuntimeError("해시 검증 실패:\n" + "\n".join(errors))


def prepare_original_fixture(game: Path, fixture: Path, manifest: dict) -> None:
    for entry in manifest["files"]:
        relative = entry["relative_path"]
        if relative in {
            "PROFITS2167_Data/resources.assets",
            "PROFITS2167_Data/StreamingAssets/aa/catalog.json",
            "PROFITS2167_Data/StreamingAssets/aa/StandaloneWindows64/localization-string-tables-english(en)_assets_all.bundle",
            "PROFITS2167_Data/sharedassets0.assets",
            "PROFITS2167_Data/level0",
        }:
            source = game / ".profits2167_ko_backup" / "0.2.0" / Path(relative)
        else:
            source = game / Path(relative)
        copy_to_root(source, fixture, relative)


def prepare_upgrade_fixture(
    game: Path,
    project: Path,
    fixture: Path,
    manifest: dict,
) -> None:
    v020 = project / "build_candidate" / "v0.2"
    prior_paths = {
        "PROFITS2167_Data/resources.assets",
        "PROFITS2167_Data/StreamingAssets/aa/catalog.json",
        "PROFITS2167_Data/StreamingAssets/aa/StandaloneWindows64/localization-string-tables-english(en)_assets_all.bundle",
        "PROFITS2167_Data/sharedassets0.assets",
        "PROFITS2167_Data/level0",
    }
    for entry in manifest["files"]:
        relative = entry["relative_path"]
        if relative in prior_paths:
            copy_to_root(v020 / Path(relative), fixture, relative)
            original = game / ".profits2167_ko_backup" / "0.2.0" / Path(relative)
            copy_to_root(
                original,
                fixture / ".profits2167_ko_backup" / "0.2.0",
                relative,
            )
        else:
            copy_to_root(game / Path(relative), fixture, relative)


def run_scenario(
    name: str,
    game: Path,
    project: Path,
    release: Path,
    manifest: dict,
    parent: Path,
) -> dict[str, object]:
    fixture = parent / name
    fixture.mkdir(parents=True)
    if name == "fresh":
        prepare_original_fixture(game, fixture, manifest)
    else:
        prepare_upgrade_fixture(game, project, fixture, manifest)

    install_output = run_ps1(release / "install.ps1", fixture)
    assert_hashes(fixture, manifest, "patched_sha256")
    verify_output = run_ps1(release / "verify.ps1", fixture)
    run_ps1(release / "uninstall.ps1", fixture)
    assert_hashes(fixture, manifest, "original_sha256")
    return {
        "scenario": name,
        "install_completed": "0.3.0" in install_output,
        "verify_completed": "0.3.0=12" in verify_output,
        "uninstall_completed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="0.3.0 설치기 격리 QA")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, required=True)
    args = parser.parse_args()
    project = args.project_root.resolve()
    game = args.game_root.resolve()
    release = project / "release_source_v0.3"
    manifest = json.loads((release / "install_manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="qa-v030-", dir=project) as temporary:
        parent = Path(temporary)
        reports = [
            run_scenario("fresh", game, project, release, manifest, parent),
            run_scenario("upgrade", game, project, release, manifest, parent),
        ]
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
