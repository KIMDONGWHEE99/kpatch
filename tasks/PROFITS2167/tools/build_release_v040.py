from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


PATCH_VERSION = "0.4.0"
PACKAGE_NAME = "PROFITS2167_Korean_Patch_v0.4.0"
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
UPGRADE_PATHS = {
    "PROFITS2167_Data/resources.assets": "resources.assets",
    "PROFITS2167_Data/il2cpp_data/Metadata/global-metadata.dat": "global-metadata.dat",
}


README = """# PROFITS2167 한국어 패치 0.4.0

게임 빌드 `V0.23.8.12`용 비공식 한국어 패치입니다.

0.4.0은 0.3.0에서 영어로 남던 성장 트리·부스터·미니맵·카메라·정비·전투 튜토리얼과 공용 PDA 메뉴·근무 결과 통계를 추가 번역합니다.

## 설치

1. 게임을 완전히 종료합니다.
2. 압축을 풉니다.
3. `설치.bat`을 실행합니다.
4. 설치기가 원본 또는 기존 0.1.0~0.3.0 상태를 확인한 뒤 0.4.0을 설치합니다.

기본 게임 폴더는 `D:\\steam\\steamapps\\common\\PROFITS2167`입니다. 다른 위치라면 PowerShell에서 다음처럼 실행하십시오.

```powershell
.\\install.ps1 -GamePath '게임 폴더 전체 경로'
```

설치기는 파일과 차이 패치의 SHA-256을 검사하고 원본을 `.profits2167_ko_backup\\0.4.0`에 보관합니다. 알 수 없는 파일은 수정하지 않습니다.

## 제거와 상태 확인

- 게임을 종료한 뒤 `제거.bat`을 실행하면 원본으로 복구합니다.
- `검증.bat`은 12개 대상 파일의 상태를 표시합니다.

## 참고

- 로고와 사진 속에 그림으로 박힌 영문은 유지됩니다.
- Steam 파일 무결성 검사나 게임 업데이트는 패치를 원본으로 되돌리거나 설치를 중단시킬 수 있습니다.
- 제작 과정에서는 사용자 게임 폴더를 자동 변경하거나 게임을 실행하지 않았습니다.
"""

RESULT_REPORT = """# 결과 보고서

## 대상

- 게임: PROFITS2167 V0.23.8.12
- 한국어 패치: 0.4.0
- 대상 파일: 12개

## 추가 수정 범위

- IL2CPP 실행 코드 문자열: 총 194개 번역(0.3.0 대비 129개 추가)
- `resources.assets` 공용 TMP 화면 문구: 207개 검사, 131개 번역
- 성장 트리·부스터·미니맵·전체 지도·카메라·전투·정비·배송·데모 안내 전체 포함
- 근무 결과 통계, PDA 메뉴, 성장 화면의 뒤로·선택·부스터 버튼 포함
- 0.3.0의 StringTable 163개, 장면 TMP 758개, 표시 데이터 318개, 기술 데이터 19개, 한국어 글꼴 수정 유지

## 정적 검증

- 공용 TMP 207개는 저장 후 재추출하여 값 일치를 확인했습니다.
- 보내주신 화면의 성장·부스터 제목과 본문은 수정 메타데이터에서 한국어 존재 및 영어 원문 부재를 확인했습니다.
- 수정 메타데이터의 16,414개 문자열을 다시 파싱했고 Il2CppDumper가 버전 31로 정상 분석했습니다.
- 모든 xdelta는 생성 직후 복원해 후보 파일 SHA-256과 비교합니다.
- 격리 복제본에서 `원본 → 0.4.0 → 원본` 및 `0.3.0 → 0.4.0 → 원본`을 검증합니다.

## 실행 검수 상태

정적 자산과 설치기는 검증했지만 실제 게임을 자동 실행하지 않았으므로 최종 육안 확인은 설치 후 필요합니다.
"""

KNOWN_ISSUES = """# 알려진 제한

- `PROFITERRA`, `SIMULATOR 2167` 같은 고유 로고와 화면 장식용 영문은 유지했습니다.
- 튜토리얼 예시 사진 속 작은 영문 HUD는 이미지에 포함되어 있어 그대로 남습니다.
- 개발용·미사용 예시 화면의 영문 자리표시자는 일부 유지했습니다.
- 한국어가 원문보다 길어 좁은 칸의 줄바꿈이 달라질 수 있습니다.
- 게임 업데이트나 다른 모드로 파일이 달라지면 안전을 위해 설치가 중단됩니다.
- 실제 플레이 전 구간의 육안 검수는 수행하지 않았습니다.
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    return {"size": path.stat().st_size, "sha256": sha256_file(path)}


def run_xdelta(xdelta: Path, source: Path, target: Path, patch: Path) -> None:
    patch.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(xdelta), "-e", "-f", "-s", str(source), str(target), str(patch)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"xdelta 생성 실패: {patch}\n{result.stdout}\n{result.stderr}")


def verify_xdelta(xdelta: Path, source: Path, patch: Path, expected: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="profits2167-ko-v040-") as temporary:
        output = Path(temporary) / "decoded.bin"
        result = subprocess.run(
            [str(xdelta), "-d", "-f", "-s", str(source), str(patch), str(output)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode or sha256_file(output) != sha256_file(expected):
            raise RuntimeError(f"xdelta 복원 결과 불일치: {patch}\n{result.stdout}\n{result.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PROFITS2167 한국어 패치 0.4.0 배포 빌드")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    args = parser.parse_args()

    project = args.project_root.resolve()
    game = args.game_root.resolve()
    candidate = project / "build_candidate" / "v0.4"
    prior_candidate = project / "build_candidate" / "v0.3"
    prior_release = project / "release_source_v0.3"
    templates = project / "release_templates_v0.3"
    release = project / "release_source_v0.4"
    zip_path = args.outputs.resolve() / f"{PACKAGE_NAME}.zip"
    if release.exists() or zip_path.exists():
        raise FileExistsError("0.4.0 배포 폴더 또는 ZIP이 이미 있습니다.")
    release.mkdir(parents=True)

    xdelta = release / "tools" / "xdelta3.exe"
    xdelta.parent.mkdir(parents=True)
    shutil.copy2(prior_release / "tools" / "xdelta3.exe", xdelta)
    for name in ["Mulmaru-OFL-1.1.txt", "Xdelta-Apache-2.0.txt"]:
        destination = release / "LICENSES" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prior_release / "LICENSES" / name, destination)

    for name in ["install.ps1", "verify.ps1", "uninstall.ps1"]:
        text = (templates / name).read_text(encoding="utf-8-sig").replace("0.3.0", "0.4.0")
        (release / name).write_text(text, encoding="utf-8", newline="\n")
    for name in ["설치.bat", "검증.bat", "제거.bat", "THIRD_PARTY_LICENSES.md"]:
        shutil.copy2(templates / name, release / name)
    (release / "README.md").write_text(README, encoding="utf-8", newline="\n")
    (release / "RESULT_REPORT.md").write_text(RESULT_REPORT, encoding="utf-8", newline="\n")
    (release / "KNOWN_ISSUES.md").write_text(KNOWN_ISSUES, encoding="utf-8", newline="\n")

    manifest: dict[str, object] = {
        "patch_id": "PROFITS2167-KO-20260829-04",
        "patch_version": PATCH_VERSION,
        "game": "PROFITS2167",
        "game_build_guid": "ef70fc61842a4a7e88293bd7daf7bd9f",
        "default_game_path": "D:\\steam\\steamapps\\common\\PROFITS2167",
        "prior_backup_versions": ["0.3.0", "0.2.0", "0.1.0"],
        "tools": {"xdelta": {"relative_path": "tools/xdelta3.exe", **file_record(xdelta), "version": "3.2.0"}},
        "files": [],
    }

    original_root = game / ".profits2167_ko_backup" / "0.3.0"
    for relative in RELATIVE_PATHS:
        relative_path = Path(relative)
        original = original_root / relative_path
        final = candidate / relative_path
        prior = prior_candidate / relative_path
        if not original.is_file() or not final.is_file() or not prior.is_file():
            raise FileNotFoundError(f"빌드 입력이 없습니다: {relative}")
        patch_name = relative_path.name + ".xdelta"
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
        if relative in UPGRADE_PATHS and sha256_file(prior) != sha256_file(final):
            stem = UPGRADE_PATHS[relative]
            upgrade_patch = release / "patches" / f"upgrade-v0.3-{stem}.xdelta"
            rollback_patch = release / "patches" / f"rollback-to-v0.3-{stem}.xdelta"
            run_xdelta(xdelta, prior, final, upgrade_patch)
            run_xdelta(xdelta, final, prior, rollback_patch)
            verify_xdelta(xdelta, prior, upgrade_patch, final)
            verify_xdelta(xdelta, final, rollback_patch, prior)
            entry["upgrade_sources"] = [{
                "label": f"0.3.0 {stem}",
                "source_size": prior.stat().st_size,
                "source_sha256": sha256_file(prior),
                "patch_file": f"patches/{upgrade_patch.name}",
                "patch_size": upgrade_patch.stat().st_size,
                "patch_sha256": sha256_file(upgrade_patch),
                "rollback_patch_file": f"patches/{rollback_patch.name}",
                "rollback_patch_size": rollback_patch.stat().st_size,
                "rollback_patch_sha256": sha256_file(rollback_patch),
            }]
        manifest["files"].append(entry)

    manifest_path = release / "install_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    sums = []
    for path in sorted(item for item in release.rglob("*") if item.is_file() and item.name != "SHA256SUMS.txt"):
        sums.append(f"{sha256_file(path)}  {path.relative_to(release).as_posix()}")
    (release / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")

    args.outputs.resolve().mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in release.rglob("*") if item.is_file()):
            archive.write(path, (Path(PACKAGE_NAME) / path.relative_to(release)).as_posix())
    with zipfile.ZipFile(zip_path, "r") as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC 검증 실패: {bad}")
    print(json.dumps({"release": str(release), "zip": str(zip_path), "zip_size": zip_path.stat().st_size, "zip_sha256": sha256_file(zip_path), "files": len(manifest["files"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
