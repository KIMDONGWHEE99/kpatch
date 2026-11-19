"""배포용 글꼴을 OFL 출처만으로 준비하고 최신 번역의 문자 범위를 기록한다."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.misc.roundTools import otRound

SOURCE = ROOT / "source_original/SOULASH_2/0.10.4.0.1_20261029/data/mods/core_2/assets/fonts"
PREVIOUS = ROOT / "working_private/SOULASH_2/font_probe/hybrid_20261030_v1"
OUTPUT = ROOT / "working_private/SOULASH_2/font_probe/release_20261030_v1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    (OUTPUT / "fonts").mkdir()
    metric_base = TTFont(SOURCE / "romulus.ttf")
    hybrid = TTFont(PREVIOUS / "fonts/PatchHangulPixel.ttf")
    donors = []
    for label, path, location in [
        ("NotoKR600", PREVIOUS.parent / "noto600/NotoSansKR-SemiBold.ttf", None),
        ("NotoSans600", PREVIOUS / "upstream/NotoSans-Variable.ttf", {"wght": 600, "wdth": 100}),
        ("NotoSC600", PREVIOUS / "upstream/NotoSansSC-Variable.ttf", {"wght": 600}),
    ]:
        font = TTFont(path)
        donors.append((label, path, font, font.getBestCmap(), font.getGlyphSet(location=location)))
    original_cmap, hybrid_cmap = metric_base.getBestCmap(), hybrid.getBestCmap()
    upm = metric_base["head"].unitsPerEm
    fb = FontBuilder(upm, isTTF=True)
    glyphs, widths, cmap, provenance = {}, {}, {}, []
    safe_low = metric_base["hhea"].descent + round(upm * .025)
    safe_high = metric_base["hhea"].ascent - round(upm * .025)
    for cp in [None] + sorted(hybrid_cmap):
        name = ".notdef" if cp is None else f"uni{cp:05X}"
        if cp is not None and cp not in original_cmap:
            # 앞선 검사에서 Noto 출처를 확인한 보충 글자만 복사한다. 원본 Romulus 윤곽은 복사하지 않는다.
            glyph = deepcopy(hybrid["glyf"][hybrid_cmap[cp]])
            width = hybrid["hmtx"][hybrid_cmap[cp]][0]
            donor_name = "existing_verified_Noto_addition"
        else:
            chosen = next((x for x in donors if cp is None or cp in x[3]), None)
            if chosen is None:
                raise ValueError(f"OFL 원본에서 글자를 찾지 못함: {cp}")
            donor_name, _, font, donor_cmap, glyph_set = chosen
            source_name = ".notdef" if cp is None else donor_cmap[cp]
            source_glyph = glyph_set[source_name]
            recording = DecomposingRecordingPen(glyph_set)
            source_glyph.draw(recording)
            width = metric_base["hmtx"][original_cmap[cp]][0] if cp is not None else round(upm * .5)
            scale_y = upm / font["head"].unitsPerEm * .80
            scale_x = width / source_glyph.width if source_glyph.width else scale_y
            offset_y = (metric_base["hhea"].ascent + metric_base["hhea"].descent) / 2 - (846 - 115) / 2 * scale_y
            pen = TTGlyphPen(None)
            recording.replay(TransformPen(pen, (scale_x, 0, 0, scale_y, 0, offset_y)))
            glyph = pen.glyph()
            glyph.recalcBounds({})
            if glyph.numberOfContours:
                height = glyph.yMax - glyph.yMin
                if height > safe_high - safe_low:
                    scale_y *= (safe_high - safe_low) / height
                    pen = TTGlyphPen(None)
                    recording.replay(TransformPen(pen, (scale_x, 0, 0, scale_y, 0, 0)))
                    glyph = pen.glyph()
                    glyph.recalcBounds({})
                    offset_y = (safe_low + safe_high - glyph.yMin - glyph.yMax) / 2
                elif glyph.yMin < safe_low:
                    offset_y += safe_low - glyph.yMin
                elif glyph.yMax > safe_high:
                    offset_y -= glyph.yMax - safe_high
                pen = TTGlyphPen(None)
                recording.replay(TransformPen(pen, (scale_x, 0, 0, scale_y, 0, offset_y)))
                glyph = pen.glyph()
                glyph.recalcBounds({})
        glyphs[name] = glyph
        widths[name] = (otRound(width), glyph.xMin if glyph.numberOfContours else 0)
        if cp is not None:
            cmap[cp] = name
        provenance.append({"codepoint": cp, "glyph": name, "donor": donor_name, "advance": width})
    fb.setupGlyphOrder(list(glyphs))
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(widths)
    fb.setupHorizontalHeader(ascent=metric_base["hhea"].ascent, descent=metric_base["hhea"].descent, lineGap=metric_base["hhea"].lineGap)
    os2_fields = ["sTypoAscender", "sTypoDescender", "sTypoLineGap", "usWinAscent", "usWinDescent", "fsSelection"]
    fb.setupOS2(**{key: getattr(metric_base["OS/2"], key) for key in os2_fields})
    copyrights = sorted(set(n.toUnicode() for _, _, f, _, _ in donors for n in f["name"].names if n.nameID == 0))
    fb.setupNameTable({"familyName": "Patch Hangul UI", "styleName": "Regular", "uniqueFontIdentifier": "Patch Hangul UI Regular 20261030 v1",
                      "fullName": "Patch Hangul UI Regular", "psName": "PatchHangulUI-Regular", "version": "Version 1.000",
                      "copyright": "\n".join(copyrights), "description": "OFL-only derivative. Noto outlines; adjusted advances and line metrics for the Korean patch.",
                      "licenseDescription": "This Font Software is licensed under the SIL Open Font License, Version 1.1.",
                      "licenseInfoURL": "https://openfontlicense.org/open-font-license-official-text/"})
    fb.setupPost()
    fb.setupMaxp()
    path = OUTPUT / "fonts/PatchHangulUI-Regular.ttf"
    fb.save(path)
    results = [{"source": "romulus.ttf", "output": path.name, "sha256": sha(path), "outline_sources": "Noto OFL only", "original_outlines_copied": 0}]
    for name in ["PatchHangulText-Regular.ttf", "PatchHangulText-Bold.ttf"]:
        target = OUTPUT / "fonts" / name
        shutil.copyfile(PREVIOUS / "fonts" / name, target)
        results.append({"source": "Lato-Regular.ttf" if "Regular" in name else "Lato-Bold.ttf", "output": name, "sha256": sha(target), "outline_sources": "Lato and Noto OFL"})
    licenses = [(PREVIOUS / "NotoKR-OFL.txt", "NotoKR-OFL.txt"), (PREVIOUS / "Lato-OFL.txt", "Lato-OFL.txt"),
                (PREVIOUS / "upstream/NotoSans-OFL.txt", "NotoSans-OFL.txt"), (PREVIOUS / "upstream/NotoSansSC-OFL.txt", "NotoSansSC-OFL.txt")]
    for source, filename in licenses:
        shutil.copyfile(source, OUTPUT / filename)
    (OUTPUT / "ui_glyph_provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "BUILT_REQUIRES_INDEPENDENT_VALIDATION", "tool_sha256": sha(__file__),
              "files": results, "metric_reference_sha256": sha(SOURCE / "romulus.ttf"), "hybrid_reference_sha256": sha(PREVIOUS / "fonts/PatchHangulPixel.ttf"),
              "donors": [{"label": label, "path": str(p.relative_to(ROOT)), "sha256": sha(p)} for label, p, *_ in donors],
              "license_sources": ["https://openfontlicense.org/ofl-faq/#32-i-have-a-font-that-needs-a-few-extra-glyphs---can-i-take-them-from-an-ofl-licensed-font-and-copy-them-into-mine",
                                  "https://openfontlicense.org/open-font-license-official-text/"],
              "notes": ["Romulus의 숫자 지표만 참조하며 윤곽·힌팅·이름·라이선스 표를 가져오지 않음", "글자 폭과 줄높이 보존은 별도 SDL 검사 필요", "전체 번역 확정 후 용량 검사를 갱신해야 함", "실제 게임 화면 검수는 부모 담당"]}
    (OUTPUT / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "files": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
