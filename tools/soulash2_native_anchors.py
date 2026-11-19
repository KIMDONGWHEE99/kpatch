"""Soulash 2 기준선의 정적 문자열·PE 가져오기 주소만 묶습니다."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import struct


ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = "0.10.4.0.1_20261029"
BASE = ROOT / "source_original" / "SOULASH_2" / BUILD
NATIVE = ROOT / "extracted_private" / "SOULASH_2" / BUILD / "native"
EVIDENCE = ROOT / "working_private/SOULASH_2/rea/initial_evidence.json"
OUTPUT = ROOT / "working_private/SOULASH_2/native_anchors/anchors.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    executable = BASE / "Soulash 2.exe"
    blob = executable.read_bytes()
    sha = digest(blob)
    summary = read_json(NATIVE / "summary.json")
    evidence = read_json(EVIDENCE)
    record = evidence["records"][0]
    imports = record["normalized_result"]
    assert sha == summary["file_sha256"] == imports["artifact"]["sha256"]
    pe_offset = struct.unpack_from("<I", blob, 0x3C)[0]
    assert blob[pe_offset:pe_offset + 4] == b"PE\0\0"
    image_base = struct.unpack_from("<Q", blob, pe_offset + 24 + 24)[0]
    assert image_base == int(summary["image_base"], 16)
    sections = summary["sections"]

    def offset_location(offset: int) -> dict:
        for section in sections:
            if section["offset"] <= offset < section["offset"] + section["size"]:
                rva = offset - section["offset"] + section["rva"]
                return {"file_offset": offset, "file_offset_hex": hex(offset),
                        "rva": hex(rva), "virtual_address": hex(image_base + rva),
                        "section": section["name"]}
        return {"file_offset": offset, "file_offset_hex": hex(offset),
                "rva": None, "virtual_address": None, "section": None}

    def rva_offset(rva: int) -> int:
        for section in sections:
            if section["rva"] <= rva < section["rva"] + section["size"]:
                return rva - section["rva"] + section["offset"]
        raise ValueError(f"RVA outside raw sections: {rva:x}")

    source_rows = [json.loads(line) for line in
                   (NATIVE / "strings.jsonl").read_text(encoding="utf-8").splitlines()]
    selected = []
    patterns = {
        "damage_media": r"(?i)damage_numbers|dmg_numbers|game_modes|(^|[^a-z])(MISS|BLOCK)([^a-z]|$)|TILE MISSING",
        "font_utf8": r"(?i)(?:font|TTF_|utf.?8|SDL_iconv_string)",
        "storage_log": r"(?i)GetPrefPath|WizardsOfTheCode|^Soulash 2$|user_settings|user\.settings|game_language|keymap\.json|logs/|^errors?\.log$|Unable to (?:create directory|delete)|Failed to open file",
        "sdl_init_error": r"^SDL_|^Mix_Init$|Mix_Init error|initialize AudioEngine|initialize gamepad|initialize glew|^Fatal Error$|missing or corrupted|Failed to load essential game files",
        "steam": r"(?i)steam",
        "network_crash": r"(?i)curl|BugSplat|MiniDmpSender|^httpInit$|itch\.io/api",
    }
    for row in source_rows:
        groups = [name for name, pattern in patterns.items()
                  if re.search(pattern, row["source"])]
        if not groups:
            continue
        # 주소·문자열은 원본 바이트와 재대조하며 기존 분류를 바꾸지 않습니다.
        raw = row["source"].encode(row["encoding"])
        offset = row["file_offset"]
        assert blob[offset:offset + len(raw)] == raw, row["location_id"]
        assert row["file_sha256"] == sha
        loc = offset_location(offset)
        assert loc["virtual_address"] == row["virtual_address"]
        selected.append({**row, **loc, "anchor_groups": groups,
                         "bytes_match_baseline": True,
                         "display_or_call_semantics": "UNKNOWN"})

    wanted_dlls = {"SDL2.dll", "SDL2_ttf.dll", "SDL2_mixer.dll",
                   "steam_api64.dll", "libcurl.dll", "BugSplat64.dll", "icuuc74.dll"}
    import_anchors = []
    for dll in imports["imports"]:
        if dll["name"] not in wanted_dlls:
            continue
        for function in dll["functions"]:
            name = function["name"]
            if dll["name"] == "icuuc74.dll" and "UTF8" not in (name or ""):
                continue
            name_rva = int(function["thunk_hex"], 16) + 2
            name_offset = rva_offset(name_rva)
            assert name and blob[name_offset:name_offset + len(name)] == name.encode("ascii")
            iat_rva = function["iat_rva"]
            import_anchors.append({
                "dll": dll["name"], "name": name,
                "name_location": offset_location(name_offset),
                "iat_location": offset_location(rva_offset(iat_rva)),
                "ilt_rva": hex(function["ilt_rva"]),
                "evidence_id": record["evidence_id"],
                "observation": "PE 가져오기 디렉터리에 기록된 항목",
                "runtime_binding_reachability": "UNKNOWN",
            })

    # 후보 목록 밖의 명령어 바이트도 포함하는 리터럴 검색입니다. 부재는 기능 부재 증거가 아닙니다.
    searches = []
    for needle in ["MISS", "BLOCK", "dmg_numbers", "damage_numbers", "game_modes",
                   "TTF_OpenFont", "TTF_RenderUTF8_Blended", "TTF_RenderGlyph32_Blended",
                   "SDL_GetPrefPath", "BugSplat", "MiniDmpSender", "data/user_settings.json",
                   "APPDATA", "Saved Games"]:
        for encoding in ["ascii", "utf-16-le"]:
            raw = needle.encode(encoding)
            matches = []
            for match in re.finditer(re.escape(raw), blob):
                offset = match.start()
                containers = [row for row in source_rows
                              if row["encoding"] == encoding
                              and row["file_offset"] <= offset
                              and offset + len(raw) <= row["file_offset"] + row["byte_length"]]
                matches.append({**offset_location(offset),
                                "containing_candidates": [{"location_id": row["location_id"],
                                                           "source": row["source"]}
                                                          for row in containers]})
            searches.append({"needle": needle, "encoding": encoding,
                             "match_count": len(matches), "matches": matches})

    result = {
        "schema_version": 1, "build": BUILD,
        "artifact": {"path": str(executable.relative_to(ROOT)), "sha256": sha, "bytes": len(blob)},
        "inputs": [{"path": str(path.relative_to(ROOT)), "sha256": digest(path.read_bytes())}
                   for path in [NATIVE / "strings.jsonl", NATIVE / "summary.json", EVIDENCE]],
        "image_base": hex(image_base), "sections": sections,
        "scope": "기준선 EXE의 정적 문자열 후보 및 기존 REA PE import 증거를 대조. 호출 경로와 화면 노출 판정은 하지 않음.",
        "statuses": {"byte_verification": "PASS", "xrefs": "NOT_RUN", "game_execution": "NOT_RUN"},
        "limitations": [
            "virtual_address는 선호 image base를 더한 정적 주소이며 실제 프로세스 주소가 아님.",
            "import 이름 문자열의 주소와 IAT 슬롯 주소는 다름. IAT를 런타임 관찰한 자료가 아님.",
            "가져오기 목록은 호출 가능성·실제 호출·화면 노출·네트워크 전송을 확정하지 않음.",
            "UTF16LE와 ASCII의 연속 바이트 검색은 조합 문자열·스프라이트·압축·다른 인코딩을 배제하지 않음.",
            "원본 문자열 분류를 그대로 보존했으며 신규 의미 판정은 UNKNOWN임.",
        ],
        "string_anchors": selected, "import_anchors": import_anchors,
        "literal_full_file_searches": searches,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "strings": len(selected),
                      "imports": len(import_anchors), "literal_searches": len(searches),
                      "sha256": digest(OUTPUT.read_bytes())}))


if __name__ == "__main__":
    main()
