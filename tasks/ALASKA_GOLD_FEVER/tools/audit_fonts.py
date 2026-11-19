"""실제 글꼴 원본과 TMP 글꼴 참조를 번역의 필요 문자에 대조합니다."""
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
import argparse
import hashlib
import json
import os
import struct
import copy
import sys

ROOT = Path(os.path.abspath(__file__)).parents[3]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
import UnityPy
from fontTools.ttLib import TTFont

BASE = ROOT / "source_original/ALASKA_GOLD_FEVER/25782395/game"
OUT = ROOT / "working_private/ALASKA_GOLD_FEVER/font_audit"
SCAN = ROOT / "extracted_private/ALASKA_GOLD_FEVER/25782395/asset_scan"
TRANSLATION = ROOT / "working_private/ALASKA_GOLD_FEVER/translation"


def long_path(path):
    value = os.path.abspath(path)
    return Path(value if value.startswith("\\\\?\\") else "\\\\?\\" + value)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def required_characters():
    required, inputs, unresolved = set(), [], []
    for path in sorted(TRANSLATION.glob("*Translations.json")):
        raw = path.read_bytes()
        rows = json.loads(raw)
        inputs.append({"path": str(path.relative_to(ROOT)), "sha256": sha(raw), "rows": len(rows)})
        for row in rows:
            if not isinstance(row["translation"], str):
                unresolved.append({"collection": row["collection"], "id": row["id"], "key": row["key"], "status": "UNKNOWN"})
                continue
            required.update(ord(c) for c in row["translation"] if not c.isspace())
    value = {"inputs": inputs, "unresolved": unresolved, "codepoints": sorted(required),
             "hangul_codepoints": sorted(c for c in required if 0xAC00 <= c <= 0xD7A3 or 0x1100 <= c <= 0x11FF or 0x3130 <= c <= 0x318F),
             "note": "교정 중간 입력의 필요 문자입니다. 최종 교정·조합 문구 확정 뒤 다시 계산해야 합니다."}
    save("required_characters.json", value)
    return required


def scan_sources():
    required = required_characters()
    data_dir = long_path(BASE / "Alaska Gold Fever_Data")
    paths = sorted(data_dir.glob("*.assets"))
    paths.extend(sorted((data_dir / "StreamingAssets/aa/StandaloneWindows64").glob("*.bundle")))
    fonts, errors, files = [], [], []
    font_dir = OUT / "embedded_fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(paths, 1):
        relative = path.relative_to(long_path(BASE)).as_posix()
        try:
            raw = path.read_bytes()
            env = UnityPy.load(raw)
            found = 0
            for obj in env.objects:
                if obj.type.name != "Font":
                    continue
                found += 1
                row = {"file": relative, "sha256": sha(raw), "asset": path.name if path.suffix == ".assets" else obj.assets_file.name, "path_id": obj.path_id}
                try:
                    tree = obj.read_typetree()
                    data = bytes(tree.get("m_FontData", []))
                    row.update({"name": tree.get("m_Name"), "data_size": len(data), "data_sha256": sha(data)})
                    if data:
                        font_file = font_dir / (sha(data) + ".font")
                        if not font_file.exists():
                            font_file.write_bytes(data)
                        font = TTFont(BytesIO(data), fontNumber=0)
                        cmap = set(font.getBestCmap() or {})
                        row.update({"codepoints": sorted(cmap), "character_count": len(cmap),
                                    "missing_required": sorted(required - cmap),
                                    "missing_hangul": sorted(c for c in required - cmap if 0xAC00 <= c <= 0xD7A3),
                                    "source_font": str(font_file.relative_to(ROOT)), "status": "PASS"})
                        font.close()
                    else:
                        row.update({"status": "UNKNOWN", "reason": "원본 폰트 바이트가 없어 외부·내장 글꼴 참조 추가 조사 필요"})
                except Exception as exc:
                    row.update({"status": "UNKNOWN", "error": str(exc)})
                    errors.append(row.copy())
                fonts.append(row)
            files.append({"file": relative, "sha256": sha(raw), "font_objects": found})
        except Exception as exc:
            errors.append({"file": relative, "status": "UNKNOWN", "error": str(exc)})
        if index % 25 == 0 or index == len(paths):
            print(json.dumps({"scanned": index, "total": len(paths), "fonts": len(fonts), "errors": len(errors)}), flush=True)
    save("source_fonts.json", {"game_id": "ALASKA_GOLD_FEVER", "build_id": "25782395", "finished_at": datetime.now(timezone.utc).isoformat(),
                              "tool_sha256": sha(Path(__file__).read_bytes()), "unitypy_version": UnityPy.__version__,
                              "fonts": fonts, "files": files, "errors": errors})


def scan_tmp():
    from scan_assets import GameGenerator
    generator = GameGenerator("6000.0.62f1")
    generator.load_local_dll_folder(str(ROOT / "extracted_private/ALASKA_GOLD_FEVER/25782395/code/dummy"))
    path = BASE / "Alaska Gold Fever_Data/resources.assets"
    env = UnityPy.load(str(path))
    env.typetree_generator = generator
    rows, errors, externals = [], [], {}
    for obj in list(env.objects):
        if obj.type.name != "MonoBehaviour":
            continue
        head = obj.parse_monobehaviour_head()
        if not ("SDF" in head.m_Name or head.m_Name == "TMP Settings"):
            continue
        row = {"file": path.relative_to(BASE).as_posix(), "sha256": sha(path.read_bytes()), "asset": path.name, "path_id": obj.path_id, "name": head.m_Name}
        externals[path.name] = [external.path for external in obj.assets_file.externals]
        try:
            row["tree"] = obj.read_typetree()
            rows.append(row)
            print(head.m_Name, "PASS", flush=True)
        except Exception as exc:
            row.update({"status": "UNKNOWN", "error": str(exc)})
            errors.append(row)
            print(head.m_Name, "UNKNOWN", str(exc), flush=True)
    save("tmp_resources.json", {"fonts_and_settings": rows, "externals": externals, "errors": errors,
                                "scope": "resources.assets의 이름에 SDF가 있는 글꼴 및 TMP Settings 우선 검사. 전체 스캔과 대조 전에는 완전한 목록으로 보지 않습니다."})


def field_differences(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            if key not in before or key not in after:
                result.append(path + "/" + key)
            else:
                result.extend(field_differences(before[key], after[key], path + "/" + key))
        return result
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [path + "/length"]
        return [item for index, (left, right) in enumerate(zip(before, after)) for item in field_differences(left, right, path + "/" + str(index))]
    return [] if before == after else [path]


def build_probe(verify_existing=False):
    """검수용 한국어 글꼴의 세 필드만 바꾸고 독립 재열기로 검사합니다."""
    from scan_assets import GameGenerator
    source = BASE / "Alaska Gold Fever_Data/resources.assets"
    probe = OUT / "probe/resources.assets"
    if probe.exists() and not verify_existing:
        raise RuntimeError("기존 검수 후보를 덮어쓸 수 없습니다.")
    generator = GameGenerator("6000.0.62f1")
    generator.load_local_dll_folder(str(ROOT / "extracted_private/ALASKA_GOLD_FEVER/25782395/code/dummy"))
    env = UnityPy.load(str(source))
    env.typetree_generator = generator
    obj = env.file.objects[5149]
    source_node = obj._get_typetree_node()
    before = obj.read_typetree()
    expected = copy.deepcopy(before)
    expected["m_SourceFontFile"] = {"m_FileID": 0, "m_PathID": 895}
    expected["m_AtlasPopulationMode"] = 1
    expected["m_IsMultiAtlasTexturesEnabled"] = 1
    expected_fields = ["/m_AtlasPopulationMode", "/m_IsMultiAtlasTexturesEnabled", "/m_SourceFontFile/m_PathID"]
    if field_differences(before, expected) != expected_fields:
        raise RuntimeError("기대하는 원본 글꼴 세 필드와 다릅니다.")
    obj.save_typetree(expected)
    payload = obj.data
    if payload is None:
        raise RuntimeError("변경 객체 직렬화 결과가 없습니다.")
    original_raw = source.read_bytes()
    original = UnityPy.load(original_raw)
    original_object = original.file.objects[5149]
    header = original.file.header
    if header.version < 22 or header.endian != "<":
        raise RuntimeError("지원하지 않는 자산 헤더 형식입니다.")
    needle = struct.pack("<qqIi", original_object.path_id, original_object.byte_start - header.data_offset, original_object.byte_size, original_object.type_id)
    metadata = original_raw[:header.data_offset]
    if metadata.count(needle) != 1:
        raise RuntimeError("변경 객체의 메타데이터 위치가 유일하지 않습니다.")
    position = metadata.index(needle)
    output = bytearray(original_raw)
    output.extend(b"\0" * (-len(output) % 8))
    offset = len(output)
    output.extend(payload)
    struct.pack_into("<qI", output, position + 8, offset - header.data_offset, len(payload))
    struct.pack_into(">q", output, 24, len(output))
    if verify_existing:
        if probe.read_bytes() != bytes(output):
            raise RuntimeError("기존 검수 후보가 기대하는 변경 결과와 다릅니다.")
    else:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(output)
    reopened = UnityPy.load(str(probe))
    reopened.typetree_generator = generator
    errors = []
    if set(original.file.objects) != set(reopened.file.objects):
        errors.append("객체 목록 변경")
    changed_objects = []
    for path_id, old in original.file.objects.items():
        new = reopened.file.objects.get(path_id)
        if new is None or old.get_raw_data() != new.get_raw_data():
            changed_objects.append(path_id)
    if changed_objects != [5149]:
        errors.append("허용 객체 외 원시 바이트 변경")
    # 별도 검수 폴더에는 원본 스크립트가 없으므로 같은 원본 스키마로 값을 독립 판독합니다.
    actual = reopened.file.objects[5149].read_typetree(nodes=source_node)
    actual_fields = field_differences(before, actual)
    if actual_fields != expected_fields or actual != expected:
        errors.append("기대하는 세 필드 외 내용 변경")
    metadata_differences = [index for index, (left, right) in enumerate(zip(original_raw, output)) if left != right]
    allowed_metadata = set(range(24, 32)) | set(range(position + 8, position + 20))
    if set(metadata_differences) - allowed_metadata:
        errors.append("허용된 헤더·객체 위치 메타데이터 외 기존 바이트 변경")
    source_font_tree = reopened.file.objects[895].read_typetree()
    font = TTFont(BytesIO(bytes(source_font_tree["m_FontData"])))
    source_cmap = set(font.getBestCmap())
    font.close()
    test_text = "붐! 쐐기를 꽂아 광산을 튼튼하게 고정하세요."
    missing_source = sorted({ord(c) for c in test_text if not c.isspace()} - source_cmap)
    if missing_source:
        errors.append("검수 문장의 원본 폰트 문자 부족")
    old_chars = {entry["m_Unicode"] for entry in before["m_CharacterTable"]}
    test_new = sorted({ord(c) for c in test_text if not c.isspace()} - old_chars)
    glyphs = {entry["m_Index"] for entry in actual["m_GlyphTable"]}
    broken_glyphs = [entry["m_Unicode"] for entry in actual["m_CharacterTable"] if entry["m_GlyphIndex"] not in glyphs]
    if broken_glyphs:
        errors.append("문자표에서 찾을 수 없는 글리프 참조")
    report = {"game_id": "ALASKA_GOLD_FEVER", "build_id": "25782395", "check_id": "G1_FONT_PROBE_STATIC", "status": "FAIL" if errors else "PASS",
              "source_file": str(source.relative_to(ROOT)), "source_sha256": sha(original_raw),
              "probe_file": str(probe.relative_to(ROOT)), "probe_sha256": sha(output), "tool_sha256": sha(Path(__file__).read_bytes()),
              "source_size": len(original_raw), "probe_size": len(output), "object_count": len(original.file.objects),
              "changed_object_ids": changed_objects, "changed_fields": actual_fields,
              "original_metadata_record_offset": position, "appended_object_offset": offset, "original_payload_size": original_object.byte_size,
              "appended_payload_size": len(payload), "metadata_differing_bytes": metadata_differences,
              "source_font": {"path_id": 895, "name": source_font_tree["m_Name"], "data_sha256": sha(bytes(source_font_tree["m_FontData"]))},
              "test_text": test_text, "test_new_characters": "".join(chr(code) for code in test_new),
              "test_source_missing": missing_source, "broken_glyph_references": broken_glyphs,
              "runtime_status": "NOT_RUN", "finished_at": datetime.now(timezone.utc).isoformat(), "errors": errors}
    save("font_probe_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise RuntimeError("글꼴 검수 후보의 독립 검증이 실패했습니다.")


def build_readable_probe(verify_existing=False, inline=False):
    """동적 생성에 필요한 아틀라스 읽기/쓰기를 추가한 새 검수본을 만듭니다."""
    from scan_assets import GameGenerator
    source = BASE / "Alaska Gold Fever_Data/resources.assets"
    first_probe = OUT / "probe/resources.assets"
    version = "v3" if inline else "v2"
    probe = OUT / ("probe_" + version) / "resources.assets"
    if probe.exists() and not verify_existing:
        raise RuntimeError("기존 검수 후보를 덮어쓸 수 없습니다.")
    first_report = json.loads((OUT / "font_probe_report.json").read_text(encoding="utf-8"))
    raw = first_probe.read_bytes()
    if sha(raw) != first_report["probe_sha256"] or first_report["status"] != "PASS":
        raise RuntimeError("검증된 첫 검수본의 내용 지문이 다릅니다.")
    env = UnityPy.load(raw)
    texture = env.file.objects[504]
    texture_before = texture.read_typetree()
    texture_expected = copy.deepcopy(texture_before)
    texture_expected["m_IsReadable"] = True
    expected_texture_fields = ["/m_IsReadable"]
    pixel_evidence = None
    if inline:
        stream = texture_before["m_StreamData"]
        resource = source.parent / stream["path"]
        if resource.parent != source.parent or stream["path"] != "resources.assets.resS":
            raise RuntimeError("기대한 원본 아틀라스 리소스 경로와 다릅니다.")
        with resource.open("rb") as reader:
            reader.seek(stream["offset"])
            pixels = reader.read(stream["size"])
        if len(pixels) != 1048576 or texture_before["m_CompleteImageSize"] != len(pixels) or texture_before["image data"]:
            raise RuntimeError("원본 아틀라스 픽셀 크기 또는 저장 방식이 기대값과 다릅니다.")
        texture_expected["image data"] = pixels
        texture_expected["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
        expected_texture_fields = ["/image data", "/m_IsReadable", "/m_StreamData/offset", "/m_StreamData/path", "/m_StreamData/size"]
        pixel_evidence = {"source_resource": str(resource.relative_to(ROOT)), "source_resource_sha256": sha(resource.read_bytes()),
                          "source_offset": stream["offset"], "size": len(pixels), "original_pixels_sha256": sha(pixels),
                          "reason": "읽기/쓰기 활성화 시 동기 로딩이 빈 inline 픽셀을 읽는 run01 오류를 해결하도록 원본 픽셀을 자산 내부에 동일하게 저장합니다.",
                          "reference": "https://docs.unity3d.com/kr/6000.0/Manual/LoadingTextureandMeshData-make-compatible.html"}
    if field_differences(texture_before, texture_expected) != expected_texture_fields:
        raise RuntimeError("기대한 원본 아틀라스 설정과 다릅니다.")
    texture.save_typetree(texture_expected)
    original_probe = UnityPy.load(raw)
    header = original_probe.file.header
    original_texture = original_probe.file.objects[504]
    needle = struct.pack("<qqIi", 504, original_texture.byte_start - header.data_offset, original_texture.byte_size, original_texture.type_id)
    if raw[:header.data_offset].count(needle) != 1:
        raise RuntimeError("아틀라스 객체 메타데이터 위치가 유일하지 않습니다.")
    position = raw.index(needle)
    output = bytearray(raw)
    output.extend(b"\0" * (-len(output) % 8))
    offset = len(output)
    output.extend(texture.data)
    struct.pack_into("<qI", output, position + 8, offset - header.data_offset, len(texture.data))
    struct.pack_into(">q", output, 24, len(output))
    if verify_existing:
        if probe.read_bytes() != bytes(output):
            raise RuntimeError("기존 두 번째 검수본이 기대 변경 결과와 다릅니다.")
    else:
        probe.parent.mkdir(parents=True)
        probe.write_bytes(output)
    source_raw = source.read_bytes()
    original = UnityPy.load(str(source))
    generator = GameGenerator("6000.0.62f1")
    generator.load_local_dll_folder(str(ROOT / "extracted_private/ALASKA_GOLD_FEVER/25782395/code/dummy"))
    original.typetree_generator = generator
    checked = UnityPy.load(str(probe))
    errors = []
    if set(original.file.objects) != set(checked.file.objects):
        errors.append("객체 목록 변경")
    changed = [key for key, obj in original.file.objects.items() if key not in checked.file.objects or obj.get_raw_data() != checked.file.objects[key].get_raw_data()]
    if changed != [504, 5149]:
        errors.append("허용 객체 밖 변경")
    changes = {}
    for path_id in (504, 5149):
        source_object = original.file.objects[path_id]
        tree_before = source_object.read_typetree()
        tree_after = checked.file.objects[path_id].read_typetree(nodes=source_object._get_typetree_node())
        changes[str(path_id)] = field_differences(tree_before, tree_after)
    if changes != {"504": expected_texture_fields, "5149": first_report["changed_fields"]}:
        errors.append("허용 필드 밖 변경")
    if checked.file.objects[504].read_typetree() != texture_expected:
        errors.append("기대 아틀라스 내용 불일치")
    if inline:
        candidate_pixels = bytes(checked.file.objects[504].read_typetree()["image data"])
        pixel_evidence["candidate_inline_sha256"] = sha(candidate_pixels)
        pixel_evidence["candidate_inline_size"] = len(candidate_pixels)
        if candidate_pixels != pixels:
            errors.append("원본과 검수본의 아틀라스 픽셀 바이트 불일치")
    font_after = checked.file.objects[5149].read_typetree(nodes=original.file.objects[5149]._get_typetree_node())
    if font_after["m_SourceFontFile"] != {"m_FileID": 0, "m_PathID": 895} or font_after["m_AtlasPopulationMode"] != 1 or font_after["m_IsMultiAtlasTexturesEnabled"] != 1:
        errors.append("동적 글꼴 설정 불일치")
    material = checked.file.objects[5].read_typetree()
    material_textures = dict(material["m_SavedProperties"]["m_TexEnvs"])
    main_texture = material_textures["_MainTex"]["m_Texture"]
    if main_texture != font_after["m_AtlasTextures"][0] or main_texture != {"m_FileID": 0, "m_PathID": 504}:
        errors.append("글꼴·재질·아틀라스 참조 불일치")
    invalid_rects = [entry["m_Index"] for entry in font_after["m_GlyphTable"] if any(entry["m_GlyphRect"][key] < 0 for key in ("m_X", "m_Y", "m_Width", "m_Height")) or entry["m_GlyphRect"]["m_X"] + entry["m_GlyphRect"]["m_Width"] > texture_expected["m_Width"] or entry["m_GlyphRect"]["m_Y"] + entry["m_GlyphRect"]["m_Height"] > texture_expected["m_Height"]]
    if invalid_rects:
        errors.append("아틀라스 범위 밖 글리프 위치")
    old_font_record = first_report["original_metadata_record_offset"]
    allowed_metadata = set(range(24, 32)) | set(range(position + 8, position + 20)) | set(range(old_font_record + 8, old_font_record + 20))
    differences = [index for index, (left, right) in enumerate(zip(source_raw, output)) if left != right]
    if set(differences) - allowed_metadata:
        errors.append("허용 메타데이터 밖 기존 파일 바이트 변경")
    report = {"game_id": "ALASKA_GOLD_FEVER", "build_id": "25782395", "check_id": "G1_FONT_PROBE_" + version.upper() + "_STATIC", "status": "FAIL" if errors else "PASS",
              "source_sha256": sha(source_raw), "first_probe_sha256": sha(raw), "probe_file": str(probe.relative_to(ROOT)),
              "probe_sha256": sha(output), "tool_sha256": sha(Path(__file__).read_bytes()), "probe_size": len(output),
              "object_count": len(original.file.objects), "changed_object_ids": changed, "changed_fields_by_object": changes,
              "metadata_differing_bytes": differences, "atlas": {"path_id": 504, "readable": texture_expected["m_IsReadable"], "width": texture_expected["m_Width"], "height": texture_expected["m_Height"], "stream": texture_expected["m_StreamData"]},
              "material_path_id": 5, "material_texture": main_texture, "invalid_glyph_rects": invalid_rects, "pixel_relocation": pixel_evidence,
              "test_text": first_report["test_text"], "test_new_characters": first_report["test_new_characters"], "runtime_status": "NOT_RUN",
              "source_note": "정적→동적 전환 시 읽기 가능한 아틀라스가 필요하다는 Unity 공식 변경이력을 참고했습니다.",
              "reference": "https://docs.unity3d.com/Packages/com.unity.textmeshpro@3.0/changelog/CHANGELOG.html",
              "finished_at": datetime.now(timezone.utc).isoformat(), "errors": errors}
    save("font_probe_" + version + "_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise RuntimeError("아틀라스 보완 검수본의 독립 검증 실패")


def audit_graph():
    required = required_characters()
    input_path = OUT / "tmp_resources.json"
    values = json.loads(input_path.read_text(encoding="utf-8"))
    rows = {row["path_id"]: row for row in values["fonts_and_settings"]}
    settings = rows[5156]["tree"]
    font_ids = [settings["m_defaultFontAsset"]["m_PathID"]] + [entry["m_PathID"] for entry in settings["m_fallbackFontAssets"]]
    font_rows = []
    glyph_errors = []
    for path_id, row in rows.items():
        tree = row["tree"]
        if "m_CharacterTable" not in tree:
            continue
        glyphs = {entry["m_Index"] for entry in tree["m_GlyphTable"]}
        bad = [entry["m_Unicode"] for entry in tree["m_CharacterTable"] if entry["m_GlyphIndex"] not in glyphs]
        glyph_errors.extend({"path_id": path_id, "unicode": code} for code in bad)
        chars = {entry["m_Unicode"] for entry in tree["m_CharacterTable"]}
        font_rows.append({"path_id": path_id, "name": row["name"], "character_count": len(chars),
                          "glyph_count": len(glyphs), "missing_required_count": len(required - chars),
                          "atlas_population_mode": tree["m_AtlasPopulationMode"], "source_font": tree["m_SourceFontFile"],
                          "multi_atlas": tree["m_IsMultiAtlasTexturesEnabled"], "atlas_size": [tree["m_AtlasWidth"], tree["m_AtlasHeight"]],
                          "fallbacks": tree["m_FallbackFontAssetTable"], "material": tree["m_Material"], "atlas_textures": tree["m_AtlasTextures"]})
    union = set().union(*({entry["m_Unicode"] for entry in rows[path_id]["tree"]["m_CharacterTable"]} for path_id in font_ids))
    missing = sorted(required - union)
    sources = json.loads((OUT / "source_fonts.json").read_text(encoding="utf-8"))
    korean = next(row for row in sources["fonts"] if row["file"] == "Alaska Gold Fever_Data/resources.assets" and row["path_id"] == 895)
    potential = union | set(korean["codepoints"])
    report = {"game_id": "ALASKA_GOLD_FEVER", "build_id": "25782395", "check_id": "G3_FONT_RESOURCES_PRELIMINARY",
              "input_sha256": sha(input_path.read_bytes()), "source_fonts_sha256": sha((OUT / "source_fonts.json").read_bytes()),
              "required_characters_sha256": sha((OUT / "required_characters.json").read_bytes()),
              "required_character_count": len(required), "required_hangul_count": sum(0xAC00 <= code <= 0xD7A3 for code in required),
              "font_assets": font_rows, "global_default_and_fallback_ids": font_ids,
              "original_global_missing_codepoints": missing, "original_global_missing_characters": "".join(chr(code) for code in missing),
              "glyph_reference_errors": glyph_errors, "probe_v2_potential_missing": sorted(required - potential),
              "source_font_id": 895, "source_font_data_sha256": korean["data_sha256"],
              "actual_text_reference_scan": "NOT_RUN", "all_asset_font_crosscheck": "NOT_RUN", "runtime_status": "NOT_RUN",
              "overall_status": "NOT_RUN", "note": "resources.assets의 전역 기본/대체 글꼴에 대한 사전 검사입니다. 전체 표시 객체 참조·최종 번역·동적 생성 실행 증거가 합쳐져야 G3/G5 통과를 판정합니다."}
    save("font_graph_report.json", report)
    print(json.dumps({"required": len(required), "original_missing": report["original_global_missing_characters"], "probe_v2_potential_missing": report["probe_v2_potential_missing"]}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-sources", action="store_true")
    parser.add_argument("--scan-tmp", action="store_true")
    parser.add_argument("--build-probe", action="store_true")
    parser.add_argument("--verify-probe", action="store_true")
    parser.add_argument("--build-readable-probe", action="store_true")
    parser.add_argument("--verify-readable-probe", action="store_true")
    parser.add_argument("--audit-graph", action="store_true")
    parser.add_argument("--build-inline-probe", action="store_true")
    parser.add_argument("--verify-inline-probe", action="store_true")
    parser.add_argument("--check-final-characters", action="store_true")
    args = parser.parse_args()
    if args.scan_sources:
        scan_sources()
    elif args.scan_tmp:
        scan_tmp()
    elif args.build_probe:
        build_probe()
    elif args.verify_probe:
        build_probe(verify_existing=True)
    elif args.build_readable_probe:
        build_readable_probe()
    elif args.verify_readable_probe:
        build_readable_probe(verify_existing=True)
    elif args.audit_graph:
        audit_graph()
    elif args.build_inline_probe:
        build_readable_probe(inline=True)
    elif args.verify_inline_probe:
        build_readable_probe(verify_existing=True, inline=True)
    elif args.check_final_characters:
        check_final_characters()
    else:
        required_characters()


def check_final_characters():
    """확정 번역 입력과 실제 v3 원본 글꼴의 문자 지원만 기본 확인합니다."""
    from scan_assets import GameGenerator
    paths = sorted(TRANSLATION.glob("*Translations.json"))
    dialogue = ROOT / "working_private/ALASKA_GOLD_FEVER/dialogue_translation"
    paths += [dialogue / (name + ".json") for name in ("main_story", "side_quests", "generic", "dlc", "playtest")]
    required, inputs, errors, excluded = set(), [], [], []
    for path in paths:
        raw = path.read_bytes()
        rows = json.loads(raw)
        inputs.append({"path": str(path.relative_to(ROOT)), "sha256": sha(raw), "rows": len(rows)})
        for row in rows:
            value = row.get("translation")
            if not isinstance(value, str):
                if value is None and row.get("review_status") == "OUT_OF_SCOPE" and row.get("korean_original") is None and row.get("key") is None:
                    excluded.append({"path": str(path.relative_to(ROOT)), "id": row.get("id"), "reason": row.get("review_note"), "classification": "기존 한국어가 없는 영어 전용 고아 항목"})
                else:
                    errors.append("문자열이 아닌 번역: " + str(row.get("id")))
            else:
                required.update(ord(c) for c in value if not c.isspace())
    probe_path = OUT / "probe_v3/resources.assets"
    probe_raw = probe_path.read_bytes()
    previous = json.loads((OUT / "font_probe_v3_report.json").read_text(encoding="utf-8"))
    if sha(probe_raw) != previous["probe_sha256"]:
        errors.append("검증된 v3 글꼴 파일 해시 불일치")
    probe = UnityPy.load(probe_raw)
    source_tree = probe.file.objects[895].read_typetree()
    font_data = bytes(source_tree["m_FontData"])
    font = TTFont(BytesIO(font_data))
    cmap = set(font.getBestCmap() or {})
    font.close()
    original_path = BASE / "Alaska Gold Fever_Data/resources.assets"
    original = UnityPy.load(str(original_path))
    generator = GameGenerator("6000.0.62f1")
    generator.load_local_dll_folder(str(ROOT / "extracted_private/ALASKA_GOLD_FEVER/25782395/code/dummy"))
    original.typetree_generator = generator
    node = original.file.objects[5149]._get_typetree_node()
    dynamic = probe.file.objects[5149].read_typetree(nodes=node)
    if dynamic["m_AtlasPopulationMode"] != 1 or dynamic["m_SourceFontFile"] != {"m_FileID": 0, "m_PathID": 895} or not dynamic["m_IsMultiAtlasTexturesEnabled"]:
        errors.append("동적 한국어 글꼴 설정 불일치")
    cached_path = OUT / "tmp_resources.json"
    cached = json.loads(cached_path.read_text(encoding="utf-8"))
    rows = {row["path_id"]: row for row in cached["fonts_and_settings"]}
    settings = rows[5156]["tree"]
    ids = [settings["m_defaultFontAsset"]["m_PathID"]] + [entry["m_PathID"] for entry in settings["m_fallbackFontAssets"]]
    coverage = {}
    for path_id in ids:
        if path_id != 5149 and original.file.objects[path_id].get_raw_data() != probe.file.objects[path_id].get_raw_data():
            errors.append("기존 전역 대체 글꼴 내용 변경: " + str(path_id))
        tree = dynamic if path_id == 5149 else rows[path_id]["tree"]
        coverage[path_id] = {entry["m_Unicode"] for entry in tree["m_CharacterTable"]}
    if original.file.objects[5156].get_raw_data() != probe.file.objects[5156].get_raw_data():
        errors.append("전역 대체 글꼴 연결 변경")
    combined = cmap | set().union(*coverage.values())
    missing = sorted(required - combined)
    if missing:
        errors.append("원본 글꼴과 전역 대체 글꼴에 없는 문자")
    for item in inputs:
        if sha((ROOT / item["path"]).read_bytes()) != item["sha256"]:
            errors.append("검사 중 번역 입력 변경: " + item["path"])
    report = {
        "game_id": "ALASKA_GOLD_FEVER", "build_id": "25782395", "check_id": "FINAL_TRANSLATION_BASIC_CHARACTER_SUPPORT",
        "status": "FAIL" if errors else "PASS", "finished_at": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": sha(Path(__file__).read_bytes()), "inputs": inputs, "row_count": sum(row["rows"] for row in inputs),
        "korean_row_count": sum(row["rows"] for row in inputs) - len(excluded), "excluded_no_korean": excluded,
        "required_codepoints": sorted(required), "required_character_count": len(required),
        "required_hangul_count": sum(0xAC00 <= code <= 0xD7A3 for code in required),
        "probe_path": str(probe_path.relative_to(ROOT)), "probe_sha256": sha(probe_raw),
        "source_font": {"path_id": 895, "name": source_tree["m_Name"], "data_sha256": sha(font_data), "cmap_count": len(cmap)},
        "dynamic_font": {"path_id": 5149, "mode": dynamic["m_AtlasPopulationMode"], "source": dynamic["m_SourceFontFile"], "multi_atlas": dynamic["m_IsMultiAtlasTexturesEnabled"]},
        "source_font_missing_codepoints": sorted(required - cmap),
        "fallback_coverage": [{"codepoint": code, "character": chr(code), "font_ids": [pid for pid, chars in coverage.items() if code in chars]} for code in sorted(required - cmap)],
        "unsupported_codepoints": missing, "unsupported_characters": "".join(chr(c) for c in missing),
        "global_font_ids": ids, "cached_font_table_sha256": sha(cached_path.read_bytes()),
        "scope": "최종 번역표 4개·대사 5개의 문자 지원과 v3 동적 글꼴 설정 기본 확인. 추가 실제 실행이나 전체 숨은 글꼴 조사는 하지 않음.",
        "reuse_condition": "inputs 9개 파일과 probe_sha256, 원본 글꼴/대체 글꼴 자료 해시가 동일할 때 재사용. 번역 변경 시 해당 문자 집합 확인 필요.",
        "errors": errors,
    }
    save("final_character_support.json", report)
    print(json.dumps({key: report[key] for key in ("status", "row_count", "required_character_count", "required_hangul_count", "source_font_missing_codepoints", "fallback_coverage", "unsupported_characters", "errors")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
