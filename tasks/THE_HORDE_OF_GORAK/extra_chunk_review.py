"""추가 앱 청크와 표준 Windows 대화상자를 원본 위치별로 판독합니다."""
from __future__ import annotations
import json
import struct
from pathlib import Path
from dat_container import DatFile, sha, utf16z, u32

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"


def parse_player_controls(data):
    """문자열 표와 대화상자 표의 상대 주소를 각각 독립 검증합니다."""
    version, string_table, dialog_table = struct.unpack_from("<III", data)
    assert version == 1 and string_table == 12
    strings, dialogs = [], []
    count = u32(data, string_table)
    string_base = string_table + 4 + count * 8
    for index in range(count):
        ident, relative = struct.unpack_from("<II", data, string_table + 4 + index * 8)
        offset = string_base + relative
        value, end = utf16z(data, offset)
        assert end <= dialog_table
        strings.append({"kind": "control_key_name", "id": ident, "offset": offset,
                        "slot_bytes": end - offset, "source": value,
                        "classification": "VISIBLE_TRANSLATE"})
    count = u32(data, dialog_table)
    base = dialog_table + 4 + count * 8

    def field(offset, kind, context):
        first = struct.unpack_from("<H", data, offset)[0]
        if first == 0xffff:
            return {"ordinal": struct.unpack_from("<H", data, offset + 2)[0]}, offset + 4
        value, end = utf16z(data, offset)
        strings.append({"kind": kind, **context, "offset": offset, "slot_bytes": end - offset,
                        "source": value,
                        "classification": "INTERNAL" if kind in ("dialog_class", "dialog_menu", "dialog_font")
                        else "VISIBLE_TRANSLATE"})
        return value, end

    for index in range(count):
        ident, relative = struct.unpack_from("<II", data, dialog_table + 4 + index * 8)
        position = start = base + relative
        limit = base + u32(data, dialog_table + 4 + (index + 1) * 8 + 4) if index + 1 < count else len(data)
        style, ex_style, controls, x, y, width, height = struct.unpack_from("<IIHhhhh", data, position)
        assert style & 0xffff != 0xffff
        position += 18
        context = {"dialog_id": ident}
        menu, position = field(position, "dialog_menu", context)
        window_class, position = field(position, "dialog_class", context)
        title, position = field(position, "dialog_title", context)
        font = None
        if style & 0x40:
            points = struct.unpack_from("<H", data, position)[0]
            face, position = field(position + 2, "dialog_font", context)
            font = {"points": points, "face": face}
        items = []
        for item_index in range(controls):
            position = (position + 3) & ~3
            item_offset = position
            item_style, item_ex_style, ix, iy, iw, ih, item_id = struct.unpack_from("<IIhhhhH", data, position)
            position += 18
            item_context = {"dialog_id": ident, "item_index": item_index, "item_id": item_id}
            item_class, position = field(position, "dialog_class", item_context)
            item_title, position = field(position, "dialog_item_title", item_context)
            extra_size = struct.unpack_from("<H", data, position)[0]
            position += extra_size or 2
            assert position <= limit
            items.append({"index": item_index, "id": item_id, "offset": item_offset,
                          "class": item_class, "title": item_title,
                          "style": item_style, "ex_style": item_ex_style,
                          "x": ix, "y": iy, "width": iw, "height": ih, "extra_bytes": extra_size})
        assert limit - position < 4 and not any(data[position:limit])
        dialogs.append({"id": ident, "offset": start, "size": limit - start,
                        "style": style, "ex_style": ex_style, "menu": menu, "class": window_class,
                        "title": title, "font": font, "x": x, "y": y,
                        "width": width, "height": height, "controls": items})
    return {"version": version, "strings": strings, "dialogs": dialogs,
            "string_table_offset": string_table, "dialog_table_offset": dialog_table}


def main():
    dat = DatFile.load(SOURCE)
    chunk = dat.one(0x225d)
    controls = parse_player_controls(chunk.decoded)
    for row in controls["strings"]:
        row.update(target=chunk.location, source_file_sha256=sha(dat.original),
                   source_container_sha256=sha(chunk.decoded),
                   source_text_sha256=sha(row["source"].encode("utf-16le")))
    controls["evidence"] = {
        "loader": "THOG RVA0x21e8 -> app+0x438",
        "dialog_dispatch": "THOG RVA0x5b090: app+0x438, table+8, count/ID/relativeOffset -> DialogBoxIndirectParamW",
        "native_evidence": "thog_chunk_handlers_disasm.json; thog_dialog_dispatch_disasm.json",
        "format_reference": ["https://learn.microsoft.com/windows/win32/api/winuser/ns-winuser-dlgtemplate",
                             "https://learn.microsoft.com/windows/win32/api/winuser/ns-winuser-dlgitemtemplate"],
        "status": "PASS", "scope": "구조/위치별 추출; 실제 화면 검수는 별도"}
    (OUT / "player_controls_225d.json").write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"dialogs": len(controls["dialogs"]), "controls": sum(len(x["controls"]) for x in controls["dialogs"]),
                      "strings": len(controls["strings"]), "visible_nonempty": sum(bool(x["source"]) and x["classification"] == "VISIBLE_TRANSLATE" for x in controls["strings"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
