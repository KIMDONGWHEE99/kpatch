#!/usr/bin/env python3
"""IL2CPP 문자열에서 게임 화면에 표시될 가능성이 높은 문구를 수집한다."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


GAME_TERMS = re.compile(
    r"(?i)profit|profiterra|quota|shift|mineral|train|station|outpost|hub|"
    r"booster|growth|cryst|token|cryptoarachnid|arachne|behemoth|leviathan|"
    r"bug|ammo|maintenance|resource|infrastructure|vibration|structural|"
    r"delivery|camera|\bmap\b|minimap|stakeholder|operator|employee|human resource|"
    r"cargo|wagon|brake|throttle|track|loading|reroll|\btier\b|\bdeck\b|"
    r"mining|processing|storage|supply|fauna|upgrade|\bjob\b|locomotive|"
    r"integrity|turret|drone|repair|personnel|growth|share received|"
    r"select shift|back to|continue|confirm|congratulations|unlocked"
)

INTERNAL_NOISE = re.compile(
    r"(?i)^(?:\[|<|/|\\|[a-z]:\\|https?://|unity|addressable|android|"
    r"serialized|texture|shader|render|control |input |system\.|microsoft\.|"
    r"failed|failure|error|exception|invalid|cannot|can't|unable|missing|"
    r"trying to|could not|couldn't|assert|debug|warning|unknown|unsupported|"
    r"loading asset|unloading asset|created |destroyed |adding |removing )"
)

IDENTIFIER = re.compile(
    r"^(?:[A-Za-z0-9]+[._:/-]){1,}[A-Za-z0-9._:/-]+$|"
    r"^[A-Za-z][A-Za-z0-9_]*(?:<[A-Za-z0-9_, .]+>)?$"
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def add_mapping(mapping: dict[str, str], source: object, translation: object) -> None:
    if isinstance(source, str) and isinstance(translation, str) and source != translation:
        mapping[source] = translation


def collect_known(root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    list_files = [
        root / "translation_entries.json",
        root / "resource_display_strings_ko.json",
        *sorted(root.glob("direct_text_level*_ko.json")),
    ]
    dict_files = [
        root / "scene_translation_overrides.json",
        root / "resource_translation_overrides_stats.json",
        root / "resource_translation_overrides_tech.json",
        root / "resource_translation_overrides_upgrades.json",
        root / "metadata_translation_overrides.json",
    ]
    for path in list_files:
        if not path.exists():
            continue
        data = load_json(path)
        for row in data:
            if isinstance(row, dict):
                add_mapping(mapping, row.get("source"), row.get("translation"))
    for path in dict_files:
        if not path.exists():
            continue
        data = load_json(path)
        if isinstance(data, dict):
            for source, translation in data.items():
                add_mapping(mapping, source, translation)
    return mapping


def looks_visible(value: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    stripped = value.strip()
    if not stripped or len(stripped) > 2000:
        return False, reasons
    if INTERNAL_NOISE.search(stripped):
        return False, reasons
    if GAME_TERMS.search(stripped):
        reasons.append("game-term")
    letters = re.findall(r"[A-Za-z]", stripped)
    upper = re.findall(r"[A-Z]", stripped)
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", stripped)
    if len(words) >= 2 and len(letters) >= 4 and len(upper) / max(len(letters), 1) >= 0.72:
        reasons.append("all-caps")
    if len(words) >= 5 and re.search(r"[.!?]|\n", stripped):
        reasons.append("sentence")
    if re.search(r"\*\*|<HIGH>|<sprite|%[A-Za-z0-9_.]+%", stripped):
        reasons.append("markup")
    if IDENTIFIER.fullmatch(stripped) and not re.search(r"[ .!?\n]", stripped):
        return False, []
    return bool(reasons), reasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--literals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    known = collect_known(args.root)
    literals = load_json(args.literals)
    rows = []
    for index, literal in enumerate(literals):
        value = literal["value"]
        visible, reasons = looks_visible(value)
        translation = known.get(value)
        if translation is not None:
            reasons = ["known-translation", *reasons]
        if translation is not None or visible:
            rows.append(
                {
                    "index": index,
                    "address": literal["address"],
                    "source": value,
                    "translation": translation,
                    "reasons": sorted(set(reasons)),
                }
            )

    translated = sum(row["translation"] is not None for row in rows)
    report = {
        "literal_count": len(literals),
        "known_translation_count": len(known),
        "candidate_count": len(rows),
        "candidate_translated_count": translated,
        "candidate_untranslated_count": len(rows) - translated,
        "entries": rows,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "entries"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
