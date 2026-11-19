"""한글 번역의 위치·용량·자리표시자·숫자·제어 문자를 전수 검사합니다."""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "working_private/THE_HORDE_OF_GORAK"
OUT = BASE / "translation_01"
SOURCE = BASE / "investigation_20261031/classification/translation_worklist.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def numbers(text):
    values = []
    for match in re.finditer(r"\d+(?:\.\d+)*(?:[kK]|천)?", text):
        value = match[0]
        multiplier = 1000 if value[-1] in "kK천" else 1
        if multiplier != 1:
            value = value[:-1]
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", value):
            value = value.replace(".", "")
        values.append(str(float(value) * multiplier))
    return Counter(values)


def protected(text):
    # 퍼센트 수치와 printf 자리표시자를 구별합니다.
    printf = re.findall(r"(?<!\d)%(?:\d+\$)?[-+#0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|ll|[hljztL])?[diuoxXeEfFgGaAcsp%]", text)
    bracket = re.findall(r"\[(?:[\d~x+/-]+|TAB|ESC)\]", text)
    breaks = re.findall(r"\r\n|[\r\n]", text)
    separators = re.findall(r"-{3,}", text)
    percentages = Counter(re.findall(r"\d+(?:\.\d+)?%", text))
    # 문장의 ' - 10 at a time' 같은 구분선을 음수로 오인하지 않습니다.
    signed = Counter("+" + value for value in re.findall(r"\+\s*(\d+)", text))
    signed.update("-" + value for value in re.findall(r"(?<![\d\w])-(\d+)", text))
    signed.update("-" + value for value in re.findall(r"^\[\d+\][^\r\n]*?\s-\s+(\d+)", text, re.MULTILINE))
    tags = re.findall(r"<[^>]+>", text)
    return {"printf": printf, "brackets": bracket, "breaks": breaks, "separators": separators,
            "percentages": dict(percentages), "signed_values": dict(signed), "tags": tags}


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--translation-id", default="translation_01")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_]+", args.translation_id):
        raise ValueError("번역 폴더 이름 오류")
    OUT = BASE / args.translation_id
    original = json.loads(SOURCE.read_text(encoding="utf-8"))
    path = OUT / "translations.json"
    translated = json.loads(path.read_text(encoding="utf-8"))
    errors, expansions, records, original_same, left_english = [], [], [], [], []
    corrections_applied = []
    allowed_words = {"Digital", "Deer", "Studio", "Steam", "TAB", "ESC", "Alt", "F", "Q", "Enter", "Backspace", "Tab",
                     "Clear", "Shift", "Ctrl", "Page", "Up", "Down", "End", "Home", "Select", "Execute", "Insert", "Delete", "Esc", "d", "k", "x"}
    if len(original) != len(translated):
        errors.append({"error": "원문 묶음 수 변경"})
    for index, (before, after) in enumerate(zip(original, translated)):
        if before["source"] != after["source"] or before["occurrences"] != after["occurrences"]:
            errors.append({"group": index, "error": "원문 또는 위치 목록 변경"})
        expected_locations = {r["location"] for r in before["occurrences"]}
        overrides = {r["location"]: r["translation"] for r in after.get("overrides", [])}
        if len(overrides) != len(after.get("overrides", [])) or set(overrides) - expected_locations:
            errors.append({"group": index, "error": "중복 또는 잘못된 위치별 번역"})
        for occurrence in before["occurrences"]:
            text = overrides.get(occurrence["location"], after.get("translation"))
            source = before["source"]
            row = {"group": index, "location": occurrence["location"], "source_sha256": sha(source.encode("utf-16le")),
                   "translation": text, "kind": occurrence["kind"], "status": "PASS"}
            if not isinstance(text, str) or not text or "\0" in text:
                errors.append({**row, "error": "누락·빈 값·NUL 포함"})
                continue
            row["translation_sha256"] = sha(text.encode("utf-16le"))
            row["required_bytes"] = len(text.encode("utf-16le")) + 2
            row["original_slot_bytes"] = occurrence["slot_bytes"]
            row["structural_builder"] = ("resource_builder" if occurrence["kind"] not in ("paragraph", "button_text", "event_string")
                                         else "button_builder" if occurrence["location"] == "object:68/extension/button_text@212" else None)
            if text == source:
                original_same.append(row)
                errors.append({**row, "error": "근거 없는 원문 동일"})
            old_tokens, new_tokens = protected(source), protected(text)
            corrected_dev = (occurrence["location"] == "object:510/paragraph:1"
                             and row["source_sha256"] == "9e0e2d94d08e2bca62ac9f6476f4462b9bd298856bf3e83a43d88121afca53b1"
                             and row["translation_sha256"] == "d60b66b69d0a0b5aa48d5ea02bccd81b73372894e4801829cf28d3332ed97bca")
            if corrected_dev:
                evidence = json.loads((OUT / "dev_instruction_corrections.json").read_text(encoding="utf-8"))
                if (evidence["translation_text_sha256"] != row["translation_sha256"]
                        or sha((ROOT / evidence["source_semantic_events_file"]).read_bytes()) != evidence["source_semantic_events_sha256"]):
                    errors.append({**row, "error": "개발 명령 원문 교정 근거 해시 불일치"})
                corrections_applied.append({"location": occurrence["location"], "evidence": "dev_instruction_corrections.json",
                                            "source_sha256": row["source_sha256"], "translation_sha256": row["translation_sha256"]})
                # 정확한 번역 해시와 이벤트 근거를 고정한 한 문단만 숫자·범위 표기 차이를 허용한다.
                for category in ("brackets", "percentages", "signed_values"):
                    old_tokens.pop(category)
                    new_tokens.pop(category)
            if old_tokens != new_tokens:
                errors.append({**row, "error": "자리표시자·대괄호·줄바꿈·구분선 불일치", "before": protected(source), "after": protected(text)})
            if numbers(source) != numbers(text) and not corrected_dev:
                errors.append({**row, "error": "수치 의미 불일치", "before": dict(numbers(source)), "after": dict(numbers(text))})
            if occurrence["kind"] == "menu_text":
                old_keys, new_keys = re.findall(r"&(.)", source), re.findall(r"&(.)", text)
                if old_keys != new_keys or source.split("\t")[1:] != text.split("\t")[1:]:
                    errors.append({**row, "error": "메뉴 단축키·탭 뒤 키 조합 불일치"})
            if row["required_bytes"] > row["original_slot_bytes"]:
                expansions.append({**row, "source": source})
                if row["structural_builder"] is None:
                    errors.append({**row, "error": "고정 슬롯 초과"})
            words = set(re.findall(r"[A-Za-z]+", text)) - allowed_words
            if words:
                left_english.append({**row, "words": sorted(words)})
                errors.append({**row, "error": "근거 없는 영문 잔존", "words": sorted(words)})
            records.append(row)
    locations = [r["location"] for r in records]
    if len(locations) != 855 or len(set(locations)) != 855:
        errors.append({"error": "위치 누락·중복", "count": len(locations), "unique": len(set(locations))})
    for filename, value in (("automatic_audit.jsonl", records),):
        (OUT / filename).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in value), encoding="utf-8")
    (OUT / "slot_expansions.json").write_text(json.dumps(expansions, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"status": "PASS" if not errors else "FAIL", "worklist_sha256": sha(SOURCE.read_bytes()),
               "translations_sha256": sha(path.read_bytes()), "groups": len(translated), "locations": len(records),
               "missing": sum(not x.get("translation") for x in translated), "unexplained_original_same": len(original_same),
               "unexplained_english": len(left_english), "fixed_slot_overflows_without_builder": sum(x.get("error") == "고정 슬롯 초과" for x in errors),
               "structural_expansions": len(expansions), "errors": errors,
               "source_corrections": corrections_applied,
               "scope": "각 위치의 원문·번역 대조, 제어 문자 순서, 숫자 의미, 단축키, 슬롯 검사",
               "not_covered": ["후보 파일 독립 재추출", "실제 화면 잘림·글꼴", "최종 게임 전체 분기 검수"]}
    (OUT / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("errors", "not_covered", "scope")}, ensure_ascii=False))
    for error in errors[:20]:
        print(json.dumps(error, ensure_ascii=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
