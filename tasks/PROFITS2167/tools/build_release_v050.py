from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


PATCH_VERSION = "0.5.1"
PACKAGE_NAME = "PROFITS2167_Korean_Patch_v0.5.1"
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
PRIOR_VERSIONS = ["0.5.0", "0.4.0", "0.3.0", "0.2.0", "0.1.0"]


README = """# PROFITS2167 한국어 패치 0.5.1

게임 빌드 `V0.23.8.12`용 비공식 한국어 패치입니다.

0.5.1은 게임 자산과 실행 코드의 문자열을 전수 검사해 만든 정적 전수 한글화판입니다. 0.5.0과 번역 내용은 같으며, Steam이 어느 드라이브나 라이브러리에 설치되어 있어도 찾을 수 있도록 설치 위치 자동 탐색을 추가했습니다.

## 설치

1. 게임을 완전히 종료합니다.
2. 압축을 풉니다.
3. `설치.bat`을 실행합니다.
4. 설치기가 Steam 기본 폴더와 모든 추가 라이브러리에서 게임을 자동으로 찾은 뒤 0.5.1을 설치합니다.

설치 위치가 여러 개 발견되면 번호로 선택할 수 있습니다. 자동으로 찾지 못하면 게임 폴더 또는 `PROFITS2167.exe`의 경로를 붙여넣으라는 안내가 나옵니다. 폴더를 `설치.bat` 위로 끌어다 놓는 방법도 지원합니다.

명령줄에서 직접 지정하려면 다음처럼 실행하십시오.

```powershell
.\\install.ps1 -GamePath '게임 폴더 전체 경로'
```

설치기는 모든 원본·이전 패치·차이 패치의 SHA-256(파일 지문)을 검사합니다. 원본은 `.profits2167_ko_backup\\0.5.1`에 보관하며, 알 수 없는 파일은 수정하지 않습니다.

## 제거와 상태 확인

- 게임을 종료한 뒤 `제거.bat`을 실행하면 원본으로 복구합니다.
- `검증.bat`은 12개 대상 파일의 상태를 표시합니다.

## 번역 범위와 남겨 둔 영문

- 화면에 표시되는 텍스트 레이어는 전수 검사·번역했습니다.
- `PROFITERRA`, 제작자 이름, 버전 번호, 역 코드처럼 고유명사·식별 정보는 원문을 유지했습니다.
- 튜토리얼의 작은 예시 사진·녹화 영상 안에 촬영 당시 박힌 영문 HUD는 영상 자체의 일부라 유지됩니다. 튜토리얼 제목과 설명 본문은 모두 한국어입니다.
- 제작 과정에서는 실제 게임 폴더를 변경하거나 게임을 자동 실행하지 않았습니다.
"""

RESULT_REPORT = """# 결과 보고서

## 대상

- 게임: PROFITS2167 V0.23.8.12
- 한국어 패치: 0.5.1
- 대상 파일: 12개

## 0.5.0 전수 보강 범위

- 화면 텍스트 자산 1,638행 전수 감사
- IL2CPP 실행 코드의 표시 문자열 260개 한국어 치환
- 장면 7개와 공용 `resources.assets`의 직렬화 문자열 재추출 검증
- 성장 트리의 열차·허브·전초기지·채굴·방어 그룹 이름을 열거형(프로그램 내부 선택지 묶음) 수준에서 한국어화
- 전초기지 상세 정보의 내구도·저장량·광물·전투 인원·탄약·배송·정비·피해 표시 보강
- 근무 완료 팝업, 툴팁, 옵션 예시 문구, 개발 콘솔의 표시 필드까지 보강
- 사용자 제보 화면의 튜토리얼·성장 트리·부스터·결과 통계 문구 포함

## 정적 검증

- 의도한 직렬화 번역값은 후보 파일 재추출 결과에서 누락 0건, 원문 잔존 0건입니다.
- 의도한 실행 코드 번역값 260개는 최종 메타데이터 재추출 결과에서 누락 0건, 원문 잔존 0건입니다.
- 최종 메타데이터 16,414개 문자열을 다시 파싱했습니다.
- Cpp2IL이 최종 메타데이터의 110,366개 메서드를 정상 매핑했습니다.
- 성장 트리 그룹 열거형의 한국어 필드 8개를 생성 DLL에서 다시 확인했습니다.
- 모든 xdelta는 생성 직후 복원해 후보 파일 SHA-256과 비교합니다.
- 격리 복제본에서 원본·0.3.0·0.4.0 상태의 설치와 제거를 검증했습니다.
- 0.5.1 설치기는 임의 위치 지정, 기본 경로 자동 탐색, Steam `libraryfolders.vdf` 추가 라이브러리 탐색을 각각 검증합니다.

## 실행 검수 상태

사용자가 전 구간을 플레이하지 않아도 되도록 정적 전수 검사를 수행했습니다. 다만 실제 게임을 자동 실행하지 않았으므로 런타임 육안 검수를 했다고 표시하지는 않습니다.
"""

KNOWN_ISSUES = """# 알려진 제한

- 튜토리얼의 작은 예시 사진과 녹화 영상 안에 촬영 당시 박힌 영문 HUD는 원본 영상의 일부라 유지됩니다. 제목·설명·버튼 등 실제 텍스트 레이어는 한국어입니다.
- `PROFITERRA`, 제작자 이름, 버전 번호, 역 코드 등 고유명사·식별 정보는 유지했습니다.
- 한국어가 원문보다 길어 매우 좁은 칸에서는 줄바꿈이 달라질 수 있습니다.
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
    with tempfile.TemporaryDirectory(prefix="profits2167-ko-v050-") as temporary:
        output = Path(temporary) / "decoded.bin"
        result = subprocess.run(
            [str(xdelta), "-d", "-f", "-s", str(source), str(patch), str(output)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode or sha256_file(output) != sha256_file(expected):
            raise RuntimeError(f"xdelta 복원 결과 불일치: {patch}\n{result.stdout}\n{result.stderr}")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def prepare_location_aware_script(source: Path, version: str) -> str:
    text = source.read_text(encoding="utf-8-sig").replace("0.5.0", version)
    old_parameter = r"    [string]$GamePath = 'D:\steam\steamapps\common\PROFITS2167'"
    if old_parameter not in text:
        raise RuntimeError(f"GamePath 기본값을 찾지 못했습니다: {source}")
    text = text.replace(old_parameter, "    [string]$GamePath", 1)

    patch_root_line = "$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path"
    if patch_root_line not in text:
        raise RuntimeError(f"PatchRoot 구문을 찾지 못했습니다: {source}")
    text = text.replace(
        patch_root_line,
        patch_root_line + "\n. (Join-Path $PatchRoot 'locate_game.ps1')",
        1,
    )

    multiline_check = """if (-not (Test-Path -LiteralPath $GamePath -PathType Container)) {
    throw \"게임 폴더를 찾을 수 없습니다: $GamePath\"
}
"""
    singleline_check = "if (-not (Test-Path -LiteralPath $GamePath -PathType Container)) { throw \"게임 폴더를 찾을 수 없습니다: $GamePath\" }\n"
    text = text.replace(multiline_check, "", 1).replace(singleline_check, "", 1)

    manifest_line = "$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json"
    if manifest_line not in text:
        manifest_line = "$Manifest = Get-Content -LiteralPath (Join-Path $PatchRoot 'install_manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json"
    if manifest_line not in text:
        raise RuntimeError(f"매니페스트 로드 구문을 찾지 못했습니다: {source}")
    resolve_line = "$GamePath = Resolve-PROFITS2167GamePath -RequestedPath $GamePath -DefaultPath ([string]$Manifest.default_game_path) -PatchRoot $PatchRoot"
    text = text.replace(manifest_line, manifest_line + "\n" + resolve_line, 1)
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="PROFITS2167 한국어 패치 0.5.1 배포 빌드")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    args = parser.parse_args()

    project = args.project_root.resolve()
    game = args.game_root.resolve()
    candidate = project / "build_candidate" / "v0.5"
    prior_release = project / "release_source_v0.5"
    release = project / "release_source_v0.5.1"
    zip_path = args.outputs.resolve() / f"{PACKAGE_NAME}.zip"
    if release.exists() or zip_path.exists():
        raise FileExistsError("0.5.1 배포 폴더 또는 ZIP이 이미 있습니다.")
    release.mkdir(parents=True)

    xdelta = release / "tools" / "xdelta3.exe"
    xdelta.parent.mkdir(parents=True)
    shutil.copy2(prior_release / "tools" / "xdelta3.exe", xdelta)
    for name in ["Mulmaru-OFL-1.1.txt", "Xdelta-Apache-2.0.txt"]:
        destination = release / "LICENSES" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prior_release / "LICENSES" / name, destination)

    templates = project / "release_templates_v0.5"
    shutil.copy2(templates / "locate_game.ps1", release / "locate_game.ps1")
    for name in ["install.ps1", "verify.ps1", "uninstall.ps1"]:
        write_text(release / name, prepare_location_aware_script(prior_release / name, PATCH_VERSION))
    for name in ["설치.bat", "검증.bat", "제거.bat"]:
        shutil.copy2(templates / name, release / name)
    shutil.copy2(prior_release / "THIRD_PARTY_LICENSES.md", release / "THIRD_PARTY_LICENSES.md")
    write_text(release / "README.md", README)
    write_text(release / "RESULT_REPORT.md", RESULT_REPORT)
    write_text(release / "KNOWN_ISSUES.md", KNOWN_ISSUES)

    manifest: dict[str, object] = {
        "patch_id": "PROFITS2167-KO-20260829-051",
        "patch_version": PATCH_VERSION,
        "game": "PROFITS2167",
        "game_build_guid": "ef70fc61842a4a7e88293bd7daf7bd9f",
        "default_game_path": "D:\\steam\\steamapps\\common\\PROFITS2167",
        "prior_backup_versions": PRIOR_VERSIONS,
        "tools": {"xdelta": {"relative_path": "tools/xdelta3.exe", **file_record(xdelta), "version": "3.2.0"}},
        "files": [],
    }

    original_root = game / ".profits2167_ko_backup" / "0.3.0"
    for relative in RELATIVE_PATHS:
        relative_path = Path(relative)
        original = original_root / relative_path
        final = candidate / relative_path
        if not original.is_file() or not final.is_file():
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

        seen_hashes = {entry["original_sha256"], entry["patched_sha256"]}
        for version in PRIOR_VERSIONS:
            prior = project / "build_candidate" / f"v{version.removesuffix('.0')}" / relative_path
            if not prior.is_file():
                continue
            prior_hash = sha256_file(prior)
            if prior_hash in seen_hashes:
                continue
            seen_hashes.add(prior_hash)
            safe_stem = relative_path.name.replace("(", "_").replace(")", "_")
            upgrade_patch = release / "patches" / f"upgrade-v{version}-{safe_stem}.xdelta"
            rollback_patch = release / "patches" / f"rollback-to-v{version}-{safe_stem}.xdelta"
            run_xdelta(xdelta, prior, final, upgrade_patch)
            run_xdelta(xdelta, final, prior, rollback_patch)
            verify_xdelta(xdelta, prior, upgrade_patch, final)
            verify_xdelta(xdelta, final, rollback_patch, prior)
            entry["upgrade_sources"].append(
                {
                    "label": f"{version} {relative_path.name}",
                    "source_size": prior.stat().st_size,
                    "source_sha256": prior_hash,
                    "patch_file": f"patches/{upgrade_patch.name}",
                    "patch_size": upgrade_patch.stat().st_size,
                    "patch_sha256": sha256_file(upgrade_patch),
                    "rollback_patch_file": f"patches/{rollback_patch.name}",
                    "rollback_patch_size": rollback_patch.stat().st_size,
                    "rollback_patch_sha256": sha256_file(rollback_patch),
                }
            )
        manifest["files"].append(entry)

    manifest_path = release / "install_manifest.json"
    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
    sums = []
    for path in sorted(item for item in release.rglob("*") if item.is_file() and item.name != "SHA256SUMS.txt"):
        sums.append(f"{sha256_file(path)}  {path.relative_to(release).as_posix()}")
    write_text(release / "SHA256SUMS.txt", "\n".join(sums) + "\n")

    args.outputs.resolve().mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in release.rglob("*") if item.is_file()):
            archive.write(path, (Path(PACKAGE_NAME) / path.relative_to(release)).as_posix())
    with zipfile.ZipFile(zip_path, "r") as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC 검증 실패: {bad}")
    print(
        json.dumps(
            {
                "release": str(release),
                "zip": str(zip_path),
                "zip_size": zip_path.stat().st_size,
                "zip_sha256": sha256_file(zip_path),
                "files": len(manifest["files"]),
                "upgrade_source_records": sum(len(entry["upgrade_sources"]) for entry in manifest["files"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
