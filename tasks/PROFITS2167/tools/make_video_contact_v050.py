#!/usr/bin/env python3
"""추출한 튜토리얼 영상에서 대표 프레임과 검수표를 만든다."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    rows = [row for row in json.loads(args.manifest.read_text(encoding="utf-8")) if row["type"] == "VideoClip"]
    frames: list[tuple[str, Path]] = []
    for row in rows:
        duration = float(row["frames"]) / float(row["frame_rate"])
        source = Path(str(row["output"]))
        for percent in (0.2, 0.5, 0.8):
            timestamp = max(0.0, min(duration - 0.05, duration * percent))
            output = args.output / f"{row['name']}-{int(percent * 100):02d}.png"
            result = subprocess.run(
                [
                    str(args.ffmpeg),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{timestamp:.3f}",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(f"대표 프레임 추출 실패: {source}\n{result.stderr}")
            frames.append((f"{row['name']} {int(percent * 100)}%", output))

    thumb_width = 320
    thumb_height = 180
    label_height = 28
    columns = 4
    sheet_rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (thumb_width * columns, (thumb_height + label_height) * sheet_rows), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for index, (label, path) in enumerate(frames):
        image = Image.open(path).convert("RGB")
        image.thumbnail((thumb_width, thumb_height))
        cell_x = (index % columns) * thumb_width
        cell_y = (index // columns) * (thumb_height + label_height)
        x = cell_x + (thumb_width - image.width) // 2
        y = cell_y + (thumb_height - image.height) // 2
        sheet.paste(image, (x, y))
        draw.text((cell_x + 5, cell_y + thumb_height + 4), label, fill="white")
    sheet_path = args.output / "tutorial_videos_contact.png"
    sheet.save(sheet_path)
    print(json.dumps({"videos": len(rows), "frames": len(frames), "contact_sheet": str(sheet_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
