"""Clicky Islands의 Godot PCK v3를 원본 보존 방식으로 조사·수정합니다.

AGROMATIC_DEMO의 pck_tools.py를 복사해 게임 이름·빌드·대상 파일만 바꿨습니다.
이 게임은 EXE 내장이 아니라 별도 .pck 파일이며, 같은 코드가 두 형태를 모두 처리합니다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[3]
GAME = "CLICKY_ISLANDS"
BUILD = "steam_26701014"
PCK_NAME = "Clicky Islands.pck"
BASELINE = ROOT / "source_original" / GAME / BUILD
EXTRACTED = ROOT / "extracted_private" / GAME / BUILD
WORK = ROOT / "working_private" / GAME
MAGIC = b"GDPC"
PRIVATE_AREAS = {"source_original", "extracted_private", "working_private", "build_candidate"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_json(path: Path, value: object) -> None:
    _private_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _private_destination(path: Path) -> Path:
    resolved = Path(path).resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError("출력 경로는 작업 공간의 비공개 영역이어야 합니다.") from error
    _require(bool(relative.parts) and relative.parts[0] in PRIVATE_AREAS, "출력 경로가 비공개 영역 밖입니다.")
    _require(relative.parts[0] != "source_original", "고정한 원본 영역에는 쓰지 않습니다.")
    return resolved


def _safe_name(name: str) -> None:
    parts = PurePosixPath(name).parts
    _require(bool(name) and not name.startswith("/") and "\\" not in name, "잘못된 내부 경로입니다: " + repr(name))
    _require(parts and all(p not in {"", ".", ".."} for p in name.split("/")), "경로 이동 요소가 있습니다: " + name)
    _require(not any(c in name for c in ':<>"|?*\x00'), "Windows에서 안전하지 않은 내부 경로입니다: " + name)
    reserved = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
    _require(all(p.rstrip(" .") == p and p.split(".")[0].casefold() not in reserved for p in parts), "Windows 예약 경로입니다: " + name)


def parse_pack(data: bytes) -> dict:
    """끝의 길이 표식으로 내장 위치를 확정하고 모든 항목의 범위·MD5를 검사합니다."""
    _require(len(data) >= 112, "PCK 머리말을 읽기에는 파일이 너무 짧습니다.")
    embedded = data[:4] != MAGIC
    if embedded:
        _require(data[:2] == b"MZ" and data[-4:] == MAGIC, "지원하는 EXE 내장 PCK 표식이 없습니다.")
        pack_size = struct.unpack_from("<Q", data, len(data) - 12)[0]
        start, end = len(data) - 12 - pack_size, len(data) - 12
        _require(0 < start < end and pack_size >= 112, "내장 PCK 길이가 잘못되었습니다.")
    else:
        start, end = 0, len(data)
        pack_size = len(data)
    _require(data[start:start + 4] == MAGIC and start + 112 <= end, "PCK 시작 위치가 잘못되었습니다.")
    version, major, minor, patch, flags = struct.unpack_from("<5I", data, start + 4)
    _require(version == 3, "이 도구는 조사한 PCK v3에만 적용합니다.")
    _require(flags in (0, 2), "암호화 또는 미지원 PCK 설정입니다.")
    base, directory = struct.unpack_from("<QQ", data, start + 24)
    absolute_base = start + base if flags & 2 else base
    absolute_directory = start + directory
    _require(start + 112 <= absolute_base <= absolute_directory < end, "PCK 본문·목록 위치가 잘못되었습니다.")
    _require(absolute_directory + 4 <= end, "PCK 목록 개수를 읽을 수 없습니다.")
    count = struct.unpack_from("<I", data, absolute_directory)[0]
    _require(0 < count <= 1_000_000, "PCK 항목 개수가 잘못되었습니다.")
    position = absolute_directory + 4
    entries, folded_names, ranges = {}, set(), []
    for index in range(count):
        _require(position + 4 <= end, f"항목 {index}의 경로 길이가 없습니다.")
        name_size = struct.unpack_from("<I", data, position)[0]
        position += 4
        _require(0 < name_size <= 1_048_576 and position + name_size + 36 <= end, f"항목 {index}의 목록 범위가 잘못되었습니다.")
        raw = data[position:position + name_size]
        position += name_size
        encoded_name = raw.rstrip(b"\0")
        _require(b"\0" not in encoded_name, f"항목 {index} 경로에 중간 NUL이 있습니다.")
        name = encoded_name.decode("utf-8", errors="strict")
        _safe_name(name)
        _require(name not in entries and name.casefold() not in folded_names, "중복 경로입니다: " + name)
        folded_names.add(name.casefold())
        offset, size = struct.unpack_from("<QQ", data, position)
        position += 16
        digest = data[position:position + 16]
        position += 16
        entry_flags = struct.unpack_from("<I", data, position)[0]
        position += 4
        _require(entry_flags == 0, "암호화·삭제 표시 항목은 지원하지 않습니다: " + name)
        payload_start = absolute_base + offset
        payload_end = payload_start + size
        _require(absolute_base <= payload_start <= payload_end <= absolute_directory, "자산의 본문 범위를 벗어났습니다: " + name)
        payload = data[payload_start:payload_end]
        _require(hashlib.md5(payload).digest() == digest, "원본 MD5가 일치하지 않습니다: " + name)
        if size:
            ranges.append((payload_start, payload_end, name))
        entries[name] = dict(raw=raw, offset=offset, size=size, md5=digest, flags=entry_flags, data=payload)
    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        _require(previous[1] <= current[0], "자산 본문이 겹칩니다: " + previous[2] + " / " + current[2])
    trailer = data[position:end]
    _require(len(trailer) <= 15 and not any(trailer), "목록 뒤에 미해석 자료가 있습니다.")
    return dict(data=data, embedded=embedded, start=start, end=end, pack_size=pack_size,
                version=version, engine=[major, minor, patch], flags=flags, base=base,
                absolute_base=absolute_base, directory=directory, absolute_directory=absolute_directory,
                directory_end=position, trailer=trailer, entries=entries)


def read_pack(path: Path) -> dict:
    return parse_pack(Path(path).read_bytes())


def manifest(pack: dict, source: Path) -> dict:
    return dict(source_path=source.relative_to(ROOT).as_posix(), source_sha256=sha(pack["data"]),
                embedded=pack["embedded"], pack_start=pack["start"], pack_size=pack["pack_size"],
                pck_sha256=sha(pack["data"][pack["start"]:pack["end"]]),
                native_prefix_sha256=sha(pack["data"][:pack["start"]]),
                pck_version=pack["version"], engine_header=pack["engine"], flags=pack["flags"],
                relative_base=pack["base"], directory=pack["directory"], trailer_hex=pack["trailer"].hex(),
                entry_count=len(pack["entries"]), md5_verified=len(pack["entries"]),
                entries=[dict(path=name, size=entry["size"], sha256=sha(entry["data"]),
                              md5=entry["md5"].hex(), offset=entry["offset"], flags=entry["flags"])
                         for name, entry in pack["entries"].items()])


def extract_pack(source: Path, destination: Path, manifest_path: Path) -> dict:
    pack = read_pack(source)
    destination = _private_destination(destination)
    _require(not destination.exists(), "기존 추출 폴더를 덮어쓰지 않습니다.")
    destination.mkdir(parents=True)
    for name, entry in pack["entries"].items():
        target = (destination / name).resolve()
        _require(target.is_relative_to(destination), "추출 경로가 목적지를 벗어났습니다.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(entry["data"])
        _require(sha(target.read_bytes()) == sha(entry["data"]), "추출 결과가 다릅니다: " + name)
    _require(sum(p.is_file() for p in destination.rglob("*")) == len(pack["entries"]), "추출 파일 수가 다릅니다.")
    report = manifest(pack, Path(source))
    report.update(extraction_status="PASS", extracted_files=len(pack["entries"]))
    save_json(manifest_path, report)
    return report


def patch_pack(source: Path, destination: Path, changes: dict[str, bytes]) -> dict:
    """원래 코드·자산 위치를 보존하고 바꿀 자산과 새 목록을 끝에 추가합니다."""
    source, destination = Path(source), _private_destination(destination)
    _require(source.resolve() != destination, "입력 파일을 덮어쓰지 않습니다.")
    _require(not destination.exists(), "기존 후보를 덮어쓰지 않습니다.")
    original = read_pack(source)
    if not changes:
        output = original["data"]
    else:
        result = bytearray(original["data"][:original["absolute_directory"]])
        entries = {name: dict(entry) for name, entry in original["entries"].items()}
        folded_names = {name.casefold(): name for name in entries}
        for name, payload in changes.items():
            _safe_name(name)
            _require(isinstance(payload, bytes), "수정 자산은 bytes여야 합니다: " + name)
            _require(name.casefold() not in folded_names or folded_names[name.casefold()] == name, "대소문자만 다른 경로를 추가할 수 없습니다.")
            if name not in entries:
                raw = name.encode("utf-8")
                raw += b"\0" * (-len(raw) % 4)
                entries[name] = dict(raw=raw, flags=0)
                folded_names[name.casefold()] = name
            result.extend(b"\0" * (-(len(result) - original["absolute_base"]) % 16))
            entries[name].update(offset=len(result) - original["absolute_base"], size=len(payload),
                                 md5=hashlib.md5(payload).digest(), data=payload)
            result.extend(payload)
        result.extend(b"\0" * (-(len(result) - original["absolute_base"]) % 16))
        struct.pack_into("<Q", result, original["start"] + 32, len(result) - original["start"])
        result.extend(struct.pack("<I", len(entries)))
        for entry in entries.values():
            result.extend(struct.pack("<I", len(entry["raw"])) + entry["raw"])
            result.extend(struct.pack("<QQ", entry["offset"], entry["size"]) + entry["md5"] + struct.pack("<I", entry["flags"]))
        result.extend(original["trailer"])
        if original["embedded"]:
            result.extend(struct.pack("<Q", len(result) - original["start"]) + MAGIC)
        output = bytes(result)
    # 저장 전·후에 원본 밖의 변경과 모든 자산 값을 확인합니다.
    checked = parse_pack(output)
    _require(checked["start"] == original["start"], "내장 PCK 시작 위치가 바뀌었습니다.")
    _require(output[:original["start"]] == original["data"][:original["start"]], "실행 코드 영역이 바뀌었습니다.")
    _require(set(checked["entries"]) == set(original["entries"]) | set(changes), "후보의 경로 목록이 다릅니다.")
    left_header = original["data"][original["start"]:original["absolute_base"]]
    right_header = output[checked["start"]:checked["absolute_base"]]
    _require(left_header[:32] + left_header[40:] == right_header[:32] + right_header[40:], "허용되지 않은 PCK 머리말 변경입니다.")
    for name, entry in checked["entries"].items():
        expected = changes[name] if name in changes else original["entries"][name]["data"]
        _require(entry["data"] == expected, "후보 자산 값이 다릅니다: " + name)
        if name in original["entries"]:
            _require(entry["raw"] == original["entries"][name]["raw"], "기존 경로의 원본 표현이 바뀌었습니다.")
        if name not in changes:
            _require(entry["offset"] == original["entries"][name]["offset"], "무변경 자산의 위치가 바뀌었습니다.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(output)
    _require(destination.read_bytes() == output, "저장한 후보가 메모리 결과와 다릅니다.")
    read_pack(destination)
    return dict(status="PASS", source_sha256=sha(original["data"]), output_sha256=sha(output),
                noop_identical=not changes and output == original["data"],
                original_entries=len(original["entries"]), candidate_entries=len(checked["entries"]),
                changed_entries=list(changes), native_prefix_unchanged=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["extract", "noop"])
    args = parser.parse_args()
    source = BASELINE / PCK_NAME
    if args.mode == "extract":
        report = extract_pack(source, EXTRACTED / "pack", EXTRACTED / "pck_manifest.json")
        print(json.dumps({k: report[k] for k in ("extraction_status", "entry_count", "md5_verified", "pack_start", "pack_size", "engine_header")}, ensure_ascii=False))
    else:
        report = patch_pack(source, WORK / "risk_probe" / "noop" / PCK_NAME, {})
        save_json(WORK / "risk_probe" / "noop_report.json", report)
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
