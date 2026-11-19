"""최종 조립본의 교정·필요 문자·내장/Windows 글꼴 경로를 정적으로 연결한다."""
from __future__ import annotations
import ctypes as C
import ctypes.wintypes as W
import hashlib
import io
import json
import struct
import winreg
from pathlib import Path

from fontTools.ttLib import TTFont
from dat_container import DatFile, utf16z
from extra_chunk_review import parse_player_controls
from native_string_inventory import dialog_fields

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "working_private/THE_HORDE_OF_GORAK"
OUT = WORK / "final_validation_02"
CANDIDATE = ROOT / "build_candidate/THE_HORDE_OF_GORAK/ko_candidate_02"
NATIVE = WORK / "native_candidate_02"
EXTRACTED = WORK / "validation_02/nebula_candidate"
FAMILY = "THOG Noto Sans KR"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def characters(values):
    return {ord(c) for value in values for c in value if ord(c) >= 32 and ord(c) != 127}


class LogFont(C.Structure):
    _fields_ = [(x, W.LONG) for x in ("Height", "Width", "Escapement", "Orientation", "Weight")] + [
        (x, C.c_ubyte) for x in ("Italic", "Underline", "StrikeOut", "CharSet", "OutPrecision", "ClipPrecision", "Quality", "PitchAndFamily")] + [("Name", W.WCHAR * 32)]


class NonClientMetrics(C.Structure):
    _fields_ = [("cbSize", W.UINT), ("iBorderWidth", C.c_int), ("iScrollWidth", C.c_int), ("iScrollHeight", C.c_int),
                ("iCaptionWidth", C.c_int), ("iCaptionHeight", C.c_int), ("lfCaptionFont", LogFont),
                ("iSmCaptionWidth", C.c_int), ("iSmCaptionHeight", C.c_int), ("lfSmCaptionFont", LogFont),
                ("iMenuWidth", C.c_int), ("iMenuHeight", C.c_int), ("lfMenuFont", LogFont),
                ("lfStatusFont", LogFont), ("lfMessageFont", LogFont), ("iPaddedBorderWidth", C.c_int)]


def main():
    OUT.mkdir(exist_ok=True)
    checks, dependencies = [], {}

    def check(label, condition, **detail):
        checks.append({"check": label, "status": "PASS" if condition else "FAIL", **detail})

    def dependency(path):
        dependencies[str(path)] = sha(path.read_bytes())
        return dependencies[str(path)]

    def save(name, value):
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_path = CANDIDATE / "assembly_manifest.json"
    manifest = load(manifest_path)
    manifest_hash = dependency(manifest_path)
    for row in manifest["files"]:
        path = CANDIDATE / "game" / row["path"]
        check("assembled_file_" + row["path"], dependency(path) == row["candidate_sha256"])
    dat_path = CANDIDATE / "game/THOG.dat"
    dat = DatFile.load(dat_path)
    candidate_hash = sha(dat.original)
    check("candidate02_dat", candidate_hash == "ead9003686811357da03b1f0e6c36f2fb05a3d6cd9aa4a060bc5b629fb6c9b6c")
    g4_path = WORK / "validation_02/g4_summary.json"
    g4 = load(g4_path)
    dependency(g4_path)
    check("g4_same_candidate", g4["status"] == "PASS" and g4["candidate_sha256"] == candidate_hash)
    dependency(EXTRACTED / "input.json")
    check("independent_extract_identity", load(EXTRACTED / "input.json")["sha256"] == candidate_hash)
    package = load(EXTRACTED / "package.json")
    dependency(EXTRACTED / "package.json")
    check("engine_font_format", package["Header"] == "PAMU" and package["ProductBuild"] == 296)
    prior_dependencies = load(WORK / "validation_02/validation_dependencies.json")
    dependency(WORK / "validation_02/validation_dependencies.json")
    for row in prior_dependencies["inputs"]:
        path = ROOT / row["path"]
        check("g4_reuse_input_" + row["path"], dependency(path) == row["sha256"])

    translation_path = WORK / "translation_02/translations.json"
    translations = load(translation_path)
    translation_hash = dependency(translation_path)
    texts = {}
    for row in translations:
        overrides = {r["location"]: r["translation"] for r in row.get("overrides", [])}
        for occurrence in row["occurrences"]:
            texts[occurrence["location"]] = overrides.get(occurrence["location"], row["translation"])
    check("dat_translation_scope", len(translations) == 590 and len(texts) == 855)
    for name in ("proofread_summary.json", "parent_review_completion.json", "audit_summary.json"):
        p = WORK / "translation_02" / name
        value = load(p)
        dependency(p)
        check("dat_review_" + name, value["status"] == "PASS" and value["translations_sha256"] == translation_hash)
    proof = load(WORK / "translation_02/proofread_summary.json")
    check("dat_independent_proofread", proof["parent_review"]["status"] == "PASS" and proof["parent_review"]["unchanged_review_reuse"]["groups"] == 589)
    proof_records = lines(WORK / "translation_02/proofread_records.jsonl")
    dependency(WORK / "translation_02/proofread_records.jsonl")
    check("dat_proofread_record_count", len(proof_records) == 590)
    for row, record in zip(translations, proof_records):
        check("dat_proofread_group_" + str(record["group"]), record["status"] == "PASS"
              and record["source_sha256"] == sha(row["source"].encode("utf-16le"))
              and record["translation_sha256"] == sha(row["translation"].encode("utf-16le")))

    native_audit = load(NATIVE / "native_patch_audit.json")
    native_proof = load(NATIVE / "independent_proofread.json")
    audit_hash = dependency(NATIVE / "native_patch_audit.json")
    dependency(NATIVE / "independent_proofread.json")
    check("native_independent_review_scope", native_audit["status"] == native_proof["status"] == "PASS"
          and native_proof["audit_sha256"] == audit_hash and len(native_audit["translations"]) == native_proof["reviewed"] == 55)
    proof_map = {(r["file"], r["offset"]): r for r in native_proof["records"]}
    check("native_proofread_unique_count", len(proof_map) == len(native_proof["records"]) == 55)
    for row in native_audit["translations"]:
        record = proof_map[(row["file"], row["file_offset"])]
        check(f"native_review_{row['file']}_{row['file_offset']}", record["status"] == "PASS"
              and record["target_utf16_sha256"] == sha(row["target"].encode("utf-16le"))
              and record["source_sha256"] == row["source_bytes_sha256"])
    for row in native_audit["files"]:
        check("native_audit_assembled_" + row["file"], sha((CANDIDATE / "game" / row["file"]).read_bytes()) == row["candidate_sha256"])
    inventory_path = WORK / "investigation_20261031/classification/inventory.jsonl"
    native_inventory_path = WORK / "investigation_20261031/native_string_inventory.jsonl"
    inventory, native_inventory = lines(inventory_path), lines(native_inventory_path)
    dependency(inventory_path)
    dependency(native_inventory_path)
    dat_required = characters(texts.values())
    dat_keep = characters(r["source"] for r in inventory if r["classification"] == "VISIBLE_KEEP")
    native_required = characters(r["target"] for r in native_audit["translations"])
    native_keep = characters(r["source"] for r in native_inventory if r["classification"] == "VISIBLE_KEEP")
    media_path = WORK / "media_ko_01/manifest.json"
    media = load(media_path)
    dependency(media_path)
    pixel_required = characters(r["translation"] for r in media["images"])
    for row in media["images"]:
        check("pixel_text_review_" + str(row["handle"]), row["review_status"] == "PASS"
              and sha(Path(row["output"]).read_bytes()) == row["output_sha256"])
    ascii_runtime = set(range(32, 127))
    required = dat_required | dat_keep | native_required | native_keep | pixel_required | ascii_runtime
    native_all = native_required | native_keep | ascii_runtime
    check("known_characters_bmp", max(required) <= 65535)
    save("required_characters.json", {"dat_translations": sorted(dat_required), "dat_visible_keep": sorted(dat_keep),
         "native_translations": sorted(native_required), "native_visible_keep": sorted(native_keep),
         "pixel_translations": sorted(pixel_required),
         "runtime_ascii": sorted(ascii_runtime), "union": sorted(required),
         "counts": {"dat_translated": len(dat_required), "dat_keep": len(dat_keep), "native_translated": len(native_required),
                    "native_keep": len(native_keep), "pixel_translated": len(pixel_required), "union": len(required)},
         "scope": "알려진 표시 문구·유지 문구와 숫자/서식/ASCII. 임의 외부 파일명·사용자 입력의 모든 유니코드 문자를 보장한다는 뜻은 아님"})

    embedded = DatFile._blocks(dat.one(0x2259).decoded)
    prior_fonts = load(WORK / "validation_02/embedded_fonts.json")
    dependency(WORK / "validation_02/embedded_fonts.json")
    font_reports, unique_fonts = [], {}
    for block, old in zip(embedded, prior_fonts):
        data = block.decoded
        digest = sha(data)
        font = TTFont(io.BytesIO(data))
        cmap = font.getBestCmap()
        missing = sorted(n for n in required if n not in cmap or cmap[n] == ".notdef")
        hangul_missing = [n for n in range(0xAC00, 0xD7A4) if n not in cmap or cmap[n] == ".notdef"]
        report = {"index": block.index, "offset": block.offset, "sha256": digest, "family": font["name"].getDebugName(1),
                  "weight": font["OS/2"].usWeightClass, "required_union_count": len(required), "missing": missing,
                  "full_hangul_missing": hangul_missing, "cmap_count": len(cmap), "embedding_flags": font["OS/2"].fsType,
                  "variable": "fvar" in font, "prior_g4_hash_identical": digest == old["sha256"]}
        check("embedded_font_" + str(block.index), not missing and not hangul_missing and report["prior_g4_hash_identical"]
              and report["family"] == FAMILY and report["embedding_flags"] == 0 and not report["variable"])
        font_reports.append(report)
        unique_fonts[digest] = data
        font.close()
    check("embedded_count", len(font_reports) == 5 and len(unique_fonts) == 2)
    check("pixel_font_matches_approved_embedded_font", media["font_sha256"] in unique_fonts)
    save("embedded_font_union_coverage.json", font_reports)

    # UI를 만들지 않는 메모리 장치 문맥에서 Windows가 실제 선택한 글꼴의 글리프를 조회한다.
    gdi, user = C.WinDLL("gdi32", use_last_error=True), C.WinDLL("user32", use_last_error=True)
    gdi.CreateCompatibleDC.argtypes = [W.HDC]
    gdi.CreateCompatibleDC.restype = W.HDC
    gdi.CreateFontIndirectW.argtypes = [C.POINTER(LogFont)]
    gdi.CreateFontIndirectW.restype = W.HFONT
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [W.HDC, W.HGDIOBJ], W.HGDIOBJ
    gdi.GetTextFaceW.argtypes = [W.HDC, C.c_int, W.LPWSTR]
    gdi.GetGlyphIndicesW.argtypes, gdi.GetGlyphIndicesW.restype = [W.HDC, W.LPCWSTR, C.c_int, C.POINTER(W.WORD), W.DWORD], W.DWORD
    gdi.GetFontData.argtypes, gdi.GetFontData.restype = [W.HDC, W.DWORD, W.DWORD, C.c_void_p, W.DWORD], W.DWORD
    gdi.AddFontMemResourceEx.argtypes, gdi.AddFontMemResourceEx.restype = [C.c_void_p, W.DWORD, C.c_void_p, C.POINTER(W.DWORD)], W.HANDLE
    gdi.RemoveFontMemResourceEx.argtypes = [W.HANDLE]
    gdi.DeleteObject.argtypes, gdi.DeleteDC.argtypes = [W.HGDIOBJ], [W.HDC]
    dc, buffers, handles = gdi.CreateCompatibleDC(None), [], []
    for data in unique_fonts.values():
        buffer, count = C.create_string_buffer(data), W.DWORD()
        handle = gdi.AddFontMemResourceEx(buffer, len(data), None, C.byref(count))
        assert handle
        buffers.append(buffer)
        handles.append(handle)
    font_cache = {}

    def glyphs(lf, points, kind, identity):
        font = gdi.CreateFontIndirectW(C.byref(lf))
        assert font
        old = gdi.SelectObject(dc, font)
        face = C.create_unicode_buffer(128)
        gdi.GetTextFaceW(dc, 128, face)
        text = "".join(map(chr, sorted(points)))
        values = (W.WORD * len(text))()
        result = gdi.GetGlyphIndicesW(dc, text, len(text), values, 1)
        assert result != 0xFFFFFFFF
        missing = [ord(c) for c, n in zip(text, values) if n in (0, 0xFFFF)]
        key = face.value, lf.Weight
        if key not in font_cache:
            size = gdi.GetFontData(dc, 0, 0, None, 0)
            if size == 0xFFFFFFFF:
                font_cache[key] = None
            else:
                raw = C.create_string_buffer(size)
                assert gdi.GetFontData(dc, 0, 0, raw, size) == size
                font_cache[key] = sha(raw.raw)
        row = {"kind": kind, "identity": identity, "requested_family": lf.Name, "selected_family": face.value,
               "height": lf.Height, "weight": lf.Weight, "charset": lf.CharSet, "required_count": len(points),
               "missing": missing, "selected_font_data_sha256": font_cache[key]}
        gdi.SelectObject(dc, old)
        gdi.DeleteObject(font)
        return row

    game_gdi = []
    for block in dat.fonts:
        game_gdi.append(glyphs(LogFont.from_buffer_copy(block.decoded[12:104]), required, "logical", block.handle))
    info = dat.one(0x2258).decoded
    mapping_links = []
    for index in range(22):
        raw = info[index * 96:(index + 1) * 96]
        offset = struct.unpack_from("<I", raw, 92)[0]
        target = next(x for x in font_reports if x["offset"] == offset)
        lf = LogFont.from_buffer_copy(raw[:92])
        mapping_links.append({"index": index, "embedded_index": target["index"], "height": lf.Height,
                              "weight": lf.Weight, "font_sha256": target["sha256"]})
        check("embedded_mapping_" + str(index), lf.Name == FAMILY and lf.Weight == target["weight"] and lf.CharSet == 129)
        game_gdi.append(glyphs(lf, required, "embedded_mapping", index))
    buttons = load(WORK / "validation_02/button_validation.json")
    dependency(WORK / "validation_02/button_validation.json")
    for row in buttons:
        path = EXTRACTED / f"extension_blobs/{row['handle']:04d}.bin"
        blob = path.read_bytes()
        check("button_font_blob_identity_" + str(row["handle"]), sha(blob) == row["blob_sha256"])
        game_gdi.append(glyphs(LogFont.from_buffer_copy(blob[36:128]), required, "button", row["handle"]))
    dialogs = parse_player_controls(dat.one(0x225D).decoded)["dialogs"]
    for dialog in dialogs:
        lf = LogFont()
        lf.Height = -round(dialog["font"]["points"] * 96 / 72)
        lf.Weight, lf.CharSet, lf.Name = 400, 1, dialog["font"]["face"]
        game_gdi.append(glyphs(lf, required, "dat_dialog", dialog["id"]))
    for row in game_gdi:
        check(f"gdi_{row['kind']}_{row['identity']}", not row["missing"] and row["selected_family"] == FAMILY
              and row["selected_font_data_sha256"] in unique_fonts)
    check("font_route_counts", len(dat.fonts) == 28 and len(mapping_links) == 22 and len(buttons) == 81 and len(dialogs) == 4)
    font_ids = {block.handle for block in dat.fonts}
    font_uses = []
    for handle, obj in package["FrameItems"]["Items"].items():
        properties = obj["Properties"]
        for index, paragraph in enumerate(properties.get("ObjectParagraphs", {}).get("Paragraphs", [])):
            font_uses.append({"object": int(handle), "field": f"ObjectParagraphs.Paragraphs.{index}.FontHandle", "font": paragraph["FontHandle"]})
        counter = properties.get("ObjectCounter", {})
        if counter.get("DisplayType") == 5:
            font_uses.append({"object": int(handle), "field": "ObjectCounter.Font", "font": counter["Font"]})
    check("actual_text_font_references_exist", all(row["font"] in font_ids for row in font_uses))
    check("final_progress_font_reference", next(row for row in font_uses if row["object"] == 514)["font"] == 6)
    save("font_usage_graph.json", {"status": "PASS", "candidate_sha256": candidate_hash,
         "logical_font_uses": font_uses, "logical_font_handles_used": sorted({row["font"] for row in font_uses}),
         "logical_font_handles_in_bank": sorted(font_ids), "embedded_mapping_links": mapping_links,
         "button_handles": [row["handle"] for row in buttons],
         "dat_dialogs": [{"id": row["id"], "font": row["font"]} for row in dialogs],
         "note": "문단·숫자 카운터의 글꼴 참조를 최종 의미 추출본에서 새로 수집. 버튼은 독립 LOGFONT, Windows 대화상자는 face/points로 추적"})
    save("game_font_gdi_coverage.json", game_gdi)
    save("embedded_mapping_links.json", mapping_links)

    ncm = NonClientMetrics()
    ncm.cbSize = C.sizeof(ncm)
    user.SystemParametersInfoW.argtypes = [W.UINT, W.UINT, C.c_void_p, W.UINT]
    assert user.SystemParametersInfoW(41, ncm.cbSize, C.byref(ncm), 0)
    system_gdi = [glyphs(ncm.lfMessageFont, native_all, "system_message_font", "SPI_GETNONCLIENTMETRICS")]
    check("system_message_font_known_glyphs", not system_gdi[0]["missing"])
    native_resources = load(NATIVE / "rea_candidate_resources_evidence.json")
    dependency(NATIVE / "rea_candidate_resources_evidence.json")
    dialog_resource = next(r for r in native_resources["mmfs2.dll"]["normalized_result"]["resources"]
                           if r["type"].get("id") == 5 and r["name"].get("id") == 100)
    loc = dialog_resource["payload"]["location"]
    native_blob = (CANDIDATE / "game/mmfs2.dll").read_bytes()[loc["offset"]:loc["offset"] + loc["bytes"]]
    check("native_dialog_payload_identity", sha(native_blob) == dialog_resource["payload"]["sha256"])
    dialog_face = next(r["source"] for r in dialog_fields(native_blob) if r["role"] == "font_name")
    links = {}
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontLink\SystemLink") as key:
        for face in ("Tahoma", "Segoe UI", "Malgun Gothic"):
            links[face] = winreg.QueryValueEx(key, face)[0]
    for face in (dialog_face, "Malgun Gothic", "Gulim"):
        lf = LogFont()
        lf.Height, lf.Weight, lf.CharSet, lf.Name = -12, 400, 1, face
        system_gdi.append(glyphs(lf, native_all, "system_or_linked_font", face))
    malgun = next(r for r in system_gdi if r["identity"] == "Malgun Gothic")
    gulim = next(r for r in system_gdi if r["identity"] == "Gulim")
    check("tahoma_korean_link_registered", dialog_face == "Tahoma" and any(x.upper().startswith("MALGUN.TTF,") for x in links["Tahoma"]))
    check("linked_korean_fonts_known_glyphs", not malgun["missing"] and not gulim["missing"])
    windows_fonts = []
    for name in ("malgun.ttf", "tahoma.ttf", "gulim.ttc"):
        path = Path("C:/Windows/Fonts") / name
        windows_fonts.append({"path": str(path), "sha256": dependency(path), "bytes": path.stat().st_size})
    native_font_report = {"status": "PASS" if not system_gdi[0]["missing"] and not malgun["missing"] and not gulim["missing"] else "FAIL",
                         "message_font": {k: getattr(ncm.lfMessageFont, k) for k, _ in LogFont._fields_},
                         "native_info_dialog_font": dialog_face, "font_link_registry": links, "gdi_glyph_checks": system_gdi,
                         "installed_font_files": windows_fonts, "ui_created": False, "graphics_qa": "NOT_RUN",
                         "scope": "현재 PC의 OS MessageBox 기본 글꼴과 등록된 Tahoma 한글 대체 글꼴의 필요 글리프 확인. 실제 대화상자의 자동 대체 선택·잘림은 관찰하지 않음"}
    save("windows_font_route_coverage.json", native_font_report)
    gdi.DeleteDC(dc)
    for handle in handles:
        gdi.RemoveFontMemResourceEx(handle)

    # 배치가 바뀐 곳은 수정 후 같은 후보를 측정한 근거만 사용한다.
    layout_path = WORK / "alignment_investigation_02/after_layout_summary.json"
    layout = load(layout_path)
    dependency(layout_path)
    check("final_layout_measurement_identity", layout["status"] == "PASS" and layout["candidate_sha256"] == candidate_hash)
    metric_path = layout_path.parent / layout["source"]
    metrics = load(metric_path)
    check("layout_gdi_measurement_digest", dependency(metric_path) == layout["source_sha256"])
    check("layout_gdi_package_identity", metrics["candidate_package_sha256"] == sha((EXTRACTED / "package.json").read_bytes()))
    check("layout_gdi_tool_identity", dependency(WORK / "measure_alignment_fonts.py") == metrics["tool_sha256"])
    dependency(WORK / "alignment_investigation_01/alignment_report.json")
    check("five_final_layout_fields", package["FrameItems"]["Items"]["514"]["Properties"]["ObjectParagraphs"]["Paragraphs"][0]["FontHandle"] == 6
          and package["FontBank"]["Fonts"]["21"]["Height"] == -20
          and struct.unpack_from("<i", info, 1344)[0] == -20
          and package["FrameItems"]["Items"]["510"]["Properties"]["ObjectParagraphs"]["Height"] == 300
          and package["FrameItems"]["Items"]["1000"]["Properties"]["ObjectParagraphs"]["Height"] == 144)
    dependency(Path(__file__))
    check("assembly_manifest_unchanged_during_g3", sha(manifest_path.read_bytes()) == manifest_hash)
    check("candidate_unchanged_during_g3", sha(dat_path.read_bytes()) == candidate_hash)
    errors = [r for r in checks if r["status"] == "FAIL"]
    save("g3_checks.json", checks)
    save("g3_dependencies.json", {"status": "PASS", "inputs": dependencies,
                                  "policy": "입력·글꼴·후보·조립 목록 해시가 바뀌면 해당 결과 STALE"})
    summary = {"status": "PASS" if not errors else "FAIL", "gate": "G3", "scope": "문맥 교정과 글꼴 준비의 정적 검증",
               "assembly_manifest_sha256": manifest_hash, "candidate_dat_sha256": candidate_hash,
               "translations_sha256": translation_hash, "native_audit_sha256": audit_hash,
               "dat_translation_groups": 590, "dat_translation_locations": 855, "native_translation_fields": 55,
               "translated_raster_images": 4, "pixel_proofread": "PASS: media_ko_01/manifest.json의 부모 직접 판독과 PNG 해시 연결",
               "dat_independent_proofread": "PASS: 589종·46개 예외의 동일성 재사용 + 변경된 개발 안내 1종 부모 재교정",
               "native_independent_proofread": "PASS: 55필드 전수 부모 교정과 원문/번역 해시 연결",
               "known_required_union_count": len(required), "logical_fonts": 28, "embedded_fonts": 5,
               "embedded_mappings": 22, "button_fonts": 81, "dat_dialog_fonts": 4, "final_layout_field_changes": 5,
               "font_checks": "5개 내장 TTF의 합집합 문자표를 새로 검사하고, 135개 실제 LOGFONT/대화상자 경로를 GDI로 새로 조회. 선택된 글꼴 바이트 해시가 승인된 TTF와 일치",
               "font_reuse": "G4 글꼴 바이트·맵·버튼 검사는 같은 후보·추출본·TTF 해시를 확인한 뒤 재사용. 55개 native 문구가 포함된 확대 문자 합집합은 이 작업에서 새로 검사",
               "windows_font_route": "현재 시스템 메시지 글꼴과 Tahoma의 등록된 한글 대체 글꼴에 필요한 글리프 존재 확인. 게임 내장 TTF 검사와 분리",
               "unity_fontasset_atlas_material": {"status": "NOT_APPLICABLE", "reason": "Clickteam Fusion 296 PAMU/DAT의 LOGFONT·내장 TrueType 구조이며 Unity/TMP FontAsset과 사전 문자 아틀라스 자산 구조가 아님"},
               "graphics_qa": "NOT_RUN", "runtime_scope": "이 검사는 게임·창을 실행하거나 조작하지 않음. 실제 GPU 렌더링/메모리 글꼴 등록/줄바꿈/클리핑/OS 대화상자 자동 폴백은 부모 G5에 별도 연결해야 함",
               "runtime_unknown_characters": "동적으로 삽입되는 임의 외부 파일명·사용자 입력의 전체 Unicode는 유한 번역 합집합에 포함되지 않음. ASCII와 완성형 한글 전체는 별도 내장 cmap 검사함",
               "checks": len(checks), "errors": errors, "tool_sha256": sha(Path(__file__).read_bytes())}
    save("g3_summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("status", "known_required_union_count", "checks", "errors", "assembly_manifest_sha256")}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
