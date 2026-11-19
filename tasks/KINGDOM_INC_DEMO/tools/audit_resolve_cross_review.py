"""승인된 통합 교정 17개 묶음을 적용하고 기존 검토 기록과 분리하여 기록합니다."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "working_private" / "KINGDOM_INC_DEMO"
TRANSLATION = WORK / "translation"
AUDIT = WORK / "audit"
REVIEW = AUDIT / "cross_review.json"
RESOLUTION = AUDIT / "cross_review_resolution.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


review_sha = sha(REVIEW)
review = read_json(REVIEW)
assert review["finding_count"] == 17
assert review["source_sha256"] == sha(WORK / "language_source.json")
parts = {}
rows = {}
owner = {}
before_hashes = {}
for entry in review["input_files"]:
    path = Path(entry["path"])
    assert sha(path) == entry["sha256"], f"검토 후 입력 변경: {path}"
    before_hashes[str(path)] = sha(path)
    parts[path] = read_json(path)
    for row in parts[path]:
        assert row["index"] not in rows
        rows[row["index"]] = row
        owner[row["index"]] = path
assert sorted(rows) == list(range(1556))

# 모든 원래 문구를 먼저 확인합니다. 적용 중 문제가 발견되어 부분 수정되는 것을 피합니다.
proposals = defaultdict(list)
for finding in review["findings"]:
    for change in finding["changes"]:
        row = rows[change["index"]]
        assert row["key"] == change["key"]
        assert row["source"] == change["source"]
        assert row["target"] == change["current"], f"원래 문구 불일치: {row['key']}"
        proposals[change["index"]].append((finding, change))

final_changes = {}
for index, entries in proposals.items():
    chosen = next((entry for entry in entries if entry[0]["id"] == "C16"), entries[-1])
    final_changes[index] = {
        "index": index,
        "key": rows[index]["key"],
        "source": rows[index]["source"],
        "original": rows[index]["target"],
        "final": chosen[1]["recommended"],
        "original_assertion": "PASS",
        "accepted_findings": [finding["id"] for finding, _ in entries],
        "precedence": "C16" if chosen[0]["id"] == "C16" and len(entries) > 1 else chosen[0]["id"],
        "reasons": [finding["reason"] for finding, _ in entries],
        "evidence": [finding["evidence"] for finding, _ in entries],
    }
assert len(final_changes) == 41

root_text = TRANSLATION / "root_0_399.txt"
assert sha(root_text) == review["latest_root_text_sha256"]
root_lines = root_text.read_text(encoding="utf-8").splitlines()
root_lookup = dict(line.split("=", 1) for line in root_lines)
assert len(root_lookup) == 400
for index, change in final_changes.items():
    if index < 400:
        assert root_lookup[change["key"]] == change["original"]

# 재생성용 구간 원고도 같은 최종 문구로 맞춥니다.
supporting = [
    (TRANSLATION / "targets_400_799.txt", "|"),
    (TRANSLATION / "part_1200_1555.targets.tsv", "\t"),
]
supporting_rows = {}
for path, delimiter in supporting:
    contents = [line.split(delimiter, 1) for line in path.read_text(encoding="utf-8").splitlines()]
    for index_text, target in contents:
        index = int(index_text)
        assert target == rows[index]["target"], f"구간 원고 불일치: {index}"
    supporting_rows[path] = (delimiter, contents)

affected_paths = {owner[index] for index in final_changes}
affected_paths.add(root_text)
affected_paths.update(path for path, _ in supporting)
for path in affected_paths:
    before_hashes.setdefault(str(path), sha(path))
for index, change in final_changes.items():
    rows[index]["target"] = change["final"]
for path in sorted(affected_paths & set(parts)):
    write_json(path, parts[path])
root_text.write_text("\n".join(
    key + "=" + (final_changes[by_index]["final"] if by_index in final_changes else target)
    for key, target in (line.split("=", 1) for line in root_lines)
    for by_index in [next(index for index in range(400) if rows[index]["key"] == key)]
) + "\n", encoding="utf-8")
for path, (delimiter, contents) in supporting_rows.items():
    path.write_text("\n".join(
        index_text + delimiter + final_changes.get(int(index_text), {"final": target})["final"]
        for index_text, target in contents
    ) + "\n", encoding="utf-8")

assembly_path = ROOT / "tasks" / "KINGDOM_INC_DEMO" / "tools" / "assemble_translation.py"
completed = subprocess.run([sys.executable, "-X", "utf8", str(assembly_path)],
                           cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8")
assembled = json.loads(completed.stdout.strip().splitlines()[-1])
assert assembled["status"] == "PASS"
assert sha(REVIEW) == review_sha
canonical = read_json(TRANSLATION / "canonical.json")
canonical_by_index = {row["index"]: row for row in canonical["rows"]}
for index, change in final_changes.items():
    assert canonical_by_index[index]["target"] == change["final"]
for entry in review["input_files"]:
    reread = read_json(Path(entry["path"]))
    for row in reread:
        index = row["index"]
        assert row == canonical_by_index[index]

# 추가 어휘 검사: 표시 이름과 설명·선행 조건에 서로 다른 이름이 남는지 확인합니다.
checks = {}
for name, indices, expected in [
    ("quest", [407, 542, 546, 550, 554, 558, 562, 568, 572, 575, 1135, 1328], "의뢰"),
    ("castle_district", [419, 1248, 1250], "왕성 구역"),
    ("pinnacle_ruins", [427, 1264, 1266], "정상 유적"),
    ("arlingen_ruins", [356, 1226, 1474], "아를링겐 유적"),
    ("saint_ilonia", [410, 1068, 1244, 1245], "성 일로니아"),
    ("resin", [518, 818, 819], "송진"),
    ("softwood_log", [484, 813], "연목 원목"),
    ("ancient_wood_log", [622, 829], "고대목 원목"),
    ("area_move", [35, 128, 806], "영역 이동"),
    ("decorations", [30, 124, 792, 1091], "꾸미기"),
    ("main_hand", [1166, 1289], "주손"),
    ("off_hand", [1167, 1290], "보조손"),
    ("exchange_tax", [401, 403, 1548], "수수료"),
    ("catacombs", [417, 1250, 1251], "옌스부르크 지하묘지"),
]:
    failures = [index for index in indices if expected not in canonical_by_index[index]["target"]]
    checks[name] = {"status": "PASS" if not failures else "FAIL",
                    "indices": indices, "expected": expected, "failures": failures}

for class_index, quest_index in [(542, 1344), (546, 1346), (550, 1338), (554, 1348),
                                 (558, 1350), (562, 1352), (568, 1354), (572, 1356)]:
    title = canonical_by_index[quest_index]["target"]
    assert f"#{title}#" in canonical_by_index[class_index]["target"]
checks["class_quest_title_links"] = {"status": "PASS", "pairs": 8}
for index, expected in [(1174, "경갑"), (1175, "중형 방어구"), (1176, "중갑")]:
    assert canonical_by_index[index]["target"] == expected
    rendered = canonical_by_index[1128]["target"].replace("{0}", expected).replace("{1}", "머리")
    assert rendered == f"{expected} - #머리#"
checks["armor_label_composition"] = {"status": "PASS", "types": 3,
                                    "scope": "문자열 조합 검사이며 실제 화면 검수는 별도입니다."}
assert all(check["status"] == "PASS" for check in checks.values())

resolved = {
    "status": "PASS",
    "applied_at_utc": datetime.now(timezone.utc).isoformat(),
    "authorization": "root가 17개 묶음 전부 채택했으며 C16 최종 문장을 우선하도록 지시했습니다.",
    "original_review": {"path": str(REVIEW), "sha256": review_sha, "preserved": True},
    "source_sha256": sha(WORK / "language_source.json"),
    "accepted_groups": 17,
    "distinct_changed_locations": len(final_changes),
    "changes": [final_changes[index] for index in sorted(final_changes)],
    "file_changes": [{"path": str(path), "before_sha256": before_hashes[str(path)],
                      "after_sha256": sha(path)}
                     for path in sorted(affected_paths)],
    "assembly": {"status": "PASS", "tool": str(assembly_path),
                 "tool_sha256": sha(assembly_path), "result": assembled},
    "outputs": [{
        "path": str(TRANSLATION / name), "sha256": sha(TRANSLATION / name),
    } for name in ["canonical.json", "language_ko.txt", "required_characters.json", "checks.json"]],
    "additional_terminology_review": {"status": "PASS", "checks": checks,
                                      "new_actionable_findings": []},
    "generated_names": {"status": "UNCHANGED",
                        "reason": "기존 이름 생성·저장 연동 근거를 유지했으며 이름 생성 자료는 변경하지 않았습니다."},
    "downstream_status": "번역 입력이 변경되어 이전 후보와 글꼴·실행 검증은 STALE입니다. root가 새 후보를 생성해야 합니다.",
}
write_json(RESOLUTION, resolved)
print(json.dumps({"status": "PASS", "groups": 17, "locations": len(final_changes),
                  "canonical_sha256": sha(TRANSLATION / "canonical.json"),
                  "review_preserved": sha(REVIEW) == review_sha}, ensure_ascii=False))
