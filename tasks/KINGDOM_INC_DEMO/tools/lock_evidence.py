"""도구·글꼴·원본 빌드의 현재 지문을 비공개 기록으로 고정합니다."""
from common import ROOT, WORK, SOURCE, EXTRACT, DATA, GAME_ID, BUILD, sha, write_json
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import hashlib
import importlib
import json
import platform
import re
import shutil
import subprocess
import sys

OUTPUT = WORK / "toolchain_lock.json"
TASK = ROOT / "tasks" / GAME_ID
DEPS = ROOT / "tools" / "python_deps"
ERRORS = []


def file_record(path, required=True):
    path = Path(path).resolve()
    if not path.is_file():
        if required:
            ERRORS.append(f"필수 파일 없음: {path}")
        return {"path": str(path), "status": "UNKNOWN"}
    before = path.stat()
    digest = sha(path)
    after = path.stat()
    stable = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    if not stable:
        ERRORS.append(f"해시 수집 중 파일 변경: {path}")
    return {"path": str(path), "size": after.st_size, "sha256": digest,
            "status": "PASS" if stable else "STALE"}


def tree_record(path, excluded=()):
    path = Path(path).resolve()
    files = []
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(path)
        if "__pycache__" in rel.parts or item.suffix in {".pyc", ".pyo"}:
            continue
        if any(part in excluded for part in rel.parts):
            continue
        record = file_record(item)
        record["relative_path"] = rel.as_posix()
        files.append(record)
    if not files:
        ERRORS.append(f"빈 도구 경로: {path}")
    # 운영체제의 디렉터리 열거 순서에 좌우되지 않는 내용 지문입니다.
    stable_rows = [{"path": item["relative_path"], "size": item["size"],
                    "sha256": item["sha256"]} for item in files if item["status"] == "PASS"]
    manifest = json.dumps(stable_rows, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    return {"path": str(path), "file_count": len(files), "files": files,
            "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "exclusions": ["__pycache__", "*.pyc", "*.pyo", *excluded]}


def command(args):
    try:
        result = subprocess.run([str(value) for value in args], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=45, creationflags=0x08000000)
        record = {"argv": [str(value) for value in args], "exit_code": result.returncode,
                  "stdout": result.stdout.strip(), "stderr": result.stderr.strip(),
                  "status": "PASS" if result.returncode == 0 else "FAIL"}
    except (OSError, subprocess.TimeoutExpired) as error:
        record = {"argv": [str(value) for value in args], "status": "FAIL", "error": str(error)}
    if record["status"] != "PASS":
        ERRORS.append(f"버전 조회 실패: {record['argv']}")
    return record


def pe_versions(paths):
    # 파일을 실행하지 않고 Windows 파일 버전과 관리 어셈블리 이름만 읽습니다.
    script = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$paths = ConvertFrom-Json ([Console]::In.ReadToEnd())
$rows = @()
foreach ($p in $paths) {
  $v = (Get-Item -LiteralPath $p).VersionInfo
  $a = $null
  try { $a = [System.Reflection.AssemblyName]::GetAssemblyName($p).FullName } catch {}
  $rows += @{path=$p;file_version=$v.FileVersion;product_version=$v.ProductVersion;assembly_name=$a}
}
ConvertTo-Json -InputObject @($rows) -Depth 4 -Compress
"""
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                            input=json.dumps([str(p.resolve()) for p in paths], ensure_ascii=False),
                            capture_output=True, text=True, encoding="utf-8",
                            timeout=45, creationflags=0x08000000)
    if result.returncode:
        ERRORS.append("파일 버전 읽기 실패: " + result.stderr[:500])
        return []
    return json.loads(result.stdout.lstrip("\ufeff"))


def package_record(distribution_name, module_name):
    distribution = metadata.distribution(distribution_name)
    module = importlib.import_module(module_name)
    module_file = Path(module.__file__).resolve()
    info_dir = Path(distribution._path).resolve()
    return {
        "distribution": distribution.metadata["Name"], "version": distribution.version,
        "module_path": str(module_file), "metadata_path": str(info_dir),
        "module_tree": tree_record(module_file.parent),
        "metadata_files": tree_record(info_dir),
        "declared_dependencies": distribution.requires or [],
        "loaded_from_expected_dependencies": module_file.is_relative_to(DEPS.resolve()),
    }


def font_record(path):
    from fontTools.ttLib import TTFont
    with TTFont(path) as font:
        return file_record(path) | {
            "family": font["name"].getDebugName(1), "style": font["name"].getDebugName(2),
            "version": font["name"].getDebugName(5),
            "postscript_name": font["name"].getDebugName(6),
            "glyph_count": font["maxp"].numGlyphs,
            "unicode_codepoints": len(font.getBestCmap()),
            "variable_axes": [{
                "tag": axis.axisTag, "minimum": axis.minValue,
                "default": axis.defaultValue, "maximum": axis.maxValue,
            } for axis in font["fvar"].axes] if "fvar" in font else [],
        }


started = datetime.now(timezone.utc).isoformat()
baseline_path = EXTRACT / "baseline.json"
baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
baseline_rows = []
for expected in baseline["files"]:
    observed = file_record(SOURCE / expected["path"])
    match = observed.get("sha256") == expected["sha256"] and observed.get("size") == expected["size"]
    if not match:
        ERRORS.append("원본 사본 지문 불일치: " + expected["path"])
    baseline_rows.append({"relative_path": expected["path"], "expected_sha256": expected["sha256"],
                          "expected_size": expected["size"], "observed": observed,
                          "status": "PASS" if match else "FAIL"})
actual_paths = {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file()}
expected_paths = {row["path"] for row in baseline["files"]}
extra = sorted(actual_paths - expected_paths)
missing = sorted(expected_paths - actual_paths)
if extra or missing:
    ERRORS.append("원본 파일 집합 차이")

packages = [
    package_record("UnityPy", "UnityPy"),
    package_record("TypeTreeGeneratorAPI", "TypeTreeGeneratorAPI"),
    package_record("fonttools", "fontTools"),
]
for package in packages:
    if not package["loaded_from_expected_dependencies"]:
        ERRORS.append("예상 경로 밖에서 불러온 패키지: " + package["distribution"])
dependencies = []
for distribution in metadata.distributions(path=[str(DEPS)]):
    dependencies.append({"name": distribution.metadata["Name"],
                         "version": distribution.version,
                         "metadata": file_record(Path(distribution._path) / "METADATA")})

dotnet = Path(shutil.which("dotnet") or r"C:\Program Files\dotnet\dotnet.exe")
dotnet_version = command([dotnet, "--version"])
dotnet_sdks = command([dotnet, "--list-sdks"])
dotnet_runtimes = command([dotnet, "--list-runtimes"])
sdk_version = dotnet_version.get("stdout", "").strip()
sdk = dotnet.parent / "sdk" / sdk_version
sdk_primary = [sdk / name for name in ("dotnet.dll", "MSBuild.dll", "Roslyn/bincore/csc.dll")]
sdk_primary = [path for path in sdk_primary if path.is_file()]
runtime_records = []
for line in dotnet_runtimes.get("stdout", "").splitlines():
    match = re.fullmatch(r"(\S+) (\S+) \[(.+)]", line.strip())
    if match:
        framework, version, base = match.groups()
        runtime_dir = Path(base) / version
        primary = [runtime_dir / name for name in
                   ("coreclr.dll", "hostpolicy.dll", "System.Private.CoreLib.dll",
                    "Microsoft.AspNetCore.dll", "WindowsBase.dll")]
        runtime_records.append({"framework": framework, "version": version,
                                "path": str(runtime_dir),
                                "primary_files": [file_record(path) for path in primary if path.is_file()]})
hostfxr = sorted((dotnet.parent / "host" / "fxr").glob("*/hostfxr.dll"))
cecil_source = ROOT / "tasks/THE_LOOPLER/tools/CodeMap/bin/Debug/net8.0/Mono.Cecil.dll"
cecil_paths = [cecil_source] + sorted((WORK / "toolchain").rglob("Mono.Cecil.dll"))
cecil_paths = [path for path in cecil_paths if path.is_file()]
if not cecil_paths:
    ERRORS.append("Mono.Cecil 경로를 찾지 못했습니다.")

xdelta_root = ROOT / "tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0"
xdelta = xdelta_root / "extracted/xdelta3-3.2.0-windows-x86_64/xdelta3.exe"
xdelta_version = command([xdelta, "-V"])
font_source = ROOT / "tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf"
font_license = font_source.parent / "OFL.txt"
font_static = WORK / "fonts/NotoSansKR-Regular.ttf"
license_text = font_license.read_text(encoding="utf-8-sig")
license_version = re.search(r"SIL OPEN FONT LICENSE Version ([^\r\n]+)", license_text)

versions_path = EXTRACT / "versions.json"
engine_versions = json.loads(versions_path.read_text(encoding="utf-8"))
engine_observed = {}
import UnityPy
for name, expected_version in engine_versions.items():
    observed_version = UnityPy.load(str(DATA / name)).file.unity_version
    engine_observed[name] = {"expected_version": expected_version,
                             "observed_version": observed_version,
                             "asset": file_record(DATA / name),
                             "status": "PASS" if expected_version == observed_version else "FAIL"}
    if expected_version != observed_version:
        ERRORS.append("엔진 헤더 버전 불일치: " + name)
mono_files = sorted(SOURCE.glob("MonoBleedingEdge/EmbedRuntime/mono-2.0-*.dll"))
managed = DATA / "Managed" / "Assembly-CSharp.dll"
is_mono = bool(mono_files) and managed.exists() and not (SOURCE / "GameAssembly.dll").exists()
if not is_mono:
    ERRORS.append("예상한 Mono 구조와 다릅니다.")

appmanifest = EXTRACT / "appmanifest.acf"
manifest_text = appmanifest.read_text(encoding="utf-8")
steam_ids = {}
for key in ("appid", "buildid", "name"):
    match = re.search(r'"' + key + r'"\s+"([^"]+)"', manifest_text)
    steam_ids[key] = match.group(1) if match else None
if steam_ids.get("appid") != "4702410" or steam_ids.get("buildid") != "25631786":
    ERRORS.append("Steam 앱 또는 빌드 번호 불일치")

binary_paths = [Path(sys.executable), Path(sys.executable).parent / "python310.dll", dotnet,
                *hostfxr, *sdk_primary, *cecil_paths, xdelta, SOURCE / "UnityPlayer.dll",
                SOURCE / "KingdomInc.exe", *mono_files]
binary_metadata = pe_versions([path for path in binary_paths if path.is_file()])
tools = tree_record(TASK / "tools", excluded=("bin", "obj"))
release_templates = tree_record(TASK / "release_template")
generated = tree_record(WORK / "toolchain", excluded=("bin", "obj"))
result = {
    "schema_version": 1,
    "status": "PASS" if not ERRORS else "FAIL",
    "scope": "현재 존재하는 제작 입력의 경로·버전·내용 지문 기록입니다. 게임 실행·화면 검수·설치·배포 성공 판정이 아닙니다.",
    "game_id": GAME_ID, "build": BUILD, "started_at_utc": started,
    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    "errors": ERRORS,
    "python": {
        "version": sys.version, "implementation": platform.python_implementation(),
        "architecture": platform.architecture()[0],
        "executable": file_record(sys.executable),
        "runtime_library": file_record(Path(sys.executable).parent / "python310.dll"),
        "standard_library_scope": "표준 라이브러리 전체 해시는 수집하지 않았으며 실행 파일·핵심 런타임과 버전을 고정했습니다.",
    },
    "python_packages": packages,
    "installed_dependency_metadata": sorted(dependencies, key=lambda item: item["name"].lower()),
    "dotnet": {
        "executable": file_record(dotnet), "sdk_version_query": dotnet_version,
        "sdk_listing": dotnet_sdks, "runtime_listing": dotnet_runtimes,
        "sdk_path": str(sdk), "sdk_primary_files": [file_record(path) for path in sdk_primary],
        "hostfxr": [file_record(path) for path in hostfxr],
        "installed_runtimes": runtime_records,
        "scope": "선택된 SDK와 설치 런타임의 핵심 파일을 고정했습니다. SDK·런타임 전체 디렉터리 해시는 아니며 실제 실행 시 선택 런타임은 각 도구의 runtimeconfig에 따라 결정됩니다.",
        "discovery_note": "dotnet --info는 서비스 관리자 조회 권한 오류가 있어 사용하지 않았습니다. --version/--list-sdks/--list-runtimes를 직접 조회했습니다.",
    },
    "cecil": {"files": [file_record(path) for path in cecil_paths],
              "versions_reference": "binary_file_versions의 assembly_name과 file_version",
              "scope": "참조 원본과 현재 toolchain의 사본들을 모두 기록했습니다."},
    "xdelta": {"executable": file_record(xdelta), "version_query": xdelta_version,
               "archive": file_record(xdelta_root / "xdelta3-3.2.0-windows-x86_64.zip"),
               "license": file_record(xdelta_root / "LICENSE-APACHE-2.0.txt")},
    "fonts": {
        "source": font_record(font_source), "static": font_record(font_static),
        "license": file_record(font_license) | {
            "identifier": "SIL Open Font License",
            "version": license_version.group(1) if license_version else None},
        "derivation": {"tool": file_record(TASK / "tools/font_patch.py"),
                       "function": "prepare_font", "axis_settings": {"wght": 400},
                       "method": "fontTools.varLib.instancer.instantiateVariableFont",
                       "status": "기존 static TTF를 기록했으며 이 실행에서 재생성하지 않았습니다."},
    },
    "work_tools": tools, "release_templates": release_templates,
    "generated_support_tools": generated,
    "generated_tool_notice": "지원 DLL과 작업 도구가 바뀌면 이 기록은 STALE입니다. 최종 빌드 뒤 lock_evidence.py를 다시 실행해야 합니다.",
    "binary_file_versions": binary_metadata,
    "baseline": {
        "manifest": file_record(baseline_path), "source_root": str(SOURCE),
        "steam_manifest": file_record(appmanifest), "steam_identifiers": steam_ids,
        "files": baseline_rows, "file_count": len(baseline_rows),
        "total_bytes": sum(row["size"] for row in baseline["files"]),
        "extra_files": extra, "missing_files": missing,
        "verified_against_private_copy_only": True,
        "installed_game_not_opened_or_modified": True,
    },
    "engine": {
        "version_manifest": file_record(versions_path), "asset_headers": engine_observed,
        "scripting_backend": "Mono" if is_mono else "UNKNOWN",
        "backend_evidence": {"managed_game_assembly": file_record(managed),
                             "mono_runtime": [file_record(path) for path in mono_files],
                             "gameassembly_dll_present": (SOURCE / "GameAssembly.dll").exists()},
    },
    "claims_not_made": ["게임 실행 성공", "실제 화면 검수 완료", "글리프 검사 통과",
                        "최종 후보 검증 완료", "패치 설치 성공", "배포 완료"],
    "privacy": "기존 파일을 제자리에서 읽고 비공개 toolchain_lock.json에 지문만 기록했습니다. 원본 자산·DLL·글꼴·라이선스 본문을 공개 경로로 복사하지 않았습니다.",
}
result["status"] = "PASS" if not ERRORS else "FAIL"
write_json(OUTPUT, result)
print(json.dumps({"status": result["status"], "baseline_files": len(baseline_rows),
                  "engine_versions": sorted(set(engine_versions.values())),
                  "python_packages": {p["distribution"]: p["version"] for p in packages},
                  "sdk": sdk_version, "errors": ERRORS, "lock_sha256": sha(OUTPUT)},
                 ensure_ascii=False))
if ERRORS:
    raise SystemExit(1)
