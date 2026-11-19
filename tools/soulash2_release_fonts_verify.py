"""배포 글꼴의 재열기·출처·문자·줄높이·실제 SDL 폭을 독립 대조한다."""
from datetime import datetime, timezone
import ctypes as ct
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
sys.path.insert(0, str(ROOT / "tools"))
from fontTools.ttLib import TTFont
from soulash2_font_probe import bind

HERE = ROOT / "working_private/SOULASH_2/font_probe/release_20261030_v1"
PREVIOUS = HERE.parent / "hybrid_20261030_v1"
SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    pairs = [("romulus.ttf", "PatchHangulUI-Regular.ttf"), ("Lato-Regular.ttf", "PatchHangulText-Regular.ttf"), ("Lato-Bold.ttf", "PatchHangulText-Bold.ttf")]
    required = set(json.loads((PREVIOUS / "required_codepoints.json").read_text(encoding="utf-8"))["codepoints"])
    preload = set(json.loads((PREVIOUS / "preload_codepoints.json").read_text(encoding="utf-8"))["codepoints"])
    records = []
    dll_dir = os.add_dll_directory(str(SOURCE))
    ttf = ct.CDLL(str(SOURCE / "SDL2_ttf.dll"))
    if bind(ttf, "TTF_Init", [], ct.c_int)():
        raise ValueError("SDL_ttf 초기화 실패")
    open_font = bind(ttf, "TTF_OpenFont", [ct.c_char_p, ct.c_int], ct.c_void_p)
    close_font = bind(ttf, "TTF_CloseFont", [ct.c_void_p], None)
    line_names = ["TTF_FontHeight", "TTF_FontAscent", "TTF_FontDescent", "TTF_FontLineSkip"]
    line_funs = {name: bind(ttf, name, [ct.c_void_p], ct.c_int) for name in line_names}
    glyph_metrics = bind(ttf, "TTF_GlyphMetrics32", [ct.c_void_p, ct.c_uint32] + [ct.POINTER(ct.c_int)] * 5, ct.c_int)
    try:
        for original, output in pairs:
            p = HERE / "fonts" / output
            source_path = SOURCE / "data/mods/core_2/assets/fonts" / original
            target, source = TTFont(p), TTFont(source_path)
            cmap, orig_cmap = target.getBestCmap(), source.getBestCmap()
            checks = {"modern_hangul_all": set(range(0xac00, 0xd7a4)) <= set(cmap), "existing_required": required <= set(cmap),
                      "preload": preload <= set(cmap), "original_characters": set(orig_cmap) <= set(cmap),
                      "original_advances": all(source["hmtx"][name][0] == target["hmtx"][cmap[cp]][0] for cp, name in orig_cmap.items()),
                      "no_reserved_primary_name": all(not any(n in record.toUnicode() for n in ["Lato", "Source", "Romulus"]) for record in target["name"].names if record.nameID in [1, 3, 4, 6, 16, 21, 25])}
            if original == "romulus.ttf":
                # 새 파일은 새 윤곽·표로 만든 글꼴이어야 하며 원본 glyph ID나 힌팅 표를 재사용하지 않는다.
                checks["new_glyph_names"] = set(target.getGlyphOrder()) & set(source.getGlyphOrder()) <= {".notdef"}
                checks["no_original_hint_tables"] = not any(tag in target for tag in ["cvt ", "fpgm", "prep", "GDEF", "gasp"])
                old = TTFont(PREVIOUS / "fonts/PatchHangulPixel.ttf")
                old_cmap = old.getBestCmap()
                checks["hangul_outlines_unchanged"] = all(target["glyf"][cmap[cp]].compile(target["glyf"]) == old["glyf"][old_cmap[cp]].compile(old["glyf"]) for cp in range(0xac00, 0xd7a4))
                old.close()
            else:
                checks["matches_verified_hybrid"] = sha(p) == sha(PREVIOUS / "fonts" / output)
            empty = [cp for cp in range(0xac00, 0xd7a4) if not target["glyf"][cmap[cp]].numberOfContours]
            checks["hangul_nonempty"] = not empty
            sdl_records = []
            for size in [21, 22, 23, 26, 30, 34]:
                handles = [open_font(str(x).encode("utf-8"), size) for x in [source_path, p]]
                if not all(handles):
                    raise ValueError("글꼴 열기 실패")
                try:
                    lines = [{name: fun(handle) for name, fun in line_funs.items()} for handle in handles]
                    differences = []
                    for cp in orig_cmap:
                        values = []
                        for handle in handles:
                            fields = [ct.c_int() for _ in range(5)]
                            if glyph_metrics(handle, cp, *(ct.byref(x) for x in fields)):
                                raise ValueError("글자 지표 읽기 실패")
                            values.append(fields[-1].value)
                        if values[0] != values[1]:
                            differences.append({"codepoint": cp, "advances": values})
                    sdl_records.append({"size": size, "line_equal": lines[0] == lines[1], "lines": lines, "advance_differences": differences})
                finally:
                    for handle in handles:
                        close_font(handle)
            checks["sdl_line_advance_equal"] = all(x["line_equal"] and not x["advance_differences"] for x in sdl_records)
            records.append({"font": output, "sha256": sha(p), "checks": checks, "sdl": sdl_records, "status": "PASS" if all(checks.values()) else "FAIL"})
            source.close()
            target.close()
    finally:
        bind(ttf, "TTF_Quit", [], None)()
        dll_dir.close()
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "tool_sha256": sha(__file__), "status": "PASS" if all(r["status"] == "PASS" for r in records) else "FAIL",
              "fonts": records, "runtime_qa": "NOT_RUN", "latest_corpus_atlas": "NOT_RUN", "scope": "기존 문자 집합과 전체 현대 한글의 구조,원본 폭과 줄높이; 전체 번역 확정 후 용량 재검사 필요"}
    with (HERE / "independent_validation.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "fonts": [{"font": x["font"], "checks": x["checks"]} for x in records]}, ensure_ascii=False))
    spec = importlib.util.spec_from_file_location("preview", PREVIOUS / "preview_hybrid.py")
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    preview.OUT = HERE / "cpu_preview"
    preview.FONTS = [("original_pixel", SOURCE / "data/mods/core_2/assets/fonts/romulus.ttf"),
                     ("previous_hybrid", PREVIOUS / "fonts/PatchHangulPixel.ttf"),
                     ("release_ui", HERE / "fonts/PatchHangulUI-Regular.ttf"),
                     ("release_regular", HERE / "fonts/PatchHangulText-Regular.ttf"),
                     ("release_bold", HERE / "fonts/PatchHangulText-Bold.ttf")]
    preview.main()


if __name__ == "__main__":
    main()
