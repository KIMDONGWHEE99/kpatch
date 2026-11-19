"""확장 객체의 실제 바이트 위치와 이미지 검수판을 비공개 폴더에 만듭니다."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
from dat_container import DatFile, utf16z


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("semantic", type=Path)
    ap.add_argument("images", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--skip-images", action="store_true")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    dat = DatFile.load(args.source)
    source_hash = digest(dat.original)
    package = json.loads((args.semantic / "package.json").read_text(encoding="utf-8-sig"))
    blobs = json.loads((args.semantic / "extension_blobs.json").read_text(encoding="utf-8-sig"))
    entries, failures, containers = [], [], []
    for record in blobs:
        handle = record["handle"]
        obj = package["FrameItems"]["Items"][str(handle)]
        raw = dat.objects[handle].decoded
        data = (args.semantic / record["path"]).read_bytes()
        extension_offset = struct.unpack_from("<H", raw, 12)[0]
        blob_offset = extension_offset + 20
        assert data == raw[blob_offset:blob_offset + len(data)]
        containers.append({**record, "object_type": obj["Header"]["Type"], "object_decoded_sha256": digest(raw), "object_offset": blob_offset, "source_sha256": source_hash})
        known = []
        def add(kind, offset, value, slot_bytes, evidence):
            entries.append({"id": f"object:{handle}/extension/{kind}@{offset}", "kind": kind, "object_handle": handle,
                "object_name": obj["Name"], "object_type": obj["Header"]["Type"], "source": value,
                "source_sha256": source_hash, "original_value_sha256": digest(value.encode("utf-16le")),
                "blob_sha256": digest(data), "object_decoded_sha256": digest(raw), "blob_offset": offset,
                "object_offset": blob_offset + offset, "slot_bytes": slot_bytes, "classification": "UNKNOWN", "evidence": evidence})
            known.append((offset, offset + slot_bytes))
        if obj["Header"]["Type"] == 32:
            try:
                font, _ = utf16z(data, 64)
                text_size = struct.unpack_from("<I", data, 208)[0]
                assert text_size >= 2 and text_size % 2 == 0 and len(data) == 212 + text_size + 8
                text, end = utf16z(data, 212)
                assert end == 212 + text_size
                add("button_font", 64, font, 64, "LOGFONTW 모양과 모든 KcBoxA 객체의 동일 필드 경계; 네이티브 사용 참조는 후속 확인")
                add("button_text", 212, text, text_size, "208의 길이값·UTF-16 NUL·뒤 8바이트 경계를 모든 KcBoxA 객체에서 확인")
            except Exception as ex:
                failures.append({"handle": handle, "stage": "button_layout", "error": str(ex), "status": "UNKNOWN"})
        elif obj["Header"]["Type"] == 35:
            value, end = utf16z(data, 2)
            add("ini_default_path", 2, value, 520, "kcini 객체의 2바이트 flags 뒤 경로(추정); 실제 읽기·쓰기 참조는 후속 확인")
        for match in re.finditer(rb"(?:[\x20-\x7e]\x00){2,}", data):
            offset, end = match.span()
            if any(a <= offset and end <= b for a, b in known):
                continue
            add("utf16_candidate", offset, match.group().decode("utf-16le"), end - offset, "바이트 검색 후보이며 표시 문자열·구조값 여부는 미분류")
    with (args.output / "extension_inventory.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    (args.output / "extension_containers.json").write_text(json.dumps(containers, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "errors.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.skip_images:
        print(json.dumps({"entries": len(entries), "containers": len(containers), "errors": len(failures)}))
        return
    media = json.loads((args.images / "media.json").read_text(encoding="utf-8-sig"))
    groups = {}
    for item in media:
        groups.setdefault(item["source_sha256"], []).append(item)
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    sheets = []
    sorted_groups = sorted(groups.values(), key=lambda x: x[0]["handle"])
    cell_w, cell_h, cols, rows = 144, 134, 8, 8
    for page_start in range(0, len(sorted_groups), cols * rows):
        canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), (40, 44, 49))
        draw = ImageDraw.Draw(canvas)
        references = []
        for slot, group in enumerate(sorted_groups[page_start:page_start + cols * rows]):
            item = group[0]
            im = Image.open(args.images / item["path"]).convert("RGBA")
            im.thumbnail((136, 108), Image.Resampling.LANCZOS)
            x, y = slot % cols * cell_w, slot // cols * cell_h
            canvas.paste(im, (x + (cell_w - im.width) // 2, y + 3), im)
            label = f"#{item['handle']} {item['Width']}x{item['Height']} n={len(group)}"
            draw.text((x + 3, y + 113), label, font=font, fill="white")
            references.append({"slot": slot, "handles": [x["handle"] for x in group], "source_sha256": item["source_sha256"], "image_path": str((args.images / item["path"]).resolve())})
        path = args.output / f"contact_{page_start // (cols * rows):02d}.png"
        canvas.save(path)
        sheets.append({"path": path.name, "sha256": digest(path.read_bytes()), "items": references, "review": "NOT_RUN"})
    (args.output / "contact_index.json").write_text(json.dumps(sheets, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"source_sha256": source_hash, "extension_containers": len(containers), "extension_strings": len(entries), "extension_errors": len(failures),
        "images": len(media), "unique_source_images": len(groups), "contact_sheets": len(sheets), "visual_review": "NOT_RUN"}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
