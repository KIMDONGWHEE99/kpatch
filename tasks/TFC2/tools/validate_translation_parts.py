from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from pathlib import Path


# 대괄호 안의 일반 문장은 번역 대상이지만 [SPACE] 같은 키 표시는 토큰입니다.
TOKEN_PATTERN = re.compile(r"<[^>]+>|\{[^{}]+\}|\[[A-Z0-9_+\-]+\]")


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 번역 분할 파일의 누락·태그·줄바꿈 검사")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    rows = {int(row["index"]): row for row in inventory["english_unique"]}
    translations: dict[int, str] = {}
    duplicate_indexes: list[int] = []
    for path in sorted(args.translations_dir.glob("localization_ko_part*.json")):
        part = json.loads(path.read_text(encoding="utf-8-sig"))
        for raw_index, value in part.items():
            index = int(raw_index)
            if index in translations:
                duplicate_indexes.append(index)
            translations[index] = str(value)

    unknown_indexes = sorted(set(translations) - set(rows))
    missing_indexes = sorted(set(rows) - set(translations))
    empty_indexes = sorted(index for index, value in translations.items() if not value.strip())
    token_mismatches: list[dict[str, object]] = []
    newline_mismatches: list[dict[str, object]] = []
    for index in sorted(set(rows) & set(translations)):
        source = str(rows[index]["source"])
        target = translations[index]
        source_tokens = TOKEN_PATTERN.findall(source)
        target_tokens = TOKEN_PATTERN.findall(target)
        if Counter(source_tokens) != Counter(target_tokens):
            token_mismatches.append(
                {
                    "index": index,
                    "source_tokens": source_tokens,
                    "target_tokens": target_tokens,
                    "source": source,
                    "translation": target,
                }
            )
        if source.count("\n") != target.count("\n") or source.count("\r") != target.count("\r"):
            newline_mismatches.append(
                {
                    "index": index,
                    "source_newlines": {"lf": source.count("\n"), "cr": source.count("\r")},
                    "target_newlines": {"lf": target.count("\n"), "cr": target.count("\r")},
                    "source": source,
                    "translation": target,
                }
            )

    report = {
        "expected": len(rows),
        "translated": len(translations),
        "duplicate_indexes": duplicate_indexes,
        "unknown_indexes": unknown_indexes,
        "missing_indexes": missing_indexes,
        "empty_indexes": empty_indexes,
        "token_mismatches": token_mismatches,
        "newline_mismatches": newline_mismatches,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    failed = bool(
        duplicate_indexes
        or unknown_indexes
        or empty_indexes
        or token_mismatches
        or newline_mismatches
        or (missing_indexes and not args.allow_incomplete)
    )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
