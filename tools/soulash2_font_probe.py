"""보호 복사본의 SDL_ttf로 글꼴을 시험한다. 게임 실행·GPU 검수가 아니다."""
import argparse
import ctypes as ct
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
import fontTools
from fontTools.ttLib import TTFont
from PIL import Image

BASELINE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"
DEFAULT_OUTPUT = ROOT / "working_private/SOULASH_2/font_probe"
SAMPLE = "한국어 글꼴 시험: 설정 저장 불러오기 체력 123 / ABC xyz !? 가나다 뷁 힣"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class Color(ct.Structure):
    _fields_ = [("r", ct.c_uint8), ("g", ct.c_uint8), ("b", ct.c_uint8), ("a", ct.c_uint8)]


class Rect(ct.Structure):
    _fields_ = [("x", ct.c_int), ("y", ct.c_int), ("w", ct.c_int), ("h", ct.c_int)]


class Surface(ct.Structure):
    _fields_ = [("flags", ct.c_uint32), ("format", ct.c_void_p), ("w", ct.c_int),
                ("h", ct.c_int), ("pitch", ct.c_int), ("pixels", ct.c_void_p),
                ("userdata", ct.c_void_p), ("locked", ct.c_int), ("list_blitmap", ct.c_void_p),
                ("clip_rect", Rect), ("map", ct.c_void_p), ("refcount", ct.c_int)]


class Version(ct.Structure):
    _fields_ = [("major", ct.c_uint8), ("minor", ct.c_uint8), ("patch", ct.c_uint8)]


def bind(library, name, args, result):
    function = getattr(library, name)
    function.argtypes, function.restype = args, result
    return function


def font_metadata(path, license_path=None):
    with TTFont(path, lazy=False) as font:
        cmap = font.getBestCmap() or {}
        names = {}
        for entry in font["name"].names:
            if entry.nameID in (0, 1, 2, 3, 5, 6, 13, 14):
                try:
                    value = entry.toUnicode()
                except Exception as error:
                    value = "DECODE_ERROR: " + repr(error)
                names.setdefault(str(entry.nameID), [])
                if value not in names[str(entry.nameID)]:
                    names[str(entry.nameID)].append(value)
        record = {"path": str(path), "sha256": sha(path), "size": path.stat().st_size,
                  "cmap_count": len(cmap), "hangul_syllable_count": sum(0xAC00 <= x <= 0xD7A3 for x in cmap),
                  "hangul_jamo_count": sum(0x1100 <= x <= 0x11FF for x in cmap),
                  "names": names, "variable_axes": [{"tag": a.axisTag, "default": a.defaultValue,
                  "minimum": a.minValue, "maximum": a.maxValue} for a in font["fvar"].axes] if "fvar" in font else [],
                  "license_file": {"path": str(license_path), "sha256": sha(license_path)} if license_path else None}
        return record, set(cmap)


def loaded_font_modules():
    """실제로 적재된 글꼴 관련 DLL의 경로만 확인한다."""
    kernel, psapi = ct.WinDLL("kernel32", use_last_error=True), ct.WinDLL("psapi", use_last_error=True)
    process = bind(kernel, "GetCurrentProcess", [], ct.c_void_p)()
    modules = (ct.c_void_p * 1024)()
    needed = ct.c_uint32()
    enum = bind(psapi, "EnumProcessModules", [ct.c_void_p, ct.c_void_p, ct.c_uint32, ct.POINTER(ct.c_uint32)], ct.c_int)
    if not enum(process, modules, ct.sizeof(modules), ct.byref(needed)):
        raise ct.WinError(ct.get_last_error())
    if needed.value > ct.sizeof(modules):
        raise RuntimeError("DLL 목록이 준비한 배열을 초과했습니다.")
    get_name = bind(kernel, "GetModuleFileNameW", [ct.c_void_p, ct.c_wchar_p, ct.c_uint32], ct.c_uint32)
    selected = {"sdl2.dll", "sdl2_ttf.dll", "freetype.dll", "zlib1.dll", "bz2.dll", "brotlicommon.dll", "brotlidec.dll", "libpng16.dll"}
    result = []
    for handle in modules[:needed.value // ct.sizeof(ct.c_void_p)]:
        buffer = ct.create_unicode_buffer(32768)
        if not get_name(handle, buffer, len(buffer)):
            raise ct.WinError(ct.get_last_error())
        path = Path(buffer.value)
        if path.name.lower() in selected:
            result.append({"path": str(path), "sha256": sha(path), "size": path.stat().st_size})
    return result


def run(output):
    output = output.resolve()
    output.relative_to((ROOT / "working_private/SOULASH_2").resolve())
    if output.exists():
        raise RuntimeError("기존 시험 결과를 덮어쓰지 않습니다.")
    manifest = ROOT / "extracted_private/SOULASH_2/0.10.4.0.1_20261029/baseline_manifest.json"
    if not manifest.exists():
        raise RuntimeError("원본 복사와 전체 해시 검증이 끝나지 않았습니다.")
    expected = {x["path"]: x["sha256"] for x in json.loads(manifest.read_text(encoding="utf-8"))["files"]}
    for name in ("SDL2.dll", "SDL2_ttf.dll", "freetype.dll"):
        if sha(BASELINE / name) != expected[name]:
            raise RuntimeError("기준선 DLL의 해시가 다릅니다: " + name)
    output.mkdir(parents=True)
    report = {"game_id": "SOULASH_2", "baseline_id": BASELINE.name, "check_id": "G1_FONT_CPU_PROBE",
              "started": now(), "status": "NOT_RUN", "graphics_qa": "NOT_RUN",
              "scope": "SDL_ttf CPU 표면 생성만 검사. 게임 실행·GPU·실제 배치 검수는 아님.",
              "command": sys.argv, "script_sha256": sha(__file__), "baseline_manifest_sha256": sha(manifest),
              "python": sys.version, "platform": platform.platform(), "fonttools": fontTools.__version__,
              "sample": SAMPLE, "required_codepoints": sorted(set(map(ord, SAMPLE))), "fonts": []}
    dll_directory = os.add_dll_directory(str(BASELINE))
    ttf_started = False
    try:
        sdl = ct.CDLL(str(BASELINE / "SDL2.dll"))
        ttf = ct.CDLL(str(BASELINE / "SDL2_ttf.dll"))
        get_error = bind(sdl, "SDL_GetError", [], ct.c_char_p)
        init = bind(ttf, "TTF_Init", [], ct.c_int)
        if init() != 0:
            raise RuntimeError(get_error().decode("utf-8", "replace"))
        ttf_started = True
        ttf_version = bind(ttf, "TTF_Linked_Version", [], ct.POINTER(Version))().contents
        sdl_version = Version()
        bind(sdl, "SDL_GetVersion", [ct.POINTER(Version)], None)(ct.byref(sdl_version))
        report["versions"] = {"sdl": [sdl_version.major, sdl_version.minor, sdl_version.patch],
                              "sdl_ttf": [ttf_version.major, ttf_version.minor, ttf_version.patch]}
        open_font = bind(ttf, "TTF_OpenFont", [ct.c_char_p, ct.c_int], ct.c_void_p)
        close_font = bind(ttf, "TTF_CloseFont", [ct.c_void_p], None)
        render = bind(ttf, "TTF_RenderUTF8_Blended", [ct.c_void_p, ct.c_char_p, Color], ct.POINTER(Surface))
        glyph32 = hasattr(ttf, "TTF_GlyphIsProvided32")
        glyph = bind(ttf, "TTF_GlyphIsProvided32" if glyph32 else "TTF_GlyphIsProvided", [ct.c_void_p, ct.c_uint32 if glyph32 else ct.c_uint16], ct.c_int)
        free_surface = bind(sdl, "SDL_FreeSurface", [ct.POINTER(Surface)], None)
        rw_file = bind(sdl, "SDL_RWFromFile", [ct.c_char_p, ct.c_char_p], ct.c_void_p)
        save_bmp = bind(sdl, "SDL_SaveBMP_RW", [ct.POINTER(Surface), ct.c_void_p, ct.c_int], ct.c_int)
        get_height = bind(ttf, "TTF_FontHeight", [ct.c_void_p], ct.c_int)
        get_ascent = bind(ttf, "TTF_FontAscent", [ct.c_void_p], ct.c_int)
        get_descent = bind(ttf, "TTF_FontDescent", [ct.c_void_p], ct.c_int)
        get_line_skip = bind(ttf, "TTF_FontLineSkip", [ct.c_void_p], ct.c_int)
        report["glyph_api"] = "TTF_GlyphIsProvided32" if glyph32 else "TTF_GlyphIsProvided"
        font_root = BASELINE / "data/mods/core_2/assets/fonts"
        fonts = [(p.stem, p, None) for p in sorted(font_root.glob("*.ttf"))]
        fonts.extend([
            ("Galmuri11-Bold", ROOT / "tasks/MR_MAGEBOY_DEMO/third_party/Galmuri/Galmuri11-Bold.ttf", ROOT / "tasks/MR_MAGEBOY_DEMO/third_party/Galmuri/LICENSE.txt"),
            ("NotoSansKR", ROOT / "tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf", ROOT / "tasks/TFC2/third_party/NotoSansKR/OFL.txt")])
        for label, path, license_path in fonts:
            record, cmap = font_metadata(path, license_path)
            record["id"], record["renders"] = label, []
            record["cmap_missing"] = sorted(set(map(ord, SAMPLE)) - cmap)
            report["fonts"].append(record)
            for size in (14, 18, 24, 32):
                font = open_font(str(path).encode("utf-8"), size)
                if not font:
                    raise RuntimeError(label + ": " + get_error().decode("utf-8", "replace"))
                surface = None
                try:
                    missing = [c for c in sorted(set(map(ord, SAMPLE))) if not glyph(font, c)]
                    surface = render(font, SAMPLE.encode("utf-8"), Color(245, 245, 245, 255))
                    if not surface:
                        raise RuntimeError(get_error().decode("utf-8", "replace"))
                    value = surface.contents
                    if min(value.w, value.h, value.pitch) <= 0 or not value.pixels:
                        raise RuntimeError("생성된 표면의 크기 또는 픽셀 포인터가 잘못됐습니다.")
                    bmp = output / f"{label}_{size}.bmp"
                    rw = rw_file(str(bmp).encode("utf-8"), b"wb")
                    if not rw or save_bmp(surface, rw, 1) != 0:
                        raise RuntimeError(get_error().decode("utf-8", "replace"))
                    png = bmp.with_suffix(".png")
                    with Image.open(bmp) as source_image:
                        rgba = source_image.convert("RGBA")
                        if rgba.size != (value.w, value.h) or not rgba.getchannel("A").getbbox():
                            raise RuntimeError("저장한 표면의 크기 또는 표시 픽셀이 잘못됐습니다.")
                        background = Image.new("RGBA", rgba.size, (32, 32, 36, 255))
                        background.alpha_composite(rgba)
                        background.convert("RGB").save(png)
                    record["renders"].append({"point_size": size, "width": value.w, "height": value.h,
                        "pitch": value.pitch, "font_height": get_height(font), "ascent": get_ascent(font),
                        "descent": get_descent(font), "line_skip": get_line_skip(font), "missing_codepoints": missing,
                        "glyph_coverage": "PASS" if not missing else "FAIL", "surface_status": "PASS",
                        "png": str(png), "png_sha256": sha(png), "bmp": str(bmp), "bmp_sha256": sha(bmp)})
                finally:
                    if surface:
                        free_surface(surface)
                    close_font(font)
        report["loaded_font_modules"] = loaded_font_modules()
        for module in report["loaded_font_modules"]:
            path = Path(module["path"])
            if path.parent.resolve() != BASELINE.resolve() or module["sha256"] != expected[path.name]:
                raise RuntimeError("글꼴 관련 DLL이 기준선 밖에서 적재되었거나 해시가 다릅니다: " + str(path))
        report["status"] = "PASS"
        report["meaning"] = "5개 글꼴의 CPU 렌더링 20건 성공. 원본 글꼴의 한글 누락은 별도 FAIL이며 G1 전체 또는 G5 통과 아님."
    except Exception as error:
        report["status"], report["error"] = "FAIL", repr(error)
        raise
    finally:
        if ttf_started:
            bind(ttf, "TTF_Quit", [], None)()
        dll_directory.close()
        report["finished"] = now()
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "fonts": len(report["fonts"]), "report": str(output / "report.json")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    run(parser.parse_args().output)
