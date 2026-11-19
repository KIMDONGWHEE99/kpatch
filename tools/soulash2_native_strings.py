"""PE 데이터 구역의 문자열 후보를 위치와 해시로 보관한다. 표시 여부는 추정하지 않는다."""
import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
OUTPUT = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/native"

def main():
    path = BASE / "Soulash 2.exe"
    data = path.read_bytes()
    file_sha256 = hashlib.sha256(data).hexdigest()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe+4] == b"PE\0\0"
    count = struct.unpack_from("<H", data, pe+6)[0]
    optional_size = struct.unpack_from("<H", data, pe+20)[0]
    optional = pe+24
    assert struct.unpack_from("<H", data, optional)[0] == 0x20B
    image_base = struct.unpack_from("<Q", data, optional+24)[0]
    sections, records = [], []
    for index in range(count):
        start = optional+optional_size+40*index
        name = data[start:start+8].rstrip(b"\0").decode("ascii")
        virtual_size, rva, raw_size, offset = struct.unpack_from("<IIII", data, start+8)
        flags = struct.unpack_from("<I", data, start+36)[0]
        section = {"name": name, "rva": rva, "offset": offset, "size": raw_size,
                   "virtual_size": virtual_size, "flags": hex(flags)}
        sections.append(section)
        if flags & 0x20000000 or name in (".pdata", ".reloc"):
            continue
        payload = data[offset:offset+raw_size]
        for encoding, pattern in [("ascii", rb"[\x09\x0a\x0d\x20-\x7e]{2,}"),
                                  ("utf-16-le", rb"(?:[\x20-\x7e]\x00){2,}")]:
            for match in re.finditer(pattern, payload):
                value = match.group().decode(encoding)
                if not re.search(r"[A-Za-z]", value):
                    continue
                file_offset = offset+match.start()
                records.append({"location_id": f"Soulash 2.exe@{file_offset:x}:{encoding}",
                    "file_sha256": file_sha256, "section": name,
                    "file_offset": file_offset, "virtual_address": hex(image_base+rva+match.start()),
                    "byte_length": len(match.group()), "encoding": encoding, "source": value,
                    "source_sha256": hashlib.sha256(match.group()).hexdigest(),
                    "classification": "UNKNOWN", "evidence": "PE 비실행 데이터 구역의 인쇄 가능한 바이트 후보. 사용 참조 미확인."})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT/"strings.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False)+"\n")
    report = {"file": path.name, "file_sha256": file_sha256,
              "sections": sections, "image_base": hex(image_base), "candidates": len(records),
              "limitations": ["명령어 안의 즉석 문자열과 비ASCII 문자열은 별도 조사 필요", "후보는 실제 사용·표시 문자열을 뜻하지 않음"]}
    (OUTPUT/"summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"candidates": len(records), "sha256": report["file_sha256"]}))

if __name__ == "__main__":
    main()
