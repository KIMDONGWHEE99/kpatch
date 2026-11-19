"""문자 후보와 실제 표시 필드를 분리하고 모든 PE 영역의 조사 범위를 기록합니다."""
import bisect
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
    resources = json.loads((OUT / "native_pe_resources_evidence.json").read_text(encoding="utf-8"))
    all_files, blank_slots, unknown_resources, code_candidates, referenced_unicode = [], [], [], [], []
    by_file = collections.defaultdict(list)
    for row in rows:
        by_file[row["file"]].append(row)
    for name, selected in by_file.items():
        data = (BASE / name).read_bytes()
        image = pefile.PE(data=data)
        base, file_hash = image.OPTIONAL_HEADER.ImageBase, sha(data)
        references, relocation_bytes = collections.defaultdict(list), set()
        for block in getattr(image, "DIRECTORY_ENTRY_BASERELOC", []):
            for entry in block.entries:
                if entry.type != 3:
                    continue
                try:
                    location = image.get_offset_from_rva(entry.rva)
                    value = struct.unpack_from("<I", data, location)[0]
                    target = image.get_offset_from_rva(value - base)
                    if not 0 <= target < len(data):
                        continue
                except (pefile.PEFormatError, struct.error, ValueError):
                    continue
                references[target].append(location)
                relocation_bytes.update(range(location, location + 4))
        targets = sorted(references)
        for row in selected:
            start, end = row["file_offset"], row["file_offset"] + row["bytes"]
            indices = targets[bisect.bisect_left(targets, start):bisect.bisect_left(targets, end)]
            row["static_references"] = [{"target_offset": target, "pointer_offsets": references[target]} for target in indices]
            if row["kind"] in ("RT_STRING", "RT_DIALOG"):
                row["candidate_type"] = "STRUCTURED_RESOURCE_FIELD"
            elif row["kind"] == "EDIF_SCHEMA":
                row["candidate_type"] = "STRUCTURED_EDITOR_SCHEMA_FIELD"
            elif all(index in relocation_bytes for index in range(start, end)):
                row["candidate_type"] = "PE_RELOCATED_POINTER_BYTES"
                if row["classification"] == "UNKNOWN":
                    row.update(classification="INTERNAL", reason="후보의 모든 바이트가 PE HIGHLOW 재배치가 지정한32비트주소 필드에 속함. 문자열이 아니라 로딩 시 보정되는 주소 값",
                               classification_evidence="native_candidate_coverage.json")
            elif indices and row.get("null_terminated"):
                row["candidate_type"] = "REFERENCED_TERMINATED_BYTE_RUN"
            elif row.get("null_terminated"):
                row["candidate_type"] = "UNREFERENCED_TERMINATED_BYTE_RUN"
            else:
                row["candidate_type"] = "UNTERMINATED_BYTE_RUN"
            row["reference_limit"] = "PE HIGHLOW 주소 참조만 수집. 참조0은 간접 계산·상대 주소·런타임 접근 부재를 뜻하지 않음"
        sections = []
        for section in image.sections:
            label = section.Name.rstrip(b"\0").decode("ascii", "replace")
            executable = bool(section.Characteristics & 0x20000000)
            raw, start = section.get_data(), section.PointerToRawData
            summary = {"name": label, "raw_offset": start, "raw_bytes": len(raw), "sha256": sha(raw), "executable": executable,
                       "rva": section.VirtualAddress, "characteristics": hex(section.Characteristics)}
            if executable:
                total = 0
                for encoding, pattern in [("ascii", rb"[\x20-\x7e\t\r\n]{4,}"), ("utf-16le", rb"(?:[\x20-\x7e\t\r\n]\x00){4,}")]:
                    for match in re.finditer(pattern, raw):
                        offset, end = start + match.start(), start + match.end()
                        indices = targets[bisect.bisect_left(targets, offset):bisect.bisect_left(targets, end)]
                        width = 2 if encoding == "utf-16le" else 1
                        code_candidates.append({"file": name, "file_sha256": file_hash, "offset": offset, "bytes": end - offset,
                                                "source": match.group().decode(encoding), "source_bytes_sha256": sha(match.group()),
                                                "encoding": encoding, "section": label, "rva": hex(section.VirtualAddress + match.start()),
                                                "type": "EXECUTABLE_SECTION_BYTE_RUN", "classification": "UNKNOWN",
                                                "null_terminated": data[end:end + width] == b"\0" * width,
                                                "reference_targets": indices,
                                                "reason": "실행 코드 영역의 문자 모양 바이트. 명령어/내장자료 여부는 제어 흐름 근거 없이 확정하지 않음"})
                        total += 1
                summary["raw_candidate_count"] = total
            sections.append(summary)
        # 기존 ASCII범위 UTF16 후보 밖의 문자는 실제 재배치 참조 시작점을 기준으로 보강합니다.
        for start in targets:
            end = start
            valid = True
            while end + 2 <= len(data) and end - start < 4096:
                code = struct.unpack_from("<H", data, end)[0]
                if code == 0:
                    break
                if code < 32 and code not in (9, 10, 13) or 0xD800 <= code <= 0xDFFF or code in (0xFFFE, 0xFFFF):
                    valid = False
                    break
                end += 2
            if not valid or end == start or end - start >= 4096 or data[end:end + 2] != b"\0\0":
                continue
            value = data[start:end].decode("utf-16le")
            if len(value) < 4 or all(ord(char) < 128 for char in value):
                continue
            referenced_unicode.append({"file": name, "file_sha256": file_hash, "offset": start, "bytes": end - start,
                                       "source": value, "source_bytes_sha256": sha(data[start:end]), "pointer_offsets": references[start],
                                       "classification": "UNKNOWN", "type": "REFERENCED_NONASCII_UTF16_INTERPRETATION",
                                       "reason": "재배치 참조와UTF16종결은 확인했으나 숫자/구조 데이터를UTF16으로도 해석할 수 있으므로 문자열 소비 확인 전 표시 문구로 단정하지 않음"})
        resource_counts = collections.Counter()
        blank_branches = []
        for directory in resources[name]["normalized_result"]["directories"]:
            if directory["id_entries"] + directory["named_entries"] == 0:
                blank_branches.append(directory)
        for resource in resources[name]["normalized_result"]["resources"]:
            ident = resource["type"].get("id", resource["type"].get("name"))
            resource_counts[str(ident)] += 1
            start, size = resource["payload"]["location"]["offset"], resource["payload"]["location"]["bytes"]
            if ident == 6:
                cursor = start
                for index in range(16):
                    length = struct.unpack_from("<H", data, cursor)[0]
                    if not length:
                        blank_slots.append({"file": name, "file_sha256": file_hash, "string_id": (resource["name"]["id"] - 1) * 16 + index,
                                            "length_offset": cursor, "language": resource["language"], "resource_sha256": resource["payload"]["sha256"],
                                            "classification": "VISIBLE_KEEP", "reason": "RT_STRING 16개길이필드 중 길이0으로 구조적으로 확인한 빈슬롯"})
                    cursor += 2 + length * 2
                assert cursor == start + size
            if ident not in (5, 6, 16, 24, "EDIF"):
                unknown_resources.append({"file": name, "file_sha256": file_hash, "resource": resource,
                                          "type": "MEDIA_RESOURCE" if ident in (1, 2, 3, 12, 14) else "OTHER_RESOURCE",
                                          "text_review": "UNKNOWN", "reason": "문자열/대화상자/버전/매니페스트/EDIF 이외의 리소스. 픽셀 또는 원시구조는 별도판정필요"})
        all_files.append({"file": name, "sha256": file_hash, "sections": sections, "resource_types": dict(resource_counts),
                          "empty_resource_directories": blank_branches, "relocation_fields": len(relocation_bytes) // 4,
                          "relocation_coverage_bytes_sha256": sha(b"".join(struct.pack("<I", index) for index in sorted(relocation_bytes))),
                          "certificate_directory": {"file_offset": image.OPTIONAL_HEADER.DATA_DIRECTORY[4].VirtualAddress, "bytes": image.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size},
                          "outside_sections": "PE 헤더·인증서·overlay는 게임 표시 문자열로 자동 취급하지 않음. 해당 구조의 바이트 위치는 PE 원본에 고정됨"})
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    for name, data in [("native_code_byte_candidates.jsonl", code_candidates), ("native_nonascii_pointer_candidates.jsonl", referenced_unicode)]:
        (OUT / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data), encoding="utf-8")
    unresolved = [row for row in rows if row["classification"] == "UNKNOWN"]
    coverage = {"status": "PARTIAL", "files": all_files, "empty_string_slots": blank_slots,
                "other_resources": unknown_resources, "known_inventory_count": len(rows),
                "classifications": dict(collections.Counter(row["classification"] for row in rows)),
                "unknown_by_type": dict(collections.Counter(row["candidate_type"] for row in unresolved)),
                "code_byte_candidates": len(code_candidates), "code_candidates_referenced": sum(bool(x["reference_targets"]) for x in code_candidates),
                "nonascii_pointer_interpretations": len(referenced_unicode),
                "limits": ["바이트 후보 수는 확정된 표시 문구 수가 아님", "실행 영역 후보는 별도색인으로 추가했으며제어흐름미확인기계어를텍스트항목수에섞지않음", "비ASCII 후보는참조시작점기준이며모든인코딩/간접계산위치의문자열포괄검사와동일하지않음"]}
    (OUT / "native_candidate_coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = json.loads((OUT / "native_string_summary.json").read_text(encoding="utf-8"))
    summary.update(classifications=coverage["classifications"], confirmed_visible=sum(row["classification"] == "VISIBLE_TRANSLATE" for row in rows),
                   unknown_by_kind=dict(collections.Counter(row["kind"] for row in unresolved)), unknown_by_file=dict(collections.Counter(row["file"] for row in unresolved)),
                   coverage="native_candidate_coverage.json 및 별도코드/비ASCII색인 참조", status="PARTIAL")
    (OUT / "native_string_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: coverage[key] for key in ["classifications", "unknown_by_type", "code_byte_candidates", "code_candidates_referenced", "nonascii_pointer_interpretations"]}))
    print(json.dumps({"empty_string_slots": len(blank_slots), "other_resources": len(unknown_resources)}))


if __name__ == "__main__":
    main()
