from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


PATCH_VERSION = "0.5.1"
RELEASE_DIRECTORY = "release_source_v0.5.1"


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


def run_ps1(
    script: Path,
    game_root: Path | None,
    expected_code: int = 0,
    extra_env: dict[str, str] | None = None,
) -> str:
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    if game_root is not None:
        command.extend(["-GamePath", str(game_root)])
    result = subprocess.run(
        command,
        capture_output=True,
        check=False,
        env={**os.environ, **(extra_env or {})},
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
        actual = sha256_file(root / Path(entry["relative_path"]))
        if actual != entry[field]:
            errors.append(f"{entry['relative_path']}: {actual} != {entry[field]}")
    if errors:
        raise RuntimeError("해시 검증 실패:\n" + "\n".join(errors))


def prepare_fixture(
    source_root: Path,
    original_root: Path,
    game_executable: Path,
    fixture: Path,
    manifest: dict,
    backup_version: str | None,
) -> None:
    shutil.copy2(game_executable, fixture / "PROFITS2167.exe")
    for entry in manifest["files"]:
        relative = entry["relative_path"]
        source = source_root / Path(relative)
        if not source.is_file():
            source = original_root / Path(relative)
        copy_file(source, fixture, relative)
        if backup_version is not None:
            copy_file(original_root / Path(relative), fixture / ".profits2167_ko_backup" / backup_version, relative)


def run_scenario(
    name: str,
    source_root: Path,
    backup_version: str | None,
    release: Path,
    original_root: Path,
    game_executable: Path,
    parent: Path,
    manifest: dict,
) -> dict[str, object]:
    fixture = parent / name
    fixture.mkdir(parents=True)
    prepare_fixture(source_root, original_root, game_executable, fixture, manifest, backup_version)
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
        "install_version_seen": PATCH_VERSION in install_output,
        "idempotent_install_seen": PATCH_VERSION in reinstall_output,
        "verify_12_of_12": f"{PATCH_VERSION}=12" in verify_output,
        "uninstall_restored_original": True,
    }


def run_unknown_file_scenario(
    release: Path,
    original_root: Path,
    game_executable: Path,
    parent: Path,
    manifest: dict,
) -> dict[str, object]:
    fixture = parent / "unknown_file_rejection"
    fixture.mkdir(parents=True)
    prepare_fixture(original_root, original_root, game_executable, fixture, manifest, None)
    victim = fixture / Path(manifest["files"][0]["relative_path"])
    with victim.open("ab") as stream:
        stream.write(b"QA")
    before = sha256_file(victim)
    output = run_ps1(release / "install.ps1", fixture, expected_code=1)
    after = sha256_file(victim)
    return {
        "scenario": "unknown_file_rejection",
        "rejected_with_nonzero_exit": True,
        "diagnostic_output_present": bool(output.strip()),
        "unknown_file_unchanged": before == after,
    }


def run_auto_default_scenario(
    release: Path,
    original_root: Path,
    game_executable: Path,
    parent: Path,
    manifest: dict,
) -> dict[str, object]:
    package = parent / "auto_package"
    shutil.copytree(release, package)
    fixture = parent / "auto_default_location"
    fixture.mkdir(parents=True)
    prepare_fixture(original_root, original_root, game_executable, fixture, manifest, None)
    local_manifest_path = package / "install_manifest.json"
    local_manifest = json.loads(local_manifest_path.read_text(encoding="utf-8"))
    local_manifest["default_game_path"] = str(fixture)
    local_manifest_path.write_text(json.dumps(local_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    isolated_locator = {"PROFITS2167_LOCATOR_SKIP_SYSTEM": "1"}
    install_output = run_ps1(package / "install.ps1", None, extra_env=isolated_locator)
    assert_hashes(fixture, manifest, "patched_sha256")
    verify_output = run_ps1(package / "verify.ps1", None, extra_env=isolated_locator)
    run_ps1(package / "uninstall.ps1", None, extra_env=isolated_locator)
    assert_hashes(fixture, manifest, "original_sha256")
    return {
        "scenario": "auto_default_location",
        "auto_detected_without_gamepath_argument": True,
        "installer_output_present": bool(install_output.strip()),
        "verify_12_of_12": f"{PATCH_VERSION}=12" in verify_output,
        "uninstall_restored_original": True,
    }


def quote_ps1(value: Path) -> str:
    return str(value).replace("'", "''")


def run_libraryfolders_scenario(release: Path, parent: Path) -> dict[str, object]:
    steam_root = parent / "fake_steam"
    library_root = parent / "custom_library"
    game_root = library_root / "steamapps" / "common" / "PROFITS2167"
    (steam_root / "steamapps").mkdir(parents=True)
    (game_root / "PROFITS2167_Data").mkdir(parents=True)
    (game_root / "PROFITS2167.exe").write_bytes(b"locator test")
    escaped_library = str(library_root).replace("\\", "\\\\")
    (steam_root / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n  "1"\n  {{\n    "path"  "{escaped_library}"\n  }}\n}}\n',
        encoding="utf-8",
    )
    command = (
        f". '{quote_ps1(release / 'locate_game.ps1')}'; "
        f"Resolve-PROFITS2167GamePath -RequestedPath '' -DefaultPath '' "
        f"-PatchRoot '{quote_ps1(release)}' "
        f"-AdditionalSteamRoots @('{quote_ps1(steam_root)}') -SkipSystemDiscovery"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        check=False,
    )
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"libraryfolders.vdf 자동 탐색 실패:\n{output}")
    return {
        "scenario": "steam_libraryfolders_detection",
        "custom_library_found": str(game_root).lower() in output.lower(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="0.5.1 설치기 격리 QA")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, required=True)
    args = parser.parse_args()
    project = args.project_root.resolve()
    game = args.game_root.resolve()
    release = project / RELEASE_DIRECTORY
    manifest = json.loads((release / "install_manifest.json").read_text(encoding="utf-8"))
    original_root = game / ".profits2167_ko_backup" / "0.3.0"
    game_executable = game / "PROFITS2167.exe"
    scenarios = [
        ("fresh", original_root, None),
        ("upgrade_from_v040", project / "build_candidate" / "v0.4", "0.4.0"),
        ("upgrade_from_v030", project / "build_candidate" / "v0.3", "0.3.0"),
    ]
    with tempfile.TemporaryDirectory(prefix="qa-v050-", dir=project) as temporary:
        parent = Path(temporary).resolve()
        if project not in parent.parents:
            raise RuntimeError(f"안전하지 않은 QA 임시 경로: {parent}")
        reports = [
            run_scenario(name, source, backup, release, original_root, game_executable, parent, manifest)
            for name, source, backup in scenarios
        ]
        reports.append(run_auto_default_scenario(release, original_root, game_executable, parent, manifest))
        reports.append(run_libraryfolders_scenario(release, parent))
        reports.append(run_unknown_file_scenario(release, original_root, game_executable, parent, manifest))
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
