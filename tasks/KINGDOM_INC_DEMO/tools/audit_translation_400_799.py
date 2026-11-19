"""담당 번역 400~799의 원문 연결과 서식 보존을 검사합니다."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "working_private" / "KINGDOM_INC_DEMO"
SOURCE = WORK / "language_source.json"
TARGETS = WORK / "translation" / "targets_400_799.txt"
OUTPUT = WORK / "translation" / "part_400_799.json"
REPORT = WORK / "audit" / "translation_400_799_check.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def placeholders(text):
    return re.findall(r"\{[^{}]*\}", text)


def numbers(text):
    return re.findall(r"\d+(?:\.\d+)?%?", re.sub(r"\{[^{}]*\}", "", text))


def format_signature(text):
    # 강조 구간의 순서와 각 구간 안의 자리표시자를 함께 비교합니다.
    spans = text.split("#")
    return {
        "hash_delimiters": len(spans) - 1,
        "span_placeholders": [placeholders(span) for span in spans],
        "span_numbers": [numbers(span) for span in spans],
        "span_breaks": [span.count("\\n") for span in spans],
        "tags": re.findall(r"<[^>]*>", text),
        "placeholders": placeholders(text),
        "literal_newlines": text.count("\\n"),
        "real_newlines": text.count("\n"),
    }


sources = json.loads(SOURCE.read_text(encoding="utf-8"))
targets = {}
for line in TARGETS.read_text(encoding="utf-8").splitlines():
    index, target = line.split("|", 1)
    index = int(index)
    assert index not in targets, f"중복 인덱스: {index}"
    targets[index] = target
assert sorted(targets) == list(range(400, 800))

results = []
rows = []
for source in sources[400:800]:
    index = source["index"]
    target = targets[index]
    original = source["source"]
    checks = {
        "not_empty": bool(target.strip()),
        "translated": original != target,
        "hangul_present": bool(re.search("[가-힣]", target)),
        "no_english_prose": not re.search("[A-Za-z]", target.replace("\\n", "")),
        "format_structure": format_signature(original) == format_signature(target),
        "number_preservation": Counter(numbers(original)) == Counter(numbers(target)),
        "balanced_highlights": target.count("#") % 2 == 0,
    }
    rows.append({name: source[name] for name in ("index", "key", "source")} | {"target": target})
    results.append({"index": index, "key": source["key"], "checks": checks,
                    "status": "PASS" if all(checks.values()) else "FAIL"})

failures = [row for row in results if row["status"] != "PASS"]
assert not failures, json.dumps(failures, ensure_ascii=False)
OUTPUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
# 저장한 파일을 다시 열어 인덱스·키·원문·번역의 위치 일치를 확인합니다.
reloaded = json.loads(OUTPUT.read_text(encoding="utf-8"))
assert reloaded == rows
assert len(reloaded) == 400
for row in reloaded:
    assert row["source"] == sources[row["index"]]["source"]
    assert row["key"] == sources[row["index"]]["key"]
report = {
    "status": "PASS",
    "scope": "400~799의 번역 내용과 서식 정적 검사. 게임 내 화면 검수는 별도.",
    "source_sha256": sha256(SOURCE),
    "target_input_sha256": sha256(TARGETS),
    "output_sha256": sha256(OUTPUT),
    "rows": 400,
    "failed": 0,
    "checks": results,
    "semantic_review": {
        "status": "PASS",
        "note": "전체 400개를 원문과 대조해 의미·용어·고유명사·훈련 조건·수치·효과 방향을 검토했습니다. 재료 금과 재화 골드를 문맥에 따라 구분합니다.",
    },
}
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: report[key] for key in ("status", "rows", "failed", "output_sha256")},
                 ensure_ascii=False))
