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


def copy_file(source: Path, root: Path, relative: str) -> None:
    destination = root / Path(relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def run_ps1(script: Path, game_root: Path, expected_code: int = 0) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-GamePath", str(game_root)],
        capture_output=True,
        check=False,
    )
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if result.returncode != expected_code:
        raise RuntimeError(f"PowerShell 종료 코드 불일치: {script.name} expected={expected_code} actual={result.returncode}\n{output}")
    return output


def assert_hashes(root: Path, manifest: dict, field: str) -> None:
    errors = []
    for entry in manifest["files"]:
        actual = sha256_file(root / Path(entry["relative_path"]))
        if actual != entry[field]:
            errors.append(f"{entry['relative_path']}: {actual} != {entry[field]}")
    if errors:
        raise RuntimeError("해시 검증 실패:\n" + "\n".join(errors))


def prepare_fixture(project: Path, original_root: Path, fixture: Path, manifest: dict, upgrade: bool) -> None:
    source_root = project / "build_candidate" / "v0.3" if upgrade else original_root
    for entry in manifest["files"]:
        relative = entry["relative_path"]
        copy_file(source_root / Path(relative), fixture, relative)
        if upgrade:
            copy_file(original_root / Path(relative), fixture / ".profits2167_ko_backup" / "0.3.0", relative)


def run_scenario(name: str, project: Path, release: Path, original_root: Path, parent: Path, manifest: dict, upgrade: bool) -> dict[str, object]:
    fixture = parent / name
    fixture.mkdir(parents=True)
    prepare_fixture(project, original_root, fixture, manifest, upgrade)
    install_output = run_ps1(release / "install.ps1", fixture)
    assert_hashes(fixture, manifest, "patched_sha256")
    reinstall_output = run_ps1(release / "install.ps1", fixture)
    assert_hashes(fixture, manifest, "patched_sha256")
    verify_output = run_ps1(release / "verify.ps1", fixture)
    run_ps1(release / "uninstall.ps1", fixture)
    assert_hashes(fixture, manifest, "original_sha256")
    run_ps1(release / "uninstall.ps1", fixture)
    return {
        "scenario": name,
        "install_version_seen": "0.4.0" in install_output,
        "idempotent_install_seen": "0.4.0" in reinstall_output,
        "verify_12_of_12": "0.4.0=12" in verify_output,
        "uninstall_restored_original": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="0.4.0 설치기 격리 QA")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, required=True)
    args = parser.parse_args()
    project = args.project_root.resolve()
    game = args.game_root.resolve()
    release = project / "release_source_v0.4"
    manifest = json.loads((release / "install_manifest.json").read_text(encoding="utf-8"))
    original_root = game / ".profits2167_ko_backup" / "0.3.0"
    with tempfile.TemporaryDirectory(prefix="qa-v040-", dir=project) as temporary:
        parent = Path(temporary).resolve()
        if project not in parent.parents:
            raise RuntimeError(f"안전하지 않은 QA 임시 경로: {parent}")
        reports = [
            run_scenario("fresh", project, release, original_root, parent, manifest, False),
            run_scenario("upgrade_from_v030", project, release, original_root, parent, manifest, True),
        ]
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
