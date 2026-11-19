"""Soulash 2 번역의 위치·원본 지문·제어 정보를 검사한다.

의미 교정이나 후보 실행 검수를 대신하지 않는다. 기본 정책은 모든 제어 토큰의
순서를 정확히 보존하며, 원본의 잘못된 태그는 번역 결함과 분리해 보고한다.
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/translation_work.jsonl"
DEFAULT_OUTPUT = ROOT / "working_private/SOULASH_2/text_validation"
PRIVATE_ROOTS = [ROOT / name for name in ("source_original", "extracted_private", "working_private", "build_candidate")]
COLOR_PREFIX = re.compile(r"\[/?color(?=[=\]\s])", re.IGNORECASE)
NAMED = re.compile(r"::[A-Za-z_][A-Za-z0-9_]*")
UNKNOWN_TAG = re.compile(r"\[/?([A-Za-z_][A-Za-z0-9_:-]*)[=:]")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def issue(code, **details):
    return {"code": code, **details}


def unicode_issues(value):
    errors = []
    for index, character in enumerate(value):
        cp = ord(character)
        if 0xD800 <= cp <= 0xDFFF:
            errors.append(issue("UNPAIRED_SURROGATE", offset=index, codepoint=f"U+{cp:04X}"))
        elif cp < 32 and character not in "\r\n\t":
            errors.append(issue("UNSUPPORTED_CONTROL_CHARACTER", offset=index, codepoint=f"U+{cp:04X}"))
    return errors


def controls(value):
    """글자가 아닌 제어 요소를 순서대로 추출하고 태그 스택을 별도 검사한다."""
    tokens, errors, stack = [], [], []
    index = 0
    while index < len(value):
        start = index
        character = value[index]
        if character in "\r\n\t":
            index += 1
            while index < len(value) and value[index] in "\r\n\t":
                index += 1
            tokens.append(("line_control", value[start:index]))
            continue
        if character == "\\":
            # JSON 해석 뒤 남은 역슬래시와 다음 문자는 리터럴 이스케이프로 보존한다.
            index = min(index + 2, len(value))
            tokens.append(("literal_escape", value[start:index]))
            continue
        named = NAMED.match(value, index)
        if named:
            tokens.append(("named", named.group()))
            index = named.end()
            continue
        if character == "[" and COLOR_PREFIX.match(value, index):
            end = value.find("]", index)
            if end == -1:
                errors.append(issue("UNCLOSED_COLOR_TAG", offset=index))
                tokens.append(("color_invalid", value[index:]))
                break
            token = value[index:end + 1]
            tokens.append(("color", token))
            if token == "[/color]":
                if stack:
                    stack.pop()
                else:
                    errors.append(issue("UNEXPECTED_COLOR_CLOSE", offset=index, token=token))
            else:
                match = re.fullmatch(r"\[color=([^\[\]]+)\]", token)
                if not match:
                    errors.append(issue("MALFORMED_COLOR_TAG", offset=index, token=token))
                else:
                    channels = match.group(1).split(",")
                    # REA: FUN_1407fd870은 RGB와 RGBA를 모두 지원한다.
                    # RGB의 알파는 기본 색에서 가져오며, 정수는 strtol 후 8비트로 저장된다.
                    if len(channels) not in (3, 4) or any(not re.fullmatch(r"\s*[+-]?\d+\s*", channel) for channel in channels):
                        errors.append(issue("COLOR_CHANNEL_SHAPE", offset=index, token=token))
                    elif any(not -(2**31) <= int(channel) < 2**31 for channel in channels):
                        errors.append(issue("COLOR_CHANNEL_RANGE", offset=index, token=token))
                    stack.append((index, token))
            index = end + 1
            continue
        if character == "[":
            unknown = UNKNOWN_TAG.match(value, index)
            if unknown:
                end = value.find("]", index)
                token = value[index:end + 1] if end >= 0 else value[index:]
                errors.append(issue("UNKNOWN_MARKUP_SYNTAX", offset=index, token=token))
                tokens.append(("unknown_markup", token))
                index = end + 1 if end >= 0 else len(value)
                continue
        if value.startswith("{{", index) or value.startswith("}}", index):
            tokens.append(("brace_escape", value[index:index + 2]))
            index += 2
            continue
        if character == "{":
            depth, index = 1, index + 1
            while index < len(value) and depth:
                if value[index] == "{":
                    depth += 1
                elif value[index] == "}":
                    depth -= 1
                index += 1
            token = value[start:index]
            tokens.append(("format", token))
            if depth:
                errors.append(issue("UNCLOSED_FORMAT_FIELD", offset=start, token=token))
            elif not re.fullmatch(r"\{(?:[0-9]+|[A-Za-z_][A-Za-z0-9_]*)?(?::[^\r\n]*)?\}", token):
                errors.append(issue("UNKNOWN_FORMAT_SYNTAX", offset=start, token=token))
            continue
        if character == "}":
            tokens.append(("format_invalid", character))
            errors.append(issue("UNEXPECTED_FORMAT_CLOSE", offset=index))
        index += 1
    for offset, token in stack:
        errors.append(issue("UNCLOSED_COLOR_OPEN", offset=offset, token=token))
    return tokens, errors


def validate_pair(source, target):
    source_errors = unicode_issues(source)
    source_tokens, source_syntax = controls(source)
    source_errors.extend(source_syntax)
    target_errors = unicode_issues(target)
    target_tokens, target_syntax = controls(target)
    target_errors.extend(target_syntax)
    if not target.strip():
        target_errors.append(issue("EMPTY_TRANSLATION"))
    if unicodedata.normalize("NFC", target) != target:
        target_errors.append(issue("NON_NFC_TRANSLATION"))
    if source_tokens != target_tokens:
        mismatch = next((index for index, pair in enumerate(zip(source_tokens, target_tokens)) if pair[0] != pair[1]), min(len(source_tokens), len(target_tokens)))
        target_errors.append(issue("CONTROL_STREAM_MISMATCH", first_difference=mismatch,
                                   expected=source_tokens[max(0, mismatch - 2):mismatch + 3],
                                   actual=target_tokens[max(0, mismatch - 2):mismatch + 3],
                                   expected_count=len(source_tokens), actual_count=len(target_tokens)))
    # 같은 결함이 원문에서 그대로 유래하면 번역의 신규 결함으로 집계하지 않는다.
    inherited = []
    if source_tokens == target_tokens:
        source_codes = Counter(error["code"] for error in source_syntax)
        remaining = []
        for error in target_errors:
            if source_codes[error["code"]]:
                source_codes[error["code"]] -= 1
                inherited.append(error)
            else:
                remaining.append(error)
        target_errors = remaining
    return {"passed": not source_errors and not target_errors, "source_issues": source_errors,
            "translation_issues": target_errors, "inherited_source_issues": inherited,
            "source_tokens": source_tokens, "target_tokens": target_tokens}


def read_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                yield line_number, json.loads(line)


def collect_profile(inventory):
    counts, formats, names, tags, ordinary_brackets = Counter(), Counter(), Counter(), Counter(), Counter()
    source_issues, examples = [], {}
    rows = 0
    for line, row in read_jsonl(inventory):
        if row.get("role") not in (None, "primary_english"):
            continue
        source = row["source"]
        rows += 1
        tokens, errors = controls(source)
        errors.extend(unicode_issues(source))
        if errors:
            source_issues.append({"location_id": row["location_id"], "source_value_sha256": row.get("source_value_sha256"), "issues": errors})
        for kind, token in tokens:
            counts[kind] += 1
            if kind == "format":
                formats[token] += 1
            elif kind == "named":
                names[token] += 1
            elif kind == "color":
                tags[token] += 1
            examples.setdefault(kind, {"location_id": row["location_id"], "token": token})
        for match in re.finditer(r"\[([^\[\]\r\n]+)\]", source):
            if not COLOR_PREFIX.match(match.group()):
                ordinary_brackets[match.group()] += 1
    return {"rows": rows, "token_counts": dict(counts), "format_tokens": dict(formats),
            "named_tokens": dict(names), "color_tokens": dict(tags), "ordinary_brackets": dict(ordinary_brackets),
            "examples": examples, "source_issue_locations": len(source_issues), "source_issues": source_issues,
            "policy": "제어 토큰의 종류·원문·순서를 모두 보존. 이름 치환 키의 이동도 기본적으로 허용하지 않음.",
            "color_contract": "동일 빌드의 REA 분석: RGB/RGBA, signed 32비트 정수→8비트 색상 저장. 기존 2555는 251로 좁혀지며 원본 태그를 변경하지 않음.",
            "limitations": ["원문 구조와 실제 코드 계약을 조사한 결과이며 모든 색상 문구를 실행 화면에서 확인한 검사가 아님", "제어 정보가 같아도 번역 의미·자동 인수의 역할은 별도 문맥 교정이 필요"]}


def canonical_report(canonical, inventory, allow_partial):
    expected, inventory_errors = {}, []
    for line, row in read_jsonl(inventory):
        location = row.get("location_id")
        if location in expected:
            inventory_errors.append(issue("DUPLICATE_INVENTORY_LOCATION", location_id=location, line=line))
        expected[location] = row
    findings, seen = [], set()
    row_count, passed = 0, 0
    for line, row in read_jsonl(canonical):
        row_count += 1
        location = row.get("location_id")
        errors = []
        for field in ("location_id", "source", "target", "source_value_sha256", "source_file_sha256"):
            if not isinstance(row.get(field), str):
                errors.append(issue("REQUIRED_FIELD_INVALID", field=field))
        if isinstance(location, str) and location in seen:
            errors.append(issue("DUPLICATE_TRANSLATION_LOCATION"))
        if isinstance(location, str):
            seen.add(location)
        match = expected.get(location) if isinstance(location, str) else None
        if match is None:
            errors.append(issue("UNKNOWN_LOCATION"))
        else:
            for field in ("source", "source_value_sha256", "source_file_sha256"):
                if row.get(field) != match.get(field):
                    errors.append(issue("SOURCE_IDENTITY_MISMATCH", field=field))
        source = row.get("source")
        target = row.get("target")
        pair = None
        if isinstance(source, str):
            try:
                actual_hash = sha256_bytes(source.encode("utf-8", errors="strict"))
                if row.get("source_value_sha256") != actual_hash:
                    errors.append(issue("SOURCE_VALUE_HASH_MISMATCH"))
            except UnicodeError:
                errors.append(issue("INVALID_SOURCE_UNICODE"))
        if isinstance(source, str) and isinstance(target, str):
            pair = validate_pair(source, target)
        ok = not errors and pair is not None and pair["passed"]
        passed += ok
        if not ok:
            findings.append({"line": line, "location_id": location, "identity_issues": errors,
                             "source_issues": pair["source_issues"] if pair else [],
                             "translation_issues": pair["translation_issues"] if pair else [],
                             "inherited_source_issues": pair["inherited_source_issues"] if pair else []})
    missing = sorted(set(expected) - seen, key=str)
    failed = bool(findings or inventory_errors or (missing and not allow_partial))
    return {"status": "FAIL" if failed else "PASS", "scope": "SUBSET" if allow_partial else "FULL_INVENTORY",
            "rows": row_count, "passed_rows": passed, "failed_rows": len(findings),
            "expected_locations": len(expected), "missing_count": len(missing), "missing_locations": missing,
            "inventory_issues": inventory_errors, "findings": findings,
            "scope_limit": "부분 검사 통과는 전체 번역 완료나 G3/G4 통과가 아님" if allow_partial else "문맥 번역 품질과 후보 위치 재추출·게임 실행은 별도 검사"}


def selftests():
    cases = [
        ("plain", "New game", "새 게임", True, None),
        ("mixed_controls", "{} gains [color=1, 2, 3, 255]{:.0f}[/color] ::damage.\nNext", "{}: [color=1, 2, 3, 255]{:.0f}[/color] ::damage 획득.\n다음", True, None),
        ("ordinary_brackets", "[Parry {}%] {} hits {}", "[막기 {}%] {}의 공격 대상: {}", True, None),
        ("nested_color", "[color=1,2,3,255]A[color=4,5,6,255]B[/color]C[/color]", "[color=1,2,3,255]가[color=4,5,6,255]나[/color]다[/color]", True, None),
        ("numbered_exact", "{0}: {1:.0f}", "{0}: {1:.0f}", True, None),
        ("escaped_braces", "{{value}} {}", "{{값}} {}", True, None),
        ("literal_escape", r"Line\n{}", r"줄\n{}", True, None),
        ("color_attribute_damage", "[color=1,2,3,255]A[/color]", "[color=1,2,4,255]가[/color]", False, "CONTROL_STREAM_MISMATCH"),
        ("tag_nesting_damage", "[color=1,2,3,255]A[/color]", "[/color]가[color=1,2,3,255]", False, "UNEXPECTED_COLOR_CLOSE"),
        ("tag_boundary_damage", "[color=1,2,3,255]{}[/color] {}", "[color=1,2,3,255]{} {}[/color]", False, "CONTROL_STREAM_MISMATCH"),
        ("empty", "A", "  ", False, "EMPTY_TRANSLATION"),
        ("format_damage", "{:.0f}", "{:.1f}", False, "CONTROL_STREAM_MISMATCH"),
        ("automatic_index_change", "{}", "{0}", False, "CONTROL_STREAM_MISMATCH"),
        ("format_reordered", "{:.0f} {}", "{} {:.0f}", False, "CONTROL_STREAM_MISMATCH"),
        ("format_unclosed", "{}", "{", False, "UNCLOSED_FORMAT_FIELD"),
        ("named_missing", "::damage ::damage_type", "::damage 피해", False, "CONTROL_STREAM_MISMATCH"),
        ("escape_damage", "{{value}}", "{value}", False, "CONTROL_STREAM_MISMATCH"),
        ("literal_escape_to_newline", r"Line\n{}", "줄\n{}", False, "CONTROL_STREAM_MISMATCH"),
        ("newline_loss", "A\n\nB", "가\n나", False, "CONTROL_STREAM_MISMATCH"),
        ("newline_type", "A\r\nB", "가\n나", False, "CONTROL_STREAM_MISMATCH"),
        ("control_order", "{}\n::name", "::name\n{}", False, "CONTROL_STREAM_MISMATCH"),
        ("decomposed_hangul", "A", "\u1100\u1161", False, "NON_NFC_TRANSLATION"),
        ("invalid_unicode", "A", "\ud800", False, "UNPAIRED_SURROGATE"),
        ("null_control", "A", "가\x00", False, "UNSUPPORTED_CONTROL_CHARACTER"),
    ]
    results = []
    for name, source, target, expected, expected_code in cases:
        result = validate_pair(source, target)
        codes = [error["code"] for error in result["translation_issues"]]
        ok = result["passed"] == expected and (expected_code is None or expected_code in codes)
        results.append({"case": name, "passed": ok, "expected_pair_pass": expected, "actual_pair_pass": result["passed"], "translation_codes": codes})
    inherited = validate_pair("[color=1,2,3,2147483648]A[/color]", "[color=1,2,3,2147483648]가[/color]")
    results.append({"case": "source_defect_separate", "passed": bool(inherited["source_issues"]) and not inherited["translation_issues"] and bool(inherited["inherited_source_issues"]) and not inherited["passed"]})
    shape = validate_pair("[color=1,2,3]A[/color]", "[color=1,2,3]가[/color]")
    results.append({"case": "source_rgb_supported", "passed": shape["passed"] and not shape["source_issues"]})
    narrowed = validate_pair("[color=1,2,3,2555]A[/color]", "[color=1,2,3,2555]가[/color]")
    results.append({"case": "source_byte_narrowing_preserved", "passed": narrowed["passed"]})
    changed = validate_pair("[color=1,2,3,2555]A[/color]", "[color=1,2,3,251]가[/color]")
    results.append({"case": "source_byte_narrowing_must_not_rewrite", "passed": not changed["passed"] and any(e["code"] == "CONTROL_STREAM_MISMATCH" for e in changed["translation_issues"])})
    wrong_shape = validate_pair("[color=1,2]A[/color]", "[color=1,2]가[/color]")
    results.append({"case": "two_color_channels_rejected", "passed": not wrong_shape["passed"]})
    return {"status": "PASS" if all(result["passed"] for result in results) else "FAIL", "count": len(results), "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--allow-partial", action="store_true", help="부분 번역 검사임을 명시하며 전체 통과로 취급하지 않음")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--selftest-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not any(output.is_relative_to(path.resolve()) for path in PRIVATE_ROOTS):
        parser.error("원문이 포함될 수 있는 결과는 네 비공개 영역 안에만 저장합니다.")
    output.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    started = datetime.now(timezone.utc).isoformat()
    report = {"game_id": "SOULASH_2", "check_id": "TEXT_CONTROL_VALIDATION", "started": started,
              "tool_sha256": sha256_file(__file__), "python": sys.version, "command": sys.argv,
              "selftests": selftests()}
    evidence_root = ROOT / "working_private/SOULASH_2/rea/responses"
    report["color_parser_evidence"] = [{"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)}
                                       for path in [evidence_root / "pseudo_color_render_parser.json", evidence_root / "pseudo_color_integer.json"] if path.exists()]
    if not args.selftest_only:
        report["inventory_sha256"] = sha256_file(args.inventory)
        report["profile"] = collect_profile(args.inventory)
    if args.canonical:
        report["canonical_sha256"] = sha256_file(args.canonical)
        report["canonical"] = canonical_report(args.canonical, args.inventory, args.allow_partial)
    report["status"] = report.get("canonical", {}).get("status", "NOT_RUN")
    if report["selftests"]["status"] != "PASS":
        report["status"] = "FAIL"
    if not args.selftest_only:
        report["inventory_sha256_after"] = sha256_file(args.inventory)
        if report["inventory_sha256_after"] != report["inventory_sha256"]:
            report["status"] = "STALE"
    if args.canonical:
        report["canonical_sha256_after"] = sha256_file(args.canonical)
        if report["canonical_sha256_after"] != report["canonical_sha256"]:
            report["status"] = "STALE"
    report["finished"] = datetime.now(timezone.utc).isoformat()
    path = output / ("text_controls_" + run_id + ".json")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
    summary = {"output": str(path), "status": report["status"], "selftests": report["selftests"]["status"], "selftest_count": report["selftests"]["count"]}
    if "profile" in report:
        summary.update({"rows": report["profile"]["rows"], "tokens": report["profile"]["token_counts"], "source_issue_locations": report["profile"]["source_issue_locations"]})
    if "canonical" in report:
        summary.update({"canonical_status": report["canonical"]["status"], "canonical_scope": report["canonical"]["scope"], "failed_rows": report["canonical"]["failed_rows"]})
    print(json.dumps(summary, ensure_ascii=True))
    return 1 if report["status"] in ("FAIL", "STALE") else 0


if __name__ == "__main__":
    raise SystemExit(main())
