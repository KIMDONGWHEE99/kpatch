"""원본에서 글꼴·위치별 번역·자원·이미지를 통합하고 허용 변경 범위를 검증한다."""
from __future__ import annotations

import argparse
import json
import re
import struct
from collections import defaultdict
from pathlib import Path

from PIL import Image

from button_builder import inspect_button, patch_button_text
from dat_container import DatFile, sha, u32, utf16z
from font_builder import FAMILY, FONT, LICENSE, apply_fonts, inspect_font
from image_builder import ALLOWED_HANDLES, ImageBank, verify_replacement
from resource_builder import patch_resources

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "working_private/THE_HORDE_OF_GORAK"
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat"
CLASSIFICATION = WORK / "investigation_20261031/classification"
FONT_HASHES = {400: "92059cbf2f73131a587426da2146e993b496349cb5c0b267d2797f4000984d35",
               700: "ef07411de3796cae75a0b8f5788b0ee2aceef44dddaae32e4371796229622ac8"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_ranges(before, after, ranges):
    if len(before) != len(after):
        raise ValueError("고정 영역의 바이트 길이가 달라짐")
    mask = bytearray(len(before))
    for start, end in ranges:
        if not 0 <= start <= end <= len(before):
            raise ValueError("허용 변경 범위가 자료 밖을 가리킴")
        mask[start:end] = b"\x01" * (end - start)
    for index, (a, b) in enumerate(zip(before, after)):
        if a != b and not mask[index]:
            raise ValueError(f"허용하지 않은 바이트 변경: {index}")


def text_checks(source, translation):
    if not isinstance(translation, str) or not translation or "\0" in translation or translation == source:
        raise ValueError("빈 번역·NUL·원문 잔존 또는 잘못된 번역 형식")
    if re.findall(r"\r\n|\r|\n", source) != re.findall(r"\r\n|\r|\n", translation):
        raise ValueError("원래 줄바꿈 순서 불일치")
    if re.findall(r"%(?:\d+\$)?[sdif]|\{[^{}]*\}|\[[A-Za-z]+\]", source) != re.findall(r"%(?:\d+\$)?[sdif]|\{[^{}]*\}|\[[A-Za-z]+\]", translation):
        raise ValueError("자리표시자 또는 입력 키 토큰 순서 불일치")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-id", default="ko_candidate_01")
    parser.add_argument("--translations", type=Path, default=WORK / "translation_01/translations.json")
    parser.add_argument("--layout-fix", action="store_true")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--source-sha256", default="60825bc8e3969274f5235088f86c38a8fd187b6265b8082de6b9625d1437e950")
    parser.add_argument("--classification", type=Path, default=CLASSIFICATION)
    parser.add_argument("--extension-inventory", type=Path, default=ROOT / "extracted_private/THE_HORDE_OF_GORAK/steam_26336311/media_review_01/extension_inventory.jsonl")
    parser.add_argument("--layout-object-map", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_]+", args.candidate_id):
        raise ValueError("후보 이름 형식 오류")
    out = ROOT / "build_candidate/THE_HORDE_OF_GORAK" / args.candidate_id
    if out.exists():
        raise ValueError("기존 후보를 덮어쓰지 않음. 새 후보 이름 사용")
    inventory_path = args.classification / "inventory.jsonl"
    inventory = [json.loads(line) for line in inventory_path.read_text(encoding="utf-8").splitlines()]
    worklist_path = args.classification / "translation_worklist.json"
    worklist = read_json(worklist_path)
    translation_rows = read_json(args.translations)
    by_source = {row["source"]: row for row in translation_rows}
    if len(by_source) != len(translation_rows) or len(by_source) != len(worklist) or set(by_source) != {row["source"] for row in worklist}:
        raise ValueError("번역 원문 목록 누락·중복·추가")
    if any(row["classification"] == "UNKNOWN" for row in inventory):
        raise ValueError("미분류 항목이 남아 있음")
    inputs = [args.source, inventory_path, worklist_path, args.translations, FONT, LICENSE,
              WORK / "font_smoke_01/build_report.json", WORK / "media_ko_01/manifest.json",
              args.extension_inventory]
    inputs.extend(WORK / "font_smoke_01/fonts" / f"THOGNotoSansKR-{w}.ttf" for w in (400, 700))
    inputs.extend(WORK / "media_ko_01" / f"{h:05d}.png" for h in sorted(ALLOWED_HANDLES))
    inputs.extend(Path(__file__).parent / name for name in ("build_patch.py", "dat_container.py", "font_builder.py", "button_builder.py", "resource_builder.py", "image_builder.py"))
    if args.layout_fix:
        inputs.append(Path(__file__).parent / 'layout_builder.py')
        if args.layout_object_map:
            inputs.append(args.layout_object_map)
        else:
            inputs.extend(args.translations.parent / name for name in ('audit_summary.json', 'dev_instruction_corrections.json'))
    locked_inputs = {str(path): sha(path.read_bytes()) for path in inputs}
    original, dat = DatFile.load(args.source), DatFile.load(args.source)
    if sha(original.original) != args.source_sha256:
        raise ValueError("지원하지 않는 원본 DAT")
    fonts = {w: (WORK / "font_smoke_01/fonts" / f"THOGNotoSansKR-{w}.ttf").read_bytes() for w in (400, 700)}
    if any(sha(data) != FONT_HASHES[w] for w, data in fonts.items()):
        raise ValueError("실제 화면 검사를 통과한 글꼴과 다름")
    embedded, mappings, font_buttons = apply_fonts(dat, fonts, args.extension_inventory)
    object_ranges, event_ranges = defaultdict(list), defaultdict(list)
    for item in font_buttons:
        face = item["name_offset"]
        object_ranges[item["object"]].extend([(face - 12, face - 8), (face - 5, face - 4), (face, face + 64)])
    resources, expected, button_changes = [], [], {}
    required = set()
    for group in worklist:
        row = by_source[group["source"]]
        if row["occurrences"] != group["occurrences"]:
            raise ValueError("번역에 포함된 원문 위치 목록 변경")
        overrides = {item["location"]: item["translation"] for item in row.get("overrides", [])}
        if len(overrides) != len(row.get("overrides", [])) or set(overrides) - {item["location"] for item in group["occurrences"]}:
            raise ValueError("해당 원문과 연결되지 않은 위치별 번역")
        for occurrence in group["occurrences"]:
            translated = overrides.get(occurrence["location"], row["translation"])
            text_checks(group["source"], translated)
            required.update(ord(c) for c in translated if ord(c) >= 32)
            change = {**occurrence, "source": group["source"], "translated": translated}
            expected.append(change)
            if occurrence["kind"] == "button_text":
                handle = int(occurrence["target"].split(":")[1])
                button_changes[handle] = patch_button_text(dat, handle, group["source"], translated)
            elif occurrence["kind"] in {"menu_text", "control_key_name", "dialog_title", "dialog_item_title"}:
                resources.append({key: change[key] for key in ("target", "offset", "source", "translated")})
            elif occurrence["kind"] in {"paragraph", "event_string"}:
                dat.patch_utf16(**{key: change[key] for key in ("target", "offset", "source", "translated", "slot_bytes")})
                ranges = object_ranges[int(occurrence["target"].split(":")[1])] if occurrence["kind"] == "paragraph" else event_ranges[occurrence["target"]]
                ranges.append((occurrence["offset"], occurrence["offset"] + occurrence["slot_bytes"]))
            else:
                raise ValueError("지원하지 않은 번역 필드 종류")
    for row in inventory:
        if row["kind"] == "dialog_font":
            resources.append({"target": row["target"], "offset": row["offset"], "source": row["source"], "translated": FAMILY})
    resource_report = patch_resources(dat, resources)
    resource_offsets = {(row["target"], row["original_offset"]): row["output_offset"] for row in resource_report}
    layout_report = None
    if args.layout_fix:
        from layout_builder import apply_layout
        layout_mapping_before = dat.get_target(dat.one(0x2258).location)[1]
        object_map = {int(k): v for k,v in read_json(args.layout_object_map).items()} if args.layout_object_map else None
        layout_report = apply_layout(dat, object_map)
        verify_ranges(layout_mapping_before, dat.get_target(dat.one(0x2258).location)[1],
                      layout_report['chunk_ranges'][0x2258])
        for handle, ranges in layout_report['object_ranges'].items():
            object_ranges[handle].extend(ranges)
    image_base = DatFile(dat.serialize())
    bank = ImageBank(dat)
    image_changes, image_expected = [], {}
    for handle in sorted(ALLOWED_HANDLES):
        path = WORK / "media_ko_01" / f"{handle:05d}.png"
        image_changes.append(bank.replace_png(handle, path))
        with Image.open(path) as image:
            image_expected[handle] = image.tobytes()
    bank.apply()
    output = dat.serialize()
    result = DatFile(output)
    assert result.serialize() == output
    verify_replacement(image_base, result, image_expected)
    location_report = []
    for change in expected:
        offset = resource_offsets.get((change["target"], change["offset"]), change["offset"])
        _, data = result.get_target(change["target"])
        actual = utf16z(data, offset)[0]
        if actual != change["translated"]:
            raise ValueError(f"위치별 번역 불일치: {change['location']}")
        location_report.append({**change, "output_offset": offset, "actual": actual, "status": "PASS"})
    assert len(location_report) == sum(len(row['occurrences']) for row in worklist)
    for before, after in zip(original.objects, result.objects):
        if before.index in button_changes:
            old, new = inspect_button(original, before.index), inspect_button(result, before.index)
            assert old["text_offset"] == new["text_offset"] and old["section_offsets"] == new["section_offsets"]
            assert old["data"][-8:] == new["data"][-8:]
            allowed = object_ranges[before.index] + [(p, p + 4) for p in button_changes[before.index]["changed_size_fields"]]
            verify_ranges(before.decoded[:old["text_offset"]], after.decoded[:old["text_offset"]], allowed)
        else:
            verify_ranges(before.decoded, after.decoded, object_ranges[before.index])
    for before, after in zip(original.fonts, result.fonts):
        assert before.handle == after.handle
        ranges = [(28, 32), (35, 36), (40, 104)]
        if layout_report:
            ranges += layout_report['font_ranges'].get(before.handle, [])
        verify_ranges(before.decoded, after.decoded, ranges)
    font_report = {w: inspect_font(data, required) for w, data in fonts.items()}
    allowed_banks = {0x2256, 0x2257, 0x2258, 0x2259, 0x2242, 0x6667, 0x5556, 0x6666, 0x5555, 0x2226, 0x225D}
    changed_chunks = []
    for location, before in original.by_location.items():
        after = result.by_location[location]
        assert (before.chunk_id, before.flag) == (after.chunk_id, after.flag)
        if before.children or before.decoded == after.decoded:
            continue
        changed_chunks.append(location)
        if location in event_ranges:
            verify_ranges(before.decoded, after.decoded, event_ranges[location])
        elif before.chunk_id not in allowed_banks:
            raise ValueError(f"허용하지 않은 청크 변경: {location}")
    assert original.header == result.header
    assert result.integrity_summary()["status"] == "PASS"
    for path, digest in locked_inputs.items():
        if sha(Path(path).read_bytes()) != digest:
            raise ValueError("제작 도중 입력 변경: 결과 STALE")
    out.mkdir(parents=True)
    (out / "THOG.dat").write_bytes(output)
    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save("location_comparison.json", location_report)
    save("resource_comparison.json", resource_report)
    save("button_changes.json", list(button_changes.values()))
    save("image_changes.json", image_changes)
    if layout_report:
        save('layout_changes.json', layout_report)
    report = {"status": "PASS", "source_sha256": sha(original.original), "candidate_sha256": sha(output),
              "candidate_bytes": len(output), "inputs": locked_inputs, "translations": len(by_source),
              "translated_locations": len(location_report), "changed_leaf_chunks": changed_chunks,
              "layout_fix": layout_report,
              "fonts": font_report, "embedded": embedded, "font_mappings": mappings,
              "object_and_event_boundaries": "PASS", "resource_fields": "PASS", "image_pixels_and_other_records": "PASS",
              "integrity": result.integrity_summary(), "independent_reextract": "NOT_RUN", "runtime_qa": "NOT_RUN",
              "scope": "정적 통합 후보. 독립 도구 재추출과 실제 화면 검사는 별도 단계"}
    save("build_report.json", report)
    print(json.dumps({"candidate": str(out / "THOG.dat"), "sha256": sha(output), "locations": len(location_report), "status": "PASS"}))


if __name__ == "__main__":
    main()
