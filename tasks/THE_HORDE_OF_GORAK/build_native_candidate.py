"""확인된 UTF16 표시 필드만 고정 PE 배치 안에서 바꾸고 독립 재판독합니다."""
from __future__ import annotations
import collections
import hashlib
import json
import re
import struct
from pathlib import Path
import pefile
from dat_container import utf16z
from native_string_inventory import dialog_fields

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
WORK = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/native_candidate_01"
TRANSLATIONS = {
    "Cannot initialize application.": "응용 프로그램을 초기화할 수 없습니다.",
    "Error while opening file.": "파일을 여는 중 오류가 발생했습니다.",
    "Not enough memory!": "메모리가 부족합니다!",
    "File error!": "파일 오류!",
    "Cannot find %s!": "%s을(를) 찾을 수 없습니다!",
    "Cannot load %s. This object might need an external program or library not yet installed.": "%s을(를) 불러올 수 없습니다. 필요한 외부 프로그램이나 라이브러리가 설치되어 있는지 확인하세요.",
    "There is not enough available space in the temporary drive. Free some disk space and try again.": "임시 드라이브의 공간이 부족합니다. 디스크 공간을 확보한 뒤 다시 시도하세요.",
    "This application has been built with an incompatible version of Clickteam Fusion.": "호환되지 않는 Clickteam Fusion 버전으로 제작된 응용 프로그램입니다.",
    "Unknown format!": "알 수 없는 형식!",
    "Application Position|*.mfs||": "게임 상태|*.mfs||",
    "Physics - Bouncing Ball movement": "물리 - 공 튀기기 이동",
    "Please drop a 'Physics Engine' object in your frame.": "프레임에 'Physics Engine' 객체를 추가하세요.",
    "Type :": "형식 :", "Width :": "너비 :", "Depth :": "색 심도 :", "Height :": "높이 :",
    "Information": "정보", "# frames :": "프레임 수 :",
    "Image files": "이미지 파일", "Animation files": "애니메이션 파일", "Graphic files": "그래픽 파일",
    "All files (*.*)|*.*||": "모든 파일 (*.*)|*.*||", "%s files (%s)": "%s 파일 (%s)", "Unknown format": "알 수 없는 형식",
    "Notice that you should only have 1 steamworks object per frame and counting %d": "프레임당 Steamworks 객체는 하나만 있어야 합니다. 현재 개수: %d",
    " - Error": " - 오류", "JSON file not found on disk or in MFX resources": "디스크나 MFX 리소스에서 JSON 파일을 찾을 수 없습니다.",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_string_block(data):
    result, cursor = [], 0
    for _ in range(16):
        size = struct.unpack_from("<H", data, cursor)[0]
        cursor += 2
        result.append(data[cursor:cursor + size * 2].decode("utf-16le"))
        cursor += size * 2
    assert cursor == len(data)
    return result


def write_string_block(values):
    return b"".join(struct.pack("<H", len(value.encode("utf-16le")) // 2) + value.encode("utf-16le") for value in values)


def rebuild_dialog(raw, replacements):
    extended = raw[2:4] == b"\xff\xff"
    style = struct.unpack_from("<I", raw, 12 if extended else 0)[0]
    count = struct.unpack_from("<H", raw, 16 if extended else 8)[0]
    cursor = 26 if extended else 18
    output = bytearray(raw[:cursor])

    def field():
        nonlocal cursor
        start = cursor
        if raw[cursor:cursor + 2] == b"\xff\xff":
            cursor += 4
            output.extend(raw[start:cursor])
        else:
            value, cursor = utf16z(raw, cursor)
            replacement = replacements.get(start, value)
            output.extend(replacement.encode("utf-16le") + b"\0\0")

    for _ in range(3):
        field()
    if style & 0x40:
        size = 6 if extended else 2
        output.extend(raw[cursor:cursor + size])
        cursor += size
        field()
    for _ in range(count):
        aligned = (cursor + 3) & ~3
        assert not any(raw[cursor:aligned])
        cursor = aligned
        output.extend(b"\0" * (-len(output) % 4))
        size = 24 if extended else 18
        output.extend(raw[cursor:cursor + size])
        cursor += size
        field()
        field()
        extra = struct.unpack_from("<H", raw, cursor)[0] or 2
        output.extend(raw[cursor:cursor + extra])
        cursor += extra
    assert not any(raw[cursor:])
    output.extend(raw[cursor:])
    return bytes(output)


def main():
    assert not OUT.exists(), "기존 후보를 덮어쓰지 않습니다."
    worklist = json.loads((WORK / "native_visible_worklist.json").read_text(encoding="utf-8"))
    resources = json.loads((WORK / "native_pe_resources_evidence.json").read_text(encoding="utf-8"))
    groups = collections.defaultdict(list)
    for row in worklist:
        target = TRANSLATIONS[row["source"]]
        assert re.findall(r"%[sd]", row["source"]) == re.findall(r"%[sd]", target)
        if "|" in row["source"]:
            assert row["source"].split("|")[1:] == target.split("|")[1:]
        groups[row["file"]].append({**row, "target": target})
    report = {"status": "PASS", "source_build": "steam_26336311", "runtime_qa": "NOT_RUN", "files": [], "translations": [],
              "limitations": ["서명된 원본 DLL의 리소스를 수정하면 발행자 전자서명은 더 이상 유효하지 않음. 인증서/검증 분기는 변경하지 않음.",
                              "MMFS2 정보창의 기존 Tahoma 지정은 유지. 실제 한글 렌더링·잘림은 부모의 GPU QA가 필요.",
                              "확인된27필드만 포함. 전체 네이티브 문자열 분류가 완료되었다는 의미가 아님."]}
    generated = {}
    for name, rows in groups.items():
        original = (BASE / name).read_bytes()
        assert sha(original) == rows[0]["file_sha256"]
        candidate = bytearray(original)
        image = pefile.PE(data=original)
        allowed = []
        checks = []
        by_resource = collections.defaultdict(list)
        for row in rows:
            if row["kind"] == "section_string":
                assert row["encoding"] == "utf-16le" and row["null_terminated"]
                offset, size = row["file_offset"], row["bytes"]
                assert original[offset:offset + size].decode("utf-16le") == row["source"]
                assert original[offset + size:offset + size + 2] == b"\0\0"
                text = row["target"].encode("utf-16le")
                assert len(text) <= size
                candidate[offset:offset + size + 2] = text.ljust(size + 2, b"\0")
                allowed.append((offset, offset + size + 2))
                checks.append({"kind": "literal", "offset": offset, "size": size + 2, "target": row["target"]})
            else:
                by_resource[(row["resource_type"]["id"], row["resource_name"]["id"], row["resource_language"]["id"])].append(row)
        for key, selected in by_resource.items():
            resource = next(r for r in resources[name]["normalized_result"]["resources"] if (r["type"].get("id"), r["name"].get("id"), r["language"].get("id")) == key)
            start, size = resource["payload"]["location"]["offset"], resource["payload"]["location"]["bytes"]
            raw = original[start:start + size]
            assert sha(raw) == resource["payload"]["sha256"]
            if key[0] == 6:
                values = read_string_block(raw)
                assert write_string_block(values) == raw
                expected = values.copy()
                for row in selected:
                    slot = row["string_id"] % 16
                    assert values[slot] == row["source"]
                    expected[slot] = row["target"]
                replacement = write_string_block(expected)
                checks.append({"kind": "string_block", "offset": start, "size": len(replacement), "expected": expected})
            else:
                assert key[0] == 5
                assert rebuild_dialog(raw, {}) == raw
                mapping = {row["file_offset"] - start: row["target"] for row in selected}
                replacement = rebuild_dialog(raw, mapping)
                before_fields = dialog_fields(raw)
                after_fields = dialog_fields(replacement)
                expected = [{"role": item["role"], "source": mapping.get(item["offset"], item["source"])} for item in before_fields]
                assert [{"role": item["role"], "source": item["source"]} for item in after_fields] == expected
                # 새 텍스트를 원문으로 복구하면 좌표·ID·스타일·폰트 등 모든 비텍스트 바이트가 동일해야 합니다.
                reverse = {after["offset"]: before["source"] for before, after in zip(before_fields, after_fields) if before["source"] != after["source"]}
                assert rebuild_dialog(replacement, reverse) == raw
                checks.append({"kind": "dialog", "offset": start, "size": len(replacement), "expected": expected})
            assert len(replacement) <= size, (name, key, size, len(replacement))
            candidate[start:start + size] = replacement.ljust(size, b"\0")
            size_offset = resource["data_entry_location"]["offset"] + 4
            struct.pack_into("<I", candidate, size_offset, len(replacement))
            allowed.extend([(start, start + size), (size_offset, size_offset + 4)])
        if image.OPTIONAL_HEADER.CheckSum:
            offset = image.OPTIONAL_HEADER.get_field_absolute_offset("CheckSum")
            struct.pack_into("<I", candidate, offset, 0)
            new_checksum = pefile.PE(data=bytes(candidate)).generate_checksum()
            struct.pack_into("<I", candidate, offset, new_checksum)
            assert pefile.PE(data=bytes(candidate)).verify_checksum()
            allowed.append((offset, offset + 4))
        assert len(candidate) == len(original)
        changed = [index for index, (a, b) in enumerate(zip(original, candidate)) if a != b]
        assert all(any(start <= index < end for start, end in allowed) for index in changed)
        # 독립 PE 판독기로 각 리소스 트리와 위치를 다시 엽니다.
        reopened = pefile.PE(data=bytes(candidate))
        assert reopened.FILE_HEADER.Machine == image.FILE_HEADER.Machine
        assert [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData, s.Characteristics) for s in reopened.sections] == [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData, s.Characteristics) for s in image.sections]
        for check in checks:
            raw = bytes(candidate[check["offset"]:check["offset"] + check["size"]])
            if check["kind"] == "literal":
                value, end = utf16z(raw)
                assert value == check["target"] and not any(raw[end:])
            elif check["kind"] == "string_block":
                assert read_string_block(raw) == check["expected"]
            else:
                assert [{"role": item["role"], "source": item["source"]} for item in dialog_fields(raw)] == check["expected"]
        aliases = [p.relative_to(BASE) for p in BASE.rglob(name) if sha(p.read_bytes()) == sha(original)]
        security = image.OPTIONAL_HEADER.DATA_DIRECTORY[4]
        report["files"].append({"file": name, "original_sha256": sha(original), "candidate_sha256": sha(candidate), "bytes": len(candidate),
                                "paths": [str(path).replace("\\", "/") for path in aliases], "fields": len(rows), "changed_bytes": len(changed),
                                "allowed_ranges": allowed, "independent_reextract": "PASS", "nontext_dialog_fields": "PASS",
                                "section_layout": "PASS", "outside_boundary": "PASS", "original_has_certificate": bool(security.Size),
                                "signature_after_patch": "INVALID_BY_CONTENT_CHANGE" if security.Size else "NOT_APPLICABLE"})
        report["translations"].extend(rows)
        for alias in aliases:
            generated[alias] = bytes(candidate)
    OUT.mkdir(parents=True)
    for alias, data in generated.items():
        (OUT / alias).parent.mkdir(parents=True, exist_ok=True)
        (OUT / alias).write_bytes(data)
    (OUT / "native_patch_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "unique_files": len(report["files"]), "physical_files": len(generated), "fields": len(report["translations"]), "runtime_qa": "NOT_RUN"}))


if __name__ == "__main__":
    main()
