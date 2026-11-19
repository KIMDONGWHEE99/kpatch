"""OFL 한글 글꼴을 내장하고 글꼴 연결 전체를 바꾸는 소규모 후보 생성기."""
from __future__ import annotations

import io
import json
import struct
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from dat_container import DatFile, encode_block, sha, u32, utf16z

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat"
FONT = ROOT / "tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf"
LICENSE = FONT.parent / "OFL.txt"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/font_smoke_01"
FAMILY = "THOG Noto Sans KR"
CHARSET = 129


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"기존 결과와 다른 내용 덮어쓰기 금지: {path}")
    if not path.exists():
        path.write_bytes(data)


def make_font(weight):
    font = TTFont(FONT, recalcTimestamp=False)
    font = instantiateVariableFont(font, {"wght": weight}, inplace=True)
    style = "Bold" if weight == 700 else "Regular"
    # 가변 글꼴의 Thin 이름과 설치된 다른 Noto 글꼴이 섞이지 않도록 이름을 일치시킨다.
    replacement_names = {1: FAMILY, 2: style, 3: f"THOG-NotoSansKR-{style}-2.004",
                         4: f"{FAMILY} {style}", 6: f"THOGNotoSansKR-{style}", 16: FAMILY, 17: style}
    font["name"].names = [n for n in font["name"].names if n.nameID not in replacement_names]
    for ident, value in replacement_names.items():
        font["name"].setName(value, ident, 3, 1, 0x409)
        font["name"].setName(value, ident, 1, 0, 0)
    font["OS/2"].usWeightClass = weight
    font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~(0x20 | 0x40)) | (0x20 if weight == 700 else 0x40)
    font["head"].macStyle = (font["head"].macStyle & ~1) | (1 if weight == 700 else 0)
    output = io.BytesIO()
    font.save(output)
    font.close()
    return output.getvalue()


def change_logfont(data, offset):
    result = bytearray(data)
    weight = 700 if u32(result, offset + 16) >= 600 else 400
    struct.pack_into("<I", result, offset + 16, weight)
    result[offset + 23] = CHARSET
    result[offset + 28:offset + 92] = (FAMILY.encode("utf-16le") + b"\0\0").ljust(64, b"\0")
    return bytes(result), weight


def inspect_font(data, required):
    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    cmap = font.getBestCmap()
    missing = sorted(c for c in required if c not in cmap or cmap[c] == ".notdef")
    report = {"sha256": sha(data), "bytes": len(data), "family": font["name"].getDebugName(1),
              "style": font["name"].getDebugName(2), "weight": font["OS/2"].usWeightClass,
              "embedding_flags": font["OS/2"].fsType, "cmap_count": len(cmap),
              "variable": "fvar" in font, "required_count": len(required), "missing": missing}
    assert report["family"] == FAMILY and not report["variable"] and not missing
    assert report["embedding_flags"] == 0
    font.close()
    return report


def apply_fonts(dat, fonts, extension_inventory=None):
    """입력 DAT에 글꼴만 적용하며 화면 문구는 바꾸지 않는다."""
    old_ttf_blocks = DatFile._blocks(dat.one(0x2259).decoded)
    bank = bytearray()
    offset_map = {}
    embedded = []
    for block in old_ttf_blocks:
        original_ttf = TTFont(io.BytesIO(block.decoded))
        weight = 700 if original_ttf["OS/2"].usWeightClass >= 600 else 400
        original_ttf.close()
        offset_map[block.offset] = len(bank)
        embedded.append({"index": block.index, "original_offset": block.offset, "offset": len(bank), "weight": weight,
                         "original_sha256": sha(block.decoded), "sha256": sha(fonts[weight])})
        bank += encode_block(fonts[weight])
    assert len(embedded) == 5
    dat.one(0x2259).replacement = bytes(bank)

    info = dat.one(0x2258).decoded
    new_info = bytearray()
    mappings = []
    for offset in range(0, len(info), 96):
        before = info[offset:offset + 96]
        after, weight = change_logfont(before, 0)
        new_offset = offset_map[u32(before, 92)]
        after = after[:92] + struct.pack("<I", new_offset)
        assert next(b["weight"] for b in embedded if b["offset"] == new_offset) == weight
        new_info += after
        mappings.append({"index": offset // 96, "weight": weight, "ttf_offset": new_offset})
    assert len(info) % 96 == 0 and len(mappings) == len(info) // 96
    dat.one(0x2258).replacement = bytes(new_info)
    for block in dat.fonts:
        block.replacement, _ = change_logfont(block.decoded, 12)

    extension_inventory = extension_inventory or ROOT / "extracted_private/THE_HORDE_OF_GORAK/steam_26336311/media_review_01/extension_inventory.jsonl"
    button_changes = []
    for line in extension_inventory.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["kind"] != "button_font":
            continue
        block = dat.objects[row["object_handle"]]
        before = block.decoded if block.replacement is None else block.replacement
        assert sha(block.decoded) == row["object_decoded_sha256"]
        block.replacement, weight = change_logfont(before, row["object_offset"] - 28)
        button_changes.append({"object": row["object_handle"], "name_offset": row["object_offset"], "weight": weight})
    assert len(button_changes) > 0
    return embedded, mappings, button_changes


def build():
    if sha(FONT.read_bytes()) != "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252":
        raise ValueError("글꼴 원본 해시 불일치")
    if sha(LICENSE.read_bytes()) != "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9":
        raise ValueError("글꼴 라이선스 해시 불일치")
    original = DatFile.load(SOURCE)
    dat = DatFile.load(SOURCE)
    fonts = {weight: make_font(weight) for weight in (400, 700)}
    # 완성형 한글 전체와 자모, 현재 표시 원문 및 시험 문구를 함께 검사한다.
    required = set(range(0xAC00, 0xD7A4)) | set(range(0x1100, 0x1200)) | set(range(0x3131, 0x318F))
    inventory = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031/classification/inventory.jsonl"
    for line in inventory.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["classification"].startswith("VISIBLE_"):
            required.update(ord(c) for c in row["source"] if ord(c) >= 32)
    required.update(map(ord, "그래픽새 게임"))
    font_reports = {weight: inspect_font(value, required) for weight, value in fonts.items()}
    for weight, value in fonts.items():
        write_new(OUT / "fonts" / f"THOGNotoSansKR-{weight}.ttf", value)
    write_new(OUT / "fonts/OFL.txt", LICENSE.read_bytes())

    embedded, mappings, button_changes = apply_fonts(dat, fonts)
    dat.patch_utf16("object:32", 148, "GRAPHICS", "그래픽")
    dat.patch_utf16("object:28", 348, "NEW GAME", "새 게임")
    output = dat.serialize()
    candidate = DatFile(output)
    assert candidate.integrity_summary()["status"] == "PASS"
    assert candidate.serialize() == output
    reread_blocks = DatFile._blocks(candidate.one(0x2259).decoded)
    assert len(reread_blocks) == 5
    for block, expected in zip(reread_blocks, embedded):
        assert block.offset == expected["offset"] and sha(block.decoded) == expected["sha256"]
        inspect_font(block.decoded, required)
    for offset in range(0, len(new_info), 96):
        row = candidate.one(0x2258).decoded[offset:offset + 96]
        ttf = next(b for b in reread_blocks if b.offset == u32(row, 92))
        report = inspect_font(ttf.decoded, required)
        assert utf16z(row, 28)[0] == report["family"] and row[23] == CHARSET and u32(row, 16) == report["weight"]
    for block in candidate.fonts:
        assert utf16z(block.decoded, 40)[0] == FAMILY and block.decoded[35] == CHARSET
    for change in button_changes:
        block = candidate.objects[change["object"]]
        assert utf16z(block.decoded, change["name_offset"])[0] == FAMILY
        assert block.decoded[change["name_offset"] - 5] == CHARSET
    assert utf16z(candidate.objects[32].decoded, 148)[0] == "그래픽"
    assert utf16z(candidate.objects[28].decoded, 348)[0] == "새 게임"
    changed = [f"0x{a.chunk_id:04x}" for a, b in zip(original.chunks, candidate.chunks) if a.decoded != b.decoded]
    assert set(changed) == {"0x2259", "0x2258", "0x2256", "0x2257", "0x2242", "0x6667", "0x5556"}
    write_new(OUT / "THOG.dat", output)
    report = {"source_sha256": sha(original.original), "candidate_sha256": sha(output), "candidate_bytes": len(output),
              "builder_sha256": sha(Path(__file__).read_bytes()), "container_tool_sha256": sha((Path(__file__).parent / "dat_container.py").read_bytes()),
              "font_source_sha256": sha(FONT.read_bytes()), "license_sha256": sha(LICENSE.read_bytes()),
              "source_metadata_url": "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/METADATA.pb",
              "source_repository": "https://github.com/notofonts/noto-cjk", "source_upstream_commit": "523d033d6cb47f4a80c58a35753646f5c3608a78",
              "fonts": font_reports, "embedded": embedded, "mappings": mappings, "button_changes": button_changes,
              "logical_fonts": len(candidate.fonts), "changed_chunks": changed, "integrity": candidate.integrity_summary(),
              "cmap_and_offsets": "PASS", "runtime_qa": "NOT_RUN",
              "scope": "글꼴 전체 연결을 바꾸고 두 문구만 한글로 바꾼 시험 후보. 키 설정 대화상자 글꼴은 별도 재조립 작업에서 처리"}
    write_new(OUT / "build_report.json", (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"candidate": str(OUT / "THOG.dat"), "sha256": sha(output), "bytes": len(output), "status": "PASS"}))


if __name__ == "__main__":
    build()
