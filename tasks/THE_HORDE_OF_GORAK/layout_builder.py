"""실제 화면과 GDI 측정으로 확인한 다중 행 배치 문제만 수정한다."""
from __future__ import annotations

import struct

from dat_container import sha, utf16z

FAMILY = "THOG Noto Sans KR"
LAYOUT_ID = "progress_line_height_02"
FIELD_CHANGES = (
    {"target": "object:514", "field": "ObjectParagraphs.Paragraphs.0.FontHandle", "before": 11, "after": 6},
    {"target": "font:21", "field": "Height", "before": -24, "after": -20},
    {"target": "chunk:2258/mapping:14", "field": "Height", "before": -24, "after": -20},
    {"target": "object:510", "field": "ObjectParagraphs.Height", "before": 223, "after": 300},
    {"target": "object:1000", "field": "ObjectParagraphs.Height", "before": 127, "after": 144},
)


def effective(block):
    return block.decoded if block.replacement is None else block.replacement


def apply_layout(dat, object_map=None):
    """apply_fonts 및 번역 적용 뒤 호출한다. 기존 후보 파일에는 직접 쓰지 않는다."""
    edits = []
    object_map = object_map or {}
    progress_handle = object_map.get(514, 514)

    def update(block, offset, format_, old, new, target, field, semantic_old=None, semantic_new=None):
        before = effective(block)
        if struct.unpack_from(format_, before, offset)[0] != old:
            raise ValueError(f"배치 수정 전 필드가 예상과 다름: {target}/{field}")
        after = bytearray(before)
        struct.pack_into(format_, after, offset, new)
        block.replacement = bytes(after)
        edits.append({"target": target, "field": field, "offset": offset, "size": struct.calcsize(format_),
                      "before": old if semantic_old is None else semantic_old,
                      "after": new if semantic_new is None else semantic_new,
                      "before_decoded_sha256": sha(before), "after_decoded_sha256": sha(after)})

    # CCN 문단의 글꼴 번호는 저장값보다 1 크다. 새 글꼴 추가 없이 기존 6번을 쓴다.
    text = effective(dat.objects[progress_handle])
    start = struct.unpack_from("<H", text, 36)[0]
    if struct.unpack_from("<iii", text, start + 4) != (480, 540, 1):
        raise ValueError("진행 상황 글상자 구조가 예상과 다름")
    paragraph = start + struct.unpack_from("<I", text, start + 16)[0]
    if paragraph != 136 or not utf16z(text, paragraph + 8)[0].startswith("현재 성채:"):
        raise ValueError("한글화된 진행 상황 문단 위치가 예상과 다름")
    update(dat.objects[progress_handle], paragraph, "<H", 10, 5, f"object:{progress_handle}",
           "ObjectParagraphs.Paragraphs.0.FontHandle", 11, 6)

    # 21번은 결과 화면의 207번 객체만 참조한다. 그 글꼴과 내장 글꼴 매핑을 함께 바꾼다.
    font = next(block for block in dat.fonts if block.handle == 21)
    if utf16z(effective(font), 40)[0] != FAMILY:
        raise ValueError("먼저 승인된 한글 글꼴을 적용해야 함")
    update(font, 12, "<i", -24, -20, "font:21", "Height")
    info = dat.one(0x2258)
    before = effective(info)
    if len(before) % 96 or len(before) < 15 * 96 or utf16z(before, 14 * 96 + 28)[0] != FAMILY:
        raise ValueError("내장 글꼴 매핑 구조가 예상과 다름")
    if struct.unpack_from("<i", before, 14 * 96 + 16)[0] != 400:
        raise ValueError("결과 화면 글꼴 굵기가 예상과 다름")
    update(info, 14 * 96, "<i", -24, -20, "chunk:2258/mapping:14", "Height")

    for handle, width, old_height, new_height in ((510, 395, 223, 300), (1000, 480, 127, 144)):
        handle = object_map.get(handle, handle)
        block = dat.objects[handle]
        data = effective(block)
        start = struct.unpack_from("<H", data, 36)[0]
        if struct.unpack_from("<i", data, start + 4)[0] != width:
            raise ValueError("다중 행 글상자 폭이 예상과 다름")
        update(block, start + 8, "<i", old_height, new_height, f"object:{handle}", "ObjectParagraphs.Height")
    return {"layout_id": LAYOUT_ID, "changes": edits, "object_ranges": {
        progress_handle: [(paragraph, paragraph + 2)],
        object_map.get(510,510): [(struct.unpack_from("<H", effective(dat.objects[object_map.get(510,510)]), 36)[0] + 8,
               struct.unpack_from("<H", effective(dat.objects[object_map.get(510,510)]), 36)[0] + 12)],
        object_map.get(1000,1000): [(struct.unpack_from("<H", effective(dat.objects[object_map.get(1000,1000)]), 36)[0] + 8,
                struct.unpack_from("<H", effective(dat.objects[object_map.get(1000,1000)]), 36)[0] + 12)]},
        "font_ranges": {21: [(12, 16)]}, "chunk_ranges": {0x2258: [(1344, 1348)]}}
