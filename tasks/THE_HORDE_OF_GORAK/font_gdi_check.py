"""별도 프로세스 메모리에만 글꼴을 등록하여 Windows의 한글 선택을 검증한다."""
import ctypes
import json
from ctypes import wintypes as w

from font_builder import FAMILY, OUT, sha, write_new


def main():
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi.AddFontMemResourceEx.argtypes = [w.LPVOID, w.DWORD, w.LPVOID, ctypes.POINTER(w.DWORD)]
    gdi.AddFontMemResourceEx.restype = w.HANDLE
    gdi.RemoveFontMemResourceEx.argtypes = [w.HANDLE]
    gdi.RemoveFontMemResourceEx.restype = w.BOOL
    gdi.CreateCompatibleDC.argtypes = [w.HDC]
    gdi.CreateCompatibleDC.restype = w.HDC
    gdi.DeleteDC.argtypes = [w.HDC]
    gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [w.DWORD] * 8 + [w.LPCWSTR]
    gdi.CreateFontW.restype = w.HFONT
    gdi.SelectObject.argtypes = [w.HDC, w.HANDLE]
    gdi.SelectObject.restype = w.HANDLE
    gdi.DeleteObject.argtypes = [w.HANDLE]
    gdi.GetTextFaceW.argtypes = [w.HDC, ctypes.c_int, w.LPWSTR]
    gdi.GetGlyphIndicesW.argtypes = [w.HDC, w.LPCWSTR, ctypes.c_int, ctypes.POINTER(w.WORD), w.DWORD]
    gdi.GetGlyphIndicesW.restype = w.DWORD
    handles, buffers, reports, registered = [], [], [], []
    dc = gdi.CreateCompatibleDC(None)
    assert dc
    try:
        for weight in (400, 700):
            path = OUT / "fonts" / f"THOGNotoSansKR-{weight}.ttf"
            data = path.read_bytes()
            buffer = ctypes.create_string_buffer(data)
            buffers.append(buffer)
            count = w.DWORD()
            handle = gdi.AddFontMemResourceEx(buffer, len(data), None, ctypes.byref(count))
            # 동아시아 글꼴은 세로쓰기 얼굴을 포함해 2개로 등록될 수 있다.
            assert handle and count.value >= 1, (weight, ctypes.get_last_error(), count.value)
            handles.append(handle)
            registered.append({"weight": weight, "registered_faces": count.value})
        chars = "".join(chr(c) for c in range(0xAC00, 0xD7A4)) + "그래픽새 게임"
        for weight in (400, 700):
            font = gdi.CreateFontW(-24, 0, 0, 0, weight, 0, 0, 0, 129, 0, 0, 0, 0, FAMILY)
            assert font
            previous = gdi.SelectObject(dc, font)
            try:
                face = ctypes.create_unicode_buffer(128)
                assert gdi.GetTextFaceW(dc, 128, face)
                glyphs = (w.WORD * len(chars))()
                assert gdi.GetGlyphIndicesW(dc, chars, len(chars), glyphs, 1) != 0xFFFFFFFF
                missing = sorted(set(ord(c) for c, glyph in zip(chars, glyphs) if glyph == 0xFFFF))
                assert face.value == FAMILY and not missing, (face.value, missing)
                reports.append({"weight": weight, "requested_family": FAMILY, "actual_family": face.value,
                                "font_sha256": sha((OUT / "fonts" / f"THOGNotoSansKR-{weight}.ttf").read_bytes()),
                                "tested_characters": len(chars), "missing": missing, "status": "PASS"})
            finally:
                gdi.SelectObject(dc, previous)
                gdi.DeleteObject(font)
    finally:
        gdi.DeleteDC(dc)
        for handle in handles:
            gdi.RemoveFontMemResourceEx(handle)
    report = {"status": "PASS", "method": "AddFontMemResourceEx→CreateFontW→GetTextFaceW/GetGlyphIndicesW",
              "scope": "이 검사 프로세스에서만 메모리에 글꼴 등록. 게임 그래픽 QA를 대체하지 않음", "registered": registered, "fonts": reports}
    write_new(OUT / "gdi_font_check.json", (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
