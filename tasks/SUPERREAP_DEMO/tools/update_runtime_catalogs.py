#!/usr/bin/env python3
"""수정된 Unity 묶음 파일의 YooAsset/Addressables 목록 정보를 갱신한다."""

from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


YOO_SIGNATURE = 5_853_007
ADDRESSABLE_OPTIONS_MARKER = "{\"m_Hash\"".encode("utf-16-le")


class BinaryReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def take(self, size: int) -> bytes:
        end = self.offset + size
        if end > len(self.data):
            raise ValueError("바이너리 목록을 읽는 중 파일 끝을 벗어났습니다.")
        value = self.data[self.offset:end]
        self.offset = end
        return value

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def utf8(self) -> str:
        return self.take(self.u16()).decode("utf-8")

    def utf8_array(self) -> list[str]:
        return [self.utf8() for _ in range(self.u16())]

    def i32_array(self) -> list[int]:
        return [self.i32() for _ in range(self.u16())]


class BinaryWriter:
    def __init__(self) -> None:
        self.parts: list[bytes] = []

    def add(self, value: bytes) -> None:
        self.parts.append(value)

    def u8(self, value: int) -> None:
        self.add(struct.pack("<B", value))

    def u16(self, value: int) -> None:
        self.add(struct.pack("<H", value))

    def u32(self, value: int) -> None:
        self.add(struct.pack("<I", value))

    def i32(self, value: int) -> None:
        self.add(struct.pack("<i", value))

    def i64(self, value: int) -> None:
        self.add(struct.pack("<q", value))

    def utf8(self, value: str) -> None:
        encoded = value.encode("utf-8")
        self.u16(len(encoded))
        self.add(encoded)

    def utf8_array(self, values: list[str]) -> None:
        self.u16(len(values))
        for value in values:
            self.utf8(value)

    def i32_array(self, values: list[int]) -> None:
        self.u16(len(values))
        for value in values:
            self.i32(value)

    def finish(self) -> bytes:
        return b"".join(self.parts)


@dataclass
class AddressableOption:
    start: int
    end: int
    text: str
    data: dict[str, Any]


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def crc32_file(path: Path) -> int:
    checksum = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum = zlib.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF


def parse_yoo_manifest(data: bytes) -> dict[str, Any]:
    reader = BinaryReader(data)
    signature = reader.u32()
    if signature != YOO_SIGNATURE:
        raise ValueError(f"알 수 없는 YooAsset 서명입니다: {signature}")

    manifest: dict[str, Any] = {
        "signature": signature,
        "file_version": reader.utf8(),
        "enable_addressable": reader.u8(),
        "support_extensionless": reader.u8(),
        "location_to_lower": reader.u8(),
        "include_asset_guid": reader.u8(),
        "output_name_style": reader.i32(),
        "build_bundle_type": reader.i32(),
        "build_pipeline": reader.utf8(),
        "package_name": reader.utf8(),
        "package_version": reader.utf8(),
        "package_note": reader.utf8(),
    }

    assets: list[dict[str, Any]] = []
    for _ in range(reader.i32()):
        assets.append(
            {
                "address": reader.utf8(),
                "asset_path": reader.utf8(),
                "asset_guid": reader.utf8(),
                "tags": reader.utf8_array(),
                "bundle_id": reader.i32(),
                "depend_ids": reader.i32_array(),
            }
        )
    manifest["assets"] = assets

    bundles: list[dict[str, Any]] = []
    for _ in range(reader.i32()):
        bundles.append(
            {
                "bundle_name": reader.utf8(),
                "unity_crc": reader.u32(),
                "file_hash": reader.utf8(),
                "file_crc": reader.u32(),
                "file_size": reader.i64(),
                "encrypted": reader.u8(),
                "tags": reader.utf8_array(),
                "depend_ids": reader.i32_array(),
            }
        )
    manifest["bundles"] = bundles

    if reader.offset != len(data):
        raise ValueError(f"YooAsset 목록 끝에 해석되지 않은 {len(data) - reader.offset}바이트가 있습니다.")
    return manifest


def write_yoo_manifest(manifest: dict[str, Any]) -> bytes:
    writer = BinaryWriter()
    writer.u32(manifest["signature"])
    writer.utf8(manifest["file_version"])
    writer.u8(manifest["enable_addressable"])
    writer.u8(manifest["support_extensionless"])
    writer.u8(manifest["location_to_lower"])
    writer.u8(manifest["include_asset_guid"])
    writer.i32(manifest["output_name_style"])
    writer.i32(manifest["build_bundle_type"])
    writer.utf8(manifest["build_pipeline"])
    writer.utf8(manifest["package_name"])
    writer.utf8(manifest["package_version"])
    writer.utf8(manifest["package_note"])

    writer.i32(len(manifest["assets"]))
    for asset in manifest["assets"]:
        writer.utf8(asset["address"])
        writer.utf8(asset["asset_path"])
        writer.utf8(asset["asset_guid"])
        writer.utf8_array(asset["tags"])
        writer.i32(asset["bundle_id"])
        writer.i32_array(asset["depend_ids"])

    writer.i32(len(manifest["bundles"]))
    for bundle in manifest["bundles"]:
        writer.utf8(bundle["bundle_name"])
        writer.u32(bundle["unity_crc"])
        writer.utf8(bundle["file_hash"])
        writer.u32(bundle["file_crc"])
        writer.i64(bundle["file_size"])
        writer.u8(bundle["encrypted"])
        writer.utf8_array(bundle["tags"])
        writer.i32_array(bundle["depend_ids"])
    return writer.finish()


def yoo_hash(data: bytes) -> str:
    # YooAsset의 BytesCRC32 문자열은 UInt32를 리틀엔디언 바이트 순서로 표시한다.
    return struct.pack("<I", crc32(data)).hex()


def parse_addressable_options(extra_data: bytes) -> list[AddressableOption]:
    options: list[AddressableOption] = []
    cursor = 0
    while True:
        start = extra_data.find(ADDRESSABLE_OPTIONS_MARKER, cursor)
        if start < 0:
            break
        if start < 4:
            raise ValueError("Addressables 옵션 길이 필드가 없습니다.")
        length = struct.unpack("<I", extra_data[start - 4:start])[0]
        end = start + length
        if end > len(extra_data):
            raise ValueError("Addressables 옵션 길이가 데이터 범위를 벗어났습니다.")
        text = extra_data[start:end].decode("utf-16-le")
        data = json.loads(text)
        options.append(AddressableOption(start=start, end=end, text=text, data=data))
        cursor = end
    return options


def replace_addressable_options(
    extra_data: bytes,
    options: list[AddressableOption],
    replacements: dict[int, str],
) -> bytes:
    result = bytearray(extra_data)
    for index in sorted(replacements, reverse=True):
        option = options[index]
        encoded = replacements[index].encode("utf-16-le")
        result[option.start - 4:option.end] = struct.pack("<I", len(encoded)) + encoded
    return bytes(result)


def update_numeric_json_field(text: str, field: str, value: int) -> str:
    pattern = rf'("{re.escape(field)}":)(-?\d+)'

    def replace(match: re.Match[str]) -> str:
        original_number = match.group(2)
        replacement_number = str(value)
        if len(replacement_number) > len(original_number):
            raise ValueError(
                f"Addressables 옵션의 {field} 값을 같은 바이트 길이로 저장할 수 없습니다: "
                f"{original_number} -> {replacement_number}"
            )
        # m_ExtraDataString 내부의 뒤쪽 위치는 m_EntryDataString에 바이트 오프셋으로
        # 기록되어 있다. 숫자가 짧아진 만큼 JSON 허용 공백을 넣어 전체 길이를
        # 보존해야 뒤쪽 ResourceLocationData가 밀리지 않는다.
        return match.group(1) + replacement_number + (" " * (len(original_number) - len(replacement_number)))

    updated, count = re.subn(pattern, replace, text, count=1)
    if count != 1:
        raise ValueError(f"Addressables 옵션에서 {field} 값을 찾지 못했습니다.")
    return updated


def patch_yoo(source_root: Path, overlay_root: Path) -> dict[str, Any]:
    source_dir = source_root / "SuperReap_Data/StreamingAssets/yoo/DefaultPackage"
    overlay_dir = overlay_root / "SuperReap_Data/StreamingAssets/yoo/DefaultPackage"
    manifests = list(source_dir.glob("DefaultPackage_*.bytes"))
    if len(manifests) != 1:
        raise ValueError(f"YooAsset 목록 파일 수가 예상과 다릅니다: {len(manifests)}")
    source_manifest_path = manifests[0]
    source_hash_path = source_manifest_path.with_suffix(".hash")
    source_data = source_manifest_path.read_bytes()
    manifest = parse_yoo_manifest(source_data)
    if write_yoo_manifest(manifest) != source_data:
        raise ValueError("YooAsset 목록 무수정 왕복 결과가 원본과 다릅니다.")
    recorded_hash = source_hash_path.read_text(encoding="utf-8").strip()
    calculated_hash = yoo_hash(source_data)
    if recorded_hash != calculated_hash:
        raise ValueError(f"원본 YooAsset 목록 해시가 맞지 않습니다: {recorded_hash} != {calculated_hash}")

    by_hash = {bundle["file_hash"].lower(): bundle for bundle in manifest["bundles"]}
    changed: list[dict[str, Any]] = []
    overlay_files = sorted(overlay_dir.glob("*.bundle"))
    if not overlay_files:
        raise ValueError("수정된 YooAsset 묶음 파일이 없습니다.")
    for overlay_file in overlay_files:
        file_hash = overlay_file.stem.lower()
        bundle = by_hash.get(file_hash)
        if bundle is None:
            raise ValueError(f"YooAsset 목록에 수정 묶음이 없습니다: {overlay_file.name}")
        source_file = source_dir / overlay_file.name
        if not source_file.is_file():
            raise ValueError(f"원본 YooAsset 묶음이 없습니다: {source_file}")
        source_crc = crc32_file(source_file)
        if bundle["file_crc"] != 0 and source_crc != bundle["file_crc"]:
            raise ValueError(
                f"원본 YooAsset CRC가 맞지 않습니다: {overlay_file.name} "
                f"{source_crc} != {bundle['file_crc']}"
            )
        new_crc = crc32_file(overlay_file)
        new_size = overlay_file.stat().st_size
        # 이 빌드는 모든 묶음의 FileCRC가 0(검사 비활성)이다. 0을 유지해
        # 원래 로딩 정책을 바꾸지 않고, 실제 CRC는 검증 보고서에만 기록한다.
        manifest_crc = bundle["file_crc"]
        changed.append(
            {
                "file": overlay_file.name,
                "old_crc": bundle["file_crc"],
                "new_crc": manifest_crc,
                "actual_source_crc": source_crc,
                "actual_modified_crc": new_crc,
                "old_size": bundle["file_size"],
                "new_size": new_size,
                "file_hash_preserved": bundle["file_hash"],
                "unity_crc_preserved": bundle["unity_crc"],
            }
        )
        bundle["file_crc"] = manifest_crc
        bundle["file_size"] = new_size

    output_data = write_yoo_manifest(manifest)
    output_manifest_path = overlay_dir / source_manifest_path.name
    output_hash_path = overlay_dir / source_hash_path.name
    output_manifest_path.write_bytes(output_data)
    output_hash_path.write_text(yoo_hash(output_data), encoding="utf-8")

    reopened = parse_yoo_manifest(output_manifest_path.read_bytes())
    reopened_by_hash = {bundle["file_hash"].lower(): bundle for bundle in reopened["bundles"]}
    for item in changed:
        bundle = reopened_by_hash[Path(item["file"]).stem.lower()]
        if bundle["file_crc"] != item["new_crc"] or bundle["file_size"] != item["new_size"]:
            raise ValueError(f"저장한 YooAsset 목록 재검사에 실패했습니다: {item['file']}")
    if output_hash_path.read_text(encoding="utf-8") != yoo_hash(output_manifest_path.read_bytes()):
        raise ValueError("저장한 YooAsset 목록 해시 재검사에 실패했습니다.")
    return {
        "source_manifest": str(source_manifest_path),
        "output_manifest": str(output_manifest_path),
        "original_roundtrip_identical": True,
        "original_hash_verified": True,
        "modified_bundle_count": len(changed),
        "modified_bundles": changed,
        "reopened": True,
    }


def patch_addressables(source_root: Path, overlay_root: Path) -> dict[str, Any]:
    relative_catalog = Path("SuperReap_Data/StreamingAssets/aa/catalog.json")
    relative_bundle_dir = Path("SuperReap_Data/StreamingAssets/aa/StandaloneWindows64")
    source_catalog_path = source_root / relative_catalog
    overlay_catalog_path = overlay_root / relative_catalog
    source_bundle_dir = source_root / relative_bundle_dir
    overlay_bundle_dir = overlay_root / relative_bundle_dir

    source_text = source_catalog_path.read_text(encoding="utf-8")
    catalog = json.loads(source_text)
    extra_data = base64.b64decode(catalog["m_ExtraDataString"], validate=True)
    options = parse_addressable_options(extra_data)
    internal_ids = catalog["m_InternalIds"]
    if len(options) != 11:
        raise ValueError(f"Addressables 묶음 옵션 수가 예상과 다릅니다: {len(options)}")

    # 현재 카탈로그에서 첫 11개 내부 경로와 첫 11개 묶음 옵션은 같은 순서다.
    for index, option in enumerate(options):
        filename = internal_ids[index].replace("\\", "/").rsplit("/", 1)[-1]
        source_file = source_bundle_dir / filename
        if not source_file.is_file():
            raise ValueError(f"원본 Addressables 묶음이 없습니다: {filename}")
        actual_size = source_file.stat().st_size
        if actual_size != option.data["m_BundleSize"]:
            raise ValueError(
                f"원본 Addressables 옵션이 파일과 맞지 않습니다: {filename} "
                f"크기 {actual_size}/{option.data['m_BundleSize']}"
            )

    replacements: dict[int, str] = {}
    changed: list[dict[str, Any]] = []
    overlay_files = sorted(overlay_bundle_dir.glob("*.bundle"))
    if not overlay_files:
        raise ValueError("수정된 Addressables 묶음 파일이 없습니다.")
    index_by_name = {
        internal_ids[index].replace("\\", "/").rsplit("/", 1)[-1].lower(): index
        for index in range(len(options))
    }
    for overlay_file in overlay_files:
        index = index_by_name.get(overlay_file.name.lower())
        if index is None:
            raise ValueError(f"Addressables 목록에 수정 묶음이 없습니다: {overlay_file.name}")
        option = options[index]
        actual_file_crc = crc32_file(overlay_file)
        # Addressables의 m_Crc는 일반 파일 CRC가 아닌 Unity AssetBundle 전용 CRC다.
        # Unity 편집기 없이 재계산할 수 없으므로 로컬 수정 묶음만 0으로 설정해
        # Unity의 공식적인 CRC 검사 생략 경로를 사용한다.
        new_crc = 0
        new_size = overlay_file.stat().st_size
        updated_text = update_numeric_json_field(option.text, "m_Crc", new_crc)
        updated_text = update_numeric_json_field(updated_text, "m_BundleSize", new_size)
        replacements[index] = updated_text
        changed.append(
            {
                "index": index,
                "file": overlay_file.name,
                "old_crc": option.data["m_Crc"],
                "new_crc": new_crc,
                "actual_modified_file_crc32": actual_file_crc,
                "old_size": option.data["m_BundleSize"],
                "new_size": new_size,
                "hash_preserved": option.data["m_Hash"],
            }
        )

    output_extra = replace_addressable_options(extra_data, options, replacements)
    if len(output_extra) != len(extra_data):
        raise ValueError(
            "Addressables 추가 데이터의 길이가 바뀌었습니다. "
            "m_EntryDataString 오프셋 보호를 위해 길이는 반드시 같아야 합니다."
        )
    output_base64 = base64.b64encode(output_extra).decode("ascii")
    pattern = re.compile(r'("m_ExtraDataString":")[^"]*(")')
    output_text, count = pattern.subn(rf'\g<1>{output_base64}\g<2>', source_text, count=1)
    if count != 1:
        raise ValueError("catalog.json에서 m_ExtraDataString을 찾지 못했습니다.")
    overlay_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_catalog_path.write_text(output_text, encoding="utf-8", newline="")

    reopened_catalog = json.loads(overlay_catalog_path.read_text(encoding="utf-8"))
    reopened_options = parse_addressable_options(
        base64.b64decode(reopened_catalog["m_ExtraDataString"], validate=True)
    )
    for item in changed:
        option = reopened_options[item["index"]].data
        if option["m_Crc"] != item["new_crc"] or option["m_BundleSize"] != item["new_size"]:
            raise ValueError(f"저장한 Addressables 목록 재검사에 실패했습니다: {item['file']}")
    return {
        "source_catalog": str(source_catalog_path),
        "output_catalog": str(overlay_catalog_path),
        "source_bundle_options_verified": len(options),
        "extra_data_length_preserved": len(output_extra) == len(extra_data),
        "modified_bundle_count": len(changed),
        "modified_bundles": changed,
        "reopened": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--overlay-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report = {
        "passed": False,
        "yooasset": patch_yoo(args.source_root, args.overlay_root),
        "addressables": patch_addressables(args.source_root, args.overlay_root),
    }
    report["passed"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
