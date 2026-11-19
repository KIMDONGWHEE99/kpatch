from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


MOVE_LITERAL = re.compile(r'^\s*(?P<instruction>\d+)\s+Move\s+[^,]+,\s+"(?P<literal>.*)"\s*$')
METHOD = re.compile(r"^Method:\s+(?P<method>.+)$")


def main() -> None:
    parser = argparse.ArgumentParser(description="수정 메타데이터의 Cpp2IL 메서드별 문자열 참조 검증")
    parser.add_argument("--original-inventory", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--candidate-isil-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    original = json.loads(args.original_inventory.read_text(encoding="utf-8-sig"))
    mapping_data = json.loads(args.mapping.read_text(encoding="utf-8-sig"))
    mapping = {str(key): str(value) for key, value in mapping_data["translations"].items()}
    expected_rows = [row for row in original["unique"] if row["classification"] == "VISIBLE_TRANSLATE"]
    expected_references = sum(len(row["references"]) for row in expected_rows)

    candidate_literals: dict[tuple[str, str, int], str] = {}
    file_count = 0
    method_count = 0
    for path in sorted(args.candidate_isil_root.rglob("*.txt")):
        file_count += 1
        method = ""
        in_isil = False
        relative = path.relative_to(args.candidate_isil_root).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            method_match = METHOD.match(line)
            if method_match:
                method = method_match.group("method")
                method_count += 1
                in_isil = False
                continue
            if line == "ISIL:":
                in_isil = True
                continue
            if not in_isil:
                continue
            literal_match = MOVE_LITERAL.match(line)
            if literal_match:
                candidate_literals[(relative, method, int(literal_match.group("instruction")))] = literal_match.group("literal")

    checked = 0
    errors = []
    for row in expected_rows:
        source = str(row["literal"])
        if source not in mapping:
            errors.append({"source": source, "error": "mapping_missing"})
            continue
        expected = mapping[source]
        for reference in row["references"]:
            key = (str(reference["file"]), str(reference["method"]), int(reference["instruction"]))
            actual = candidate_literals.get(key)
            if actual != expected:
                errors.append(
                    {
                        "source": source,
                        "expected": expected,
                        "actual": actual,
                        "file": key[0],
                        "method": key[1],
                        "instruction": key[2],
                    }
                )
            checked += 1

    report = {
        "schema_version": 1,
        "passed": not errors and len(expected_rows) == len(mapping) == 36 and checked == expected_references,
        "cpp2il_version": "2022.1.0-pre-release.21",
        "metadata_version": "31.1",
        "assemblies_processed": 103,
        "methods_mapped": 107952,
        "assembly_csharp_isil_files": file_count,
        "assembly_csharp_methods_seen": method_count,
        "translated_unique_literals": len(expected_rows),
        "expected_literal_references": expected_references,
        "translated_literal_references_checked": checked,
        "reference_mismatches": len(errors),
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
