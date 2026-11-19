from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


TOKEN_PATTERN = re.compile(r"<[^>]+>|\{[^{}]+\}|\[[A-Z0-9_+\-]+\]")
ALLOWED_CLASSIFICATIONS = {
    "VISIBLE_TRANSLATE",
    "VISIBLE_KEEP",
    "INTERNAL",
    "MEDIA",
    "UNKNOWN",
}


def signature(text: str) -> dict[str, Any]:
    return {
        "tokens": Counter(TOKEN_PATTERN.findall(text)),
        "lf": text.count("\n"),
        "cr": text.count("\r"),
        "line_separator": text.count("\u2028"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="직접 UI 문구 분류와 번역 구조를 검증")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    rows = inventory.get("records", [])
    errors: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    translated = 0

    for row in rows:
        key = (str(row.get("file", "")), int(row.get("path_id", 0)))
        if key in seen:
            errors.append({"type": "duplicate_occurrence", "key": key})
        seen.add(key)

        classification = str(row.get("classification", ""))
        if classification not in ALLOWED_CLASSIFICATIONS:
            errors.append({"type": "invalid_classification", "key": key, "value": classification})
            continue
        if classification == "UNKNOWN":
            errors.append({"type": "unknown", "key": key})
        if classification != "VISIBLE_TRANSLATE":
            continue

        translated += 1
        source = str(row.get("source", ""))
        target_value = row.get("translation")
        if not isinstance(target_value, str) or not target_value:
            errors.append({"type": "empty_translation", "key": key, "source": source})
            continue
        target = target_value
        if unicodedata.normalize("NFC", target) != target:
            errors.append({"type": "not_nfc", "key": key, "source": source})
        if signature(source) != signature(target):
            errors.append(
                {
                    "type": "control_structure_mismatch",
                    "key": key,
                    "source": source,
                    "translation": target,
                    "source_signature": dict(signature(source)),
                    "translation_signature": dict(signature(target)),
                }
            )

    counts = Counter(str(row.get("classification", "")) for row in rows)
    report = {
        "schema_version": 1,
        "passed": not errors,
        "record_count": len(rows),
        "unique_occurrence_count": len(seen),
        "visible_translate_count": translated,
        "classification_counts": dict(counts),
        "unknown_count": counts.get("UNKNOWN", 0),
        "error_count": len(errors),
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
