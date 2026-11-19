"""동결 native03의 추가 121문구 독립 교정과 글꼴 준비 근거를 보존한다."""
from __future__ import annotations
import ctypes as C
import ctypes.wintypes as W
import hashlib
import io
import json
import re
import struct
import winreg
from pathlib import Path

from fontTools.ttLib import TTFont
from dat_container import DatFile, utf16z
from native_string_inventory import dialog_fields
from verify_g3 import LogFont, NonClientMetrics

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "working_private/THE_HORDE_OF_GORAK"
NATIVE = WORK / "native_candidate_03"
BASELINE = WORK / "native_candidate_02"
OUT = WORK / "native_review_03"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def chars(values):
    return {ord(c) for text in values for c in text if ord(c) >= 32 and ord(c) != 127}


def tokens(text):
    # &&는 화면에 보이는 &이고, 단일 & 다음 글자는 Windows 단축키이다.
    ampersands, index = [], 0
    while index < len(text):
        if text[index] != "&":
            index += 1
            continue
        if index + 1 >= len(text):
            ampersands.append(["dangling", "&"])
            index += 1
        else:
            ampersands.append(["literal" if text[index + 1] == "&" else "mnemonic", text[index + 1]])
            index += 2
    return {"printf": re.findall(r"%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspn%]", text),
            "ampersands": ampersands, "line_breaks": re.findall(r"\r\n|\r|\n", text)}


def main():
    OUT.mkdir(exist_ok=True)
    inputs, checks = {}, []

    def dependency(path):
        inputs[str(path)] = sha(path.read_bytes())
        return inputs[str(path)]

    def check(name, condition, **detail):
        checks.append({"check": name, "status": "PASS" if condition else "FAIL", **detail})

    def save(name, value):
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit = load(NATIVE / "native_patch_audit.json")
    old = load(BASELINE / "native_patch_audit.json")
    audit_hash = dependency(NATIVE / "native_patch_audit.json")
    dependency(BASELINE / "native_patch_audit.json")
    prior_review = load(BASELINE / "independent_proofread.json")
    dependency(BASELINE / "independent_proofread.json")
    check("baseline_review_identity", prior_review["status"] == "PASS" and prior_review["reviewed"] == 55
          and prior_review["audit_sha256"] == sha((BASELINE / "native_patch_audit.json").read_bytes()))
    old_map = {(r["file"], r["file_offset"], r["source_bytes_sha256"]): r for r in old["translations"]}
    prior_review_map = {(r["file"], r["offset"]): r for r in prior_review["records"]}
    native_bytes = {}
    for row in audit["files"]:
        native_bytes[row["file"]] = (NATIVE / row["file"]).read_bytes()
        check("native_file_identity_" + row["file"], dependency(NATIVE / row["file"]) == row["candidate_sha256"])
    evidence = load(NATIVE / "rea_candidate_resources_evidence.json")
    dependency(NATIVE / "rea_candidate_resources_evidence.json")
    payloads, native_dialogs = {}, []
    for file, file_evidence in evidence.items():
        check("rea_resource_file_identity_" + file, file_evidence["normalized_result"]["artifact"]["sha256"] == sha(native_bytes[file]))
        for resource in file_evidence["normalized_result"]["resources"]:
            location = resource["payload"]["location"]
            raw = native_bytes[file][location["offset"]:location["offset"] + location["bytes"]]
            check(f"resource_payload_{file}_{resource['index']}", sha(raw) == resource["payload"]["sha256"])
            ident = resource["type"].get("id")
            key = file, ident, resource["name"].get("id"), resource["language"].get("id")
            payloads[key] = raw
            if ident == 5:
                fields = dialog_fields(raw)
                font = next((x for x in fields if x["role"] == "font_name"), None)
                native_dialogs.append({"file": file, "id": key[2], "language": key[3], "payload_sha256": sha(raw),
                                       "face": font["source"] if font else None,
                                       "points": struct.unpack_from("<H", raw, font["offset"] - 2)[0] if font else None})
    reviewed, reused = [], []
    for row in audit["translations"]:
        identity = row["file"], row["file_offset"], row["source_bytes_sha256"]
        is_new = identity not in old_map
        if not is_new:
            prior = old_map[identity]
            check(f"prior_55_text_unchanged_{row['file']}_{row['file_offset']}", row["source"] == prior["source"] and row["target"] == prior["target"])
            old_review = prior_review_map[(row["file"], row["file_offset"])]
            check(f"prior_human_review_hash_{row['file']}_{row['file_offset']}", old_review["status"] == "PASS"
                  and old_review["source_sha256"] == row["source_bytes_sha256"]
                  and old_review["target_utf16_sha256"] == sha(row["target"].encode("utf-16le")))
        if row["kind"] == "section_string":
            actual = utf16z(native_bytes[row["file"]], row["file_offset"])[0]
        else:
            key = row["file"], row["resource_type"]["id"], row["resource_name"]["id"], row["resource_language"]["id"]
            raw = payloads[key]
            if row["kind"] == "RT_STRING":
                values, cursor = [], 0
                for _ in range(16):
                    length = struct.unpack_from("<H", raw, cursor)[0]
                    cursor += 2
                    values.append(raw[cursor:cursor + length * 2].decode("utf-16le"))
                    cursor += length * 2
                actual = values[row["string_id"] % 16]
            else:
                actual = next(x["source"] for x in dialog_fields(raw) if x["role"] == row["role"])
        check(f"independent_read_{row['file']}_{row['file_offset']}", actual == row["target"])
        if is_new:
            check(f"new_tokens_{row['file']}_{row['file_offset']}", tokens(row["source"]) == tokens(row["target"]))
            numeric_before, numeric_after = re.findall(r"\d+", row["source"]), re.findall(r"\d+", row["target"])
            natural_four = row["source"] == "4 corners" and row["target"] == "네 모서리"
            check(f"new_numbers_{row['file']}_{row['file_offset']}", numeric_before == numeric_after or natural_four)
        record = {"file": row["file"], "offset": row["file_offset"], "source_sha256": row["source_bytes_sha256"],
                  "target_utf16_sha256": sha(row["target"].encode("utf-16le")), "status": "PASS",
                  "reviewer": "/root/clickteam_format" if is_new else "부모 제작자 55필드 교정 재사용",
                  "independent": True, "kind": row["kind"], "resource_name": row.get("resource_name"), "role": row.get("role"),
                  "checks": ["뜻과 효과/방향/물리 속성 문맥", "한글 문장·띄어쓰기", "단축키 & 및 표시 &&의 순서", "printf 형식·퍼센트·제어 줄바꿈", "새 후보에서 독립 재추출"],
                  "notes": (["4를 한국어 수관형사 네로 옮겼으며 모서리 개수는 동일"] if row["source"] == "4 corners" else [])}
        (reviewed if is_new else reused).append(record)
    check("review_counts", len(reviewed) == 121 and len(reused) == 55 and len(audit["translations"]) == 176)
    check("new_file_counts", sum(r["file"] == "Box2DBouncingBall.mvx" for r in reviewed) == 7 and sum(r["file"] == "cctrans.dll" for r in reviewed) == 114)

    previous_required_path = WORK / "final_validation_02/required_characters.json"
    previous_required = load(previous_required_path)
    dependency(previous_required_path)
    required_native = chars(r["target"] for r in audit["translations"]) | set(range(32, 127))
    union = set(previous_required["union"]) | required_native
    additional = sorted(union - set(previous_required["union"]))
    dat_path = ROOT / "build_candidate/THE_HORDE_OF_GORAK/ko_candidate_02/THOG.dat"
    dat = DatFile.load(dat_path)
    dat_hash = dependency(dat_path)
    check("unchanged_dat_component02", dat_hash == "ead9003686811357da03b1f0e6c36f2fb05a3d6cd9aa4a060bc5b629fb6c9b6c")
    font_reports, font_bytes = [], {}
    prior_fonts = load(WORK / "final_validation_02/embedded_font_union_coverage.json")
    dependency(WORK / "final_validation_02/embedded_font_union_coverage.json")
    for block, prior in zip(DatFile._blocks(dat.one(0x2259).decoded), prior_fonts):
        f = TTFont(io.BytesIO(block.decoded))
        cmap = f.getBestCmap()
        missing = sorted(n for n in union if n not in cmap or cmap[n] == ".notdef")
        digest = sha(block.decoded)
        check("extended_font_union_" + str(block.index), not missing and digest == prior["sha256"])
        font_reports.append({"index": block.index, "sha256": digest, "required_count": len(union), "missing": missing,
                             "weight": f["OS/2"].usWeightClass, "family": f["name"].getDebugName(1)})
        font_bytes[digest] = block.decoded
        f.close()
    dependency(WORK / "final_validation_02/game_font_gdi_coverage.json")
    prior_gdi = load(WORK / "final_validation_02/game_font_gdi_coverage.json")
    check("existing_135_font_routes_reuse", len(prior_gdi) == 135 and all(not r["missing"] and r["selected_font_data_sha256"] in font_bytes for r in prior_gdi))
    save("required_characters.json", {"native176": sorted(required_native), "combined_union": sorted(union), "new_since_g3_02": additional,
         "native_count": len(required_native), "union_count": len(union), "additional_count": len(additional),
         "dat_component_sha256": dat_hash, "native03_audit_sha256": audit_hash,
         "scope": "DAT02·픽셀·유지문구 합집합에 native03 176문구를 추가한 준비 검사. 미조립 fullgame03 바인딩은 하지 않음"})
    save("embedded_extended_union.json", font_reports)
    save("native_dialog_fonts.json", native_dialogs)

    # 창을 만들지 않고 메모리 DC에서 실제 글꼴과 글리프만 조회한다.
    g, u = C.WinDLL("gdi32", use_last_error=True), C.WinDLL("user32", use_last_error=True)
    g.CreateCompatibleDC.argtypes, g.CreateCompatibleDC.restype = [W.HDC], W.HDC
    g.CreateFontIndirectW.argtypes, g.CreateFontIndirectW.restype = [C.POINTER(LogFont)], W.HFONT
    g.SelectObject.argtypes, g.SelectObject.restype = [W.HDC, W.HGDIOBJ], W.HGDIOBJ
    g.GetTextFaceW.argtypes = [W.HDC, C.c_int, W.LPWSTR]
    g.GetGlyphIndicesW.argtypes, g.GetGlyphIndicesW.restype = [W.HDC, W.LPCWSTR, C.c_int, C.POINTER(W.WORD), W.DWORD], W.DWORD
    g.GetFontData.argtypes, g.GetFontData.restype = [W.HDC, W.DWORD, W.DWORD, C.c_void_p, W.DWORD], W.DWORD
    g.AddFontMemResourceEx.argtypes, g.AddFontMemResourceEx.restype = [C.c_void_p, W.DWORD, C.c_void_p, C.POINTER(W.DWORD)], W.HANDLE
    g.RemoveFontMemResourceEx.argtypes, g.DeleteObject.argtypes, g.DeleteDC.argtypes = [W.HANDLE], [W.HGDIOBJ], [W.HDC]
    dc, buffers, handles = g.CreateCompatibleDC(None), [], []
    for data in font_bytes.values():
        buf, count = C.create_string_buffer(data), W.DWORD()
        handle = g.AddFontMemResourceEx(buf, len(data), None, C.byref(count))
        assert handle
        buffers.append(buf)
        handles.append(handle)

    def probe(lf, points, name):
        hf = g.CreateFontIndirectW(C.byref(lf))
        assert hf
        old = g.SelectObject(dc, hf)
        face = C.create_unicode_buffer(128)
        g.GetTextFaceW(dc, 128, face)
        text = "".join(map(chr, sorted(points)))
        ids = (W.WORD * len(text))()
        assert g.GetGlyphIndicesW(dc, text, len(text), ids, 1) != 0xFFFFFFFF
        missing = [ord(c) for c, ident in zip(text, ids) if ident in (0, 0xFFFF)]
        size = g.GetFontData(dc, 0, 0, None, 0)
        assert size != 0xFFFFFFFF
        data = C.create_string_buffer(size)
        assert g.GetFontData(dc, 0, 0, data, size) == size
        row = {"route": name, "requested_family": lf.Name, "selected_family": face.value, "weight": lf.Weight,
               "required_count": len(points), "missing": missing, "selected_font_data_sha256": sha(data.raw)}
        g.SelectObject(dc, old)
        g.DeleteObject(hf)
        return row

    gdi_rows = []
    for weight in (400, 700):
        lf = LogFont()
        lf.Height, lf.Weight, lf.CharSet, lf.Name = -16, weight, 129, "THOG Noto Sans KR"
        row = probe(lf, union, "embedded_representative_" + str(weight))
        check(row["route"], not row["missing"] and row["selected_font_data_sha256"] in font_bytes)
        gdi_rows.append(row)
    ncm = NonClientMetrics()
    ncm.cbSize = C.sizeof(ncm)
    u.SystemParametersInfoW.argtypes = [W.UINT, W.UINT, C.c_void_p, W.UINT]
    assert u.SystemParametersInfoW(41, ncm.cbSize, C.byref(ncm), 0)
    row = probe(ncm.lfMessageFont, required_native, "os_message_font")
    check("os_message_font_glyphs", not row["missing"])
    gdi_rows.append(row)
    for name in ("Tahoma", "Malgun Gothic", "Gulim"):
        lf = LogFont()
        lf.Height, lf.Weight, lf.CharSet, lf.Name = -12, 400, 1, name
        row = probe(lf, required_native, name)
        if name != "Tahoma":
            check(name + "_fallback_glyphs", not row["missing"])
        gdi_rows.append(row)
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontLink\SystemLink") as key:
        links = winreg.QueryValueEx(key, "Tahoma")[0]
    check("tahoma_fallback_registered", any(x.upper().startswith("MALGUN.TTF,") for x in links)
          and any(x.upper().startswith("GULIM.TTC,") for x in links))
    check("native_dialog_font_scope", len([x for x in native_dialogs if x["file"] == "cctrans.dll"]) == 19
          and len([x for x in native_dialogs if x["file"] == "mmfs2.dll"]) == 1
          and all(x["face"] == "Tahoma" for x in native_dialogs))
    for name in ("malgun.ttf", "tahoma.ttf", "gulim.ttc"):
        dependency(Path("C:/Windows/Fonts") / name)
    g.DeleteDC(dc)
    for handle in handles:
        g.RemoveFontMemResourceEx(handle)
    save("gdi_font_routes.json", {"status": "PASS", "records": gdi_rows, "Tahoma_SystemLink": links,
         "native_dialogs": 20, "ui_created": False,
         "scope": "직접 글리프 조회와 등록된 한글 대체 글꼴의 보유 여부. 실제 dialog 자동 폴백 선택·잘림은 UI 검수로 분리",
         "caller_font_boundary": "Box2D 디버그 문구는 호출자 출력 버퍼에 기록되는 형식이며 실제 호출자가 선택하는 글꼴은 이 검사에서 관찰하지 않음. cctrans 효과 이름을 나열하는 호스트의 글꼴도 20개 명시 Tahoma 대화상자와 구분. 이 결과는 글리프 준비 근거이며 모든 표시 소비자의 실제 글꼴 선택을 증명하지 않음"})
    for row in audit["files"]:
        check("frozen_native_unchanged_" + row["file"], sha((NATIVE / row["file"]).read_bytes()) == row["candidate_sha256"])
    check("frozen_native_audit_unchanged", sha((NATIVE / "native_patch_audit.json").read_bytes()) == audit_hash)
    dependency(Path(__file__))
    dependency(ROOT / "tasks/THE_HORDE_OF_GORAK/verify_g3.py")
    dependency(ROOT / "tasks/THE_HORDE_OF_GORAK/native_string_inventory.py")
    errors = [x for x in checks if x["status"] != "PASS"]
    status = "PASS" if not errors else "FAIL"
    save("independent_proofread.json", {"status": status, "audit_sha256": audit_hash, "reviewed": 176,
         "newly_reviewed": 121, "reused_unchanged": 55, "records": reused + reviewed,
         "new_review_method": "독립 에이전트가 추가 원문/번역121개 전부를 두 구간으로 직접 읽고 물리속성·전환방향/효과명·단축키/표시기호·띄어쓰기를 교정. 수정 필요 없음",
         "reuse_basis": "native02 부모교정55필드의 원문·번역·위치 식별자가 동일함을 대조하고 native03에서176값전체를별도원시파서로재확인",
         "not_claimed": ["미조립 fullgame03 검증", "전환 설정/이동 디버그 창의 실제 실행·배치 검수"]})
    save("review_checks.json", checks)
    save("dependencies.json", {"status": status, "inputs": inputs, "full_candidate_binding": "NOT_RUN",
         "scope": "동결 native03 구성요소 지문과 DAT02 글꼴 재사용 입력만 연결. 추후 최종 조립본 해시에 다시 바인딩 필요"})
    summary = {"status": status, "native_audit_sha256": audit_hash, "new_reviewed_fields": 121, "reused_fields": 55,
               "new_reviewed_files": {"Box2DBouncingBall.mvx": 7, "cctrans.dll": 114}, "source_corrections_needed": 0,
               "known_union_count": len(union), "additional_characters_count": len(additional),
               "font_cmap_missing": 0 if all(not x["missing"] for x in font_reports) else None,
               "native_dialogs": 20, "font_route": "Tahoma→등록된Gulim/MalgunGothic; OS메시지글꼴별도조회",
               "caller_font_scope": "Box2D 디버그 출력 버퍼 및 cctrans 효과 이름 소비자의 실제 호스트 글꼴 선택은 미관찰. 명시 Tahoma 대화상자20개·OS메시지 기본 글꼴·등록 대체 글꼴의 보유 여부까지만 검사",
               "full_candidate_binding": "NOT_RUN", "graphics_qa": "NOT_RUN", "checks": len(checks), "errors": errors,
               "scope": "native03 추가표시필드교정·글꼴준비. 전체native G2완료/최종game03조립을대신하지않음"}
    save("g3_native03_preparation.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
