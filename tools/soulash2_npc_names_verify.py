"""생성된 인명 파일을 다시 읽어 원본·기대 번역·줄바꿈과 독립 비교한다."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
HERE = ROOT / "working_private/SOULASH_2/translations/npc_names_20261030"
TARGETS = ROOT / "working_private/SOULASH_2/translations/npc_names_reviewed_targets.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    batch = HERE / "npc_names_001.jsonl"
    rows = [json.loads(line) for line in batch.read_text(encoding="utf-8").splitlines()]
    expected = json.loads(TARGETS.read_text(encoding="utf-8"))
    grouped = defaultdict(dict)
    failures, checked = [], []
    assert len(rows) == 2422 and len({r["location_id"] for r in rows}) == len(rows)
    for row in rows:
        assert row["line"] not in grouped[row["file"]]
        grouped[row["file"]][row["line"]] = row
    baseline = json.loads((ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json").read_text(encoding="utf-8"))
    baseline_files = {x["path"]: x["sha256"] for x in baseline["files"]}
    actual = {p.relative_to(HERE / "payload").as_posix() for p in (HERE / "payload").rglob("*") if p.is_file()}
    assert actual == set(grouped)
    for relative, by_line in sorted(grouped.items()):
        original, output = SOURCE / relative, HERE / "payload" / relative
        old_data, new_data = original.read_bytes(), output.read_bytes()
        assert hashlib.sha256(old_data).hexdigest() == baseline_files[relative]
        old_lines, new_lines = old_data.decode("utf-8").splitlines(), new_data.decode("utf-8").splitlines()
        desired = expected[original.stem].split("|")
        checks = {"line_count": len(old_lines) == len(new_lines) == len(desired) == len(by_line), "line_endings": re.findall(rb"\r\n|\r|\n", old_data) == re.findall(rb"\r\n|\r|\n", new_data),
                  "final_newline": old_data.endswith((b"\n", b"\r")) == new_data.endswith((b"\n", b"\r")), "independent_target_readback": new_lines == desired,
                  "no_untranslated_latin": not re.search(r"[A-Za-z]", new_data.decode("utf-8")), "no_blank_names": all(new_lines)}
        for i, (old, new) in enumerate(zip(old_lines, new_lines), 1):
            row = by_line[i]
            if row["source"] != old or row["target"] != new or row["source_file_sha256"] != sha(original) or row["source_value_sha256"] != hashlib.sha256(old.encode("utf-8")).hexdigest():
                failures.append({"file": relative, "line": i, "reason": "위치별 원문·번역·해시 불일치"})
        if not all(checks.values()):
            failures.append({"file": relative, "checks": checks})
        checked.append({"file": relative, "rows": len(new_lines), "sha256": sha(output), "checks": checks})
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "FAIL" if failures else "PASS", "rows": len(rows), "files": len(checked),
              "tool_sha256": sha(__file__), "batch_sha256": sha(batch), "targets_sha256": sha(TARGETS), "checks": checked, "failures": failures,
              "runtime_qa": "NOT_RUN", "scope": "별도 생성한 인명35파일의 위치별 독립 재추출·출처·원문 잔존·범위·줄끝 검사"}
    with (HERE / "independent_validation.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "rows": len(rows), "files": len(checked), "failures": failures}, ensure_ascii=False))


if __name__ == "__main__":
    main()
