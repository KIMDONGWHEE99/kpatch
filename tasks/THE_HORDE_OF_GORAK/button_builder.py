"""객체 마지막에 놓인 KcBoxA 버튼 문구를 길이와 함께 재조립한다."""
import struct

from dat_container import u32, utf16z


def inspect_button(dat, handle):
    headers = dat.one(0x2253).decoded
    matching = [headers[p:p + 16] for p in range(0, len(headers), 16)
                if struct.unpack_from("<H", headers, p)[0] == handle]
    if len(matching) != 1 or struct.unpack_from("<h", matching[0], 2)[0] != 32:
        raise ValueError("확인한 KcBoxA 타입32 객체가 아님")
    block, data = dat.get_target(f"object:{handle}")
    extension = struct.unpack_from("<H", data, 12)[0]
    blob = extension + 20
    text_offset = blob + 212
    text_size = u32(data, blob + 208)
    if (u32(data) != len(data) or extension < 64 or u32(data, extension) != len(data) - extension
            or text_size < 2 or text_size % 2 or text_offset + text_size + 8 != len(data)):
        raise ValueError("버튼의 객체·확장·문구·후미 길이 관계 불일치")
    # 알려진 다른 섹션이 변경할 문자열 뒤에 있으면 위치 재배치가 필요하므로 거부한다.
    offsets = {str(p): struct.unpack_from("<H", data, p)[0] for p in (4, 6, 12, 14, 36, 38, 40, 62)}
    offsets.update({str(p): u32(data, p) for p in (54, 58)})
    if any(value >= text_offset for value in offsets.values()):
        raise ValueError("문구 뒤에 다른 객체 섹션이 있어 안전한 후미 확장 범위를 벗어남")
    source, end = utf16z(data, text_offset)
    if end > text_offset + text_size or any(data[end:text_offset + text_size]):
        raise ValueError("문구 슬롯의 NUL 뒤에 해석하지 않은 데이터가 있음")
    return {"block": block, "data": data, "extension_offset": extension, "blob_offset": blob,
            "text_offset": text_offset, "text_size": text_size, "source": source, "section_offsets": offsets}


def patch_button_text(dat, handle, source, translated):
    info = inspect_button(dat, handle)
    if info["source"] != source or "\0" in translated:
        raise ValueError("기대 버튼 원문 불일치 또는 번역 안의 NUL 문자")
    data = info["data"]
    encoded = translated.encode("utf-16le") + b"\0\0"
    result = bytearray(data[:info["text_offset"]] + encoded + data[-8:])
    struct.pack_into("<I", result, 0, len(result))
    struct.pack_into("<I", result, info["extension_offset"], len(result) - info["extension_offset"])
    struct.pack_into("<I", result, info["blob_offset"] + 208, len(encoded))
    info["block"].replacement = bytes(result)
    verified = inspect_button(dat, handle)
    assert verified["source"] == translated and verified["section_offsets"] == info["section_offsets"]
    assert verified["data"][-8:] == data[-8:]
    return {"handle": handle, "before_bytes": len(data), "after_bytes": len(result),
            "text_before_bytes": info["text_size"], "text_after_bytes": len(encoded),
            "changed_size_fields": [0, info["extension_offset"], info["blob_offset"] + 208],
            "section_offsets_unchanged": info["section_offsets"], "tail_8_unchanged": True}
