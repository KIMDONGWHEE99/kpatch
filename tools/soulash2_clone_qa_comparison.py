"""중단된 검수 사본을 보존하고 같은 고정 입력으로 새 실행 사본을 만든다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "working_private/SOULASH_2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(PRIVATE) or output.exists():
        raise ValueError("새 비공개 검수 경로가 필요합니다")
    source = PRIVATE / "qa_resume_02"
    base_path = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json"
    old_path = PRIVATE / "qa_resume_01_preparation.json"
    font_path = PRIVATE / "qa_resume_02_preparation.json"
    baseline, previous, font_comparison = map(read, (base_path, old_path, font_path))
    assert previous["status"] == font_comparison["status"] == "PASS"
    expected = {row["path"]: row["sha256"] for row in baseline["files"]}
    for row in previous["differences"]:
        expected[row["file"]] = row["sha256"]
    for row in font_comparison["font_changes"]:
        expected[row["file"]] = row["comparison_sha256"]
    settings = PRIVATE / "qa_isolation/settings_proposed.json"
    inputs = [base_path, old_path, font_path, settings, Path(__file__)]
    snapshots = {p: sha(p) for p in inputs}
    started = datetime.now(timezone.utc).isoformat()
    output.mkdir(parents=True)
    for relative, digest in expected.items():
        origin, target = source / relative, output / relative
        if not origin.resolve().is_relative_to(source) or not target.resolve().is_relative_to(output):
            raise ValueError("파일 경계 이탈")
        if sha(origin) != digest:
            raise ValueError("검수 고정 자산 변경: " + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)
    print(json.dumps({"static_files": len(expected)}), flush=True)
    shutil.copyfile(settings, output / "data/user_settings.json")
    expected["data/user_settings.json"] = sha(settings)
    saved = []
    for row in font_comparison["copied_qa_save"]:
        relative = row["file"]
        original = PRIVATE / "qa_resume_01" / relative
        target = output / relative
        if not relative.startswith("saves/qa/") or not target.resolve().is_relative_to(output):
            raise ValueError("검수 저장 경계 이탈")
        if sha(original) != row["sha256"]:
            raise ValueError("이전 비교 기준 저장 변경")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        expected[relative] = row["sha256"]
        saved.append(row)
    actual = {p.relative_to(output).as_posix(): sha(p) for p in output.rglob("*") if p.is_file()}
    if expected != actual:
        raise ValueError("검수 사본 재읽기 불일치")
    if any((output / "data" / n).exists() for n in ("tutorial_values.json", "user.settings.json")):
        raise ValueError("시작 전 이주 파일 존재")
    if any(sha(p) != s for p, s in snapshots.items()):
        raise ValueError("준비 중 입력 변경")
    report = {"status": "PASS", "started": started, "finished": datetime.now(timezone.utc).isoformat(),
              "purpose": "QA_ONLY_FONT_COMPARISON_DO_NOT_DISTRIBUTE", "output": output.relative_to(ROOT).as_posix(),
              "static_assets_equal_qa02": "PASS", "settings_reset_to_proposed": True,
              "source_qa02_modified": False, "save_source": "qa_resume_01/saves/qa", "copied_qa_save": saved,
              "migration_files_absent": "PASS", "files": len(actual), "graphics_qa": "NOT_RUN", "release_ready": False,
              "inputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": s} for p, s in snapshots.items()]}
    with (output.parent / (output.name + "_preparation.json")).open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": "PASS", "files": len(actual)}))


if __name__ == "__main__":
    main()
