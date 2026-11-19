"""검증한 부분 번역으로 저장 격리된 실행 검수 사본을 새로 만든다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BUILD = "0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2" / BUILD
PRIVATE = ROOT / "working_private/SOULASH_2"
MANIFEST = ROOT / "extracted_private/SOULASH_2" / BUILD / "baseline_manifest.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stage, output = args.stage.resolve(), args.output.resolve()
    if not stage.is_relative_to(ROOT / "build_candidate/SOULASH_2") or not output.is_relative_to(PRIVATE):
        raise ValueError("검수 경로 경계 위반")
    if output.exists():
        raise ValueError("기존 검수 사본 덮어쓰기 금지")
    manifest = read(MANIFEST)
    if sha(MANIFEST) != "56672598007cff88e3fe74558d063d3a652a553697d3b42bd73e56c14ec1eb24":
        raise ValueError("원본 목록 변경")
    report_path = stage / "stage_report.json"
    stage_report = read(report_path)
    checked = read(stage / "independent_validation.json")
    if checked["status"] != "PASS" or checked["stage_report_sha256"] != sha(report_path):
        raise ValueError("부분 번역 재추출 검사 불일치")
    font = PRIVATE / "font_probe/soulash_qa/SoulashKoreanQA-SemiBold.ttf"
    settings = PRIVATE / "qa_isolation/settings_proposed.json"
    isolation = PRIVATE / "qa_isolation/g1_isolation_manifest.json"
    patches = read(isolation)
    if sha(isolation) != "2fcda5f858ffeb321871279509116ce1b109c4377b454f89a79a5301f9f67e5d":
        raise ValueError("검수 격리 명세 변경")
    if sha(font) != "2dc2869175db8afb006233be96e937f2a081aef715dbe043fda3ebc2ac896d73":
        raise ValueError("검증 글꼴 변경")
    inputs = [MANIFEST, report_path, stage / "independent_validation.json", font, settings, isolation, Path(__file__)]
    inputs += [stage / "payload" / item["file"] for item in stage_report["files"]]
    input_hashes = {path: sha(path) for path in inputs}
    expected = {item["path"]: item["sha256"] for item in manifest["files"]}
    output.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    for item in manifest["files"]:
        relative = item["path"]
        source, target = SOURCE / relative, output / relative
        if not source.resolve().is_relative_to(SOURCE) or not target.resolve().is_relative_to(output):
            raise ValueError("원본 목록 경계 위반")
        if source.stat().st_size != item["size"] or sha(source) != item["sha256"]:
            raise ValueError("원본 변경: " + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    print(json.dumps({"copied": len(expected)}), flush=True)
    executable = output / "Soulash 2.exe"
    original = executable.read_bytes()
    if hashlib.sha256(original).hexdigest() != patches["source_sha256"]:
        raise ValueError("실행 파일 원본 변경")
    modified = bytearray(original)
    for patch in patches["patches"]:
        offset, before, after = patch["offset"], bytes.fromhex(patch["before"]), bytes.fromhex(patch["after"])
        if modified[offset:offset+len(before)] != before or len(before) != len(after):
            raise ValueError("검수 변경 경계 불일치")
        modified[offset:offset+len(after)] = after
    if hashlib.sha256(modified).hexdigest() != patches["qa_sha256"]:
        raise ValueError("검수 실행 파일 지문 불일치")
    executable.write_bytes(modified)
    expected["Soulash 2.exe"] = patches["qa_sha256"]
    differences = [{"file": "Soulash 2.exe", "role": "QA_ONLY_DO_NOT_DISTRIBUTE", "sha256": patches["qa_sha256"]}]
    for name in ("Lato-Bold.ttf", "Lato-Regular.ttf", "romulus.ttf"):
        relative = "data/mods/core_2/assets/fonts/" + name
        shutil.copyfile(font, output / relative)
        expected[relative] = sha(font)
        differences.append({"file": relative, "role": "KOREAN_FONT", "sha256": sha(font)})
    for item in stage_report["files"]:
        relative = item["file"]
        if expected[relative] != item["source_sha256"] or sha(stage / "payload" / relative) != item["candidate_sha256"]:
            raise ValueError("번역 자산 지문 불일치")
        shutil.copyfile(stage / "payload" / relative, output / relative)
        expected[relative] = item["candidate_sha256"]
        differences.append({"file": relative, "role": "PARTIAL_TRANSLATION", "sha256": expected[relative]})
    shutil.copyfile(settings, output / "data/user_settings.json")
    expected["data/user_settings.json"] = sha(settings)
    for name in ("tutorial_values.json", "user.settings.json"):
        if (output / "data" / name).exists():
            raise ValueError("사용자 설정 이주를 유발하는 파일 존재")
    actual = {p.relative_to(output).as_posix(): sha(p) for p in output.rglob("*") if p.is_file()}
    if actual != expected:
        raise ValueError("검수 사본 전체 파일 경계 불일치")
    for path, digest in input_hashes.items():
        if sha(path) != digest:
            raise ValueError("준비 도중 입력 변경")
    report = {"status": "PASS", "purpose": "QA_ONLY_DO_NOT_DISTRIBUTE", "started": started,
              "finished": datetime.now(timezone.utc).isoformat(), "candidate": output.relative_to(ROOT).as_posix(),
              "source_files": len(manifest["files"]), "actual_files": len(actual), "locations": stage_report["accepted_rows"],
              "difference_allowlist": "PASS", "migration_files_absent": "PASS", "runtime_isolation": "NOT_RUN",
              "g5": "NOT_RUN", "release_ready": False, "differences": differences,
              "added_files": [{"file": "data/user_settings.json", "sha256": sha(settings), "role": "QA_SETTINGS"}],
              "inputs": [{"path": path.relative_to(ROOT).as_posix(), "sha256": value} for path, value in input_hashes.items()]}
    destination = output.parent / (output.name + "_preparation.json")
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": "PASS", "files": len(actual), "locations": stage_report["accepted_rows"]}))


if __name__ == "__main__":
    main()
