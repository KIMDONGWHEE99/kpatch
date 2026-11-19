#!/usr/bin/env python3
"""GameAssembly의 문자열 참조를 메서드와 연결한다."""

from __future__ import annotations

import argparse
import bisect
import json
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path


def read_sections(data: bytes):
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("PE 파일이 아닙니다")
    coff = pe_offset + 4
    section_count = struct.unpack_from("<H", data, coff + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff + 16)[0]
    optional = coff + 20
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic != 0x20B:
        raise ValueError(f"PE32+ 파일이 아닙니다: 0x{magic:X}")
    image_base = struct.unpack_from("<Q", data, optional + 24)[0]
    table = optional + optional_size
    sections = []
    for index in range(section_count):
        offset = table + index * 40
        name = data[offset : offset + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", data, offset + 8)
        characteristics = struct.unpack_from("<I", data, offset + 36)[0]
        sections.append(
            {
                "name": name,
                "virtual_size": virtual_size,
                "rva": rva,
                "raw_size": raw_size,
                "raw_offset": raw_offset,
                "executable": bool(characteristics & 0x20000000),
            }
        )
    return image_base, sections


def assembly_csharp_method_rvas(dump_path: Path) -> set[int]:
    result: set[int] = set()
    current_type = -1
    typedef_re = re.compile(r"TypeDefIndex: (\d+)")
    rva_re = re.compile(r'RVA:\s*0x([0-9A-Fa-f]+)')
    with dump_path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line in handle:
            type_match = typedef_re.search(line)
            if type_match:
                current_type = int(type_match.group(1))
                if current_type > 6358:
                    break
            if 5632 <= current_type <= 6358:
                rva_match = rva_re.search(line)
                if rva_match:
                    result.add(int(rva_match.group(1), 16))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--game-assembly", type=Path, required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--literals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.vendor))
    from capstone import CS_ARCH_X86, CS_MODE_64, Cs  # type: ignore
    from capstone.x86 import X86_OP_MEM, X86_REG_RIP  # type: ignore

    binary = args.game_assembly.read_bytes()
    _, sections = read_sections(binary)
    script = json.loads(args.script.read_text(encoding="utf-8-sig"))["ScriptMethod"]
    literals = json.loads(args.literals.read_text(encoding="utf-8-sig"))
    literal_by_rva = {int(item["address"], 16): (index, item) for index, item in enumerate(literals)}

    names_by_rva: dict[int, list[str]] = defaultdict(list)
    for method in script:
        rva = int(method["Address"])
        if rva:
            names_by_rva[rva].append(method["Name"])
    method_rvas = sorted(names_by_rva)
    assembly_rvas = assembly_csharp_method_rvas(args.dump)
    refs: dict[int, list[dict]] = defaultdict(list)

    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    decoded = 0
    for section in sections:
        if not section["executable"] or not section["raw_size"]:
            continue
        start = section["raw_offset"]
        code = binary[start : start + section["raw_size"]]
        for insn in decoder.disasm(code, section["rva"]):
            decoded += 1
            targets = set()
            for operand in insn.operands:
                if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                    targets.add(insn.address + insn.size + operand.mem.disp)
            for target in targets & literal_by_rva.keys():
                pos = bisect.bisect_right(method_rvas, insn.address) - 1
                method_rva = method_rvas[pos] if pos >= 0 else 0
                if not method_rva or insn.address - method_rva > 0x20000:
                    continue
                refs[target].append(
                    {
                        "instruction_rva": f"0x{insn.address:X}",
                        "method_rva": f"0x{method_rva:X}",
                        "method_names": names_by_rva[method_rva],
                        "assembly_csharp": method_rva in assembly_rvas,
                    }
                )

    entries = []
    for rva, (index, literal) in literal_by_rva.items():
        matches = refs.get(rva, [])
        if matches:
            entries.append(
                {
                    "index": index,
                    "address": literal["address"],
                    "value": literal["value"],
                    "assembly_csharp": any(match["assembly_csharp"] for match in matches),
                    "references": matches,
                }
            )
    result = {
        "decoded_instruction_count": decoded,
        "literal_count": len(literals),
        "referenced_literal_count": len(entries),
        "assembly_csharp_literal_count": sum(entry["assembly_csharp"] for entry in entries),
        "entries": entries,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "entries"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
