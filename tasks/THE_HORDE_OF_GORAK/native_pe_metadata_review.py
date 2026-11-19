"""PE 자체 이름표·최적화 디버그 자료·실제 API 기호를 타입 근거로 분류합니다."""
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


def main():
    path = OUT / "native_string_inventory.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    symbols, ranges, files, failures = {}, [], [], []
    names = sorted({row["file"] for row in rows})
    sources = [BASE / name for name in names]
    sources += [Path("C:/Windows/SysWOW64") / name for name in ("uxtheme.dll", "imm32.dll", "winmm.dll", "dbghelp.dll", "oleaut32.dll", "ntdll.dll", "kernelbase.dll")]
    for source in sources:
        if not source.exists():
            continue
        data = source.read_bytes()
        image = pefile.PE(data=data)
        file_hash = sha(data)
        files.append({"path": str(source), "sha256": file_hash})
        if hasattr(image, "DIRECTORY_ENTRY_EXPORT"):
            directory = image.DIRECTORY_ENTRY_EXPORT
            module_start = image.get_offset_from_rva(directory.struct.Name)
            module_end = data.index(b"\0", module_start) + 1
            if source.parent == BASE:
                ranges.append({"file": source.name, "start": module_start, "end": module_end, "type": "IMAGE_EXPORT_DIRECTORY.Name", "sha256": sha(data[module_start:module_end])})
            for item in directory.symbols:
                if item.name:
                    symbols[item.name.decode("ascii", "replace")] = {"path": str(source), "file_sha256": file_hash, "rva": hex(item.address), "ordinal": item.ordinal}
        if source.parent != BASE:
            continue
        for entry in getattr(image, "DIRECTORY_ENTRY_DEBUG", []):
            if entry.struct.Type != 13:
                continue
            start, size = entry.struct.PointerToRawData, entry.struct.SizeOfData
            raw = data[start:start + size]
            cursor, records = 4, []
            try:
                assert raw[:4] in (b"GCTL", b"LTCG", b"PGU\0", b"PGO\0", b"\0\0\0\0")
                while cursor + 8 < len(raw):
                    rva, length = struct.unpack_from("<II", raw, cursor)
                    end = raw.index(b"\0", cursor + 8)
                    label = raw[cursor + 8:end].decode("ascii")
                    assert not rva or image.get_section_by_rva(rva) is not None
                    records.append({"rva": rva, "bytes": length, "section_label": label})
                    cursor = (end + 4) & ~3
                assert not any(raw[cursor:])
                ranges.append({"file": source.name, "start": start, "end": start + size, "type": "IMAGE_DEBUG_TYPE_POGO", "sha256": sha(raw), "records": records})
            except Exception as error:
                failures.append({"file": source.name, "start": start, "bytes": size, "error": str(error)})
    changed = []
    for row in rows:
        if row["classification"] != "UNKNOWN" or row["kind"] != "section_string":
            continue
        owner = next((item for item in ranges if item["file"] == row["file"] and item["start"] <= row["file_offset"] and row["file_offset"] + row["bytes"] <= item["end"]), None)
        if owner:
            row.update(classification="INTERNAL", reason="PE 구조 해석으로 확인한 이름/최적화 디버그 자료 내부: " + owner["type"],
                       classification_evidence="native_pe_metadata_evidence.json", containing_structure=owner)
            changed.append(row)
        elif row["source"] in symbols:
            row.update(classification="INTERNAL", reason="원본 확장 모듈 또는 Windows DLL에서 실제 내보내는 함수 이름과 정확히 일치하는 코드 식별자. 게임 확장 함수 이름표/동적 API 조회에서 사용",
                       classification_evidence="native_pe_metadata_evidence.json; runtime_extension_import_tables.json", symbol_reference=symbols[row["source"]])
            changed.append(row)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    result = {"files": files, "typed_ranges": ranges, "symbols": symbols, "failures": failures,
              "symbol_limit": "동일한 함수명 식별자와 내보내기 사실을 대조함. 알려지지 않은 자연어 문구를 API라는 추정만으로 제외하지 않음"}
    (OUT / "native_pe_metadata_evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"typed_ranges": len(ranges), "failures": len(failures), "new_internal": len(changed), "by_file": dict(collections.Counter(row["file"] for row in changed))}))


if __name__ == "__main__":
    main()
