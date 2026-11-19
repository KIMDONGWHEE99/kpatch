#!/usr/bin/env python3
"""디컴파일된 C# 코드의 문자열 리터럴을 표시 가능성별로 조사한다."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


LITERAL_RE = re.compile(
    r'(?P<prefix>\$?@|@?\$)?"(?P<body>(?:""|\\.|[^"\\])*)"'
)
CJK_RE = re.compile(r"[\u3400-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z]{2,}")
VISIBLE_CALL_RE = re.compile(
    r"(?:\.text\s*=|SetText\s*\(|GetLocalized(?:String)?\s*\(|"
    r"AddRow\s*\(|CreateGlobalItem\s*\(|CreateItem\s*\(|"
    r"Show(?:Tip|Message|Toast|Dialog)|SetLabel|SetTitle)",
    re.IGNORECASE,
)
INTERNAL_CONTEXT_RE = re.compile(
    r"(?:Debug\.(?:Log|LogWarning|LogError)|throw\s+new|"
    r"Analytics|PlayerPrefs|ES3\.|Load(?:Asset|Prefab|Sprite)|"
    r"Addressables|Resources\.Load)",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def decode_literal(prefix: str, body: str) -> str:
    if "@" in prefix:
        return body.replace('""', '"')
    escape_map = {
        "0": "\0",
        "a": "\a",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "\\": "\\",
        '"': '"',
        "'": "'",
    }

    def replace_escape(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("u"):
            return chr(int(token[1:], 16))
        if token.startswith("U"):
            return chr(int(token[1:], 16))
        if token.startswith("x"):
            return chr(int(token[1:], 16))
        return escape_map.get(token, "\\" + token)

    return re.sub(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|x[0-9A-Fa-f]{1,4}|.)", replace_escape, body)


def looks_human(text: str) -> bool:
    if CJK_RE.search(text):
        return True
    words = WORD_RE.findall(text)
    return len(words) >= 2 or (len(words) == 1 and len(words[0]) >= 4)


def classify(file_name: str, line: str, text: str) -> tuple[str, str]:
    stripped = text.strip()
    if not stripped:
        return "INTERNAL", "빈 문자열 또는 공백"
    if INTERNAL_CONTEXT_RE.search(line) and not VISIBLE_CALL_RE.search(line):
        return "INTERNAL", "로그·분석·저장·자원 경로 문맥"
    if VISIBLE_CALL_RE.search(line):
        return "VISIBLE_TRANSLATE", "UI 텍스트 대입 또는 표시 함수 인자"
    if file_name.startswith("Debug") and looks_human(stripped):
        return "VISIBLE_TRANSLATE", "게임에 포함된 개발 화면의 표시 후보"
    if file_name in {
        "FarmLocalization.cs",
        "GameEndWnd.cs",
        "DemoCompletionWnd.cs",
        "GameplayLocalization.cs",
        "StoreLocalization.cs",
        "TalentLocalization.cs",
        "SkillTreeLocalization.cs",
    } and looks_human(stripped):
        return "VISIBLE_TRANSLATE", "현지화 또는 결과 화면의 런타임 문구"
    if looks_human(stripped):
        return "UNKNOWN", "사람이 읽을 수 있는 문자열로 보여 사용처 확인 필요"
    return "INTERNAL", "식별자·서식·경로·짧은 제어 문자열"


def main() -> None:
    args = parse_args()
    rows: list[dict[str, object]] = []
    for path in sorted(args.source.rglob("*.cs")):
        relative = path.relative_to(args.source).as_posix()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1
        ):
            for match in LITERAL_RE.finditer(line):
                prefix = match.group("prefix") or ""
                text = decode_literal(prefix, match.group("body"))
                classification, reason = classify(path.name, line, text)
                rows.append(
                    {
                        "layer": "Mono managed code literal",
                        "classification": classification,
                        "reason": reason,
                        "file": relative,
                        "line": line_number,
                        "source": text,
                        "context": line.strip(),
                        "translation": "",
                    }
                )

    counts = Counter(row["classification"] for row in rows)
    report = {
        "summary": {
            "literal_occurrences": len(rows),
            "unique_literals": len({row["source"] for row in rows}),
            "classifications": dict(sorted(counts.items())),
        },
        "entries": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
