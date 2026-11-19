"""미해결 필드의 REA 참조 추적 출발 주소를 원본 실행 파일 바이트로 확인한다."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029"
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
OUTPUT = BASE / "reference_triage"
QUERIES = {
    "equipment_display": ["equipment", "name", "id", "right_hand", "torso_cloth", "custom_slots"],
    "map_and_location": ["chained", "map", "RESERVED", "RESERVED_core_2_leader_tile", "spawn_on", "internal_name", "placement", "on_background", "random_spread", "matches_resource"],
    "ability_enum": ["animation", "target", "aoe_self", "damage_type", "effects", "statistics", "ability_target", "skill"],
    "schema_and_dictionary": ["components", "component_type", "properties", "templates", "follow_up", "occupations", "occupation_per_race", "biomes", "directions", "action_plan_description", "names", "language_metadata"],
    "layout": ["align", "middle", "right"],
}


def main():
    OUTPUT.mkdir(exist_ok=True)
    destination = OUTPUT / "native_field_literal_anchors.json"
    if destination.exists():
        raise ValueError("기존 리터럴 주소 목록을 덮어쓰지 않습니다.")
    data = (SOURCE / "Soulash 2.exe").read_bytes()
    source_sha = hashlib.sha256(data).hexdigest()
    baseline = json.loads((BASE / "baseline_manifest.json").read_text(encoding="utf-8"))
    assert source_sha == next(row["sha256"] for row in baseline["files"] if row["path"] == "Soulash 2.exe")
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    assert data[pe:pe + 4] == b"PE\0\0"
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    assert struct.unpack_from("<H", data, pe + 24)[0] == 0x20b
    image_base = struct.unpack_from("<Q", data, pe + 48)[0]
    sections = []
    for index in range(count):
        pos = pe + 24 + optional_size + 40 * index
        name = data[pos:pos + 8].rstrip(b"\0").decode("ascii")
        virtual_size, rva, size, offset = struct.unpack_from("<IIII", data, pos + 8)
        sections.append({"name": name, "rva": rva, "offset": offset, "size": size, "virtual_size": virtual_size})

    def location(offset):
        for section in sections:
            if section["offset"] <= offset < section["offset"] + section["size"]:
                rva = offset - section["offset"] + section["rva"]
                return {"file_offset": offset, "file_offset_hex": hex(offset), "rva": hex(rva),
                        "preferred_virtual_address": hex(image_base + rva), "section": section["name"]}
        return {"file_offset": offset, "file_offset_hex": hex(offset), "rva": None, "preferred_virtual_address": None, "section": None}

    existing = defaultdict(list)
    for line in (BASE / "native/strings.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        existing[(row["source"], row["encoding"])].append(row)
    searches = []
    for group, needles in QUERIES.items():
        for needle in needles:
            for encoding in ("ascii", "utf-16-le"):
                raw = needle.encode(encoding)
                terminator = b"\0" if encoding == "ascii" else b"\0\0"
                matches = []
                for match in re.finditer(re.escape(raw), data):
                    offset = match.start()
                    trailing_nul = data[offset + len(raw):offset + len(raw) + len(terminator)] == terminator
                    leading_nul = offset >= len(terminator) and data[offset - len(terminator):offset] == terminator
                    matches.append({**location(offset), "raw_sha256": hashlib.sha256(raw).hexdigest(),
                                    "trailing_nul": trailing_nul, "leading_nul": leading_nul,
                                    "standalone_extracted_candidate": any(row["file_offset"] == offset for row in existing[(needle, encoding)]),
                                    "classification": "UNKNOWN", "xref_status": "NOT_RUN"})
                searches.append({"group": group, "literal": needle, "encoding": encoding, "byte_length": len(raw),
                                 "raw_match_count": len(matches), "null_terminated_count": sum(row["trailing_nul"] for row in matches), "matches": matches})
    report = {"status": "PASS", "source_file": "Soulash 2.exe", "source_file_sha256": source_sha,
              "preferred_image_base": hex(image_base), "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "searches": searches, "limitations": ["정적 선호 VA이며 실행 프로세스의 ASLR 주소가 아님", "바이트 존재는 parser 사용·화면 노출·실제 실행의 근거가 아님",
                                                     "주소마다 REA xref와 소비 코드를 추가 확인해야 함", "부재는 기능 부재를 뜻하지 않음. 부분 문자열 주소도 구별 보존"]}
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([{ "literal": row["literal"], "va": [match["preferred_virtual_address"] for match in row["matches"] if match["trailing_nul"]], "raw_matches": row["raw_match_count"]}
                      for row in searches if row["encoding"] == "ascii"], ensure_ascii=True))


if __name__ == "__main__":
    main()
