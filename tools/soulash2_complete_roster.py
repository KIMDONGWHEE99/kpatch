"""표시 근거가 추가된 항목을 기존 번역 로스터에 넣고 분류·문서 지문을 연결한다."""
import argparse
import hashlib
import json
from pathlib import Path

from soulash2_complete_stage import ROOT, SOURCE, INVENTORY, contained, unique


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=INVENTORY)
    parser.add_argument("--addition", type=Path, action="append", required=True)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshots = {}

    def record(path):
        path = path.resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("근거 입력 경계 오류")
        data = path.read_bytes()
        snapshots[path] = data
        return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(data).hexdigest()}

    def rows(path):
        record(path)
        return [json.loads(line, object_pairs_hook=unique) for line in snapshots[path.resolve()].decode("utf-8-sig").splitlines() if line.strip()]

    entries = {}
    for row in rows(args.base):
        if row["location_id"] in entries:
            raise ValueError("원 로스터 중복 위치")
        entries[row["location_id"]] = row
    original_count = len(entries)
    common_evidence = [record(Path(__file__)), record(args.base)] + [record(path) for path in args.evidence]
    additions = []
    for path in args.addition:
        added_rows = rows(path)
        proof = record(path)
        additions.append(proof)
        for row in added_rows:
            if row.get("classification") != "VISIBLE_TRANSLATE":
                continue
            loc = row["location_id"]
            if loc in entries:
                raise ValueError("추가 로스터 중복 위치: " + loc)
            if not row.get("reason"):
                raise ValueError("표시 분류 사유 없음")
            evidence = [*common_evidence, proof]
            for document in row.get("document_evidence", []):
                source_path = contained(SOURCE, document["file"])
                item = record(source_path)
                if item["sha256"] != document["file_sha256"]:
                    raise ValueError("분류 문서 지문 변경")
                lines = snapshots[source_path].decode("utf-8-sig").splitlines()
                actual = "\n".join(lines[document["line_start"] - 1:document["line_end"]])
                if actual != document["text"]:
                    raise ValueError("분류 문서 위치 또는 인용문 변경")
                evidence.append(item)
            entries[loc] = {**row, "roster_evidence": evidence}
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "working_private/SOULASH_2/translations"):
        raise ValueError("로스터 출력 경계 오류")
    output.mkdir(parents=True, exist_ok=False)
    target = output / "roster.jsonl"
    target.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in entries.values()), encoding="utf-8")
    for path, data in snapshots.items():
        if path.read_bytes() != data:
            raise ValueError("로스터 입력 도중 변경")
    manifest = {"status": "PASS", "scope": "DECLARED_TRANSLATION_ROSTER_ONLY", "g2_status": "NOT_RUN", "original_rows": original_count, "added_rows": len(entries) - original_count, "rows": len(entries), "output": record(target), "inputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(data).hexdigest()} for p, data in sorted(snapshots.items())]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("status", "original_rows", "added_rows", "rows")}))


if __name__ == "__main__":
    main()
