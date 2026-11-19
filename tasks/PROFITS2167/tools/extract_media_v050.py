#!/usr/bin/env python3
"""튜토리얼 이미지와 영상을 비공개 검수 폴더로 추출한다."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import UnityPy


IMAGE_NAME = re.compile(r"(?:tutor|tutorial|brief|settings|level select|exit|logo)", re.I)


def safe_name(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z가-힣._ -]+", "_", value).strip(" .")
    return value or "unnamed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []
    for asset_name in ("resources.assets", "sharedassets0.assets"):
        asset_path = args.data_root / asset_name
        env = UnityPy.load(str(asset_path))
        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()
                name = str(data.m_Name)
                if not IMAGE_NAME.search(name):
                    continue
                output = args.output / "images" / f"{asset_name}-{obj.path_id}-{safe_name(name)}.png"
                output.parent.mkdir(parents=True, exist_ok=True)
                data.image.save(output)
                manifest.append(
                    {
                        "asset": asset_name,
                        "path_id": int(obj.path_id),
                        "type": "Texture2D",
                        "name": name,
                        "width": int(data.m_Width),
                        "height": int(data.m_Height),
                        "output": str(output),
                    }
                )
            elif obj.type.name == "VideoClip":
                data = obj.read()
                resource = data.m_ExternalResources
                stream_path = args.data_root / str(resource.m_Source)
                output = args.output / "videos" / f"{asset_name}-{obj.path_id}-{safe_name(str(data.m_Name))}.m4v"
                output.parent.mkdir(parents=True, exist_ok=True)
                with stream_path.open("rb") as stream:
                    stream.seek(int(resource.m_Offset))
                    payload = stream.read(int(resource.m_Size))
                if len(payload) != int(resource.m_Size):
                    raise RuntimeError(f"영상 스트림 길이 불일치: {data.m_Name}")
                output.write_bytes(payload)
                manifest.append(
                    {
                        "asset": asset_name,
                        "path_id": int(obj.path_id),
                        "type": "VideoClip",
                        "name": str(data.m_Name),
                        "width": int(data.Width),
                        "height": int(data.Height),
                        "frames": int(data.m_FrameCount),
                        "frame_rate": float(data.m_FrameRate),
                        "offset": int(resource.m_Offset),
                        "size": int(resource.m_Size),
                        "stream": str(resource.m_Source),
                        "output": str(output),
                    }
                )

    manifest_path = args.output / "media_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "images": sum(row["type"] == "Texture2D" for row in manifest),
                "videos": sum(row["type"] == "VideoClip" for row in manifest),
                "manifest": str(manifest_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
