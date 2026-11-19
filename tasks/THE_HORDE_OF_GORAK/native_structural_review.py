"""문자처럼 보이는 GPU 코드·PE 구조를 해당 컨테이너 경계로 식별합니다."""
import collections
import json
import re
import struct
from pathlib import Path
import pefile
from dat_container import sha

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"


def dxbc_ranges(data):
    result = []
    for match in re.finditer(b"DXBC", data):
        start = match.start()
        if start + 32 > len(data):
            continue
        version, size, count = struct.unpack_from("<III", data, start + 20)
        if version != 1 or not 1 <= count <= 256 or size < 32 + 4 * count or start + size > len(data):
            continue
        parts, valid = [], True
        for index in range(count):
            relative = struct.unpack_from("<I", data, start + 32 + 4 * index)[0]
            if relative < 32 + 4 * count or relative + 8 > size:
                valid = False
                break
            fourcc = data[start + relative:start + relative + 4]
            part_size = struct.unpack_from("<I", data, start + relative + 4)[0]
            if relative + 8 + part_size > size:
                valid = False
                break
            parts.append({"type": fourcc.decode("ascii", "replace"), "offset": relative, "bytes": part_size})
        if valid:
            result.append({"start": start, "end": start + size, "kind": "DXBC_SHADER", "sha256": sha(data[start:start + size]), "parts": parts})
    return result


def d3d9_ranges(data):
    result = []
    for match in re.finditer(rb"\x00[\x02\x03][\xfe\xff]\xff", data):
        start = match.start()
        if start % 4:
            continue
        cursor, count, has_comment, valid = start + 4, 0, False, False
        while cursor + 4 <= min(len(data), start + 65536) and count < 4096:
            token = struct.unpack_from("<I", data, cursor)[0]
            opcode = token & 0xffff
            if token == 0xffff:
                cursor += 4
                valid = count > 0
                break
            if opcode == 0xfffe:
                size = (token >> 16) & 0x7fff
                has_comment = True
            else:
                if opcode > 96:
                    break
                size = (token >> 24) & 15
            cursor += 4 * (1 + size)
            count += 1
        if valid and has_comment:
            result.append({"start": start, "end": cursor, "kind": "D3D9_SHADER", "sha256": sha(data[start:cursor]), "instructions": count})
    return result


def d3d_comment_ranges(data):
    result = []
    for match in re.finditer(rb"CTAB|DBUG|PRSI", data):
        start = match.start() - 4
        if start < 0 or start % 4:
            continue
        token = struct.unpack_from("<I", data, start)[0]
        words = (token >> 16) & 0x7fff
        end = start + 4 + words * 4
        if token & 0xffff != 0xfffe or not 2 <= words < 16384 or end > len(data):
            continue
        result.append({"start": start, "end": end, "kind": "D3D_SHADER_COMMENT", "sha256": sha(data[start:end]), "comment_kind": match.group().decode("ascii")})
    return result


def main():
    path = OUT / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row["file"]].append(row)
    proof, dynamic_exports = {}, {}
    system_names = set()
    for name in sorted(groups):
        image = pefile.PE(str(BASE / name))
        for module in getattr(image, "DIRECTORY_ENTRY_IMPORT", []):
            system_names.add(module.dll.decode("ascii").lower())
    for name in sorted(system_names):
        library = Path("C:/Windows/SysWOW64") / name
        if not library.is_file():
            continue
        image = pefile.PE(str(library), fast_load=False)
        if hasattr(image, "DIRECTORY_ENTRY_EXPORT"):
            dynamic_exports[name] = {"path": str(library), "sha256": sha(library.read_bytes()),
                                     "names": [item.name.decode("ascii") for item in image.DIRECTORY_ENTRY_EXPORT.symbols if item.name]}
    exported = {value for entry in dynamic_exports.values() for value in entry["names"]}
    for name, subset in groups.items():
        data = (BASE / name).read_bytes()
        ranges = dxbc_ranges(data) + d3d9_ranges(data) + d3d_comment_ranges(data)
        proof[name] = {"file_sha256": sha(data), "ranges": ranges}
        for row in subset:
            if row["classification"] != "UNKNOWN" or row["kind"] != "section_string":
                continue
            start, end = row["file_offset"], row["file_offset"] + row["bytes"]
            owner = next((item for item in ranges if item["start"] <= start and end <= item["end"]), None)
            if owner:
                row.update(classification="INTERNAL", reason="유효한 GPU 셰이더 컨테이너 내부의 컴파일 코드·심볼·디버그 메타데이터. 컨테이너 크기/구간/종단을 검증",
                           classification_evidence="native_structural_evidence.json", containing_structure={k: owner[k] for k in ("start", "end", "kind", "sha256")})
            elif row["source"] in exported:
                row.update(classification="INTERNAL", reason="로컬 Windows 시스템 DLL의 정확한 내보내기 함수 이름과 일치하는 API 식별자",
                           classification_evidence="native_system_export_names.json")
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    (OUT / "native_structural_evidence.json").write_text(json.dumps({"files": proof,
        "format_sources": ["https://github.com/microsoft/DirectXShaderCompiler/blob/main/include/dxc/DxilContainer/DxilContainer.h",
                           "https://learn.microsoft.com/en-us/windows-hardware/drivers/display/instruction-token"]}, indent=2), encoding="utf-8")
    (OUT / "native_system_export_names.json").write_text(json.dumps(dynamic_exports, indent=2), encoding="utf-8")
    print(json.dumps({"shader_containers": sum(len(v["ranges"]) for v in proof.values()), "classifications": dict(collections.Counter(row["classification"] for row in rows))}))


if __name__ == "__main__":
    main()
