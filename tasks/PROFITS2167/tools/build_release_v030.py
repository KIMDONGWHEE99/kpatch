from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


PATCH_VERSION = "0.3.0"
PACKAGE_NAME = "PROFITS2167_Korean_Patch_v0.3.0"
RELATIVE_PATHS = [
    "PROFITS2167_Data/resources.assets",
    "PROFITS2167_Data/StreamingAssets/aa/catalog.json",
    "PROFITS2167_Data/StreamingAssets/aa/StandaloneWindows64/localization-string-tables-english(en)_assets_all.bundle",
    "PROFITS2167_Data/sharedassets0.assets",
    "PROFITS2167_Data/level0",
    "PROFITS2167_Data/level1",
    "PROFITS2167_Data/level2",
    "PROFITS2167_Data/level3",
    "PROFITS2167_Data/level4",
    "PROFITS2167_Data/level5",
    "PROFITS2167_Data/level6",
    "PROFITS2167_Data/il2cpp_data/Metadata/global-metadata.dat",
]
PRIOR_BACKUP_PATHS = set(RELATIVE_PATHS[:5])
UPGRADE_RESOURCE = "PROFITS2167_Data/resources.assets"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_xdelta(xdelta: Path, source: Path, target: Path, patch: Path) -> None:
    patch.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(xdelta), "-e", "-f", "-s", str(source), str(target), str(patch)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"xdelta 생성 실패: {patch}\n{result.stdout}\n{result.stderr}")


def verify_xdelta(xdelta: Path, source: Path, patch: Path, expected: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="profits2167-ko-v030-") as temporary:
        output = Path(temporary) / "decoded.bin"
        result = subprocess.run(
            [str(xdelta), "-d", "-f", "-s", str(source), str(patch), str(output)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"xdelta 검증 복원 실패: {patch}\n{result.stdout}\n{result.stderr}")
        if output.stat().st_size != expected.stat().st_size or sha256_file(output) != sha256_file(expected):
            raise RuntimeError(f"xdelta 복원 결과 불일치: {patch}")


def file_record(path: Path) -> dict[str, object]:
    return {"size": path.stat().st_size, "sha256": sha256_file(path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="PROFITS2167 한국어 패치 0.3.0 배포 빌드")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    args = parser.parse_args()

    project = args.project_root.resolve()
    game = args.game_root.resolve()
    candidate = project / "build_candidate" / "v0.3"
    candidate_v020 = project / "build_candidate" / "v0.2"
    templates = project / "release_templates_v0.3"
    prior_release = project / "release_source_v0.2"
    release = project / "release_source_v0.3"
    zip_path = args.outputs.resolve() / f"{PACKAGE_NAME}.zip"
    if release.exists():
        raise FileExistsError(f"새 배포 폴더가 이미 있습니다: {release}")
    if zip_path.exists():
        raise FileExistsError(f"새 배포 ZIP이 이미 있습니다: {zip_path}")
    release.mkdir(parents=True)

    xdelta_source = prior_release / "tools" / "xdelta3.exe"
    xdelta = release / "tools" / "xdelta3.exe"
    xdelta.parent.mkdir(parents=True)
    shutil.copy2(xdelta_source, xdelta)
    for name in ["Mulmaru-OFL-1.1.txt", "Xdelta-Apache-2.0.txt"]:
        destination = release / "LICENSES" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prior_release / "LICENSES" / name, destination)
    for path in templates.iterdir():
        if path.is_file():
            shutil.copy2(path, release / path.name)

    manifest: dict[str, object] = {
        "patch_id": "PROFITS2167-KO-20260829-03",
        "patch_version": PATCH_VERSION,
        "game": "PROFITS2167",
        "game_build_guid": "ef70fc61842a4a7e88293bd7daf7bd9f",
        "default_game_path": "D:\\steam\\steamapps\\common\\PROFITS2167",
        "prior_backup_versions": ["0.2.0", "0.1.0"],
        "tools": {
            "xdelta": {
                "relative_path": "tools/xdelta3.exe",
                **file_record(xdelta),
                "version": "3.2.0",
            }
        },
        "files": [],
    }

    for relative in RELATIVE_PATHS:
        relative_path = Path(relative)
        final = candidate / relative_path
        if relative in PRIOR_BACKUP_PATHS:
            original = game / ".profits2167_ko_backup" / "0.2.0" / relative_path
        else:
            original = game / relative_path
        if not original.is_file():
            raise FileNotFoundError(f"원본 파일이 없습니다: {original}")
        if not final.is_file():
            raise FileNotFoundError(f"후보 파일이 없습니다: {final}")

        patch_name = relative_path.name + ".xdelta"
        if relative_path.name == "global-metadata.dat":
            patch_name = "global-metadata.dat.xdelta"
        patch = release / "patches" / patch_name
        run_xdelta(xdelta, original, final, patch)
        verify_xdelta(xdelta, original, patch, final)
        entry: dict[str, object] = {
            "relative_path": relative,
            "original_size": original.stat().st_size,
            "original_sha256": sha256_file(original),
            "patched_size": final.stat().st_size,
            "patched_sha256": sha256_file(final),
            "patch_file": f"patches/{patch_name}",
            "patch_size": patch.stat().st_size,
            "patch_sha256": sha256_file(patch),
            "upgrade_sources": [],
        }
        if relative == UPGRADE_RESOURCE:
            upgrade_source = candidate_v020 / relative_path
            upgrade_patch = release / "patches" / "upgrade-v0.2-resources.assets.xdelta"
            rollback_patch = release / "patches" / "rollback-to-v0.2-resources.assets.xdelta"
            run_xdelta(xdelta, upgrade_source, final, upgrade_patch)
            run_xdelta(xdelta, final, upgrade_source, rollback_patch)
            verify_xdelta(xdelta, upgrade_source, upgrade_patch, final)
            verify_xdelta(xdelta, final, rollback_patch, upgrade_source)
            entry["upgrade_sources"] = [
                {
                    "label": "0.1.0/0.2.0 resources.assets",
                    "source_size": upgrade_source.stat().st_size,
                    "source_sha256": sha256_file(upgrade_source),
                    "patch_file": "patches/upgrade-v0.2-resources.assets.xdelta",
                    "patch_size": upgrade_patch.stat().st_size,
                    "patch_sha256": sha256_file(upgrade_patch),
                    "rollback_patch_file": "patches/rollback-to-v0.2-resources.assets.xdelta",
                    "rollback_patch_size": rollback_patch.stat().st_size,
                    "rollback_patch_sha256": sha256_file(rollback_patch),
                }
            ]
        manifest["files"].append(entry)

    manifest_path = release / "install_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    sums = []
    for path in sorted(item for item in release.rglob("*") if item.is_file() and item.name != "SHA256SUMS.txt"):
        sums.append(f"{sha256_file(path)}  {path.relative_to(release).as_posix()}")
    (release / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")

    args.outputs.resolve().mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in release.rglob("*") if item.is_file()):
            archive.write(path, (Path(PACKAGE_NAME) / path.relative_to(release)).as_posix())

    print(
        json.dumps(
            {
                "release": str(release),
                "zip": str(zip_path),
                "zip_size": zip_path.stat().st_size,
                "zip_sha256": sha256_file(zip_path),
                "files": len(manifest["files"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
