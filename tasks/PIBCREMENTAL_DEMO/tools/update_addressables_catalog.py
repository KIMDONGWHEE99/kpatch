from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_all(data: bytes, needle: bytes) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        position = data.find(needle, start)
        if position < 0:
            return positions
        positions.append(position)
        start = position + 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Addressables 이진 카탈로그의 로컬 묶음 검사값 수정")
    parser.add_argument("--source-catalog", type=Path, required=True)
    parser.add_argument("--source-bundle-dir", type=Path, required=True)
    parser.add_argument("--overlay-bundle-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source_data = args.source_catalog.read_bytes()
    output_data = bytearray(source_data)
    overlay_files = sorted(args.overlay_bundle_dir.glob("*.bundle"), key=lambda path: path.name.casefold())
    if not overlay_files:
        raise RuntimeError("수정된 Addressables 묶음 파일이 없습니다.")

    rows: list[dict[str, Any]] = []
    used_positions: set[int] = set()
    for overlay in overlay_files:
        source_bundle = args.source_bundle_dir / overlay.name
        if not source_bundle.is_file():
            raise FileNotFoundError(f"원본 Addressables 묶음이 없습니다: {overlay.name}")
        old_size = source_bundle.stat().st_size
        new_size = overlay.stat().st_size
        if old_size > 0xFFFFFFFF or new_size > 0xFFFFFFFF:
            raise RuntimeError(f"묶음 크기가 32비트 범위를 벗어납니다: {overlay.name}")

        matches = find_all(source_data, struct.pack("<I", old_size))
        # AssetBundleRequestOptions.SerializedData는 hashId, bundleNameId, crc,
        # bundleSize, commonId 순서의 32비트 값이다. 파일 크기 앞뒤의 세 참조가
        # 실제 카탈로그 범위에 있어야 후보로 인정한다.
        candidates: list[int] = []
        for position in matches:
            if position < 12 or position + 8 > len(source_data):
                continue
            hash_id, bundle_name_id, _, stored_size, common_id = struct.unpack_from(
                "<IIIII", source_data, position - 12
            )
            if stored_size != old_size:
                continue
            if all(0 < value < len(source_data) for value in (hash_id, bundle_name_id, common_id)):
                candidates.append(position)
        if len(candidates) != 1:
            raise RuntimeError(
                f"카탈로그에서 {overlay.name}의 묶음 옵션 위치를 하나로 결정하지 못했습니다: "
                f"크기 일치 {len(matches)}, 유효 후보 {len(candidates)}"
            )
        position = candidates[0]
        if position in used_positions:
            raise RuntimeError(f"카탈로그 옵션 위치가 중복되었습니다: {overlay.name}")
        used_positions.add(position)
        old_crc = struct.unpack_from("<I", source_data, position - 4)[0]

        # Unity AssetBundle CRC는 일반 파일 CRC32와 다르므로 재계산할 수 없다.
        # 로컬 수정 묶음만 0으로 설정해 Unity가 제공하는 CRC 검사 생략 경로를 쓴다.
        struct.pack_into("<I", output_data, position - 4, 0)
        struct.pack_into("<I", output_data, position, new_size)
        rows.append(
            {
                "file": overlay.name,
                "option_offset": position - 12,
                "old_crc": old_crc,
                "new_crc": 0,
                "old_size": old_size,
                "new_size": new_size,
                "modified_file_crc32": zlib.crc32(overlay.read_bytes()) & 0xFFFFFFFF,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_data)
    reopened = args.output.read_bytes()
    if len(reopened) != len(source_data):
        raise RuntimeError("이진 카탈로그 길이가 바뀌었습니다.")
    for row in rows:
        position = int(row["option_offset"]) + 12
        crc = struct.unpack_from("<I", reopened, position - 4)[0]
        size = struct.unpack_from("<I", reopened, position)[0]
        if crc != 0 or size != row["new_size"]:
            raise RuntimeError(f"수정 카탈로그 재검사 실패: {row['file']}")

    report = {
        "schema_version": 1,
        "source_catalog": str(args.source_catalog),
        "output_catalog": str(args.output),
        "catalog_size_preserved": len(source_data) == len(reopened),
        "source_sha256": sha256(source_data),
        "output_sha256": sha256(reopened),
        "modified_bundle_count": len(rows),
        "modified_bundles": rows,
        "reopened": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
