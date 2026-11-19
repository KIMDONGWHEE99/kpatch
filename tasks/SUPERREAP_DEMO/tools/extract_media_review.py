#!/usr/bin/env python3
"""검수용 Sprite/Texture2D 미리보기와 연락 시트(contact sheet)를 만든다."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any


NAME_HINT_RE = re.compile(
    r"(?:logo|title|menu|button|btn|start|exit|setting|demo|wishlist|steam|"
    r"credit|language|english|chinese|新游戏|开始|设置|退出|制作|愿望|文字|字体|标题|按钮)",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--python-packages", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("candidates", "all"), default="candidates")
    parser.add_argument("--items-per-sheet", type=int, default=60)
    return parser.parse_args()


def safe_label(text: str, limit: int = 38) -> str:
    text = text.replace("\r", " ").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def is_candidate(name: str, width: int, height: int) -> bool:
    if NAME_HINT_RE.search(name):
        return True
    if width >= 64 and height >= 16 and width / max(1, height) >= 2.4:
        return True
    return False


def main() -> None:
    args = parse_args()
    sys.path.insert(0, str(args.python_packages.resolve()))
    import UnityPy  # type: ignore
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    file_rows = [row for row in inventory["files"] if row.get("media")]
    args.out.mkdir(parents=True, exist_ok=True)
    images_dir = args.out / "images"
    sheets_dir = args.out / "sheets"
    images_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    unique: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    skipped_empty_atlases: list[dict[str, str]] = []
    sequence = 0

    for file_row in file_rows:
        relative = file_row["relative_path"]
        source_path = args.data_root / Path(relative)
        try:
            env = UnityPy.load(str(source_path))
            for obj in env.objects:
                if obj.type.name not in {"Sprite", "Texture2D"}:
                    continue
                try:
                    data = obj.read()
                    name = str(getattr(data, "m_Name", "") or getattr(data, "name", ""))
                    declared_width = int(getattr(data, "m_Width", 0) or 0)
                    declared_height = int(getattr(data, "m_Height", 0) or 0)
                    if (
                        obj.type.name == "Texture2D"
                        and declared_width == 0
                        and declared_height == 0
                    ):
                        skipped_empty_atlases.append(
                            {
                                "file": relative,
                                "path_id": str(obj.path_id),
                                "name": name,
                                "classification": "INTERNAL",
                                "reason": "픽셀이 없는 런타임 글꼴 아틀라스 자리표시자",
                            }
                        )
                        continue
                    image = data.image
                    width, height = image.size
                    if args.mode == "candidates" and not is_candidate(name, width, height):
                        continue
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    png = buffer.getvalue()
                    digest = hashlib.sha256(png).hexdigest()
                    ref = {
                        "file": relative,
                        "path_id": int(obj.path_id),
                        "object_type": obj.type.name,
                        "name": name,
                    }
                    if digest in unique:
                        unique[digest]["references"].append(ref)
                        continue
                    sequence += 1
                    file_name = f"{sequence:04d}_{digest[:12]}.png"
                    output_path = images_dir / file_name
                    output_path.write_bytes(png)
                    unique[digest] = {
                        "index": sequence,
                        "sha256": digest,
                        "width": width,
                        "height": height,
                        "preview": output_path.relative_to(args.out).as_posix(),
                        "references": [ref],
                    }
                except Exception as exc:  # 개별 이미지 실패가 전체 조사를 막지 않게 기록한다.
                    stream = getattr(locals().get("data", None), "m_StreamData", None)
                    inline_data = getattr(locals().get("data", None), "m_ImageData", b"")
                    errors.append(
                        {
                            "file": relative,
                            "path_id": str(obj.path_id),
                            "object_type": obj.type.name,
                            "name": str(getattr(locals().get("data", None), "m_Name", "")),
                            "width": str(getattr(locals().get("data", None), "m_Width", "")),
                            "height": str(getattr(locals().get("data", None), "m_Height", "")),
                            "stream_path": str(getattr(stream, "path", "")),
                            "stream_offset": str(getattr(stream, "offset", "")),
                            "stream_size": str(getattr(stream, "size", "")),
                            "inline_size": str(len(inline_data) if inline_data is not None else ""),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        except Exception as exc:
            errors.append(
                {
                    "file": relative,
                    "path_id": "",
                    "object_type": "container",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    items = sorted(unique.values(), key=lambda row: row["index"])
    font = ImageFont.load_default()
    cell_width, cell_height = 220, 170
    thumb_width, thumb_height = 204, 128
    columns = 5
    per_sheet = max(columns, args.items_per_sheet)
    rows_per_sheet = (per_sheet + columns - 1) // columns

    for page_start in range(0, len(items), per_sheet):
        page_items = items[page_start : page_start + per_sheet]
        sheet = Image.new(
            "RGBA", (cell_width * columns, cell_height * rows_per_sheet), "#242424"
        )
        draw = ImageDraw.Draw(sheet)
        for slot, item in enumerate(page_items):
            x = (slot % columns) * cell_width
            y = (slot // columns) * cell_height
            preview = Image.open(args.out / item["preview"]).convert("RGBA")
            preview.thumbnail((thumb_width, thumb_height))
            px = x + (cell_width - preview.width) // 2
            py = y + 2 + (thumb_height - preview.height) // 2
            checker = Image.new("RGBA", (thumb_width, thumb_height), "#6a6a6a")
            sheet.alpha_composite(checker, (x + 8, y + 2))
            sheet.alpha_composite(preview, (px, py))
            ref = item["references"][0]
            label = f"#{item['index']:04d} {item['width']}x{item['height']} {safe_label(ref['name'])}"
            draw.text((x + 8, y + 134), label, fill="white", font=font)
            draw.text(
                (x + 8, y + 150),
                safe_label(Path(ref["file"]).name, 32),
                fill="#bdbdbd",
                font=font,
            )
        page_number = page_start // per_sheet + 1
        sheet.convert("RGB").save(sheets_dir / f"sheet_{page_number:03d}.jpg", quality=90)

    report = {
        "mode": args.mode,
        "unique_images": len(items),
        "duplicate_references": sum(len(item["references"]) - 1 for item in items),
        "sheet_count": (len(items) + per_sheet - 1) // per_sheet,
        "skipped_empty_atlases": skipped_empty_atlases,
        "errors": errors,
        "items": items,
    }
    (args.out / "index.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "unique_images": report["unique_images"],
                "duplicate_references": report["duplicate_references"],
                "sheet_count": report["sheet_count"],
                "errors": len(errors),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
