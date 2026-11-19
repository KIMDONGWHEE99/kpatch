from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


MOVE_LITERAL = re.compile(r'^\s*(?P<instruction>\d+)\s+Move\s+[^,]+,\s+"(?P<literal>.*)"\s*$')
METHOD = re.compile(r"^Method:\s+(?P<method>.+)$")


def looks_human_facing(value: str) -> bool:
    """식별자와 파일 경로를 빼고 사람이 읽는 문구 후보를 넓게 잡는다."""
    if not value or not re.search(r"[A-Za-z]", value):
        return False
    if value.startswith((
        "event:/", "snapshot:/", "bus:/", "vca:/", "GUID:", "http://", "https://",
        "Assets/", "Packages/", "resources/", "/Saves/", "/User/",
    )):
        return False
    if re.fullmatch(r"[A-Za-z0-9_.:/\\+\-]+", value):
        return False
    return bool(re.search(r"\s", value) or re.search(r"[.!?,:;%{}<>]", value))


def main() -> None:
    parser = argparse.ArgumentParser(description="Cpp2IL ISIL에서 실행 코드 문자열 후보를 조사")
    parser.add_argument("--isil-root", type=Path, required=True)
    parser.add_argument("--localization", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    localization = json.loads(args.localization.read_text(encoding="utf-8"))
    localized_sources = {
        str(row["source"])
        for row in localization.get("entries", [])
        if row.get("locale") == "en"
    }
    review = json.loads(args.review.read_text(encoding="utf-8"))
    translations = {str(key): str(value) for key, value in review.get("translations", {}).items()}
    keep = {str(value) for value in review.get("keep", [])}

    occurrences: list[dict[str, object]] = []
    by_literal: dict[str, list[dict[str, object]]] = defaultdict(list)
    file_count = 0
    for path in sorted(args.isil_root.rglob("*.txt")):
        file_count += 1
        method = ""
        in_isil = False
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            method_match = METHOD.match(line)
            if method_match:
                method = method_match.group("method")
                in_isil = False
                continue
            if line == "ISIL:":
                in_isil = True
                continue
            if not in_isil:
                continue
            match = MOVE_LITERAL.match(line)
            if not match:
                continue
            literal = match.group("literal")
            row = {
                "file": path.relative_to(args.isil_root).as_posix(),
                "line": line_number,
                "method": method,
                "instruction": int(match.group("instruction")),
                "literal": literal,
            }
            occurrences.append(row)
            by_literal[literal].append(row)

    unique: list[dict[str, object]] = []
    for literal in sorted(by_literal, key=lambda value: (value.casefold(), value)):
        refs = by_literal[literal]
        human_facing = looks_human_facing(literal)
        if literal in translations:
            classification = "VISIBLE_TRANSLATE"
            translation = translations[literal]
            reason = "실행 코드가 화면에 조합하는 문구로 확인"
        elif literal in keep:
            classification = "VISIBLE_KEEP"
            translation = literal
            reason = "화면에 쓰일 수 있으나 언어와 무관한 서식·식별 표기"
        else:
            classification = "INTERNAL"
            translation = None
            reason = (
                "사람이 읽는 문장이 아닌 키·경로·포맷·식별자"
                if not human_facing
                else "호출 메서드 검토 결과 로그·오류 진단·이벤트 키·시험 코드"
            )
        unique.append(
            {
                "literal": literal,
                "occurrence_count": len(refs),
                "human_facing_candidate": human_facing,
                "localization_source_exact": literal in localized_sources,
                "classification": classification,
                "translation": translation,
                "reason": reason,
                "references": refs,
            }
        )

    report = {
        "schema_version": 1,
        "isil_root": str(args.isil_root.resolve()),
        "file_count": file_count,
        "occurrence_count": len(occurrences),
        "unique_count": len(unique),
        "human_facing_candidate_count": sum(bool(row["human_facing_candidate"]) for row in unique),
        "localization_source_exact_count": sum(bool(row["localization_source_exact"]) for row in unique),
        "classification_counts": dict(sorted(Counter(str(row["classification"]) for row in unique).items())),
        "unknown_count": sum(row["classification"] == "UNKNOWN" for row in unique),
        "review_translation_keys_missing_from_isil": sorted(set(translations) - set(by_literal)),
        "review_keep_keys_missing_from_isil": sorted(keep - set(by_literal)),
        "files_with_literals": dict(
            sorted(Counter(str(row["file"]) for row in occurrences).items())
        ),
        "unique": unique,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({key: value for key, value in report.items() if key not in {"unique", "files_with_literals"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
