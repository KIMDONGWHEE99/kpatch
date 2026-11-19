"""최종 후보를 Nebula와 별도 원시 독해로 검증합니다. 빌더 보고서를 입력으로 쓰지 않습니다."""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
import re
import struct
import zlib
import lz4.block
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image
from fontTools.ttLib import TTFont

from dat_container import DatFile, utf16z
from extra_chunk_review import parse_player_controls
from inventory import event_operations

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "working_private/THE_HORDE_OF_GORAK"
BASE = ROOT / "extracted_private/THE_HORDE_OF_GORAK/steam_26336311"
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat"
FAMILY = "THOG Noto Sans KR"
TRANSLATION_SHA = "9826a6dbc93d2a40be2dbec91dc518e8ef35768abc65bd5a50e546418e4d9c15"
FONT_HASHES = {400: "92059cbf2f73131a587426da2146e993b496349cb5c0b267d2797f4000984d35",
               700: "ef07411de3796cae75a0b8f5788b0ee2aceef44dddaae32e4371796229622ac8"}
IMAGE_IDS = {215, 980, 1512, 1820}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]


def uint(data, offset=0):
    return int.from_bytes(data[offset:offset + 4], "little")


def word(data, offset=0):
    return int.from_bytes(data[offset:offset + 2], "little")


def compressed_records(data):
    """글꼴 내장 묶음을 빌더의 블록 재조립 함수를 거치지 않고 읽습니다."""
    result, position = [], 0
    while position < len(data):
        size, packed = struct.unpack_from("<II", data, position)
        end = position + 8 + packed
        if end > len(data):
            raise ValueError("내장 글꼴 블록 경계 오류")
        decoded = zlib.decompress(data[position + 8:end])
        if len(decoded) != size:
            raise ValueError("내장 글꼴 해제 크기 오류")
        result.append((position, decoded))
        position = end
    if position != len(data):
        raise ValueError("내장 글꼴 후미 데이터")
    return result


def menu_items(data):
    result = {}
    header, offset, length, accelerator, accelerator_size = struct.unpack_from("<5I", data)
    if header != 20 or offset != 20 or data[offset:offset + 4] != b"\0" * 4:
        raise ValueError("표준 메뉴 헤더 오류")
    def read(position, parent="menu"):
        index = 0
        while True:
            flags = word(data, position)
            position += 2
            ident = None
            if not flags & 16:
                ident = word(data, position)
                position += 2
            start = position
            value, position = utf16z(data, position)
            key = f"{parent}/{index}"
            result[key] = {"source": value, "flags": flags, "id": ident, "offset": start}
            if flags & 16:
                position = read(position, key)
            if flags & 128:
                return position
            index += 1
    end = read(offset + 4)
    if end != offset + length or end != accelerator or accelerator + accelerator_size != len(data):
        raise ValueError("메뉴 길이·단축키 위치 오류")
    return result, data[accelerator:]


def control_key(row):
    if row["kind"] == "control_key_name":
        return (row["kind"], row["id"])
    return row["kind"], row["dialog_id"], row.get("item_index")


def dialog_structure(parsed):
    value = copy.deepcopy(parsed["dialogs"])
    for dialog in value:
        for name in ("offset", "size", "title"):
            dialog.pop(name)
        if dialog["font"]:
            dialog["font"].pop("face")
        for item in dialog["controls"]:
            item.pop("offset")
            item.pop("title")
    return value


def get_path(value, path):
    for key in path:
        value = value[int(key)] if isinstance(value, list) else value[str(key)]
    return value


def set_path(value, path, new):
    owner = get_path(value, path[:-1])
    owner[int(path[-1]) if isinstance(owner, list) else str(path[-1])] = new


def differences(a, b, path=()):
    if type(a) is not type(b):
        yield {"path": list(path), "expected": a, "actual": b}
    elif isinstance(a, dict):
        for key in sorted(a.keys() | b.keys()):
            if key not in a or key not in b:
                yield {"path": list(path + (key,)), "expected": a.get(key), "actual": b.get(key), "presence_changed": True}
            else:
                yield from differences(a[key], b[key], path + (key,))
    elif isinstance(a, list):
        if len(a) != len(b):
            yield {"path": list(path), "expected_length": len(a), "actual_length": len(b)}
        for index, (old, new) in enumerate(zip(a, b)):
            yield from differences(old, new, path + (str(index),))
    elif a != b:
        yield {"path": list(path), "expected": a, "actual": b}


def runtime_checksum(data):
    value, full = 0, len(data) & ~3
    values = [int.from_bytes(data[p:p + 4], "little") for p in range(0, full, 4)] + list(data[full:])
    for item in values:
        value = ((value * 2 + (value >> 31)) + item) & 0xFFFFFFFF
    return value ^ 13


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default="ko_candidate_01")
    parser.add_argument("--validation", default="validation_01")
    parser.add_argument("--layout-fix", action="store_true")
    parser.add_argument("--translation-id", default="translation_01")
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    profile = load(args.profile) if args.profile else {}
    source_path = Path(profile.get('source', SOURCE))
    source_semantic = Path(profile.get('semantic', BASE / 'nebula_03'))
    classification_path = Path(profile.get('classification', WORK / 'investigation_20261031/classification'))
    layout_map = {int(k):v for k,v in profile.get('layout_map',{}).items()}
    out = WORK / args.validation
    extracted = out / "nebula_candidate"
    candidate_path = ROOT / "build_candidate/THE_HORDE_OF_GORAK" / args.candidate / "THOG.dat"
    candidate_bytes = candidate_path.read_bytes()
    candidate_digest = sha(candidate_bytes)
    reports, checks, errors = {}, [], []
    def check(name, truth, **detail):
        row = {"check": name, "status": "PASS" if truth else "FAIL", **detail}
        checks.append(row)
        if not truth:
            errors.append(row)
    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    original, candidate = DatFile.load(source_path), DatFile(candidate_bytes)
    check("source_identity", sha(original.original) == profile.get('source_sha256', "60825bc8e3969274f5235088f86c38a8fd187b6265b8082de6b9625d1437e950"))
    check("independent_extractor_candidate_identity", load(extracted / "input.json")["sha256"] == candidate_digest)
    check("baseline_extractor_source_identity", load(source_semantic / "input.json")["sha256"] == sha(original.original))
    check("extraction_completed", (extracted / "summary.json").exists() and not load(extracted / "errors.json"))
    source_package = load(source_semantic / "package.json")
    actual_package = load(extracted / "package.json")
    expected_package = copy.deepcopy(source_package)
    translation_path = WORK / args.translation_id / "translations.json"
    approved_translation_hash = {"translation_01": TRANSLATION_SHA,
                                 "translation_02": "382f1b53a6e16a795f6a06bc037c7c415fe9555d33327c5e72931da90ac33f7f"}.get(args.translation_id)
    approved_translation_hash = profile.get('translations_sha256', approved_translation_hash)
    check("approved_translation_identity", sha(translation_path.read_bytes()) == approved_translation_hash)
    translations = load(translation_path)
    inventory = lines(classification_path / "inventory.jsonl")
    by_location = {row["location"]: row for row in inventory}
    expected_text = {}
    for row in translations:
        overrides = {x["location"]: x["translation"] for x in row.get("overrides", [])}
        for occurrence in row["occurrences"]:
            location = occurrence["location"]
            check("translation_source_" + location, by_location[location]["source"] == row["source"] and location not in expected_text)
            expected_text[location] = overrides.get(location, row["translation"])
    worklist = load(classification_path / 'translation_worklist.json')
    check("translation_cardinality", len(translations) == len(worklist) and len(expected_text) == sum(len(r['occurrences']) for r in worklist))
    required = {ord(c) for t in expected_text.values() for c in t if ord(c) >= 32}
    required.update(ord(c) for row in inventory if row["classification"] == "VISIBLE_KEEP" for c in row["source"] if ord(c) >= 32)
    verified_locations, location_report = set(), []
    def record_location(row, actual, method):
        location = row["location"]
        expected = expected_text.get(location, row["source"])
        success = actual == expected
        check("text_" + location, success)
        if location in expected_text and success:
            verified_locations.add(location)
        location_report.append({"location": location, "kind": row["kind"], "expected": expected, "actual": actual,
                                "source": row["source"], "translated": location in expected_text, "status": "PASS" if success else "FAIL", "method": method})
    # 원본 위치 목록과 독립 의미 트리 양쪽에서 전체 문단을 읽습니다.
    paragraphs = [r for r in inventory if r["kind"] == "paragraph"]
    for row in paragraphs:
        path = row["semantic_path"].split(".")
        actual = get_path(actual_package, path)
        check("paragraph_baseline_" + row["location"], get_path(source_package, path) == row["source"])
        record_location(row, actual, "Nebula ObjectParagraphs의 객체·문단 번호")
        set_path(expected_package, path, expected_text.get(row["location"], row["source"]))
    check("paragraph_total", len(paragraphs) == sum(len(o['Properties'].get('ObjectParagraphs',{}).get('Paragraphs',[])) for o in source_package['FrameItems']['Items'].values()))
    # 이벤트는 원시 구조를 다시 읽어 수·위치를 확인한 뒤 Nebula 의미 트리도 전체 대조합니다.
    raw_events, event_fields = [], {}
    frame_chunks = [c for c in candidate.chunks if c.chunk_id == 0x3333]
    source_frames = [c for c in original.chunks if c.chunk_id == 0x3333]
    for frame_index, (old_frame, frame) in enumerate(zip(source_frames, frame_chunks)):
        old = next(c for c in old_frame.children if c.chunk_id == 0x333D)
        new = next(c for c in frame.children if c.chunk_id == 0x333D)
        old_events, events = event_operations(old.decoded), event_operations(new.decoded)
        check(f"frame_{frame_index}_event_count", len(events) == len(old_events))
        raw_events.append({"frame": frame_index, "events": len(events), "source_sha256": sha(old.decoded), "candidate_sha256": sha(new.decoded)})
        for event in events:
            for kind in ("Conditions", "Actions"):
                for operation in event[kind]:
                    for parameter in operation["parameters"]:
                        for item in parameter["strings"]:
                            key = f"frame:{frame_index}/event:{event['index']}/{kind}:{operation['index']}/param:{parameter['index']}/{item['field']}"
                            event_fields[key] = item["value"]
    event_rows = [r for r in inventory if r["kind"] == "event_string"]
    check("event_strings_inventory_identity", set(event_fields) == {r["location"] for r in event_rows} and len(event_fields) == len(event_rows))
    for row in event_rows:
        record_location(row, event_fields.get(row["location"]), "별도 event_operations 원시 이벤트 재추출")
        if row["location"] in expected_text:
            for semantic_index in row["semantic_operation_indices"]:
                path = ["Frames", str(row["frame"]), "FrameEvents", "Events", str(row["event"]), row["operation_kind"], str(semantic_index), "Parameters", str(row["parameter_index"]), "Data"]
                if row["expression_index"] is not None:
                    path += ["Expressions", str(row["expression_index"]), "Expression", "Value"]
                else:
                    path += ["Value"]
                check("semantic_event_source_" + row["location"], get_path(source_package, path) == row["source"])
                set_path(expected_package, path, expected_text[row["location"]])
    # 버튼의 문구·폰트와 이동한 후미를 독립 Nebula blob과 전체 객체 바이트 양쪽에서 검증합니다.
    button_rows = [r for r in inventory if r["kind"] == "button_text"]
    object_expected = {b.index: bytearray(b.decoded) for b in original.objects}
    if args.layout_fix:
        # 빌더를 호출하지 않고 승인된 원시 필드 및 Nebula 의미 필드를 각각 고정한다.
        progress_handle = layout_map.get(514,514)
        check("layout_original_menu_font", word(original.objects[progress_handle].decoded, 136) == 10)
        struct.pack_into("<H", object_expected[progress_handle], 136, 5)
        expected_package["FrameItems"]["Items"][str(progress_handle)]["Properties"]["ObjectParagraphs"]["Paragraphs"][0]["FontHandle"] = 6
        for handle, old_height, height in ((510, 223, 300), (1000, 127, 144)):
            handle = layout_map.get(handle,handle)
            check(f"layout_original_height_{handle}", uint(original.objects[handle].decoded, 124) == old_height)
            struct.pack_into("<I", object_expected[handle], 124, height)
            expected_package["FrameItems"]["Items"][str(handle)]["Properties"]["ObjectParagraphs"]["Height"] = height
    for row in paragraphs:
        if row["location"] not in expected_text:
            continue
        handle, offset, capacity = int(row["target"].split(":")[1]), row["offset"], row["slot_bytes"]
        encoded = (expected_text[row["location"]].encode("utf-16le") + b"\0\0").ljust(capacity, b"\0")
        check("paragraph_capacity_" + row["location"], len(encoded) == capacity)
        object_expected[handle][offset:offset + capacity] = encoded
    button_report = []
    for row in button_rows:
        handle = row["object_handle"]
        old = original.objects[handle].decoded
        new = candidate.objects[handle].decoded
        before_blob = (source_semantic / f"extension_blobs/{handle:04d}.bin").read_bytes()
        after_blob = (extracted / f"extension_blobs/{handle:04d}.bin").read_bytes()
        value, end = utf16z(after_blob, 212)
        record_location(row, value, "Nebula 독립 추출 KcBoxA blob")
        desired = expected_text.get(row["location"], row["source"])
        encoded = desired.encode("utf-16le") + b"\0\0"
        check(f"button_{handle}_text_bounds", uint(after_blob, 208) == len(encoded) and end == 212 + len(encoded) and after_blob[end:] == before_blob[-8:])
        weight = 700 if uint(before_blob, 52) >= 600 else 400
        check(f"button_{handle}_font", utf16z(after_blob, 64)[0] == FAMILY and uint(after_blob, 52) == weight and after_blob[59] == 129)
        expected_blob = bytearray(before_blob[:212] + encoded + before_blob[-8:])
        struct.pack_into("<I", expected_blob, 52, weight)
        expected_blob[59] = 129
        expected_blob[64:128] = (FAMILY.encode("utf-16le") + b"\0\0").ljust(64, b"\0")
        struct.pack_into("<I", expected_blob, 208, len(encoded))
        check(f"button_{handle}_blob_change_boundary", bytes(expected_blob) == after_blob)
        extension = word(old, 12)
        expected_object = bytearray(old[:extension + 20]) + expected_blob
        struct.pack_into("<I", expected_object, 0, len(expected_object))
        struct.pack_into("<I", expected_object, extension, len(expected_blob) + 20)
        object_expected[handle] = expected_object
        path = ["FrameItems", "Items", str(handle), "Properties", "ObjectExtension", "ExtensionData"]
        set_path(expected_package, path, {"byte_length": len(after_blob), "sha256": sha(after_blob)})
        button_report.append({"handle": handle, "text": value, "font": FAMILY, "weight": weight, "charset": after_blob[59], "blob_sha256": sha(after_blob)})
    check("all_buttons", len(button_rows) == sum(o['Header']['Type']==32 for o in source_package['FrameItems']['Items'].values()))
    check("object_count", len(original.objects) == len(candidate.objects) == len(source_package['FrameItems']['Items']))
    for block in candidate.objects:
        check(f"object_{block.index}_complete_byte_boundary", block.decoded == object_expected[block.index])
    # 메뉴와 대화상자는 예전 바이트 주소가 아닌 항목의 고유 위치로 비교합니다.
    old_menu, old_accels = menu_items(original.one(0x2226).decoded)
    new_menu, new_accels = menu_items(candidate.one(0x2226).decoded)
    check("menu_identity_and_accelerators", old_menu.keys() == new_menu.keys() and old_accels == new_accels)
    for location, item in old_menu.items():
        row = by_location[location]
        record_location(row, new_menu[location]["source"], "Windows 메뉴 계층·항목 번호")
        check("menu_structure_" + location, (item["flags"], item["id"]) == (new_menu[location]["flags"], new_menu[location]["id"]))
        path = ["MenuBar", "Items"]
        indexes = location.split("/")[1:]
        for position, index in enumerate(indexes):
            path.append(index)
            if position + 1 < len(indexes):
                path.append("Items")
        set_path(expected_package, path + ["Name"], expected_text[location].replace("&", ""))
    old_controls = parse_player_controls(original.one(0x225D).decoded)
    new_controls = parse_player_controls(candidate.one(0x225D).decoded)
    new_fields = {control_key(r): r for r in new_controls["strings"]}
    source_resource_rows = {r["offset"]: r for r in inventory if r.get("target") == original.one(0x225D).location}
    check("controls_identity", {control_key(r) for r in old_controls["strings"]} == set(new_fields) and len(new_fields) == 75)
    check("dialog_geometry_and_actions", dialog_structure(old_controls) == dialog_structure(new_controls))
    for row in old_controls["strings"]:
        actual = new_fields[control_key(row)]["source"]
        if row["kind"] == "dialog_font":
            check(f"dialog_{row['dialog_id']}_font", actual == FAMILY)
        else:
            record_location(source_resource_rows[row["offset"]], actual, "Windows 표준 대화상자 ID·컨트롤 번호·필드 종류")
    check("four_dialog_fonts", sum(r["kind"] == "dialog_font" for r in old_controls["strings"]) == 4)
    # 논리 글꼴과 내장 TTF는 승인 글꼴의 바이트·자체 문자표·실제 연결로 검사합니다.
    fonts_report = []
    for before, after in zip(original.fonts, candidate.fonts):
        expected = bytearray(before.decoded)
        weight = 700 if uint(before.decoded, 28) >= 600 else 400
        struct.pack_into("<I", expected, 28, weight)
        expected[35] = 129
        expected[40:104] = (FAMILY.encode("utf-16le") + b"\0\0").ljust(64, b"\0")
        if args.layout_fix and before.handle == 21:
            check("layout_original_font21_height", struct.unpack_from("<i", before.decoded, 12)[0] == -24)
            struct.pack_into("<i", expected, 12, -20)
        check(f"font_{before.handle}_boundary", before.handle == after.handle and bytes(expected) == after.decoded)
        semantic = expected_package["FontBank"]["Fonts"][str(before.handle)]
        semantic.update(Name=FAMILY.ljust(32, "\0"), Weight=weight, CharSet=129)
        if args.layout_fix and before.handle == 21:
            semantic["Height"] = -20
        fonts_report.append({"handle": before.handle, "weight": weight, "family": utf16z(after.decoded, 40)[0], "charset": after.decoded[35]})
    check("logical_font_count", len(candidate.fonts) == len(original.fonts) == 28)
    old_ttf = compressed_records(original.one(0x2259).decoded)
    new_ttf = compressed_records(candidate.one(0x2259).decoded)
    check("embedded_font_count", len(old_ttf) == len(new_ttf) == 5)
    ttf_reports, ttf_weights = [], []
    for index, ((old_offset, old_data), (offset, data)) in enumerate(zip(old_ttf, new_ttf)):
        source_font = TTFont(io.BytesIO(old_data))
        expected_weight = 700 if source_font["OS/2"].usWeightClass >= 600 else 400
        source_font.close()
        font = TTFont(io.BytesIO(data))
        cmap = font.getBestCmap()
        missing = sorted(c for c in required if c not in cmap or cmap[c] == ".notdef")
        glyph_report = {"index": index, "offset": offset, "sha256": sha(data), "family": font["name"].getDebugName(1),
                        "style": font["name"].getDebugName(2), "weight": font["OS/2"].usWeightClass, "required_count": len(required),
                        "missing": missing, "variable": "fvar" in font, "embedding_flags": font["OS/2"].fsType}
        check(f"embedded_{index}_approved_bytes", sha(data) == FONT_HASHES[expected_weight] and (extracted / f"fonts/{index:02d}.ttf").read_bytes() == data)
        check(f"embedded_{index}_font_tables", not missing and glyph_report["family"] == FAMILY and glyph_report["weight"] == expected_weight and not glyph_report["variable"] and glyph_report["embedding_flags"] == 0)
        ttf_reports.append(glyph_report)
        ttf_weights.append(expected_weight)
        expected_package["TrueTypeFontBank"]["Fonts"][index]["Name"] = FAMILY
        expected_package["TrueTypeFontBank"]["Fonts"][index]["FontData"] = {"byte_length": len(data), "sha256": sha(data)}
        font.close()
    expected_package["TrueTypeFontBank"]["OffsetToIndex"] = {str(offset): i for i, (offset, _) in enumerate(new_ttf)}
    old_indices = {offset: i for i, (offset, _) in enumerate(old_ttf)}
    mapping_report = []
    old_info, new_info = original.one(0x2258).decoded, candidate.one(0x2258).decoded
    check("mapping_count", len(old_info) == len(new_info) and len(old_info) % 96 == 0)
    for pos in range(0, len(old_info), 96):
        before, after = old_info[pos:pos + 96], new_info[pos:pos + 96]
        index = old_indices[uint(before, 92)]
        weight = 700 if uint(before, 16) >= 600 else 400
        expected = bytearray(before)
        struct.pack_into("<I", expected, 16, weight)
        expected[23] = 129
        expected[28:92] = (FAMILY.encode("utf-16le") + b"\0\0").ljust(64, b"\0")
        struct.pack_into("<I", expected, 92, new_ttf[index][0])
        if args.layout_fix and pos == 1344:
            check("layout_original_mapping14_height", struct.unpack_from("<i", before)[0] == -24)
            struct.pack_into("<i", expected, 0, -20)
        check(f"mapping_{pos // 96}_exact_fields", bytes(expected) == after and ttf_weights[index] == weight)
        mapping_report.append({"index": pos // 96, "font_index": index, "weight": weight, "ttf_offset": uint(after, 92)})
    # 모든 압축 객체·글꼴·이미지의 실제 위치에서 위치표를 독립적으로 생성해 대조합니다.
    object_table = b"".join(struct.pack("<I", b.offset) for b in candidate.objects)
    check("object_offsets_actual_boundaries", object_table == candidate.one(0x2257).decoded)
    font_offsets = list(struct.unpack("<" + "I" * (len(original.one(0x5556).decoded) // 4), original.one(0x5556).decoded))
    for record in candidate.fonts:
        font_offsets[record.handle - 1] = record.offset + 260
    check("font_offsets_actual_boundaries", struct.pack("<" + "I" * len(font_offsets), *font_offsets) == candidate.one(0x5556).decoded)
    expected_package["FontOffsets"].update(Offsets=font_offsets, SortedOffsets=sorted(v for v in font_offsets if v))
    raw_bank = candidate.one(0x6666).decoded
    offsets = list(struct.unpack("<" + "I" * (len(original.one(0x5555).decoded) // 4), original.one(0x5555).decoded))
    source_image_records = {}
    source_image_bank = original.one(0x6666).decoded
    source_position = 4
    for _ in range(uint(source_image_bank)):
        record_end = source_position + 40 + uint(source_image_bank, source_position + 16)
        source_image_records[uint(source_image_bank, source_position) - 1] = source_image_bank[source_position:record_end]
        source_position = record_end
    check("source_image_records_bounds", source_position == len(source_image_bank))
    position, image_handles, image_raw_hashes = 4, [], {}
    for index in range(uint(raw_bank)):
        handle = uint(raw_bank, position) - 1
        offsets[handle] = position + 260
        image_handles.append(handle)
        record_end = position + 40 + uint(raw_bank, position + 16)
        record = raw_bank[position:record_end]
        source_record = source_image_records[handle]
        if handle in IMAGE_IDS:
            check(f"image_{handle}_header_unchanged", record[:16] + record[20:44] == source_record[:16] + source_record[20:44])
            pixels = lz4.block.decompress(record[44:], uncompressed_size=uint(record, 40))
            image_raw_hashes[handle] = sha(pixels)
        else:
            check(f"image_{handle}_compressed_record_unchanged", record == source_record)
        position = record_end
    check("image_record_bounds", position == len(raw_bank) and len(image_handles) == len(set(image_handles)) == uint(source_image_bank))
    check("image_offsets_actual_boundaries", struct.pack("<" + "I" * len(offsets), *offsets) == candidate.one(0x5555).decoded)
    expected_package["ImageOffsets"].update(Offsets=offsets, SortedOffsets=sorted(v for v in offsets if v))
    # 이미지 전수는 원본 PNG 재사용 조건을 확인하고 실제 RGBA를 비교합니다.
    image_source_dir = source_semantic if profile else BASE / 'nebula_01'
    source_media = {r["handle"]: r for r in load(image_source_dir / "media.json")}
    candidate_media = {r["handle"]: r for r in load(extracted / "media.json")}
    source_png_package = load(image_source_dir / "package.json")
    check("original_png_reuse_same_source_and_pre_render_bank", load(image_source_dir / "input.json")["sha256"] == sha(original.original) and source_png_package["ImageBank"] == source_package["ImageBank"])
    check("image_handle_identity", source_media.keys() == candidate_media.keys() == set(image_handles))
    image_report = []
    for handle in sorted(source_media):
        old, new = source_media[handle], candidate_media[handle]
        if old['path'] is None and new['path'] is None:
            check(f'image_{handle}_dimensions', (old['Width'],old['Height'],old['GraphicMode']) == (new['Width'],new['Height'],new['GraphicMode']))
            if handle in IMAGE_IDS:
                target_png = WORK / f'media_ko_01/{handle:05d}.png'
                with Image.open(target_png) as im:
                    rgba = im.convert('RGBA').tobytes()
                    bgra = im.convert('RGBA').tobytes('raw','BGRA')
                check(f'image_{handle}_approved_pixels', sha(bgra) == image_raw_hashes[handle] == new['source_sha256'])
                expected_package['ImageBank']['Images'][str(handle)]['ImageData']['sha256'] = image_raw_hashes[handle]
            else:
                check(f'image_{handle}_independent_pixels_unchanged', old['source_sha256'] == new['source_sha256'])
            image_report.append({'handle':handle,'translated':handle in IMAGE_IDS,'source_sha256':old['source_sha256'],'actual_sha256':new['source_sha256'],'status':'PASS' if not errors else 'CHECK_SUMMARY'})
            continue
        source_png = BASE / "nebula_01" / old["path"]
        candidate_png = extracted / new["path"]
        check(f"image_{handle}_baseline_reuse", sha(source_png.read_bytes()) == old["sha256"])
        target_png = WORK / f"media_ko_01/{handle:05d}.png" if handle in IMAGE_IDS else source_png
        with Image.open(target_png) as image:
            expected_rgba, dimensions = image.convert("RGBA").tobytes(), image.size
        with Image.open(candidate_png) as image:
            actual_rgba, actual_dimensions = image.convert("RGBA").tobytes(), image.size
        success = expected_rgba == actual_rgba and dimensions == actual_dimensions
        check(f"image_{handle}_rgba", success)
        image_report.append({"handle": handle, "translated": handle in IMAGE_IDS, "expected_png_sha256": sha(target_png.read_bytes()), "actual_png_sha256": sha(candidate_png.read_bytes()), "rgba_sha256": sha(actual_rgba), "status": "PASS" if success else "FAIL"})
        if handle in IMAGE_IDS:
            # 압축된 BGRA의 지문은 의미 이미지와 정확 픽셀 대조를 통과한 네 위치만 변경 허용합니다.
            expected_package["ImageBank"]["Images"][str(handle)]["ImageData"]["sha256"] = image_raw_hashes[handle]
    # 원시 이벤트 전체 바이트의 변경을 네 번역 슬롯에만 제한합니다.
    for old_frame, frame in zip(source_frames, frame_chunks):
        old = next(c for c in old_frame.children if c.chunk_id == 0x333D)
        new = next(c for c in frame.children if c.chunk_id == 0x333D)
        expected = bytearray(old.decoded)
        for row in event_rows:
            if row["target"] == old.location and row["location"] in expected_text:
                size, pos = row["slot_bytes"], row["offset"]
                expected[pos:pos + size] = (expected_text[row["location"]].encode("utf-16le") + b"\0\0").ljust(size, b"\0")
        check("complete_event_boundary_" + old.location, bytes(expected) == new.decoded)
    # 미지원 설명 906건은 후보의 해당 원시 영역이 원본과 완전히 같을 때만 근거를 재사용합니다.
    resolution_path = classification_path / "description_error_resolution.jsonl"
    resolutions = lines(resolution_path)
    unresolved = []
    for row in resolutions:
        chunk = candidate.by_location[row["target"]]
        raw = chunk.decoded[row["offset"]:row["offset"] + row["size"]]
        if sha(raw) != row["sha256"] or raw.hex() != row["raw_hex"]:
            unresolved.append(row)
    candidate_unknown = []
    for path in sorted((extracted / "frames").glob("*.json")):
        for row in load(path):
            if row["display"] is None or "[ERROR]" in row["display"] or "Unknown" in row["display"]:
                candidate_unknown.append(row)
    source_unknown = [r for p in sorted((source_semantic / 'frames').glob('*.json')) for r in load(p)
                      if r['display'] is None or '[ERROR]' in r['display'] or 'Unknown' in r['display']]
    unknown_key = lambda r: (r["frame"], r["ev"], r["kind"], r["index"], r["ObjectType"], r["Num"], r["display"])
    check("descriptions_reused_only_with_identical_raw_regions", len(resolutions) == len(candidate_unknown) == len(source_unknown) and not unresolved and {unknown_key(x) for x in source_unknown} == {unknown_key(x) for x in candidate_unknown})
    save("description_resolution_reuse.json", {"status": "PASS" if not unresolved else "FAIL", "source_report_sha256": sha(resolution_path.read_bytes()), "count": len(resolutions), "candidate_unknown_count": len(candidate_unknown), "changed_raw_regions": unresolved})
    # 크기 메타데이터는 실제 읽은 청크 크기로 한정해 기대값을 갱신합니다.
    for name, ident in (("MenuBar", 0x2226), ("TrueTypeFontBank", 0x2259), ("ImageBank", 0x6666), ("ImageOffsets", 0x5555), ("FontBank", 0x6667), ("FontOffsets", 0x5556)):
        expected_package[name]["ChunkSize"] = len(candidate.one(ident).raw)
    for index, frame in enumerate(frame_chunks):
        expected_package["Frames"][index]["ChunkSize"] = len(frame.raw)
        expected_package["Frames"][index]["FrameEvents"]["ChunkSize"] = len(next(c for c in frame.children if c.chunk_id == 0x333D).raw)
    check("header_unchanged", candidate.header == original.header)
    for dat, label in ((original, "source"), (candidate, "candidate")):
        start = len(dat.header) + dat.one(0x222F).offset
        end = len(dat.header) + dat.one(0x2242).offset
        check(label + "_independent_runtime_checksum", runtime_checksum(dat.original[start:end]) == uint(dat.one(0x2242).decoded))
    expected_package["Protection"] = {"byte_length": 4, "sha256": sha(candidate.one(0x2242).decoded)}
    allowed = {0x225D, 0x2226, 0x2259, 0x2258, 0x2256, 0x2257, 0x2242, 0x6666, 0x5555, 0x6667, 0x5556}
    changes = []
    check("chunk_identity", set(original.by_location) == set(candidate.by_location))
    for location, before in original.by_location.items():
        after = candidate.by_location[location]
        check("chunk_flags_" + location, (before.chunk_id, before.flag) == (after.chunk_id, after.flag))
        if not before.children and before.raw != after.raw:
            permitted = before.chunk_id in allowed or location in {r['target'] for r in event_rows if r['location'] in expected_text}
            check("changed_chunk_" + location, permitted)
            changes.append(location)
    semantic_errors = list(differences(expected_package, actual_package))
    save("unexpected_semantic_changes.json", semantic_errors)
    check("complete_semantic_tree_expected_values", not semantic_errors, unexpected=len(semantic_errors))
    check("all_translation_locations_verified", verified_locations == set(expected_text))
    check("candidate_unchanged_during_validation", sha(candidate_path.read_bytes()) == candidate_digest)
    for name, report in (("location_comparison.json", location_report), ("button_validation.json", button_report), ("logical_fonts.json", fonts_report),
                         ("embedded_fonts.json", ttf_reports), ("font_mappings.json", mapping_report), ("image_validation.json", image_report), ("event_frames.json", raw_events), ("checks.json", checks)):
        save(name, report)
    summary = {"status": "PASS" if not errors else "FAIL", "source_sha256": sha(original.original), "candidate_sha256": candidate_digest,
               "candidate_path": str(candidate_path), "translations_sha256": sha(translation_path.read_bytes()),
               "layout_fix": args.layout_fix, "checks": len(checks), "errors": errors,
               "translation_groups": len(translations), "translation_locations": len(verified_locations), "paragraphs": len(paragraphs), "raw_event_strings": len(event_fields),
               "objects": len(candidate.objects), "frames": len(frame_chunks), "logical_fonts": len(fonts_report), "embedded_fonts": len(ttf_reports),
               "font_mappings": len(mapping_report), "buttons": len(button_report), "dialogs": len(new_controls["dialogs"]), "images": len(image_report),
               "translated_images": len(IMAGE_IDS), "unchanged_images": len(image_report) - len(IMAGE_IDS), "changed_leaf_chunks": changes,
               "semantic_tree_unexpected_changes": len(semantic_errors), "description_unknowns_with_identical_raw_proof": len(resolutions),
               "method": "승인 원문·번역과 독립 Nebula 전체 추출, 원시 event_operations/Windows 자원 파서, fontTools 문자표, PNG RGBA 전수 대조. 빌더 보고서·성공 카운터를 입력으로 사용하지 않음",
               "tool_sha256": sha(Path(__file__).read_bytes()), "graphics_qa": "NOT_RUN", "scope": "G4 정적 독립 재추출 검증; 실제 화면은 부모 별도 담당"}
    save("g4_summary.json", summary)
    print(json.dumps({key: summary[key] for key in ("status", "candidate_sha256", "checks", "translation_locations", "semantic_tree_unexpected_changes")}, ensure_ascii=False))
    for error in errors[:15]:
        print(json.dumps(error, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
