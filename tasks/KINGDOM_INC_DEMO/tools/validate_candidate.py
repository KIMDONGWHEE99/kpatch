"""저장된 후보를 원본·번역 원본과 다시 대조하는 독립 G4 검사기."""
from common import ROOT, WORK, SOURCE, DATA, DATA_NAME, EXTRACT, GAME_ID, sha, write_json, load_asset, read_tree, asset_files
from pathlib import Path
from collections import Counter, defaultdict
import argparse
import copy
import hashlib
import io
import json
import math
import re
import struct
import subprocess
import tempfile
import traceback
from types import SimpleNamespace
from fontTools.ttLib import TTFont
from PIL import Image


FONT_IDS = {
    ("resources.assets", 26), ("resources.assets", 27),
    ("sharedassets0.assets", 34), ("sharedassets0.assets", 88),
    ("sharedassets0.assets", 89), ("sharedassets0.assets", 2),
    ("sharedassets0.assets", 3), ("sharedassets0.assets", 32),
    ("sharedassets0.assets", 6), ("sharedassets0.assets", 7),
}
LANGUAGE_ID = ("resources.assets", 21)
IMAGE_ID = ("sharedassets1.assets", 27)
ATLAS_ID = ("sharedassets0.assets", 11)
ATLAS_SPRITE_ID = ("resources.assets", 82)
ATLAS_OBJECT_SHA256 = "2413dbd04a30f74d2f159673a0486dbc3334e5733bfe594b5656bff8e08ff5c9"
ATLAS_SPRITE_SHA256 = "a5df78766419f0c8f7218fb5ace99d4af7fb59ffd8fca135cdd32c4d3905b13e"
LAYOUT_SPEC = {
    ("sharedassets1.assets", 806): {
        "type": "RectTransform", "field": "/m_SizeDelta/x", "source": -16.0, "expected": -120.0,
        "source_object_sha256": "86d725380f4eba870629255e8842debae263134d4ef7a97f4031dcb71fb95f26",
    },
    ("sharedassets1.assets", 678): {
        "type": "RectTransform", "field": "/m_SizeDelta/y", "source": 72.0, "expected": 96.0,
        "source_object_sha256": "829feacd728e169507e10eade10a574222245d8827e7359e1f1e3bb00b305207",
    },
    ("sharedassets1.assets", 1022): {
        "type": "MonoBehaviour", "field": "/m_lineSpacing", "source": 20.0, "expected": 0.0,
        "source_object_sha256": "d66ac02b346188d45c0f7428aafa8c83244288d1f4982560aa21bb7c3fec366f",
    },
}
CODE_REL = f"{DATA_NAME}/Managed/Assembly-CSharp.dll"
CODE_SITES = {
    ("System.String Assets.Source.Util.GameMath::FormatTime(System.Int32,System.Boolean)", 63): "d ",
    ("System.String Assets.Source.Util.GameMath::FormatTime(System.Int32,System.Boolean)", 86): "h ",
    ("System.String Assets.Source.Util.GameMath::FormatTime(System.Int32,System.Boolean)", 104): "m",
    ("System.Void Assets.Behaviour.UI.MainMenu.OptionsUI::OnEnable()", 226): "Custom",
}
ADDITIONS = {
    "TooltipItemLevel": "{0}레벨",
    "TimeFormatMS": "{1}분 {2}초",
    "TimeFormatHMS": "{0}시간 {1}분 {2}초",
    "ForestCrewUnassigned2": "미배치 인부",
    "ForestCrewUnassignedDesc": "아직 작업을 배정받지 않은 인부입니다.",
    "SlotScroll": "두루마리",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def field(tree, path):
    for key in path.strip("/").split("/"):
        tree = tree[int(key)] if isinstance(tree, list) else tree[key]
    return tree


def replace_field(tree, path, value):
    keys = path.strip("/").split("/")
    for key in keys[:-1]:
        tree = tree[int(key)] if isinstance(tree, list) else tree[key]
    tree[int(keys[-1]) if isinstance(tree, list) else keys[-1]] = value


def equal_tree(actual, expected, label, tolerances=frozenset(), path=""):
    """직렬화 과정의 32비트 반올림은 명시한 글꼴 치수에서만 허용합니다."""
    if path in tolerances:
        require(math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-5), f"{label}{path}: 글꼴 치수 불일치")
    elif isinstance(expected, dict):
        require(isinstance(actual, dict) and set(actual) == set(expected), f"{label}{path}: 필드 집합 변경")
        for key in expected:
            equal_tree(actual[key], expected[key], label, tolerances, path + "/" + key)
    elif isinstance(expected, (list, tuple)):
        require(isinstance(actual, (list, tuple)) and len(actual) == len(expected), f"{label}{path}: 목록 크기 변경")
        if actual == expected:
            return
        for index, value in enumerate(expected):
            equal_tree(actual[index], value, label, tolerances, path + "/" + str(index))
    else:
        require(actual == expected, f"{label}{path}: 기대값 불일치")


def parse_language(text):
    result = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(";"):
            continue
        require("=" in line, "언어 표의 잘못된 행")
        key, value = line.split("=", 1)
        result.append((key.strip(), value.strip()))
    require(len(result) == len({key for key, _ in result}), "언어 표의 중복 키")
    return result


def check_controls(source, target, label):
    require(not source.strip() or target.strip(), f"{label}: 빈 번역")
    token = r"(?<!\{)\{[^{}]*\}(?!\})"
    require(Counter(re.findall(token, source)) == Counter(re.findall(token, target)), f"{label}: 자리표시자")
    require(re.findall(r"\\n|\r\n|\n|\r", source) == re.findall(r"\\n|\r\n|\n|\r", target), f"{label}: 줄바꿈")
    require(source.count("#") == target.count("#") and target.count("#") % 2 == 0, f"{label}: 강조 구분")
    tags_source, tags_target = re.findall(r"<[^<>]+>", source), re.findall(r"<[^<>]+>", target)
    require(tags_source == tags_target, f"{label}: 태그 순서·속성")
    stack = []
    for tag in tags_target:
        match = re.match(r"<(/?)([A-Za-z][\w-]*)", tag)
        if not match:
            continue
        closing, name = match.groups()
        if closing:
            require(stack and stack.pop() == name, f"{label}: 태그 중첩")
        elif name not in {"br", "sprite", "space", "page", "quad"} and not tag.endswith("/>"):
            stack.append(name)
    require(not stack, f"{label}: 닫히지 않은 태그")


def check_shader(actual, template, label):
    require(actual == template, f"{label}: SDF 셰이더가 검증된 원본 템플릿과 다름")


def check_layout(pair, original, actual):
    """제작 도구를 불러오지 않고 허용 필드·값을 독립 상수와 비교합니다."""
    spec = LAYOUT_SPEC[pair]
    require(field(original, spec["field"]) == spec["source"], f"{pair}: 기술 카드 원본 필드")
    expected = copy.deepcopy(original)
    replace_field(expected, spec["field"], spec["expected"])
    equal_tree(actual, expected, f"{pair}: 기술 카드 배치")


def check_atlas_pixels(original, actual, icon):
    require(original.size == actual.size == (256, 256) and icon.size == (16, 16), "아이콘 묶음 크기")
    require(actual.crop((35, 35, 51, 51)).tobytes() == icon.tobytes(), "작은 아이콘 셀 픽셀 불일치")
    before, after = original.tobytes(), actual.tobytes()
    outside_before, outside_after = bytearray(), bytearray()
    for y in range(256):
        start, end = y * 256 * 4, (y + 1) * 256 * 4
        spans = [(start, start + 35 * 4), (start + 51 * 4, end)] if 35 <= y < 51 else [(start, end)]
        for left, right in spans:
            outside_before.extend(before[left:right])
            outside_after.extend(after[left:right])
    require(outside_before == outside_after, "작은 아이콘 셀 밖 RGBA 변경")
    return {"outside_rgba_sha256": digest(outside_after), "outside_pixels": 256 * 256 - 16 * 16,
            "changed_pixels": sum(before[i:i+4] != after[i:i+4] for i in range(0, len(before), 4))}


def check_sprite_binding(value):
    rect = {"x": 35.0, "y": 205.0, "width": 16.0, "height": 16.0}
    require(value["m_Name"] == "Icons_32" and value["m_Rect"] == rect, "작은 아이콘 Sprite 위치")
    require(value["m_RD"]["textureRect"] == rect, "작은 아이콘 Sprite 실제 영역")
    require(value["m_RD"]["texture"] == {"m_FileID": 3, "m_PathID": 11}, "작은 아이콘 Sprite 원본 연결")
    require(value["m_RD"]["settingsRaw"] == 64 and value["m_RD"]["downscaleMultiplier"] == 1.0,
            "작은 아이콘 패킹 회전·크기")
    require(value["m_SpriteAtlas"] == {"m_FileID": 0, "m_PathID": 0} and not value["m_AtlasTags"], "별도 SpriteAtlas 연결")


def byte_boundary(source_path, candidate_path, original, candidate, allowed):
    """파일 앞부분을 통째로 비교하여 객체 주소·크기 이외의 변조도 검출합니다."""
    source_bytes, candidate_bytes = source_path.read_bytes(), candidate_path.read_bytes()
    require(set(original.file.objects) == set(candidate.file.objects), f"{source_path.name}: 객체 추가·삭제")
    require(len(candidate_bytes) >= len(source_bytes), f"{source_path.name}: 파일 축소")
    prefix = bytearray(candidate_bytes[:len(source_bytes)])
    prefix[24:32] = source_bytes[24:32]
    require(struct.unpack_from(">q", candidate_bytes, 24)[0] == len(candidate_bytes), "파일 길이 헤더")
    modified, ranges = [], []
    for pid, old in original.file.objects.items():
        new = candidate.file.objects[pid]
        require(new.type_id == old.type_id and new.type == old.type, f"{source_path.name}/{pid}: 객체 형식")
        old_raw, new_raw = old.get_raw_data(), new.get_raw_data()
        if old_raw == new_raw:
            require((new.byte_start, new.byte_size) == (old.byte_start, old.byte_size), f"{source_path.name}/{pid}: 불필요한 재배치")
            continue
        require((source_path.name, pid) in allowed, f"{source_path.name}/{pid}: 허용 목록 밖 변경")
        require(new.byte_start >= len(source_bytes), f"{source_path.name}/{pid}: 원본 영역 덮어쓰기")
        needle = struct.pack("<qqIi", pid, old.byte_start - original.file.header.data_offset, old.byte_size, old.type_id)
        head = source_bytes[:original.file.header.data_offset]
        require(head.count(needle) == 1, f"{source_path.name}/{pid}: 객체 기록 위치 모호")
        pos = head.index(needle)
        expected_record = struct.pack("<qqIi", pid, new.byte_start - candidate.file.header.data_offset, new.byte_size, new.type_id)
        require(candidate_bytes[pos:pos + len(needle)] == expected_record, f"{source_path.name}/{pid}: 객체 기록 손상")
        prefix[pos + 8:pos + 20] = source_bytes[pos + 8:pos + 20]
        modified.append({"file": source_path.name, "path_id": pid,
                         "source_object_sha256": digest(old_raw), "candidate_object_sha256": digest(new_raw)})
        ranges.append((new.byte_start, new.byte_start + new.byte_size))
    require(bytes(prefix) == source_bytes, f"{source_path.name}: 원본 데이터·메타데이터의 허용 범위 밖 변경")
    cursor = len(source_bytes)
    for start, end in sorted(ranges):
        require(start >= cursor and start - cursor <= 7 and not any(candidate_bytes[cursor:start]),
                f"{source_path.name}: 객체 사이에 알 수 없는 데이터")
        cursor = end
    require(cursor == len(candidate_bytes), f"{source_path.name}: 알 수 없는 후미 데이터")
    return modified


def main(build_path, output_path):
    report = {"status": "FAIL", "scope": "G4 독립 재추출·위치·변경 경계·글꼴 검사",
              "runtime_qa": "NOT_RUN", "checks": [], "validator_sha256": sha(__file__)}
    def stage(name, operation):
        result = operation()
        report["checks"].append({"name": name, "status": "PASS", "result": result})
        print(name + ": PASS", flush=True)
        return result
    try:
        proof_inputs = [build_path, Path(__file__), Path(__file__).with_name("common.py"),
                        WORK / "translation/canonical.json", WORK / "translation/language_ko.txt",
                        WORK / "translation/required_characters.json", WORK / "language_source.json",
                        WORK / "audit/direct_translations.json", WORK / "audit/asset_classification.json",
                        WORK / "audit/key_coverage_original.json", WORK / "audit/code_direct_translations.json",
                        WORK / "fonts/NotoSansKR-Regular.ttf", WORK / "media/IconDecoLabel_evidence.json",
                        WORK / "media/IconDecoLabel_ko_32.png", WORK / "toolchain/TextPatch/TextPatch.dll",
                        Path(__file__).with_name("layout_patch.py"),
                        Path(__file__).with_name("atlas_patch.py"), WORK / "media/Icons32_ko_16_v2.png",
                        WORK / "media/Icons32_ko_evidence_v2.json",
                        EXTRACT / "baseline.json"]
        report["verification_inputs"] = [{"path": str(p), "sha256": sha(p)} for p in proof_inputs]
        build = read_json(build_path)
        candidate_root = Path(build["candidate"]).resolve()
        expected_root = ROOT / "build_candidate" / GAME_ID / build["build_id"] / "game"
        require(candidate_root == expected_root.resolve(), "후보 경로가 해당 빌드의 격리 폴더와 다릅니다.")
        require(build["game_id"] == GAME_ID, "게임 식별자")
        report.update(build_id=build["build_id"], candidate=str(candidate_root), build_sha256=sha(build_path))
        baseline_path = EXTRACT / "baseline.json"
        baseline = read_json(baseline_path)
        originals = {r["path"]: r for r in baseline["files"]}
        recorded = {r["path"]: r for r in build["files"]}
        def inputs_check():
            require(build["baseline_manifest_sha256"] == sha(baseline_path), "원본 목록 변경")
            require(len(originals) == len(baseline["files"]) == 191, "원본 목록 수")
            require(len(recorded) == len(build["files"]), "후보 목록 중복")
            actual_names = {p.relative_to(candidate_root).as_posix() for p in candidate_root.rglob("*") if p.is_file()}
            require(actual_names == set(originals) == set(recorded), "후보 파일 누락·추가")
            source_names = {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file()}
            require(source_names == set(originals), "격리 원본 파일 집합 변경")
            for relative, original in originals.items():
                require(sha(SOURCE / relative) == original["sha256"], f"{relative}: 원본 해시")
                require((SOURCE / relative).stat().st_size == original["size"], f"{relative}: 원본 크기")
                current = candidate_root / relative
                require(sha(current) == recorded[relative]["sha256"], f"{relative}: 후보 해시")
                require(current.stat().st_size == recorded[relative]["size"], f"{relative}: 후보 크기")
            input_paths = [str(Path(item["path"]).resolve()) for item in build["inputs"]]
            require(len(input_paths) == len(set(input_paths)), "중복 제작 입력 기록")
            expected_inputs = [
                WORK / "translation/canonical.json", WORK / "translation/language_ko.txt",
                WORK / "translation/required_characters.json", WORK / "audit/direct_translations.json",
                WORK / "audit/code_direct_translations.json", WORK / "media/IconDecoLabel_ko_32.png",
                Path(__file__).with_name("font_patch.py"), Path(__file__).with_name("build_candidate.py"),
                WORK / "toolchain/TextPatch/TextPatch.dll", Path(__file__).with_name("common.py"),
                Path(__file__).with_name("layout_patch.py"), Path(__file__).with_name("translation_checks.py"),
                WORK / "fonts/NotoSansKR-Regular.ttf", ROOT / "tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf",
                EXTRACT / "baseline.json", EXTRACT / "trees/resources.assets/21.json", WORK / "language_source.json",
                Path(__file__).parent / "TextPatch/Program.cs", Path(__file__).with_name("atlas_patch.py"),
                WORK / "media/Icons32_ko_16_v2.png", WORK / "media/Icons32_ko_evidence_v2.json",
                WORK / "audit/media_classification.json", WORK / "audit/media_reclassification_icons32.json",
                WORK / "audit/media_resolution_icons32.json"]
            require({str(p.resolve()) for p in expected_inputs} <= set(input_paths), "제작 입력 의존 관계 기록 누락")
            for item in build["inputs"]:
                require(sha(item["path"]) == item["sha256"], f"STALE 제작 입력: {item['path']}")
            require(build["language_sha256"] == sha(WORK / "translation/language_ko.txt"), "STALE 번역 파일")
            return {"source_files": len(originals), "candidate_files": len(recorded), "input_files": len(build["inputs"])}
        stage("입력·원본·후보 해시", inputs_check)
        direct = read_json(WORK / "audit/direct_translations.json")
        code = read_json(WORK / "audit/code_direct_translations.json")
        canonical = read_json(WORK / "translation/canonical.json")
        source_rows = read_json(WORK / "language_source.json")
        language_text = (WORK / "translation/language_ko.txt").read_text(encoding="utf-8")
        by_object = defaultdict(list)
        for row in direct:
            by_object[(row["file"], row["path_id"])].append(row)
        require(not set(by_object) & set(LAYOUT_SPEC), "동일 객체의 번역·배치 변경 규칙을 다시 검토해야 합니다.")
        allowed = set(by_object) | FONT_IDS | set(LAYOUT_SPEC) | {LANGUAGE_ID, IMAGE_ID, ATLAS_ID}
        source_assets, candidate_assets = {}, {}
        def read_assets():
            modified = []
            for path in asset_files():
                name = path.name
                old, new = load_asset(path), load_asset(candidate_root / DATA_NAME / name)
                source_assets[name], candidate_assets[name] = old, new
                modified += byte_boundary(path, candidate_root / DATA_NAME / name, old, new, allowed)
            changed_files = {f"{DATA_NAME}/{row['file']}" for row in modified} | {CODE_REL}
            for relative in originals:
                if relative not in changed_files:
                    require(recorded[relative]["sha256"] == originals[relative]["sha256"], f"{relative}: 변경 금지 파일")
            report["changed_objects"] = modified
            report["changed_files"] = sorted(changed_files)
            return {"asset_files": len(source_assets), "changed_objects": len(modified), "changed_files": len(changed_files)}
        stage("전체 파일·객체 원시 바이트 경계", read_assets)
        def obj(pair, original=False):
            return (source_assets if original else candidate_assets)[pair[0]].file.objects[pair[1]]
        def tree(pair, original=False):
            return read_tree(obj(pair, original))
        def layout_check():
            expected_records = [{"file": pair[0], "path_id": pair[1], **spec} for pair, spec in LAYOUT_SPEC.items()]
            require(build["layout_expected"] == expected_records, "기술 카드 배치 명세 변경")
            for pair, spec in LAYOUT_SPEC.items():
                require(obj(pair, True).type.name == obj(pair).type.name == spec["type"], f"{pair}: 배치 객체 형식")
                require(digest(obj(pair, True).get_raw_data()) == spec["source_object_sha256"], f"{pair}: 배치 원본 객체 해시")
                check_layout(pair, tree(pair, True), tree(pair))
            return {"objects": len(LAYOUT_SPEC), "fields": len(LAYOUT_SPEC), "visual_layout_qa": "NOT_RUN",
                    "description_size_intended": [224, 80], "image_gap_intended": 8,
                    "note": "정적 필드와 변경 범위만 통과했으며 실제 카드 배치는 새 그래픽 QA에서 확인해야 합니다."}
        stage("기술 카드 배치 3필드·변경 경계", layout_check)
        def text_check():
            classifications = read_json(WORK / "audit/asset_classification.json")
            classified_ids = {r["id"] for r in classifications if r["classification"] == "VISIBLE_TRANSLATE"}
            direct_ids = {r["id"] for r in direct}
            require(len(direct) == len(direct_ids) == 154, "직접 문구 위치 수")
            require(classified_ids == direct_ids | {"resources.assets/21/m_Script"}, "번역 대상으로 분류된 위치 누락")
            require(build["expected"] == direct, "제작 기록의 기대값과 현재 번역 원본 불일치")
            positions = set()
            for pair, rows in by_object.items():
                original = tree(pair, True)
                expected = copy.deepcopy(original)
                for row in rows:
                    position = (pair, row["field"])
                    require(position not in positions, "직접 번역 위치 중복")
                    positions.add(position)
                    require(sha(DATA / pair[0]) == row["file_sha256"], f"{row['id']}: 출처 파일 해시")
                    require(digest(obj(pair, True).get_raw_data()) == row["object_sha256"], f"{row['id']}: 출처 객체 해시")
                    require(field(original, row["field"]) == row["source"], f"{row['id']}: 출처 위치 원문")
                    require(digest(row["source"].encode()) == row["source_sha256"], f"{row['id']}: 원문 해시")
                    check_controls(row["source"], row["expected"], row["id"])
                    replace_field(expected, row["field"], row["expected"])
                equal_tree(tree(pair), expected, f"{pair}: 직접 번역")
            require(canonical["source_sha256"] == sha(WORK / "language_source.json"), "표 원문 해시")
            require(canonical["addition_evidence_sha256"] == sha(WORK / "audit/key_coverage_original.json"), "추가 키 근거 해시")
            rows = canonical["rows"]
            require(len(rows) == len(source_rows) == 1556, "번역 표 위치 수")
            for index, (row, source) in enumerate(zip(rows, source_rows)):
                require(row["index"] == index and all(row[k] == source[k] for k in ("index", "key", "source")), f"표 {index}: 출처 위치")
                check_controls(row["source"], row["target"], row["key"])
            require(canonical["additions"] == ADDITIONS, "검증되지 않은 추가 키")
            original = tree(LANGUAGE_ID, True)
            actual = tree(LANGUAGE_ID)
            require(parse_language(original["m_Script"]) == [(r["key"], r["source"]) for r in source_rows], "원본 언어 표 재추출 불일치")
            expected_rows = [(r["key"], r["target"]) for r in rows] + list(ADDITIONS.items())
            require(parse_language(actual["m_Script"]) == expected_rows, "후보 언어 표 위치·값·수·순서")
            require(dict(expected_rows)["locale"] == "en-US", "영문 슬롯 식별자 변경")
            require(actual["m_Script"] == language_text, "후보 언어 본문 바이트 대응")
            original["m_Script"] = language_text
            equal_tree(actual, original, "언어 TextAsset")
            expected_chars = sorted({ord(c) for c in language_text + "".join(r["expected"] for r in direct + code) if c not in "\r\n\t"} | set(range(32, 127)))
            require(read_json(WORK / "translation/required_characters.json") == expected_chars, "필요 문자 목록")
            return {"direct_positions": len(positions), "table_positions": len(rows), "additions": len(ADDITIONS), "required_characters": len(expected_chars)}
        stage("위치별 번역·서식·언어 표", text_check)
        required_chars = set(read_json(WORK / "translation/required_characters.json"))
        font_file = WORK / "fonts/NotoSansKR-Regular.ttf"
        font_raw = font_file.read_bytes()
        font = TTFont(io.BytesIO(font_raw))
        font_cmap = set(font.getBestCmap())
        def font_exact_check():
            require(not required_chars - font_cmap, "Noto 원본 글꼴에 필요한 문자 없음")
            require(font["OS/2"].usWeightClass == 400 and "fvar" not in font, "고정 Regular 글꼴")
            for pair in [("resources.assets", 26), ("resources.assets", 27), ("sharedassets0.assets", 34)]:
                expected = tree(pair, True)
                expected["m_FontData"], expected["m_FontNames"] = list(font_raw), ["Noto Sans KR"]
                equal_tree(tree(pair), expected, f"{pair}: 원본 글꼴")
            material_template = tree(("resources.assets", 6), True)
            font_template = tree(("resources.assets", 2058), True)
            shader_template = obj(("resources.assets", 20), True).get_raw_data()
            check_shader(obj(("sharedassets0.assets", 32)).get_raw_data(), shader_template, "sharedassets0.assets/32")
            for pid, material_id, atlas_id in [(88, 2, 6), (89, 3, 7)]:
                expected_material = copy.deepcopy(material_template)
                expected_material["m_Name"] = tree(("sharedassets0.assets", material_id), True)["m_Name"]
                expected_material["m_Shader"] = {"m_FileID": 0, "m_PathID": 32}
                for key, value in expected_material["m_SavedProperties"]["m_TexEnvs"]:
                    if key == "_MainTex":
                        value["m_Texture"] = {"m_FileID": 0, "m_PathID": atlas_id}
                expected_material["m_SavedProperties"]["m_Floats"] = [
                    (key, 1024.0 if key in {"_TextureWidth", "_TextureHeight"} else value)
                    for key, value in expected_material["m_SavedProperties"]["m_Floats"]]
                equal_tree(tree(("sharedassets0.assets", material_id)), expected_material, f"재질 {material_id}")
                expected = copy.deepcopy(font_template)
                expected["m_Name"] = tree(("sharedassets0.assets", pid), True)["m_Name"]
                expected.update(m_SourceFontFile={"m_FileID": 0, "m_PathID": 34},
                                m_Material={"m_FileID": 0, "m_PathID": material_id},
                                m_AtlasTextures=[{"m_FileID": 0, "m_PathID": atlas_id}],
                                m_GlyphTable=[], m_CharacterTable=[], m_UsedGlyphRects=[],
                                m_FreeGlyphRects=[{"m_X": 0, "m_Y": 0, "m_Width": 1023, "m_Height": 1023}],
                                m_AtlasWidth=1024, m_AtlasHeight=1024, m_AtlasPopulationMode=1,
                                m_IsMultiAtlasTexturesEnabled=True, m_AtlasTextureIndex=0)
                units = font["head"].unitsPerEm
                scale = 64 / units
                metrics = dict(m_FamilyName="Noto Sans KR", m_StyleName="Regular", m_PointSize=64.0,
                               m_UnitsPerEM=units, m_LineHeight=(font["hhea"].ascent - font["hhea"].descent + font["hhea"].lineGap) * scale,
                               m_AscentLine=font["hhea"].ascent * scale, m_DescentLine=font["hhea"].descent * scale,
                               m_CapLine=font["OS/2"].sCapHeight * scale, m_MeanLine=font["OS/2"].sxHeight * scale)
                expected["m_FaceInfo"].update(metrics)
                tolerances = frozenset("/m_FaceInfo/" + key for key, value in metrics.items() if isinstance(value, float))
                equal_tree(tree(("sharedassets0.assets", pid)), expected, f"TMP 글꼴 {pid}", tolerances)
                atlas_expected = tree(("sharedassets0.assets", atlas_id), True)
                atlas_expected.update(m_Width=1024, m_Height=1024, m_CompleteImageSize=1048576, m_MipCount=1,
                                      m_TextureFormat=1, m_IsReadable=True, m_StreamData={"offset": 0, "size": 0, "path": ""},
                                      **{"image data": bytes(1048576)})
                atlas_expected["m_TextureSettings"]["m_FilterMode"] = 1
                equal_tree(tree(("sharedassets0.assets", atlas_id)), atlas_expected, f"동적 문자판 {atlas_id}")
            return {"fixed_objects": len(FONT_IDS), "font_sha256": sha(font_file), "missing_codepoints": 0,
                    "sdf_shader_source": "resources.assets/20", "sdf_shader_sha256": digest(shader_template)}
        stage("고정 글꼴 10객체·SDF 템플릿·문자판", font_exact_check)
        def resolve(pair, pointer):
            pid, file_id = pointer["m_PathID"], pointer["m_FileID"]
            if not pid:
                return None
            name = pair[0]
            if file_id:
                externals = candidate_assets[name].file.externals
                require(0 < file_id <= len(externals), f"{pair}: 외부 파일 참조")
                name = Path(externals[file_id - 1].path.replace("\\", "/")).name
            result = (name, pid)
            require(name in candidate_assets and pid in candidate_assets[name].file.objects, f"{pair}: 끊어진 참조 {result}")
            return result
        def graph_check():
            fonts, consumers, settings, source_fonts = {}, [], [], {}
            for name, env in candidate_assets.items():
                for item in env.objects:
                    pair = (name, item.path_id)
                    if item.type.name == "Font":
                        data = bytes(read_tree(item)["m_FontData"])
                        source_fonts[pair] = set(TTFont(io.BytesIO(data)).getBestCmap())
                    elif item.type.name == "MonoBehaviour":
                        value = read_tree(item)
                        if "m_CharacterTable" in value and "m_GlyphTable" in value:
                            fonts[pair] = value
                        if "m_fontAsset" in value:
                            consumers.append((pair, value))
                        if "m_defaultFontAsset" in value:
                            settings.append((pair, value))
            require(set(source_fonts) == {("resources.assets", 26), ("resources.assets", 27), ("sharedassets0.assets", 34)}, "원본 글꼴 수")
            require(set(fonts) == {("resources.assets", 2058), ("resources.assets", 2059), ("sharedassets0.assets", 88), ("sharedassets0.assets", 89)}, "TMP 글꼴 수")
            edges, coverage, summaries = {}, {}, []
            template_shader = obj(("resources.assets", 20), True).get_raw_data()
            for pair, value in fonts.items():
                glyphs = {r["m_Index"] for r in value["m_GlyphTable"]}
                require(len(glyphs) == len(value["m_GlyphTable"]), f"{pair}: 중복 글리프")
                require(len({r["m_Unicode"] for r in value["m_CharacterTable"]}) == len(value["m_CharacterTable"]), f"{pair}: 중복 문자")
                require(all(r["m_GlyphIndex"] in glyphs for r in value["m_CharacterTable"]), f"{pair}: 문자와 글리프 연결")
                coverage[pair] = {r["m_Unicode"] for r in value["m_CharacterTable"]}
                atlas_pairs = [resolve(pair, p) for p in value["m_AtlasTextures"]]
                require(atlas_pairs and all(p and obj(p).type.name == "Texture2D" for p in atlas_pairs), f"{pair}: 문자판 연결")
                material_pair = resolve(pair, value["m_Material"])
                require(material_pair and obj(material_pair).type.name == "Material", f"{pair}: 재질 연결")
                material = tree(material_pair)
                texenvs = dict(material["m_SavedProperties"]["m_TexEnvs"])
                require(resolve(material_pair, texenvs["_MainTex"]["m_Texture"]) in atlas_pairs, f"{pair}: 재질 문자판 연결")
                shader_pair = resolve(material_pair, material["m_Shader"])
                require(shader_pair is not None, f"{pair}: SDF 셰이더 연결")
                check_shader(obj(shader_pair).get_raw_data(), template_shader, str(pair))
                require(value["m_AtlasRenderMode"] == 4169, f"{pair}: SDF 렌더 모드")
                dynamic = value["m_AtlasPopulationMode"] == 1
                if dynamic:
                    source_pair = resolve(pair, value["m_SourceFontFile"])
                    require(source_pair in source_fonts, f"{pair}: 동적 원본 글꼴")
                    require(value["m_IsMultiAtlasTexturesEnabled"], f"{pair}: 다중 문자판 꺼짐")
                    require(all(tree(p)["m_IsReadable"] for p in atlas_pairs), f"{pair}: 문자판 읽기 불가")
                    require(value["m_AtlasWidth"] > 0 and value["m_AtlasHeight"] > 0 and value["m_FreeGlyphRects"], f"{pair}: 동적 문자판 여유 없음")
                    coverage[pair] |= source_fonts[source_pair]
                edges[pair] = []
                for pointer in value.get("m_FallbackFontAssetTable", []) + value.get("fallbackFontAssets", []):
                    dest = resolve(pair, pointer)
                    if dest:
                        require(dest in fonts, f"{pair}: 폴백 대상 형식")
                        edges[pair].append(dest)
                summaries.append({"file": pair[0], "path_id": pair[1], "dynamic": dynamic, "characters": len(value["m_CharacterTable"]),
                                  "glyphs": len(glyphs), "atlases": len(atlas_pairs), "material": material_pair, "shader": shader_pair})
            def available(pair, active=frozenset()):
                require(pair not in active, f"{pair}: 폴백 순환")
                result = set(coverage[pair])
                for child in edges[pair]:
                    result |= available(child, active | {pair})
                return result
            for pair in fonts:
                require(not required_chars - available(pair), f"{pair}: 폴백 포함 필요 문자 누락")
            require(len(consumers) == 407, f"TMP 소비자 수 변경: {len(consumers)}")
            for pair, value in consumers:
                target = resolve(pair, value["m_fontAsset"])
                require(target in fonts, f"{pair}: 글꼴 소비자 연결")
                material_pair = resolve(pair, value["m_sharedMaterial"])
                require(material_pair == resolve(target, fonts[target]["m_Material"]), f"{pair}: 소비자 재질과 글꼴 불일치")
                require(not required_chars - available(target), f"{pair}: 실제 소비자 문자 누락")
            require(len(settings) == 1, "TMP 전역 설정 수")
            for pair, value in settings:
                target = resolve(pair, value["m_defaultFontAsset"])
                require(target in fonts and not required_chars - available(target), "기본 글꼴 문자 누락")
                for pointer in value.get("m_fallbackFontAssets", []):
                    require(resolve(pair, pointer) in fonts, "전역 폴백 연결")
            report["font_graph"] = summaries
            return {"source_fonts": len(source_fonts), "tmp_fonts": len(fonts), "consumers": len(consumers), "settings": len(settings), "missing_characters": 0}
        stage("실사용 글꼴·폴백·소비자 전체 연결", graph_check)
        def image_check():
            expected_path = WORK / "media/IconDecoLabel_ko_32.png"
            evidence = read_json(WORK / "media/IconDecoLabel_evidence.json")
            expected = Image.open(expected_path).convert("RGBA")
            actual = obj(IMAGE_ID).read().image.convert("RGBA")
            require(expected.size == actual.size == (32, 32), "이미지 크기")
            require(actual.tobytes() == expected.tobytes(), "후보 이미지 픽셀 불일치")
            require(sha(expected_path) == evidence["expected_sha256"], "이미지 파일 근거 해시")
            require(digest(actual.tobytes()) == evidence["expected_rgba_sha256"], "이미지 픽셀 근거 해시")
            original_tree, actual_tree = tree(IMAGE_ID, True), tree(IMAGE_ID)
            require(actual_tree["m_TextureFormat"] == 4, "이미지 RGBA32 형식")
            require(actual_tree["m_StreamData"] == {"offset": 0, "size": 0, "path": ""}, "이미지 외부 스트림 잔존")
            require(len(actual_tree["image data"]) == 4096, "이미지 바이트 수")
            for key in ("image data", "m_StreamData"):
                original_tree[key] = actual_tree[key]
            equal_tree(actual_tree, original_tree, "이미지 허용 필드")
            return {"texture": "/".join(map(str, IMAGE_ID)), "rgba_sha256": digest(actual.tobytes()), "pixels": 1024}
        stage("한국어 이미지 픽셀·필드", image_check)
        def atlas_check():
            icon_path = WORK / "media/Icons32_ko_16_v2.png"
            icon = Image.open(icon_path).convert("RGBA")
            expected = Image.open(WORK / "media/IconDecoLabel_ko_32.png").convert("RGBA").crop((8, 6, 24, 22))
            require(icon.tobytes() == expected.tobytes(), "작은 아이콘의 검수된 원본 글자 영역 불일치")
            evidence = read_json(WORK / "media/Icons32_ko_evidence_v2.json")
            require(evidence["crop_box"] == [8, 6, 24, 22] and evidence["resample"] == "NONE", "작은 아이콘 자르기 규칙")
            require(sha(icon_path) == evidence["expected_png_sha256"], "작은 아이콘 PNG 근거 해시")
            require(digest(icon.tobytes()) == evidence["expected_rgba_sha256"], "작은 아이콘 RGBA 근거 해시")
            require(sha(WORK / "media/IconDecoLabel_ko_32.png") == evidence["source_png_sha256"], "작은 아이콘 원본 그림 해시")
            require(digest(obj(ATLAS_ID, True).get_raw_data()) == ATLAS_OBJECT_SHA256, "아이콘 묶음 원본 객체 해시")
            require(digest(obj(ATLAS_SPRITE_ID, True).get_raw_data()) == ATLAS_SPRITE_SHA256, "작은 Sprite 원본 객체 해시")
            before, after = tree(ATLAS_ID, True), tree(ATLAS_ID)
            require(before["m_TextureFormat"] == after["m_TextureFormat"] == 4, "아이콘 묶음 RGBA32 형식 보존")
            require(len(after["image data"]) == 262144, "아이콘 묶음 원시 바이트 수")
            before["image data"] = after["image data"]
            equal_tree(after, before, "아이콘 묶음 이미지 이외 메타데이터")
            original_pixels = obj(ATLAS_ID, True).read().image.convert("RGBA")
            candidate_pixels = obj(ATLAS_ID).read().image.convert("RGBA")
            result = check_atlas_pixels(original_pixels, candidate_pixels, icon)
            check_sprite_binding(tree(ATLAS_SPRITE_ID))
            require(resolve(ATLAS_SPRITE_ID, tree(ATLAS_SPRITE_ID)["m_RD"]["texture"]) == ATLAS_ID, "작은 Sprite 외부 파일 연결")
            require(obj(ATLAS_SPRITE_ID).get_raw_data() == obj(ATLAS_SPRITE_ID, True).get_raw_data(), "작은 Sprite 메타데이터 변경")
            sprite_image = obj(ATLAS_SPRITE_ID).read().image.convert("RGBA")
            require(sprite_image.size == (16, 16) and sprite_image.tobytes() == icon.tobytes(), "후보 Sprite 재추출 픽셀 불일치")
            sprite_path = output_path.parent / "Icons32_candidate_sprite.png"
            sprite_image.save(sprite_path)
            result.update(texture="sharedassets0.assets/11", sprite="resources.assets/82", sprite_png=str(sprite_path),
                          sprite_png_sha256=sha(sprite_path), sprite_rgba_sha256=digest(sprite_image.tobytes()),
                          unity_cell=[35, 205, 16, 16], png_cell=[35, 35, 16, 16], runtime_readability="NOT_RUN")
            return result
        stage("작은 아이콘 Sprite 재추출·셀 밖 RGBA 불변", atlas_check)
        def code_check():
            require(len(code) == 4 and {(r["method"], r["offset"]): r["source"] for r in code} == CODE_SITES, "코드 번역 위치 허용 목록")
            for row in code:
                require(row["assembly_sha256"] == sha(SOURCE / CODE_REL), "코드 원본 해시")
                require(row["source_sha256"] == digest(row["source"].encode()), "코드 원문 해시")
                check_controls(row["source"], row["expected"], row["id"])
            tool = WORK / "toolchain/TextPatch/TextPatch.dll"
            result = subprocess.run(["dotnet", str(tool), "verify", str(SOURCE / CODE_REL), str(candidate_root / CODE_REL),
                                     str(WORK / "audit/code_direct_translations.json")],
                                    capture_output=True, text=True, encoding="utf-8", timeout=90)
            require(result.returncode == 0, f"독립 DLL 재검사 실패: {result.stderr.strip()}")
            checked = json.loads(result.stdout.strip())
            require(checked["status"] == "PASS", "독립 DLL 검사 상태")
            checked["verifier_sha256"] = sha(tool)
            return checked
        stage("DLL 모든 명령·메타데이터 재대조", code_check)
        def freshness_check():
            for item in report["verification_inputs"] + build["inputs"]:
                require(sha(item["path"]) == item["sha256"], f"STALE 검사 중 입력 변경: {item['path']}")
            for relative, recorded_file in recorded.items():
                require(sha(candidate_root / relative) == recorded_file["sha256"], f"STALE 검사 중 후보 변경: {relative}")
            return {"unchanged_verification_inputs": len(report["verification_inputs"]), "unchanged_candidate_files": len(recorded)}
        stage("검사 시작·종료 입력 동일성", freshness_check)
        report["status"] = "PASS"
    except Exception as error:
        if str(error).startswith("STALE"):
            report["status"] = "STALE"
        report["failure"] = str(error)
        report["traceback"] = traceback.format_exc()
        print("FAIL: " + str(error), flush=True)
    finally:
        write_json(output_path, report)
    return report["status"] == "PASS"


def self_test():
    """위치·원시 바이트 변조와 실제로 실패했던 셰이더를 거부하는지 확인합니다."""
    results = []
    def reject(label, operation):
        try:
            operation()
        except ValueError as error:
            results.append({"case": label, "status": "PASS", "rejected": str(error)})
        else:
            raise AssertionError(label + ": 결함을 놓쳤습니다.")
    good = "<b>#{0:N2}#</b>\\n다음"
    check_controls(good, good, "정상")
    for label, bad in [
        ("빈 번역", ""), ("자리표시자 형식 손실", good.replace(":N2", "")),
        ("줄바꿈 누락", good.replace("\\n", "")), ("강조 누락", good.replace("#", "")),
        ("태그 변경", good.replace("<b>", "<i>")), ("태그 순서", "<b><i>값</b></i>"),
    ]:
        source = bad if label == "태그 순서" else good
        reject(label, lambda source=source, bad=bad: check_controls(source, bad, label))
    reject("언어 중복 키", lambda: parse_language("A=가\nA=나"))
    reject("번역 위치 교환", lambda: equal_tree({"a": "나", "b": "가"}, {"a": "가", "b": "나"}, "교환"))
    layout_source = load_asset(DATA / "sharedassets1.assets")
    for pair, spec in LAYOUT_SPEC.items():
        original = read_tree(layout_source.file.objects[pair[1]])
        expected = copy.deepcopy(original)
        replace_field(expected, spec["field"], spec["expected"])
        check_layout(pair, original, expected)
        reject(f"배치 수정 누락 {pair[1]}", lambda pair=pair, original=original: check_layout(pair, original, original))
    original = read_tree(layout_source.file.objects[806])
    wrong_width = copy.deepcopy(original)
    wrong_width["m_SizeDelta"]["x"] = -119.0
    reject("설명 폭 기대값 이탈", lambda: check_layout(("sharedassets1.assets", 806), original, wrong_width))
    wrong_other_field = copy.deepcopy(original)
    wrong_other_field["m_SizeDelta"].update(x=-120.0, y=-24.0)
    reject("배치 허용 필드 밖 변경", lambda: check_layout(("sharedassets1.assets", 806), original, wrong_other_field))
    atlas = load_asset(DATA / "sharedassets0.assets").file.objects[11].read().image.convert("RGBA")
    icon = Image.open(WORK / "media/Icons32_ko_16_v2.png").convert("RGBA")
    normal_atlas = atlas.copy()
    normal_atlas.paste(icon, (35, 35))
    check_atlas_pixels(atlas, normal_atlas, icon)
    reject("작은 아이콘 누락", lambda: check_atlas_pixels(atlas, atlas, icon))
    outside_mutation = normal_atlas.copy()
    outside_mutation.putpixel((0, 0), (1, 2, 3, 4))
    reject("작은 아이콘 셀 밖 픽셀 변경", lambda: check_atlas_pixels(atlas, outside_mutation, icon))
    inverted_location = atlas.copy()
    inverted_location.paste(icon, (35, 205))
    reject("Unity/PNG 좌표 상하 반전 오류", lambda: check_atlas_pixels(atlas, inverted_location, icon))
    wrong_sprite = read_tree(load_asset(DATA / "resources.assets").file.objects[82])
    wrong_sprite["m_RD"]["texture"]["m_PathID"] = 10
    reject("작은 Sprite 대상 연결 오류", lambda: check_sprite_binding(wrong_sprite))
    require(WORK.resolve().is_relative_to(ROOT.resolve()), "자체 시험 폴더 범위")
    with tempfile.TemporaryDirectory(prefix="validator_selftest_", dir=WORK) as folder:
        temporary = Path(folder).resolve()
        require(temporary.is_relative_to(WORK.resolve()), "임시 폴더 정리 범위")
        original_path, candidate_path = temporary / "test.assets", temporary / "candidate.assets"
        raw = bytearray(256)
        struct.pack_into(">q", raw, 24, 256)
        struct.pack_into("<qqIi", raw, 64, 1, 0, 4, 42)
        raw[128:132] = b"old!"
        original_path.write_bytes(raw)
        patched = bytearray(raw) + b"new!"
        struct.pack_into(">q", patched, 24, len(patched))
        struct.pack_into("<qI", patched, 72, 128, 4)
        candidate_path.write_bytes(patched)
        def fixture(start, payload):
            record = SimpleNamespace(path_id=1, type_id=42, type="TextAsset", byte_start=start,
                                     byte_size=len(payload), get_raw_data=lambda: payload)
            return SimpleNamespace(file=SimpleNamespace(header=SimpleNamespace(data_offset=128), objects={1: record}))
        old, new = fixture(128, b"old!"), fixture(256, b"new!")
        allow = {("test.assets", 1)}
        require(len(byte_boundary(original_path, candidate_path, old, new, allow)) == 1, "정상 바이트 시험")
        reject("변경 객체 허용 목록 이탈", lambda: byte_boundary(original_path, candidate_path, old, new, set()))
        damaged = bytearray(patched)
        damaged[140] = 1
        candidate_path.write_bytes(damaged)
        reject("원본 미사용 영역 변조", lambda: byte_boundary(original_path, candidate_path, old, new, allow))
        damaged = bytearray(patched) + b"secret"
        struct.pack_into(">q", damaged, 24, len(damaged))
        candidate_path.write_bytes(damaged)
        reject("알 수 없는 후미 데이터", lambda: byte_boundary(original_path, candidate_path, old, new, allow))
        candidate_path.write_bytes(patched)
        missing = SimpleNamespace(file=SimpleNamespace(header=SimpleNamespace(data_offset=128), objects={}))
        reject("객체 삭제", lambda: byte_boundary(original_path, candidate_path, old, missing, allow))
    template = load_asset(DATA / "resources.assets").file.objects[20].get_raw_data()
    probe04 = WORK / "probe04/game" / DATA_NAME / "sharedassets0.assets"
    probe05 = WORK / "probe05/game" / DATA_NAME / "sharedassets0.assets"
    require(probe04.is_file() and probe05.is_file(), "실제 실패·성공 표본 누락")
    failed_shader = load_asset(probe04).file.objects[32].get_raw_data()
    passed_shader = load_asset(probe05).file.objects[32].get_raw_data()
    reject("실제 probe04 검정 글자 셰이더", lambda: check_shader(failed_shader, template, "probe04"))
    check_shader(passed_shader, template, "probe05")
    results.append({"case": "실제 probe05 SDF 셰이더", "status": "PASS",
                    "file_sha256": sha(probe05), "shader_sha256": digest(passed_shader)})
    output = {"status": "PASS", "validator_sha256": sha(__file__), "cases": results,
              "real_bad_case_file_sha256": sha(probe04), "rejected_mutations": len(results) - 1}
    write_json(WORK / "validator_self_test.json", output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", nargs="?", help="build.json 경로 또는 build_id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False))
        raise SystemExit(0)
    if not args.build:
        parser.error("build.json 경로 또는 build_id가 필요합니다.")
    build_path = Path(args.build)
    if not build_path.is_file():
        build_path = WORK / args.build / "build.json"
    output = args.output or build_path.with_name("static_validation.json")
    raise SystemExit(0 if main(build_path, output) else 1)
