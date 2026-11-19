#!/usr/bin/env python3
"""0.5.0 전수 한글화용 문자열 출처를 한 보고서로 모은다."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ASCII_LETTER = re.compile(r"[A-Za-z]")
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
GUID = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
PATHISH = re.compile(r"(?:[/\\]|\.(?:png|jpg|jpeg|asset|prefab|wav|ogg|mp3|json|txt|shader|mat|dll))", re.I)
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:+<>`/\-]*$")
LOG_PREFIX = re.compile(
    r"^(?:error|warning|exception|failed|failure|invalid|cannot|can't|unable|missing|"
    r"trying|could not|couldn't|assert|debug|loading|loaded|unloading|created|destroyed|"
    r"adding|removing|found|setting|set |get |requested|registered|unregistered)\b",
    re.I,
)
RUNTIME_VISIBLE_REF = re.compile(
    r"Tutorial|Presentation|Popup|Tooltip|Results|Result|Menu|Screen|Panel|Dialog|"
    r"Notification|Description|Title|Label|Button|Settings|Shift|Booster|Growth|"
    r"Tech|Upgrade|Job|Outpost|Hub|Train|Quota|Stat|Deck|Card|Vibration|Maintenance|"
    r"Delivery|Combat|Wave|Camera|Map|Credits|Intro|Outro",
    re.I,
)
RUNTIME_INTERNAL_REF = re.compile(
    r"Save|Serialize|Debug|Test|Editor|Pool|Service|Installer|Dependency|Container|"
    r"Addressable|Injector|Provider|Repository|Factory|Resolver|Validator|Logger",
    re.I,
)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def has_display_words(value: str) -> bool:
    stripped = value.strip()
    if not stripped or not ASCII_LETTER.search(stripped):
        return False
    plain = re.sub(r"<[^>]+>|%[^%]+%|\{[^{}]+\}", " ", stripped)
    if GUID.fullmatch(stripped) or PATHISH.search(plain):
        return False
    words = WORD.findall(plain)
    if not words:
        return False
    if len(words) == 1 and IDENTIFIER.fullmatch(words[0]) and words[0].lower() in {
        "normal", "highlighted", "pressed", "selected", "disabled", "true", "false",
        "none", "null", "default", "value", "name", "id", "guid", "version",
    }:
        return False
    return True


def classify_runtime(value: str, references: list[dict[str, str]]) -> tuple[str, list[str]]:
    joined = " ".join(
        f"{ref.get('file', '')} {ref.get('type', '')} {ref.get('method', '')}" for ref in references
    )
    reasons: list[str] = []
    stripped = value.strip()
    if not has_display_words(value):
        return "INTERNAL_OR_TOKEN", reasons
    if LOG_PREFIX.search(stripped):
        reasons.append("log-prefix")
    if RUNTIME_VISIBLE_REF.search(joined):
        reasons.append("visible-reference")
    if RUNTIME_INTERNAL_REF.search(joined):
        reasons.append("internal-reference")
    words = WORD.findall(stripped)
    if len(words) >= 3 or re.search(r"[.!?\n]", stripped):
        reasons.append("sentence")
    if re.search(r"\*\*|<[^>]+>|%[A-Za-z0-9_.]+%|\{[^{}]+\}", stripped):
        reasons.append("formatting")
    if "visible-reference" in reasons and "log-prefix" not in reasons:
        return "REVIEW_VISIBLE", reasons
    if "log-prefix" in reasons and "visible-reference" not in reasons:
        return "INTERNAL_LOG", reasons
    if "sentence" in reasons and "internal-reference" not in reasons:
        return "REVIEW_SENTENCE", reasons
    return "REVIEW_AMBIGUOUS", reasons


def collect_known(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.glob("*_ko.json")):
        data = load(path)
        if isinstance(data, list):
            for row in data:
                if not isinstance(row, dict):
                    continue
                source = row.get("source")
                translation = row.get("translation")
                if isinstance(source, str) and isinstance(translation, str) and source != translation:
                    result[source] = translation
    for pattern in (
        "translations_ko_by_key.json",
        "scene_translation_overrides.json",
        "resource_translation_overrides_*.json",
        "metadata_translation_overrides*.json",
        "resource_tmp_overrides*.json",
        "serialized_translation_overrides*.json",
    ):
        for path in sorted(root.glob(pattern)):
            data = load(path)
            if isinstance(data, dict):
                for source, translation in data.items():
                    if isinstance(source, str) and isinstance(translation, str) and source != translation:
                        result[source] = translation
    return result


def audit_direct(root: Path, known: dict[str, str]) -> dict[str, Any]:
    files = [*sorted(root.glob("direct_text_level*_ko.json")), root / "direct_text_resources_v040_ko.json"]
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total = changed = 0
    for path in files:
        if not path.exists():
            continue
        for row in load(path):
            total += 1
            source = str(row.get("source", ""))
            translation = str(row.get("translation", ""))
            changed += source != translation
            if source == translation and source not in known and has_display_words(source):
                by_source[source].append(
                    {
                        "file": path.name,
                        "path_id": row.get("path_id"),
                        "class": row.get("class"),
                        "game_object": row.get("game_object"),
                    }
                )
    entries = [
        {"source": source, "known_translation": known.get(source), "uses": uses}
        for source, uses in sorted(by_source.items(), key=lambda item: item[0].lower())
    ]
    return {
        "total_rows": total,
        "translated_rows": changed,
        "untranslated_display_unique": len(entries),
        "entries": entries,
    }


def audit_runtime(root: Path, known: dict[str, str]) -> dict[str, Any]:
    source = load(root / "assembly_csharp_literals.json")
    entries = []
    counts: Counter[str] = Counter()
    for row in source["entries"]:
        value = str(row["value"])
        translation = known.get(value)
        if translation is not None:
            classification = "TRANSLATED"
            reasons = ["known-translation"]
        else:
            classification, reasons = classify_runtime(value, row.get("references", []))
        counts[classification] += 1
        entries.append(
            {
                "index": row["index"],
                "address": row["address"],
                "source": value,
                "translation": translation,
                "classification": classification,
                "reasons": reasons,
                "references": row.get("references", []),
            }
        )
    return {
        "total_referenced_literals": len(entries),
        "classification_counts": dict(sorted(counts.items())),
        "entries": entries,
    }


def audit_serialized(root: Path, known: dict[str, str]) -> dict[str, Any]:
    files = [
        *sorted(root.glob("mono_strings_v040_level*.json")),
        root / "mono_strings_v040_sharedassets0.json",
        root / "mono_strings_resources_v040_verify.json",
    ]
    by_value: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in files:
        if not path.exists():
            continue
        for row in load(path):
            value = str(row.get("source", ""))
            if value in known or not has_display_words(value):
                continue
            field_path = ".".join(str(item) for item in row.get("field_path", []))
            if re.search(
                r"(?:m_AnimationTriggers|m_MethodName|AssemblyTypeName|m_ActionId|m_TableCollectionName|"
                r"_id$|IdRaw|Property|eventName|parameter|guid|assetGuid)",
                field_path,
                re.I,
            ):
                continue
            by_value[value].append(
                {
                    "file": path.name,
                    "path_id": row.get("path_id"),
                    "class": row.get("class"),
                    "game_object": row.get("game_object"),
                    "field_path": field_path,
                }
            )
    entries = [
        {"source": value, "uses": uses}
        for value, uses in sorted(by_value.items(), key=lambda item: item[0].lower())
    ]
    return {"untranslated_display_unique": len(entries), "entries": entries}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    known = collect_known(args.root)
    report = {
        "known_translation_count": len(known),
        "direct_text": audit_direct(args.root, known),
        "runtime_literals": audit_runtime(args.root, known),
        "serialized_fields": audit_serialized(args.root, known),
    }
    write(args.output, report)
    print(
        json.dumps(
            {
                "known_translation_count": report["known_translation_count"],
                "direct_text": {key: value for key, value in report["direct_text"].items() if key != "entries"},
                "runtime_literals": {
                    key: value for key, value in report["runtime_literals"].items() if key != "entries"
                },
                "serialized_fields": {
                    key: value for key, value in report["serialized_fields"].items() if key != "entries"
                },
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
