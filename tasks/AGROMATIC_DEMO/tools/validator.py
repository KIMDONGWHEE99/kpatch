"""번역 문구의 자리표시자·태그·제어문자를 독립적으로 검사합니다."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "working_private/AGROMATIC_DEMO"
TRANSLATIONS = WORK / "translations"
PERCENT = re.compile(r"%(?:\d+\$)?[-+#0]*\d*(?:\.\d+)?[diouxXeEfFgGcrsv]|%%")
BRACES = re.compile(r"(?<!\{)\{[^{}\n]+\}(?!\})")
BRACKETS = re.compile(r"\[[^\]\n]*\]")
CONTROLS = re.compile(r"\r\n|[\r\n\t]")
TAG_NAMES = {
    "b", "i", "u", "s", "code", "kbd", "center", "left", "right", "fill",
    "indent", "url", "img", "font", "font_size", "color", "bgcolor", "bg_color",
    "fgcolor", "outline_color", "outline_size", "table", "cell", "pulse", "wave",
    "tornado", "shake", "fade", "rainbow", "lang", "opentype_features", "p", "ul",
    "ol", "li", "dropcap", "hint", "br", "hr", "lb", "rb",
}
VOID_TAGS = {"br", "hr", "lb", "rb"}
TAG_HEADER = re.compile(r"^\[(/?)([A-Za-z_][A-Za-z_0-9]*)(?=[\s=\]])")
# 다음 두 항목은 인자·태그가 아니라 실제 표시되는 대괄호 문구입니다.
DEFAULT_LITERAL_BRACKETS = {"[ASSIGNED]", "[ View the photo ]"}


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path: Path, value: Any) -> None:
    resolved = path.resolve()
    relative = resolved.relative_to(ROOT.resolve())
    if not relative.parts or relative.parts[0] not in {"working_private", "extracted_private", "build_candidate"}:
        raise ValueError("검사 결과는 작업 공간의 비공개 영역에만 저장합니다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def tag_parts(text: str) -> tuple[list[str], list[str]]:
    """실제 BBCode와 명령 인자·표시 대괄호를 구분합니다."""
    tags, other = [], []
    for token in BRACKETS.findall(text):
        match = TAG_HEADER.match(token)
        if match and match.group(2) in TAG_NAMES:
            tags.append(token)
        else:
            other.append(token)
    return tags, other


def tag_structure(tags: list[str], allow_fragments: bool = True) -> dict:
    """중첩 위반을 검출하며 문자열 조각의 외부 닫힘·남은 열림도 기록합니다."""
    stack, external_closes, errors, pairs = [], [], [], []
    for index, token in enumerate(tags):
        match = TAG_HEADER.match(token)
        assert match
        closing, name = bool(match.group(1)), match.group(2)
        if name in VOID_TAGS:
            if closing:
                errors.append({"index": index, "tag": token, "reason": "닫을 수 없는 단일 태그"})
            continue
        if closing:
            if stack and stack[-1][0] == name:
                opened = stack.pop()
                pairs.append([opened[1], index])
            elif stack:
                errors.append({"index": index, "tag": token, "reason": "태그 중첩 순서 위반", "open_stack": [t[0] for t in stack]})
            else:
                external_closes.append(name)
        else:
            stack.append((name, index))
    if not allow_fragments and (external_closes or stack):
        errors.append({"reason": "완결 문구에서 열린 태그 또는 외부 닫힘", "external_closes": external_closes, "open_stack": [t[0] for t in stack]})
    return {"external_closes": external_closes, "open_stack": [t[0] for t in stack], "pairs": pairs, "errors": errors}


def validate_text(source: str, target: str, *, allow_fragments: bool = True,
                  literal_brackets: set[str] | None = None,
                  require_named_order: bool = False) -> list[dict]:
    """이름 있는 인자는 이름·횟수, 위치 인자와 태그는 순서를 비교합니다."""
    errors = []
    if not isinstance(source, str) or not isinstance(target, str):
        return [{"kind": "type", "reason": "원문·번역은 문자열이어야 합니다."}]
    if source.strip() and not target.strip():
        errors.append({"kind": "empty", "reason": "표시 문구의 번역이 비었습니다."})
    named_source, named_target = BRACES.findall(source), BRACES.findall(target)
    named_ok = named_source == named_target if require_named_order else Counter(named_source) == Counter(named_target)
    if not named_ok:
        errors.append({"kind": "named_placeholders", "source": named_source, "target": named_target})
    percent_source, percent_target = PERCENT.findall(source), PERCENT.findall(target)
    if percent_source != percent_target:
        errors.append({"kind": "percent_placeholders", "source": percent_source, "target": percent_target})
    control_source, control_target = CONTROLS.findall(source), CONTROLS.findall(target)
    if control_source != control_target:
        errors.append({"kind": "control_characters", "source": control_source, "target": control_target})
    tags_source, brackets_source = tag_parts(source)
    tags_target, brackets_target = tag_parts(target)
    if tags_source != tags_target:
        errors.append({"kind": "bbcode_order_attributes", "source": tags_source, "target": tags_target})
    structure_source = tag_structure(tags_source, allow_fragments)
    structure_target = tag_structure(tags_target, allow_fragments)
    if structure_source["errors"]:
        errors.append({"kind": "source_bbcode_nesting", "details": structure_source})
    if structure_target["errors"]:
        errors.append({"kind": "target_bbcode_nesting", "details": structure_target})
    if {k: structure_source[k] for k in ("external_closes", "open_stack", "pairs")} != {k: structure_target[k] for k in ("external_closes", "open_stack", "pairs")}:
        errors.append({"kind": "bbcode_boundary", "source": structure_source, "target": structure_target})
    allowed = DEFAULT_LITERAL_BRACKETS if literal_brackets is None else literal_brackets
    # 표시 대괄호의 한국어 대응도 제외하되, 다른 인자 대괄호는 엄밀히 보존합니다.
    literal_pairs = {"[ASSIGNED]": "[배정됨]", "[ View the photo ]": "[ 사진 보기 ]"}
    ignored_targets = {literal_pairs[s] for s in allowed if s in brackets_source and s in literal_pairs}
    protected_source = [s for s in brackets_source if s not in allowed]
    protected_target = [s for s in brackets_target if s not in ignored_targets]
    if protected_source != protected_target:
        errors.append({"kind": "bracket_tokens", "source": protected_source, "target": protected_target})
    return errors


def source_text(row: dict) -> str:
    """원본 번역표보다 현재 빌드에서 확인한 원문을 우선합니다."""
    return row.get("effective_source", row.get("source_text", row.get("source", "")))


def validate_rows(rows: list[dict], origin: str) -> dict:
    errors, classifications = [], Counter()
    for index, row in enumerate(rows):
        classifications[row.get("classification", "UNKNOWN")] += 1
        row_id = row.get("key") or row.get("location_id") or f"{origin}#{index}"
        if row.get("classification", "UNKNOWN") == "UNKNOWN":
            errors.append({"index": index, "id": row_id, "kind": "classification", "reason": "미분류 문구"})
        if "target" not in row:
            errors.append({"index": index, "id": row_id, "kind": "missing_target"})
            continue
        for error in validate_text(source_text(row), row["target"]):
            errors.append({"index": index, "id": row_id, **error})
    return {"origin": origin, "rows": len(rows), "classifications": dict(classifications), "errors": errors,
            "status": "FAIL" if errors else "PASS"}


def synthetic_tests() -> dict:
    """같은 개수의 태그 바꿔치기도 실패해야 합니다."""
    failures = {
        "empty_target": ("Welcome", ""),
        "deleted_placeholder": ("%s: %d", "%s"),
        "placeholder_count": ("{count}/{count}", "{count}"),
        "positional_order": ("%s: %d", "%d: %s"),
        "tag_order_swap": ("[b][color=red]A[/color][/b]", "[color=red][b]가[/b][/color]"),
        "tag_crossing": ("[b][color=red]A[/color][/b]", "[b][color=red]가[/b][/color]"),
        "tag_attribute_change": ("[color=red]A[/color]", "[color=blue]가[/color]"),
        "control_order": ("a\nb\tc", "가\t나\n다"),
        "command_argument": ("spawn [item_id]", "spawn [아이템]"),
    }
    results = [{"case": name, "expected": "FAIL", "observed": "FAIL" if validate_text(*pair) else "PASS"}
               for name, pair in failures.items()]
    for name, pair in {
        "named_reorder": ("{item}: {count}", "{count}개의 {item}"),
        "fragment_open": ("[color=red]Error: ", "[color=red]오류: "),
        "fragment_close": ("[/color]", "[/color]"),
        "literal_percent": ("20% faster", "20% 더 빠름"),
        "literal_status": ("[ASSIGNED]", "[배정됨]"),
    }.items():
        results.append({"case": name, "expected": "PASS", "observed": "FAIL" if validate_text(*pair) else "PASS"})
    return {"status": "PASS" if all(r["expected"] == r["observed"] for r in results) else "FAIL", "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--translations", nargs="+", type=Path, default=[TRANSLATIONS / n for n in (
        "ko_part_a.json", "ko_part_b.json", "supplemental_ko.json", "supplemental_extra_ko.json",
        "resource_extra_ko.json", "resource_story_extra_ko.json")])
    parser.add_argument("--report", type=Path, default=TRANSLATIONS / "format_validation_report.json")
    args = parser.parse_args()
    reports = []
    for path in args.translations:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("번역 입력은 행 배열이어야 합니다: " + str(path))
        report = validate_rows(rows, path.name)
        report["sha256"] = sha(path)
        reports.append(report)
    tests = synthetic_tests()
    output = {"schema": "agromatic.format-validation.v1", "validator_sha256": sha(Path(__file__)),
              "validation_source": "effective_source → source_text → source", "synthetic_tests": tests,
              "files": reports, "error_count": sum(len(r["errors"]) for r in reports)}
    output["status"] = "PASS" if not output["error_count"] and tests["status"] == "PASS" else "FAIL"
    save(args.report, output)
    print(json.dumps({"status": output["status"], "rows": sum(r["rows"] for r in reports),
                      "errors": output["error_count"], "synthetic": tests["status"]}, ensure_ascii=False))
    return 0 if output["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
