"""Soulash 2 이미지 목록과 육안 검수판을 만든다. 원본 이미지는 수정하지 않는다."""
import argparse
import hashlib
import json
import math
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
from PIL import Image, ImageDraw, ImageFile, ImageFont

SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
OUTPUT = ROOT / "working_private/SOULASH_2/media_review"
IMAGE_EXTENSIONS = {".png", ".gif", ".jpg", ".jpeg", ".bmp", ".tga", ".webp", ".dds", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".webm", ".ogv", ".mov", ".mkv"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def png_crc_errors(path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return []
    offset, errors = 8, []
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        recorded = struct.unpack_from(">I", data, offset + 8 + length)[0]
        observed = zlib.crc32(kind + payload) & 0xFFFFFFFF
        if recorded != observed:
            errors.append({"offset": offset, "type": kind.decode("ascii"), "recorded": hex(recorded), "observed": hex(observed)})
        offset += 12 + length
    return errors


def open_image(path, crc_errors):
    # 알려진 손상 색상 프로필의 체크섬만 무시한다. 중요 픽셀 청크 손상은 허용하지 않는다.
    if crc_errors and any(e["type"] != "iCCP" for e in crc_errors):
        raise RuntimeError("픽셀 또는 구조 청크의 체크섬 불일치: " + str(path))
    ImageFile.LOAD_TRUNCATED_IMAGES = bool(crc_errors)
    im = Image.open(path)
    im.load()
    return im


def decorate(image, target):
    image = image.convert("RGBA")
    if image.width <= target[0] and image.height <= target[1]:
        scale = min(4, target[0] // image.width, target[1] // image.height)
        image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    else:
        image.thumbnail(target, Image.Resampling.LANCZOS)
    background = Image.new("RGB", image.size, (57, 60, 65))
    background.paste(image, mask=image.getchannel("A"))
    return background


def contact_sheets(items, prefix, columns=4, rows=4, cell=(320, 250), image_box=(304, 198)):
    pages = []
    label_font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 13)
    for start in range(0, len(items), columns * rows):
        group = items[start:start + columns * rows]
        page_number = len(pages) + 1
        sheet = Image.new("RGB", (columns * cell[0], rows * cell[1]), (27, 29, 33))
        draw = ImageDraw.Draw(sheet)
        for j, item in enumerate(group):
            x, y = (j % columns) * cell[0], (j // columns) * cell[1]
            thumb = decorate(item["image"], image_box)
            sheet.paste(thumb, (x + (cell[0] - thumb.width) // 2, y + 4 + (image_box[1] - thumb.height) // 2))
            draw.text((x + 5, y + image_box[1] + 9), item["id"], font=label_font, fill=(255, 235, 155))
            draw.text((x + 5, y + image_box[1] + 27), item["label"][-39:], font=label_font, fill=(230, 230, 230))
        name = f"{prefix}_{page_number:02d}.png"
        path = OUTPUT / name
        sheet.save(path)
        pages.append({"page": name, "sha256": sha(path), "items": [x["id"] for x in group], "review_status": "NOT_RUN"})
    return pages


def main():
    if OUTPUT.exists():
        raise RuntimeError("기존 검수 결과를 덮어쓰지 않습니다.")
    OUTPUT.mkdir(parents=True)
    all_files = sorted(p for p in SOURCE.rglob("*") if p.is_file())
    images = [p for p in all_files if p.suffix.lower() in IMAGE_EXTENSIONS]
    files, by_hash, unique = [], {}, []
    error_records = []
    thumbnail_items, gif_items, detail_items = [], [], []
    for path in images:
        relative, digest = path.relative_to(SOURCE).as_posix(), sha(path)
        occurrence = {"path": relative, "sha256": digest, "size": path.stat().st_size}
        files.append(occurrence)
        if digest in by_hash:
            by_hash[digest]["paths"].append(relative)
            continue
        identity = f"I{len(unique) + 1:03d}"
        errors = png_crc_errors(path)
        record = {"id": identity, "sha256": digest, "paths": [relative], "classification": "MEDIA", "treatment": "UNKNOWN", "evidence": [], "crc_errors": errors}
        by_hash[digest] = record
        unique.append(record)
        try:
            with open_image(path, errors) as im:
                record.update({"width": im.width, "height": im.height, "format": im.format, "mode": im.mode, "frame_count": getattr(im, "n_frames", 1)})
                if errors:
                    error_records.append({"id": identity, "source_sha256": digest, "error": "Pillow 엄격 읽기에서 색상 프로필 iCCP 체크섬 오류", "resolution": "픽셀 청크가 아닌 iCCP의 체크섬만 무시함. IDAT/IHDR을 포함한 다른 모든 청크의 체크섬 일치와 전체 픽셀 해석 성공을 확인함. 원본은 변경하지 않음.", "status": "PASS", "crc_errors": errors})
                frame = im.convert("RGBA")
                thumbnail_items.append({"id": identity, "label": relative, "image": frame})
                if record["frame_count"] > 1:
                    for frame_index in range(record["frame_count"]):
                        im.seek(frame_index)
                        gif_items.append({"id": f"{identity} F{frame_index:03d}", "label": relative, "image": im.convert("RGBA")})
                # 게임 이미지가 검수판에서 축소되면 픽셀 크기 조각으로 추가 확인한다.
                if not relative.startswith("data/docs/") and (im.width > 400 or im.height > 300):
                    for y in range(0, frame.height, 450):
                        for x in range(0, frame.width, 450):
                            crop = frame.crop((x, y, min(x + 450, frame.width), min(y + 450, frame.height)))
                            detail_items.append({"id": f"{identity} ({x},{y})", "label": relative, "image": crop})
                record["decode_status"] = "PASS"
        except Exception as error:
            record["decode_status"], record["decode_error"] = "FAIL", repr(error)
            error_records.append({"id": identity, "source_sha256": digest, "error": repr(error), "status": "FAIL"})
    overview_pages = contact_sheets(thumbnail_items, "overview")
    detail_pages = contact_sheets(detail_items, "detail", columns=2, rows=2, cell=(470, 500), image_box=(450, 450))
    gif_pages = contact_sheets(gif_items, "gif")
    audio_headers = []
    for path in all_files:
        if path.suffix.lower() == ".ogg":
            prefix = path.read_bytes()[:4096]
            audio_headers.append({"path": path.relative_to(SOURCE).as_posix(), "signature": "vorbis" if b"\x01vorbis" in prefix else "theora" if b"\x80theora" in prefix else "UNKNOWN"})
    report = {"game_id": "SOULASH_2", "baseline_id": SOURCE.name, "created": datetime.now(timezone.utc).isoformat(), "script_sha256": sha(Path(__file__)),
              "file_count": len(files), "unique_hash_count": len(unique), "decoded_unique_count": len(thumbnail_items), "files": files, "unique": unique,
              "overview_pages": overview_pages, "detail_pages": detail_pages, "gif_pages": gif_pages, "gif_frame_count": len(gif_items),
              "extraction_errors": error_records, "videos_by_extension": [p.relative_to(SOURCE).as_posix() for p in all_files if p.suffix.lower() in VIDEO_EXTENSIONS],
              "ogg_signatures": audio_headers, "review_status": "NOT_RUN"}
    write_json(OUTPUT / "catalog.json", report)
    print(json.dumps({k: report[k] for k in ("file_count", "unique_hash_count", "decoded_unique_count", "gif_frame_count")}, ensure_ascii=False))
    print(json.dumps({"overview_pages": len(overview_pages), "detail_pages": len(detail_pages), "gif_pages": len(gif_pages), "extraction_errors": len(error_records)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    OUTPUT = parser.parse_args().output.resolve()
    OUTPUT.relative_to((ROOT / "working_private/SOULASH_2").resolve())
    main()
