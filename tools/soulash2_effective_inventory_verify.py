"""통합 출력물을 다시 읽어 원행 보존, 적용 기록, 번역 후보의 위치 일치를 독립 대조한다."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
OUTPUT = BASE / "effective_inventory"
AXES = [("json_value", "json_strings.jsonl"), ("json_key", "json_property_keys.jsonl"),
        ("text_line", "text_lines.jsonl"), ("map_name", "map_names.jsonl"),
        ("media", "media_inventory.jsonl"), ("native_string", "native/strings.jsonl")]


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for raw in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(raw)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", choices=["initial", "v2", "v3", "v4"], default="initial")
    args = parser.parse_args()
    global OUTPUT
    if args.revision != "initial":
        OUTPUT = OUTPUT / args.revision
    destination = OUTPUT / "independent_merge_validation.json"
    if destination.exists():
        raise ValueError("기존 검사 결과를 덮어쓰지 않습니다.")
    summary = json.loads((OUTPUT / "effective_inventory_summary.json").read_text(encoding="utf-8"))
    failures, counts, expected_work = [], Counter(), {}
    applications = {}
    for line in (OUTPUT / "overlay_application_ledger.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        if row["entry_id"] in applications:
            failures.append("중복 적용 이력: " + row["entry_id"])
        applications[row["entry_id"]] = row
    referenced = Counter()
    with (OUTPUT / "effective_classification_ledger.jsonl").open(encoding="utf-8") as ledger:
        for axis, relative in AXES:
            for number, raw in enumerate((BASE / relative).open("rb"), 1):
                original = json.loads(raw)
                actual = json.loads(next(ledger))
                if actual["original_record"] != original or actual["axis"] != axis:
                    failures.append("원행 보존/축 실패: " + relative + ":" + str(number))
                origin = actual["inventory_origin"]
                if origin["row_number"] != number or origin["row_sha256"] != hashlib.sha256(raw).hexdigest():
                    failures.append("원행 위치/해시 실패: " + relative + ":" + str(number))
                expected_class = original["classification"]
                for entry in actual["overlay_history"]:
                    application = applications[entry["entry_id"]]
                    referenced[entry["entry_id"]] += 1
                    patch = application["record"]
                    if application["disposition"].startswith("REJECTED"):
                        expected_class = "UNKNOWN"
                    else:
                        expected_class = patch["classification"]
                    if patch["location_id"] != original["location_id"]:
                        failures.append("다른 위치의 보강 적용: " + entry["entry_id"])
                if expected_class != actual["classification"]:
                    failures.append("유효 분류 실패: " + actual["record_id"])
                counts[axis] += 1
                primary = axis == "json_value" and original.get("role") == "primary_english"
                name_file = axis == "text_line" and original["file"].startswith("data/mods/core_2/") and "/translations/" not in original["file"]
                if (primary or name_file) and actual["classification"] == "VISIBLE_TRANSLATE":
                    expected_work[actual["record_id"]] = actual
        if next(ledger, None) is not None:
            failures.append("입력에 없는 통합행")
    if set(referenced) != set(applications) or any(count != 1 for count in referenced.values()):
        failures.append("보강 이력의 누락 또는 중복 적용")
    work_count = 0
    for line in (OUTPUT / "translation_work_v2.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        actual = expected_work.pop(row["record_id"])
        original = actual["original_record"]
        if any(row.get(key) != original.get(key) for key in ("location_id", "file", "field_path", "occurrence_path", "source", "source_file_sha256", "source_value_sha256")):
            failures.append("번역 후보의 원본 위치/값 실패: " + row["record_id"])
        if row["target"] is not None or row["translation_status"] != "NOT_RUN":
            failures.append("G1 전 번역 값 존재: " + row["record_id"])
        work_count += 1
    if expected_work:
        failures.append("번역 후보 누락: " + str(len(expected_work)))
    for filename, expected in summary["outputs"].items():
        if digest(OUTPUT / filename) != expected:
            failures.append("출력 지문 불일치: " + filename)
    report = {"status": "FAIL" if failures else "PASS", "scope": "통합 파일의 원행·분류 이력·번역 후보 독립 재읽기", "axis_rows": counts,
              "overlay_rows": len(applications), "translation_locations": work_count, "failures": failures,
              "summary_sha256": digest(OUTPUT / "effective_inventory_summary.json"), "tool_sha256": digest(Path(__file__)),
              "g1_status": summary["g1_status"], "g2_status": "FAIL", "runtime_observed": False}
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
