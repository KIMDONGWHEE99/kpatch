"""설치된 Microsoft CRT 정적 라이브러리의 수학 상수 절 전체와 대조합니다."""
import collections
import json
import struct
from pathlib import Path
from dat_container import sha

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"
LIB = Path("C:/Program Files (x86)/Windows Kits/10/Lib/10.0.22621.0/ucrt/x86/libucrt.lib")


def members(raw):
    assert raw[:8] == b"!<arch>\n"
    position, names = 8, b""
    while position + 60 <= len(raw):
        header = raw[position:position + 60]
        assert header[58:60] == b"`\n"
        size, name = int(header[48:58]), header[:16].decode("ascii").strip()
        data = raw[position + 60:position + 60 + size]
        if name == "//":
            names = data
        elif name.startswith("/") and name[1:].isdigit():
            name = names[int(name[1:]):].split(b"\0", 1)[0].split(b"\n", 1)[0].rstrip(b"/").decode("utf-8", "replace")
            yield name, position + 60, data
        elif name not in ("/", "//"):
            yield name.rstrip("/"), position + 60, data
        position += 60 + size + size % 2


def main():
    library = LIB.read_bytes()
    sections, failures = [], []
    for name, member_offset, data in members(library):
        is_math = "\\tran\\" in name.lower()
        is_character = name.rsplit("\\", 1)[-1].lower() in ("ctype.obj", "_ctype.obj", "_wctype.obj", "mbctype.obj", "nlsdata.obj")
        if not is_math and not is_character:
            continue
        if len(data) < 20 or struct.unpack_from("<H", data)[0] != 0x14C:
            failures.append({"member": name, "reason": "수학 회원이 일반 x86 COFF 객체가 아님"})
            continue
        machine, count, _, pointer, symbols_count, optional, _ = struct.unpack_from("<HHIIIHH", data)
        symbols, string_table = collections.defaultdict(list), data[pointer + symbols_count * 18:]
        index = 0
        while index < symbols_count:
            record = data[pointer + index * 18:pointer + (index + 1) * 18]
            if record[:4] == b"\0\0\0\0":
                start = struct.unpack_from("<I", record, 4)[0]
                symbol = string_table[start:].split(b"\0", 1)[0].decode("ascii", "replace")
            else:
                symbol = record[:8].rstrip(b"\0").decode("ascii", "replace")
            value, section, _, storage, extra = struct.unpack_from("<IhHBB", record, 8)
            if section > 0 and not symbol.startswith("."):
                symbols[section].append({"name": symbol, "offset": value, "storage": storage})
            index += 1 + extra
        for index in range(count):
            start = 20 + optional + index * 40
            label, _, _, size, offset, _, _, relocations, _, flags = struct.unpack_from("<8sIIIIIIHHI", data, start)
            label = label.rstrip(b"\0").decode("ascii", "replace")
            if flags & 0x20000000 or not flags & 0x40 or relocations or not 32 <= size <= 65536 or label.startswith(".debug"):
                continue
            raw = data[offset:offset + size]
            assert len(raw) == size
            sections.append({"member": name, "member_sha256": sha(data), "member_offset": member_offset,
                             "section": label, "section_index": index + 1, "section_data_offset": offset,
                             "section_bytes": size, "section_sha256": sha(raw), "symbols": symbols[index + 1], "raw": raw,
                             "data_role": "CRT 수학 상수·조회표" if is_math else "CRT 문자분류·대소문자·다중바이트 코드페이지 자료"})
    path = OUT / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    matches = []
    for file in sorted({row["file"] for row in rows}):
        data = (BASE / file).read_bytes()
        for section in sections:
            cursor = 0
            while True:
                start = data.find(section["raw"], cursor)
                if start < 0:
                    break
                matches.append({"file": file, "file_sha256": sha(data), "start": start, "end": start + len(section["raw"]),
                                **{key: value for key, value in section.items() if key != "raw"}})
                cursor = start + len(section["raw"])
    changed = []
    for row in rows:
        if row["classification"] != "UNKNOWN" or row["kind"] != "section_string":
            continue
        owner = next((match for match in matches if match["file"] == row["file"] and match["start"] <= row["file_offset"] and row["file_offset"] + row["bytes"] <= match["end"]), None)
        if owner:
            row.update(classification="INTERNAL", reason="Microsoft CRT 객체의 재배치 없는 COFF 자료 절 전체와 바이트가 정확히 일치: " + owner["data_role"],
                       classification_evidence="native_coff_math_evidence.json", containing_structure=owner)
            changed.append(row)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    evidence = {"library": str(LIB), "library_sha256": sha(library), "math_data_sections": len(sections), "matches": matches,
                "unsupported_objects": failures, "limitation": "라이브러리/컴파일러 전체 버전이 같다고 단정하지 않으며, 재배치 없는 자료 절 전체의 정확한 일치만 판정에 사용함"}
    (OUT / "native_coff_math_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sections": len(sections), "matches": len(matches), "new_internal": len(changed), "by_file": dict(collections.Counter(row["file"] for row in changed))}))


if __name__ == "__main__":
    main()
