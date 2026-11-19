"""실행하지 않고 PE 표시 리소스와 문자열 후보를 위치별로 수집합니다."""
from __future__ import annotations
import collections
import hashlib
import json
import re
import struct
from pathlib import Path
import pefile
from dat_container import utf16z

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def preserve_nonstandard_escapes(literal):
    out, index = [], 0
    while index < len(literal):
        if literal[index] == "\\" and index + 1 < len(literal):
            following = literal[index + 1]
            out.append(("\\" if following in '"\\/bfnrtu' else "\\\\") + following)
            index += 2
        else:
            out.append(literal[index])
            index += 1
    return "".join(out)


def dialog_fields(data):
    """표준/확장 Windows 대화상자의 문자열 필드 경계를 읽습니다."""
    extended = data[2:4] == b"\xff\xff"
    style = struct.unpack_from("<I", data, 12 if extended else 0)[0]
    count = struct.unpack_from("<H", data, 16 if extended else 8)[0]
    cursor = 26 if extended else 18
    rows = []

    def field(role):
        nonlocal cursor
        offset = cursor
        if data[cursor:cursor + 2] == b"\xff\xff":
            cursor += 4
            return
        value, cursor = utf16z(data, cursor)
        rows.append({"offset": offset, "size": cursor - offset, "source": value, "role": role})

    field("menu_name")
    field("window_class")
    field("dialog_title")
    if style & 0x40:
        cursor += 6 if extended else 2
        field("font_name")
    for index in range(count):
        cursor = (cursor + 3) & ~3
        ident = struct.unpack_from("<I" if extended else "<H", data, cursor + (20 if extended else 16))[0]
        cursor += 24 if extended else 18
        field(f"control:{index}:{ident}:class")
        field(f"control:{index}:{ident}:text")
        extra = struct.unpack_from("<H", data, cursor)[0]
        cursor += extra or 2
    assert cursor <= len(data) and not any(data[cursor:])
    return rows


def run():
    evidence = json.loads((OUT / "native_pe_resources_evidence.json").read_text(encoding="utf-8"))
    records, files, failures = [], [], []
    for name, resource_evidence in evidence.items():
        path = SOURCE / name
        data = path.read_bytes()
        image = pefile.PE(data=data)
        file_hash = sha(data)
        duplicates = [str(p.relative_to(SOURCE)).replace("\\", "/") for p in SOURCE.rglob(name) if sha(p.read_bytes()) == file_hash]
        resources = resource_evidence["normalized_result"]["resources"]
        occupied = []
        metadata = {}
        for table in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            for module in getattr(image, table, []):
                metadata[module.dll.decode("ascii")] = "PE 가져오기 모듈 이름"
                for entry in module.imports:
                    if entry.name:
                        metadata[entry.name.decode("ascii")] = "PE 가져오기 함수 이름"
        if hasattr(image, "DIRECTORY_ENTRY_EXPORT"):
            for entry in image.DIRECTORY_ENTRY_EXPORT.symbols:
                if entry.name:
                    metadata[entry.name.decode("ascii")] = "PE 내보내기 함수 이름"

        def add(text, offset, size, encoding, kind, **extra):
            row = {"file": name, "file_sha256": file_hash, "file_offset": offset,
                   "bytes": size, "source": text, "source_bytes_sha256": sha(data[offset:offset + size]),
                   "encoding": encoding, "kind": kind, "classification": "UNKNOWN", "reason": None,
                   "evidence_id": resource_evidence["evidence_id"], **extra}
            try:
                row["rva"] = hex(image.get_rva_from_offset(offset))
                row["preferred_va"] = hex(image.OPTIONAL_HEADER.ImageBase + image.get_rva_from_offset(offset))
            except pefile.PEFormatError:
                pass
            if not text or re.fullmatch(r"[\s\d.,:;_%+\-*/=<>!?()\[\]{}&#|\\]+", text):
                row.update(classification="VISIBLE_KEEP" if kind in ("RT_STRING", "RT_DIALOG") else "INTERNAL",
                           reason="표시 슬롯의 빈 값·숫자·순수 기호" if kind in ("RT_STRING", "RT_DIALOG") else "숫자·구분 기호만 있는 구조 후보")
            elif text in metadata:
                row.update(classification="INTERNAL", reason=metadata[text])
            elif extra.get("role") in ("font_name", "window_class", "menu_name") or str(extra.get("role", "")).endswith(":class"):
                row.update(classification="INTERNAL", reason="대화상자 글꼴·클래스·메뉴 리소스 식별자")
            elif kind == "RT_DIALOG":
                row.update(classification="VISIBLE_TRANSLATE", reason="Windows 대화상자 제목·컨트롤 표시 슬롯. 게임 접근성은 추가 확인 대상")
            elif kind == "RT_STRING":
                row.update(classification="UNKNOWN", reason="길이 지정 Windows 문자열 리소스. 실제 소비가 편집기 전용인지 런타임인지 확인 필요")
            elif extra.get("section") == ".reloc":
                row.update(classification="INTERNAL", reason="PE 재배치 주소 표 내부 바이트가 문자 정규식에 우연히 일치함. 표시 문자열 영역이 아님")
            elif text.startswith((".?A", "??_", "?", "_Z")) and " " not in text:
                row.update(classification="INTERNAL", reason="C++ 장식된 형식·기호 이름 형식")
            records.append(row)

        for resource in resources:
            ident = resource["type"].get("id")
            location = resource["payload"]["location"]
            start, size = location["offset"], location["bytes"]
            raw = data[start:start + size]
            occupied.append((start, start + size))
            ref = {"resource_type": resource["type"], "resource_name": resource["name"], "resource_language": resource["language"],
                   "resource_sha256": resource["payload"]["sha256"]}
            try:
                if ident == 6:
                    cursor = 0
                    for index in range(16):
                        length = struct.unpack_from("<H", raw, cursor)[0]
                        cursor += 2
                        value = raw[cursor:cursor + 2 * length].decode("utf-16le")
                        if length:
                            add(value, start + cursor, length * 2, "utf-16le", "RT_STRING",
                                string_id=(resource["name"]["id"] - 1) * 16 + index, **ref)
                        cursor += length * 2
                    assert cursor == len(raw)
                elif ident == 5:
                    for item in dialog_fields(raw):
                        add(item["source"], start + item["offset"], item["size"], "utf-16le", "RT_DIALOG", role=item["role"], **ref)
                elif ident in (16, 24):
                    # 버전/매니페스트는 표시 슬롯과 분리해서 원본 해시로 추적합니다.
                    pass
                elif resource["type"].get("name") == "EDIF":
                    text = raw.rstrip(b"\0").decode("utf-8-sig")
                    # EDIF는 후행 쉼표를 허용합니다. 인용 문자열은 건드리지 않습니다.
                    clean = re.sub(r'("(?:\\.|[^"\\])*")|,(?=\s*[}\]])',
                                   lambda match: match.group(1) if match.group(1) else " ", text)
                    clean = re.sub(r'"(?:\\.|[^"\\])*"', lambda match: preserve_nonstandard_escapes(match.group()), clean)
                    obj = json.loads(clean)
                    (OUT / "steamworks_edif_private.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
                    for token in re.finditer(rb'"(?:\\.|[^"\\])*"', raw):
                        literal = token.group().decode("utf-8")
                        normalized = preserve_nonstandard_escapes(literal)
                        value = json.loads(normalized)
                        add(value, start + token.start(), len(token.group()), "utf-8-json", "EDIF_SCHEMA", **ref)
                        if normalized != literal:
                            records[-1]["noncanonical_escape"] = True
                            records[-1]["reason"] = "원본 EDIF에 표준 JSON 밖의 역슬래시가 있음. 원문 바이트를 보존하여 문자 후보로 읽었고 런타임 해석은 미확인"
            except Exception as error:
                failures.append({"file": name, "resource": ref, "error": str(error), "status": "UNKNOWN"})

        for section in image.sections:
            section_name = section.Name.rstrip(b"\0").decode("ascii", "replace")
            # 기계어·그림을 자연어로 오인하지 않도록 코드와 리소스는 별도 근거를 사용합니다.
            if section.Characteristics & 0x20000000 or section_name == ".rsrc":
                continue
            start = section.PointerToRawData
            raw = section.get_data()
            for encoding, pattern in [("ascii", rb"[\x20-\x7e\t\r\n]{4,}"), ("utf-16le", rb"(?:[\x20-\x7e\t\r\n]\x00){4,}")]:
                for match in re.finditer(pattern, raw):
                    offset, end = match.span()
                    if any(a <= start + offset < b for a, b in occupied):
                        continue
                    text = match.group().decode(encoding)
                    add(text, start + offset, end - offset, encoding, "section_string", section=section_name,
                        null_terminated=raw[end:end + (2 if encoding == "utf-16le" else 1)] == (b"\0\0" if encoding == "utf-16le" else b"\0"))
        files.append({"file": name, "sha256": file_hash, "bytes": len(data), "same_hash_paths": duplicates,
                      "resources": len(resources), "evidence_id": resource_evidence["evidence_id"]})
    with (OUT / "native_string_inventory.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in records:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {"files": files, "records": len(records), "classifications": dict(collections.Counter(x["classification"] for x in records)),
               "kinds": dict(collections.Counter(x["kind"] for x in records)), "failures": failures,
               "coverage": "REA PE 리소스 트리 전수. RT_STRING/RT_DIALOG는 구조 해석. 비실행·비리소스 영역은 ASCII 및 ASCII 범위 UTF16 후보. 비ASCII 코드 문자열, 실행 영역의 내장 텍스트, EDIF의 소비 분류는 추가 조사 대상",
               "status": "PARTIAL"}
    (OUT / "native_string_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("files", "coverage")}, ensure_ascii=False))


if __name__ == "__main__":
    run()
