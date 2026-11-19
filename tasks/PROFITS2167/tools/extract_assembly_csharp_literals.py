#!/usr/bin/env python3
"""Cpp2IL ISIL 덤프에서 Assembly-CSharp가 참조하는 문자열을 주소 기준으로 추출한다."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


ABSOLUTE_ADDRESS = re.compile(r"\[([0-9A-Fa-f]{8,16})h(?:[+\-][^\]]+)?\]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--isil-root", type=Path, required=True)
    parser.add_argument("--literals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-base", type=lambda value: int(value, 0), default=0x180000000)
    args = parser.parse_args()

    literals = json.loads(args.literals.read_text(encoding="utf-8-sig"))
    literal_by_rva = {int(item["address"], 16): (index, item) for index, item in enumerate(literals)}
    refs: dict[int, set[tuple[str, str, str]]] = defaultdict(set)

    for path in sorted(args.isil_root.rglob("*.txt")):
        current_type = ""
        current_method = ""
        in_disassembly = False
        relative = str(path.relative_to(args.isil_root))
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if line.startswith("Type: "):
                current_type = line[6:]
            elif line.startswith("Method: "):
                current_method = line[8:]
                in_disassembly = False
            elif line == "Disassembly:":
                in_disassembly = True
            elif line == "ISIL:":
                in_disassembly = False
            elif in_disassembly:
                for match in ABSOLUTE_ADDRESS.finditer(line):
                    absolute = int(match.group(1), 16)
                    rva = absolute - args.image_base
                    if rva in literal_by_rva:
                        refs[rva].add((relative, current_type, current_method))

    entries = []
    for rva, (index, literal) in literal_by_rva.items():
        if rva not in refs:
            continue
        entries.append(
            {
                "index": index,
                "address": literal["address"],
                "value": literal["value"],
                "references": [
                    {"file": file, "type": type_name, "method": method}
                    for file, type_name, method in sorted(refs[rva])
                ],
            }
        )

    result = {
        "literal_count": len(literals),
        "assembly_csharp_literal_count": len(entries),
        "entries": entries,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"literal_count": len(literals), "assembly_csharp_literal_count": len(entries)}))


if __name__ == "__main__":
    main()
