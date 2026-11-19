"""최종 ZIP을 독립적으로 검사하고 그 안의 도구로 차이를 다시 복원합니다."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

from common import ROOT, WORK, SOURCE, sha, write_json


def audit(report_path, readme_path):
    report_path = Path(report_path).resolve()
    report_path.relative_to(WORK.resolve())
    scratch = report_path.parent
    package = json.loads(report_path.read_text(encoding="utf-8"))
    archive = Path(package["archive"])
    extracted = scratch / "from_final_zip"
    build_path = WORK / package["candidate"] / "build.json"
    build = json.loads(build_path.read_text(encoding="utf-8"))
    candidate = Path(build["candidate"])
    static_path = build_path.with_name("static_validation.json")
    static = json.loads(static_path.read_text(encoding="utf-8"))
    assert static["status"] == "PASS" and static["build_sha256"] == sha(build_path)
    for row in static["verification_inputs"] + build["inputs"]:
        assert sha(row["path"]) == row["sha256"], "STALE: " + row["path"]
    assert sha(archive) == package["zip_sha256"]
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        assert len(names) == len(set(names))
        manifest = json.loads(zipped.read("manifest.json").decode("utf-8"))
        allowed = {
            "Install.cmd", "Remove.cmd", "Patch.ps1", "ChooseGame.ps1", "README.txt", "manifest.json",
            "tools/xdelta3.exe", "licenses/xdelta3-APACHE-2.0.txt", "licenses/NotoSansKR-OFL.txt",
        }
        for row in manifest["changes"]:
            allowed.update([row["forward"], row["reverse"]])
        assert set(names) == allowed == set(package["allowed_files"])
        assert len(allowed) == 9 + 2 * len(manifest["changes"])
        assert not any(name.endswith((".dll", ".assets", ".resS", ".resource", ".ttf", ".sav", ".cs")) for name in names)
        assert not any("KoreanQA" in name or "save" in name.lower() or "probe" in name.lower() for name in names)
        assert zipped.testzip() is None
        for row in manifest["payload"]:
            raw = zipped.read(row["path"])
            assert hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
            assert sha(extracted / row["path"]) == row["sha256"], row["path"]
        # 패키지 저장 시 Windows 줄바꿈과 UTF-8 BOM이 추가되므로 내용 기준으로 대조합니다.
        actual_readme = zipped.read("README.txt").decode("utf-8-sig").replace("\r\n", "\n")
        assert actual_readme == Path(readme_path).read_text(encoding="utf-8-sig")
    assert manifest["candidate"] == build["build_id"]
    assert manifest["steam_app_id"] == "4702410" and manifest["steam_build"] == "25631786"
    assert sha(extracted / "manifest.json") == package["manifest_sha256"]
    recorded = {row["path"]: row for row in build["files"]}
    assert len(recorded) == len(package["candidate_files"]) == 191
    for row in package["candidate_files"]:
        assert row == recorded[row["path"]]
        assert sha(candidate / row["path"]) == row["sha256"]
    checks = []
    with tempfile.TemporaryDirectory(prefix="final_zip_roundtrip_", dir=scratch) as folder:
        temporary = Path(folder).resolve()
        assert temporary.is_relative_to(scratch.resolve())
        for index, row in enumerate(manifest["changes"]):
            assert sha(SOURCE / row["path"]) == row["original_sha256"]
            assert sha(candidate / row["path"]) == row["patched_sha256"]
            for mode, start, wanted in [
                ("forward", SOURCE / row["path"], row["patched_sha256"]),
                ("reverse", candidate / row["path"], row["original_sha256"]),
            ]:
                target = temporary / f"{index:02d}.{mode}.rebuilt"
                result = subprocess.run(
                    [str(extracted / "tools/xdelta3.exe"), "-d", "-s", str(start), str(extracted / row[mode]), str(target)],
                    capture_output=True, timeout=120,
                )
                assert result.returncode == 0, result.stderr
                assert sha(target) == wanted
                checks.append({
                    "file": row["path"], "direction": mode, "status": "PASS",
                    "rebuilt_sha256": sha(target), "patch_sha256": sha(extracted / row[mode]),
                })
                target.unlink()
    result = {
        "status": "PASS", "scope": "최종 ZIP 허용 목록·추출 도구 정역방향 복원·후보 G4 의존 관계 재확인",
        "archive": str(archive), "zip_sha256": sha(archive), "archive_size": archive.stat().st_size,
        "manifest_sha256": sha(extracted / "manifest.json"), "candidate": build["build_id"],
        "build_sha256": sha(build_path), "G4_report_sha256": sha(static_path),
        "allowed_file_count": len(allowed), "allowed_files": sorted(allowed),
        "modified_game_files": len(manifest["changes"]), "roundtrip_checks": checks,
        "forbidden_payload_checks": {
            "original_game_assets": "PASS", "game_dlls": "PASS", "qa_dll_or_source": "PASS",
            "save_files": "PASS", "standalone_font_asset": "PASS",
        },
        "readme_template_sha256": sha(readme_path), "packaged_readme_sha256": sha(extracted / "README.txt"),
        "readme_comparison": "BOM 제거 및 CRLF/LF 정규화 후 내용 동일",
        "audit_tool_sha256": sha(__file__), "game_execution": "NOT_RUN",
        "actual_steam_installation": "NOT_RUN", "G5": "NOT_RUN", "G7": "NOT_RUN",
    }
    test_path = scratch / "installer_tests.json"
    if test_path.exists():
        tests = json.loads(test_path.read_text(encoding="utf-8"))
        assert tests["zip_sha256"] == sha(archive)
        assert tests["status"] == "PASS"
        result["G7"] = "PASS"
        result["installer_tests_sha256"] = sha(test_path)
    assert sha(archive) == package["zip_sha256"]
    output = scratch / "final_zip_audit.json"
    write_json(output, result)
    return {"status": "PASS", "report": str(output), "report_sha256": sha(output), "zip_sha256": sha(archive),
            "allowed_files": len(allowed), "roundtrips": len(checks), "G7": result["G7"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-report", required=True, type=Path)
    parser.add_argument("--readme", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.package_report, args.readme), ensure_ascii=False))
