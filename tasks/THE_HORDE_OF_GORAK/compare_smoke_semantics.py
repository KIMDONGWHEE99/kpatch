"""소규모 시험 후보를 Nebula로 다시 읽은 결과와 원본 전체 구조를 대조합니다."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def compare(before, after, path=""):
    if type(before) is not type(after):
        return [{"path": path, "before": before, "after": after}]
    out = []
    if isinstance(before, dict):
        for key in sorted(before.keys() | after.keys()):
            if key not in before or key not in after:
                out.append({"path": path + "/" + key, "missing": True})
            else:
                out.extend(compare(before[key], after[key], path + "/" + key))
    elif isinstance(before, list):
        if len(before) != len(after):
            out.append({"path": path, "before_length": len(before), "after_length": len(after)})
        for index, (left, right) in enumerate(zip(before, after)):
            out.extend(compare(left, right, path + "/" + str(index)))
    elif before != after:
        out.append({"path": path, "before": before, "after": after})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8-sig"))
    changes = compare(baseline, candidate)
    expected = {
        "/FrameItems/Items/32/Properties/ObjectParagraphs/Paragraphs/0/Value": ("GRAPHICS", "그래픽"),
        "/FontBank/Fonts/16/Name": ("Trebuchet MS".ljust(32, "\0"), "Malgun Gothic".ljust(32, "\0")),
        "/FontBank/ChunkSize": (1634, 1637),
        "/FontOffsets/ChunkSize": (101, 99),
    }
    errors = []
    for change in changes:
        path = change["path"]
        if path in expected:
            if (change.get("before"), change.get("after")) != expected[path]:
                errors.append(change)
        elif path.startswith("/FontOffsets/Offsets/") or path.startswith("/FontOffsets/SortedOffsets/"):
            if not isinstance(change.get("before"), int) or change["before"] < 838 or change.get("after") != change["before"] + 3:
                errors.append(change)
        else:
            errors.append(change)
    for path in expected:
        if path not in {x["path"] for x in changes}:
            errors.append({"path": path, "error": "필수 변경이 없음"})
    result = {"status": "FAIL" if errors else "PASS", "scope": "작은 시험 후보의 독립 의미 구조 대조; 실행 검수 아님",
        "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        "candidate_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
        "changes": changes, "errors": errors}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "changes": len(changes), "errors": len(errors)}))
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
