"""재개 시 기준선·설치본과 G1 보고서의 파일 지문을 다시 확인한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BUILD = "0.10.4.0.1_20261029"
BASE = ROOT / "extracted_private/SOULASH_2" / BUILD
OUT = ROOT / "working_private/SOULASH_2/resume_20261030"


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_tree(root, entries):
    root = root.resolve(strict=True)
    expected = {entry["path"]: entry for entry in entries}
    if len(expected) != len(entries):
        raise ValueError("기준선 파일 경로 중복")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}

    def check(entry):
        path = root / entry["path"]
        try:
            if not path.resolve().is_relative_to(root) or path.is_symlink():
                return {"path": entry["path"], "status": "FAIL", "reason": "경로 경계"}
            stat_before = path.stat()
            actual_hash = digest(path)
            stat_after = path.stat()
            stable = (stat_before.st_size, stat_before.st_mtime_ns) == (stat_after.st_size, stat_after.st_mtime_ns)
            if stat_after.st_size != entry["size"] or actual_hash != entry["sha256"] or not stable:
                return {"path": entry["path"], "status": "FAIL", "size": stat_after.st_size,
                        "sha256": actual_hash, "stable_during_read": stable}
        except OSError as error:
            return {"path": entry["path"], "status": "BLOCKED", "error": str(error)}
        return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        failures = [result for result in pool.map(check, entries) if result]
    missing, added = sorted(set(expected) - actual), sorted(actual - set(expected))
    return {"root": str(root), "status": "FAIL" if failures or missing or added else "PASS",
            "expected_files": len(expected), "actual_files": len(actual),
            "checked_bytes": sum(entry["size"] for entry in entries),
            "missing": missing, "added": added, "failures": failures}


def report_references(value, trail=""):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            yield trail, value
        for key, child in value.items():
            yield from report_references(child, trail + "/" + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from report_references(child, trail + "/" + str(index))


def verify_g1(path):
    report = json.loads(path.read_text(encoding="utf-8"))
    records = []
    references = list(report_references(report))
    for name in ("Lato-Bold.ttf", "Lato-Regular.ttf", "romulus.ttf"):
        references.append(("/candidate_font/" + name, {
            "path": report["candidate"] + "/data/mods/core_2/assets/fonts/" + name,
            "sha256": report["font"]["sha256"]}))
    process = report["process"]["observed"]
    references.append(("/process/observed", {"path": process["ActualPath"],
                                           "sha256": process["ExecutableSha256"].lower()}))
    for trail, reference in references:
        item = {"report_location": trail, "path": reference["path"], "expected_sha256": reference["sha256"]}
        target = (ROOT / reference["path"]).resolve()
        try:
            if not target.is_relative_to(ROOT):
                raise ValueError("작업 영역 밖 G1 참조")
            item["actual_sha256"] = digest(target)
            item["status"] = "PASS" if item["actual_sha256"] == item["expected_sha256"] else "STALE"
        except (OSError, ValueError) as error:
            item.update(status="BLOCKED", error=str(error))
        records.append(item)
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path),
            "status": "PASS" if records and all(r["status"] == "PASS" for r in records) else "STALE",
            "original_status": report["status"], "scope": report["scope"], "references": records,
            "limitation": "기존 G1 증거의 현재 파일 일치 검사이며 새 그래픽 실행이나 G5 통과가 아님"}


def main():
    started = datetime.now(timezone.utc)
    manifest_path = BASE / "baseline_manifest.json"
    manifest_hash = digest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = {"game_id": "SOULASH_2", "build_id": BUILD, "check_id": "RESUME_INPUT_REVALIDATION",
              "started": started.isoformat(), "command": sys.argv, "python": sys.version,
              "tool_sha256": digest(__file__), "manifest_sha256": manifest_hash}
    for key, root in [("baseline", ROOT / "source_original/SOULASH_2" / BUILD),
                      ("installed", Path(manifest["source"]))]:
        try:
            result[key] = verify_tree(root, manifest["files"])
        except OSError as error:
            result[key] = {"root": str(root), "status": "BLOCKED", "error": str(error)}
        print(json.dumps({"check": key, "status": result[key]["status"],
                          "failures": len(result[key].get("failures", []))}), flush=True)
    result["g1"] = verify_g1(ROOT / "working_private/SOULASH_2/qa_isolation/g1_02_json_font_report.json")
    result["manifest_sha256_after"] = digest(manifest_path)
    result["status"] = "PASS" if all(result[k]["status"] == "PASS" for k in ("baseline", "installed", "g1")) and manifest_hash == result["manifest_sha256_after"] else "FAIL"
    result["finished"] = datetime.now(timezone.utc).isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / ("resume_integrity_" + started.strftime("%Y%m%dT%H%M%S_%fZ") + ".json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"output": str(output), "status": result["status"], "g1": result["g1"]["status"]}, ensure_ascii=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
