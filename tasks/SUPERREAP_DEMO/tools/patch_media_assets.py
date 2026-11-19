#!/usr/bin/env python3
"""ImageGen 기반 한글 스프라이트를 실제 Unity Texture2D에 주입하고 검증한다."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import UnityPy
from PIL import Image, ImageChops, ImageStat


TARGETS = [
    {
        "file": "sharedassets0.assets",
        "path_id": 105,
        "image": "new_badge_ko.png",
        "label": "가방 새 배지(기본 자산)",
    },
    {
        "file": "sharedassets0.assets",
        "path_id": 331,
        "image": "settings_ko.png",
        "label": "설정 버튼(기본 자산)",
    },
    {
        "file": "StreamingAssets/yoo/DefaultPackage/724fd7887af016644d655d57fbc7ee9f.bundle",
        "path_id": 7568154705151158573,
        "image": "new_badge_ko.png",
        "label": "가방 새 배지(YooAsset)",
    },
    {
        "file": "StreamingAssets/yoo/DefaultPackage/dfa99baf3020132933558a01994b8a9c.bundle",
        "path_id": 8940992715402494823,
        "image": "settings_ko.png",
        "label": "설정 버튼(YooAsset)",
    },
    {
        "file": "StreamingAssets/yoo/DefaultPackage/9578efb46f5c6523c9cbdb8188e5ae74.bundle",
        "path_id": 742611586594813104,
        "image": "slot_ko.png",
        "label": "행운 룰렛 슬롯머신",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--patched-root", type=Path, required=True)
    parser.add_argument("--media-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_environment(env: Any) -> bytes:
    return env.file.save(packer="original")


def main() -> None:
    args = parse_args()
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in TARGETS:
        by_file[str(target["file"])].append(target)

    report_files = []
    for relative, targets in sorted(by_file.items(), key=lambda item: item[0].casefold()):
        output_path = args.patched_root / Path(relative)
        input_path = output_path if output_path.is_file() else args.source_root / Path(relative)
        input_bytes = input_path.read_bytes()
        env = UnityPy.load(str(input_path))
        wanted = {int(target["path_id"]): target for target in targets}
        rows = []
        for obj in env.objects:
            if obj.type.name != "Texture2D" or int(obj.path_id) not in wanted:
                continue
            target = wanted.pop(int(obj.path_id))
            value = obj.read()
            image_path = args.media_dir / str(target["image"])
            with Image.open(image_path) as image:
                expected_size = (int(value.m_Width), int(value.m_Height))
                if image.size != expected_size:
                    raise RuntimeError(
                        f"이미지 크기 불일치 {target['label']}: {image.size} / {expected_size}"
                    )
            original_format = int(value.m_TextureFormat)
            original_mips = max(1, int(getattr(value, "m_MipCount", 1) or 1))
            value.set_image(str(image_path), target_format=original_format, mipmap_count=original_mips)
            value.save()
            rows.append(
                {
                    "label": target["label"],
                    "path_id": int(obj.path_id),
                    "image": str(image_path),
                    "width": expected_size[0],
                    "height": expected_size[1],
                    "texture_format": original_format,
                    "mip_count": original_mips,
                }
            )
        if wanted:
            raise RuntimeError(f"Texture2D 누락 {relative}: {sorted(wanted)}")
        output_bytes = save_environment(env)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(output_bytes)

        # 저장 파일을 다시 열어 디코딩 가능 여부와 목표 이미지 오차를 검사한다.
        verify_env = UnityPy.load(str(output_path))
        verify_objects = {
            int(obj.path_id): obj for obj in verify_env.objects if obj.type.name == "Texture2D"
        }
        for row in rows:
            obj = verify_objects[row["path_id"]]
            actual = obj.read().image.convert("RGBA")
            with Image.open(row["image"]) as expected_image:
                expected = expected_image.convert("RGBA")
                if actual.size != expected.size:
                    raise RuntimeError(f"재개방 이미지 크기 불일치: {row['label']}")
                difference = ImageChops.difference(actual, expected)
                row["decoded_mean_absolute_error"] = sum(ImageStat.Stat(difference).mean) / 4.0
                row["decoded"] = True
        report_files.append(
            {
                "file": relative,
                "input": str(input_path),
                "input_size": len(input_bytes),
                "input_sha256": sha256(input_bytes),
                "output_size": len(output_bytes),
                "output_sha256": sha256(output_bytes),
                "textures": rows,
            }
        )

    report = {
        "schema_version": 1,
        "passed": True,
        "modified_files": len(report_files),
        "modified_textures": sum(len(row["textures"]) for row in report_files),
        "files": report_files,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
