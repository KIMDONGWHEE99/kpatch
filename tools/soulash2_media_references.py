"""미디어 파일명과 자산 식별자의 정적 참조를 한정된 검색 범위와 함께 기록한다."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
OUTPUT = ROOT / "working_private/SOULASH_2/media_review/review_v2/reference_followup.json"
PATTERNS = ["create_mod1.png", "mod_7.png", "mods_list_create.png", "mods_option.png",
            "dmg_numbers.png", "damage_numbers", "Soulash_patreon.png", "Soulash_patreon",
            "tweet.png", "tweet", "game_modes.png", "game_modes", "data/docs", "docs/index.html"]
TEXT_EXTENSIONS = {".json", ".html", ".css", ".txt", ".smap", ".frag", ".vert"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matches(data, needle):
    start, found = 0, []
    while True:
        index = data.find(needle, start)
        if index < 0:
            return found
        found.append(index)
        start = index + 1


def main():
    manifest_path = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {x["path"]: x["sha256"] for x in manifest["files"]}
    files = sorted(p for p in SOURCE.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS)
    search_records = []
    for path in files + [SOURCE / "Soulash 2.exe"]:
        data = path.read_bytes()
        relative = path.relative_to(SOURCE).as_posix()
        assert hashlib.sha256(data).hexdigest() == expected[relative]
        lowered = data.lower()
        found = {}
        for pattern in PATTERNS:
            ascii_offsets = matches(lowered, pattern.lower().encode("ascii"))
            wide_offsets = matches(lowered, pattern.lower().encode("utf-16le")) if path.suffix.lower() == ".exe" else []
            if ascii_offsets or wide_offsets:
                found[pattern] = {"ascii_offsets": [hex(x) for x in ascii_offsets], "utf16le_offsets": [hex(x) for x in wide_offsets]}
                if path.suffix.lower() == ".exe":
                    found[pattern]["containing_null_terminated_ascii"] = [{"start": hex(data.rfind(b"\0", 0, x) + 1),
                        "text": data[data.rfind(b"\0", 0, x) + 1:data.find(b"\0", x)].decode("ascii", "replace")} for x in ascii_offsets]
                if path.suffix.lower() != ".exe":
                    found[pattern]["line_numbers"] = [data.count(b"\n", 0, x) + 1 for x in ascii_offsets]
        if found:
            search_records.append({"path": relative, "sha256": expected[relative], "matches": found})
    assets_path = SOURCE / "data/mods/core_2/assets.json"
    assets = json.loads(assets_path.read_text(encoding="utf-8"))
    assets_records = []
    selected = {"assets/gfx/dmg_numbers.png", "assets/gfx/promo/Soulash_patreon.png", "assets/gfx/promo/tweet.png", "assets/gfx/ui/game_modes.png"}
    def walk(value, pointer=""):
        if isinstance(value, dict):
            if value.get("file") in selected:
                assets_records.append({"pointer": pointer, "record": value})
            for key, child in value.items():
                walk(child, pointer + "/" + key.replace("~", "~0").replace("/", "~1"))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, pointer + "/" + str(index))
    walk(assets)
    image_info = {
        "data/mods/core_2/assets/gfx/dmg_numbers.png": {"size_pixels": [120, 32], "tiles": [10, 2], "tile_size_pixels": [12, 16],
            "top_row": [{"observed": c, "rectangle_top_left": [i * 12, 0, 12, 16], "inferred_bottom_left_index": 10 + i} for i, c in enumerate(["!", "M", "I", "S", "B", "L", "O", "C", "K", "transparent"])],
            "bottom_row": [{"observed": str(i), "rectangle_top_left": [i * 12, 16, 12, 16], "inferred_bottom_left_index": i} for i in range(10)],
            "limits": "타일 ID는 동봉 문서의 왼쪽 아래 시작 규칙을 적용한 추론. 실제 MISS/BLOCK 조합 코드·타일 소비는 아직 확인되지 않음."},
        "data/mods/core_2/assets/gfx/promo/Soulash_patreon.png": {"size_pixels": [300, 77], "tiles": None, "region": [0, 0, 300, 77], "text": "Support Soulash on PATREON", "asset_reference": "UNKNOWN"},
        "data/mods/core_2/assets/gfx/promo/tweet.png": {"size_pixels": [80, 25], "tiles": None, "region": [0, 0, 80, 25], "text": "Tweet", "limits": "assets.json에서 별도 tiles/slicing 지정 없음. 실제 버튼 배치는 런타임 미확인."},
        "data/mods/core_2/assets/gfx/ui/game_modes.png": {"size_pixels": [780, 766], "tiles": [3, 2], "tile_size_pixels": [260, 383],
            "sign_regions": [[90, 190, 120, 70], [90, 580, 120, 70]],
            "inferred_panel_indices": [3, 0], "text_status": "UNKNOWN", "reinspection": "회색·컬러 확대 이미지를 다시 직접 판독. 두 단어 형태이며 Gate 추정 외에는 읽기를 확정할 수 없음. 고유명사/안내 여부 미확정."}}
    for relative, item in image_info.items():
        item["sha256"] = expected[relative]
    unresolved_docs = []
    for relative in ("data/docs/create_mod1.png", "data/docs/img/mod_7.png", "data/docs/mods_list_create.png", "data/docs/mods_option.png"):
        unresolved_docs.append({"path": relative, "sha256": expected[relative], "size": (SOURCE / relative).stat().st_size,
            "treatment": "UNKNOWN", "decision": "파일 실체·모드 제작 화면임은 확인. 동봉 HTML·텍스트·JSON과 주 실행 파일의 파일명 참조 검색은 음성이나, 동적 파일 열거 또는 간접 경로 소비까지 배제하지 못해 보존 확정 근거로 사용하지 않음."})
    result = {"game_id": "SOULASH_2", "baseline_id": SOURCE.name, "finished": datetime.now(timezone.utc).isoformat(),
        "script_sha256": sha(Path(__file__)), "baseline_manifest_sha256": sha(manifest_path),
        "search_scope": {"text_file_count": len(files), "extension_counts": dict(Counter(p.suffix.lower() for p in files)), "binary": "Soulash 2.exe",
            "patterns": PATTERNS, "match_mode": "대소문자 무시 ASCII 바이트. 주 실행 파일은 UTF-16LE도 검색. 전체 검색 파일의 기준선 해시 검증.",
            "excluded": "다른 DLL·실행 중 메모리·사용자 모드·Steam Workshop·동적 파일 열거는 이 검색 범위 밖.",
            "negative_result_limit": "정적 문자열이 없다는 사실은 런타임 비표시를 증명하지 않는다."},
        "matches": search_records, "asset_source": {"path": "data/mods/core_2/assets.json", "sha256": sha(assets_path), "records": assets_records},
        "images": image_info, "documentation_unknowns": unresolved_docs,
        "conclusions": {"image_editing": "NOT_RUN", "runtime_input": "NOT_RUN", "unknown_resolution": "NONE"}}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"text_files": len(files), "matched_files": len(search_records), "asset_records": assets_records,
        "native_matches": [x for x in search_records if x["path"].endswith(".exe")]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
