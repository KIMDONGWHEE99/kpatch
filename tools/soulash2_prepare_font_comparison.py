"""같은 부분 번역과 격리 저장으로 글꼴만 바꾼 비교 사본을 만든다."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "working_private/SOULASH_2"
PREVIOUS = PRIVATE / "qa_resume_01"
OUTPUT = PRIVATE / "qa_resume_02"
FONT = PRIVATE / "font_probe/hybrid_20261030_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}


def main():
    baseline_path = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json"
    prep_path = PRIVATE / "qa_resume_01_preparation.json"
    validation_path = FONT / "independent_validation.json"
    settings = PRIVATE / "qa_isolation/settings_proposed.json"
    baseline, prep, fonts = read(baseline_path), read(prep_path), read(validation_path)
    assert prep["status"] == fonts["status"] == "PASS"
    expected = {r["path"]: r["sha256"] for r in baseline["files"]}
    for change in prep["differences"]:
        expected[change["file"]] = change["sha256"]
    font_map = {}
    for font in fonts["font_results"]:
        path = FONT / "fonts" / font["output"]
        assert sha(path) == font["output_sha256"]
        assert not font["missing_required"] and not font["missing_preload"]
        font_map["data/mods/core_2/assets/fonts/" + font["source"]] = path
    assert len(font_map) == 3
    inputs = [baseline_path, prep_path, validation_path, settings, Path(__file__), *font_map.values()]
    snapshots = {path: sha(path) for path in inputs}
    OUTPUT.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    for relative, digest in expected.items():
        source, target = PREVIOUS / relative, OUTPUT / relative
        assert source.resolve().is_relative_to(PREVIOUS) and target.resolve().is_relative_to(OUTPUT)
        assert sha(source) == digest, relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(font_map.get(relative, source), target)
    print(json.dumps({"static_files": len(expected)}), flush=True)
    changes = []
    for relative, path in font_map.items():
        changes.append({"file": relative, "previous_sha256": expected[relative], "comparison_sha256": sha(path)})
        expected[relative] = sha(path)
    shutil.copyfile(settings, OUTPUT / "data/user_settings.json")
    expected["data/user_settings.json"] = sha(settings)
    saved = []
    for path in sorted((PREVIOUS / "saves/qa").rglob("*")):
        if path.is_symlink():
            raise ValueError("검수 저장에 연결 파일 존재")
        if not path.is_file():
            continue
        relative = path.relative_to(PREVIOUS).as_posix()
        destination = OUTPUT / relative
        before = sha(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        assert sha(path) == sha(destination) == before
        expected[relative] = before
        saved.append({"file": relative, "sha256": before, "bytes": path.stat().st_size})
    assert saved
    assert all(not (OUTPUT / "data" / name).exists() for name in ("tutorial_values.json", "user.settings.json"))
    actual = {p.relative_to(OUTPUT).as_posix(): sha(p) for p in OUTPUT.rglob("*") if p.is_file()}
    assert actual == expected
    assert all(sha(path) == digest for path, digest in snapshots.items())
    report = {"purpose": "QA_ONLY_FONT_COMPARISON_DO_NOT_DISTRIBUTE", "status": "PASS", "started": started,
              "finished": datetime.now(timezone.utc).isoformat(), "output": OUTPUT.relative_to(ROOT).as_posix(),
              "fonts_only_changed_against_previous_static_assets": "PASS", "font_changes": changes,
              "copied_qa_save": saved, "user_save_data_copied": False, "settings": ref(settings),
              "inputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": s} for p, s in snapshots.items()],
              "files": len(actual), "migration_files_absent": "PASS", "g5": "NOT_RUN", "release_ready": False,
              "limitations": ["기존 격리 검수 세계를 복제한 글꼴 비교용 사본", "새 번역 묶음은 적용하지 않음", "Romulus 파생 글꼴의 배포 허용 근거 미확정"]}
    with (PRIVATE / "qa_resume_02_preparation.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": "PASS", "files": len(actual), "fonts": 3, "qa_save_files": len(saved)}))


if __name__ == "__main__":
    main()
