"""OFL Noto Sans의 누락 문자만 더하고 기존 글리프를 독립 비교합니다."""
from __future__ import annotations

import io
import json
from pathlib import Path

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from font_builder import inspect_font, sha, write_new

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/COBALT_MINER'
UPSTREAM = ROOT / 'working_private/SOULASH_2/font_probe/hybrid_20261030_v1/upstream'
OUTPUT = WORK / 'font_complete_02'
CODEPOINTS = [0x104, 0x105, 0x106, 0x107, 0x118, 0x119, 0x141, 0x142,
              0x15A, 0x15B, 0x179, 0x17A, 0x17B, 0x17C]


def outline(font, name):
    glyphs = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    return pen.value


def build():
    donor_path = UPSTREAM / 'NotoSans-Variable.ttf'
    donor_license = UPSTREAM / 'NotoSans-OFL.txt'
    assert sha(donor_path.read_bytes()) == 'bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d'
    assert sha(donor_license.read_bytes()) == 'cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a'
    results = []
    required = set(range(0xAC00, 0xD7A4)) | set(range(0x1100, 0x1200)) | set(range(0x3131, 0x318F)) | set(range(32, 127)) | set(CODEPOINTS)
    for weight in (400, 700):
        source = WORK / 'font_smoke_01/fonts' / f'CobaltNotoSansKR-{weight}.ttf'
        old = TTFont(source, recalcTimestamp=False)
        font = TTFont(source, recalcTimestamp=False)
        donor = instantiateVariableFont(TTFont(donor_path, recalcTimestamp=False), {'wght': weight, 'wdth': 100}, inplace=True)
        assert font['head'].unitsPerEm == donor['head'].unitsPerEm == 1000
        old_order = list(font.getGlyphOrder())
        added = []
        for cp in CODEPOINTS:
            assert cp not in font.getBestCmap()
            donor_name = donor.getBestCmap()[cp]
            name = f'cobalt_polish_{cp:04x}'
            pen = DecomposingRecordingPen(donor.getGlyphSet())
            donor.getGlyphSet()[donor_name].draw(pen)
            glyph_pen = TTGlyphPen(None)
            pen.replay(glyph_pen)
            font['glyf'][name] = glyph_pen.glyph()
            font['hmtx'].metrics[name] = donor['hmtx'].metrics[donor_name]
            if 'vmtx' in font:
                font['vmtx'].metrics[name] = (1000, 0)
            for table in font['cmap'].tables:
                if table.isUnicode() and table.format in (4, 12):
                    table.cmap[cp] = name
            added.append(name)
        font.setGlyphOrder(old_order + added)
        font['name'].setName(f'CobaltNotoSansKR-{weight}-Polish-v2', 3, 3, 1, 0x409)
        font['name'].setName('Version 1.002; Cobalt Korean and Polish coverage', 5, 3, 1, 0x409)
        font['head'].fontRevision = 1.002
        stream = io.BytesIO()
        font.save(stream)
        output = stream.getvalue()
        checked = TTFont(io.BytesIO(output), recalcTimestamp=False)
        assert checked.getGlyphOrder()[:len(old_order)] == old_order
        assert len(checked.getGlyphOrder()) == len(old_order) + len(CODEPOINTS)
        # 모든 기존 글자 모양과 가로·세로 폭을 재개방 글꼴에서 직접 대조합니다.
        for name in old_order:
            assert old['glyf'][name].compile(old['glyf']) == checked['glyf'][name].compile(checked['glyf']), name
            assert old['hmtx'].metrics[name] == checked['hmtx'].metrics[name], name
            if 'vmtx' in old:
                assert old['vmtx'].metrics[name] == checked['vmtx'].metrics[name], name
        for cp in CODEPOINTS:
            name = checked.getBestCmap()[cp]
            donor_name = donor.getBestCmap()[cp]
            # TrueType 저장 과정의 정수 반올림을 적용한 윤곽을 별도로 비교합니다.
            pen = DecomposingRecordingPen(donor.getGlyphSet())
            donor.getGlyphSet()[donor_name].draw(pen)
            expected_pen = TTGlyphPen(None)
            pen.replay(expected_pen)
            expected_glyph = expected_pen.glyph()
            actual = checked['glyf'][name]
            assert list(actual.coordinates) == list(expected_glyph.coordinates)
            assert list(actual.endPtsOfContours) == list(expected_glyph.endPtsOfContours)
            assert checked['hmtx'].metrics[name] == donor['hmtx'].metrics[donor_name]
        result = inspect_font(output, required)
        result.update(input_sha256=sha(source.read_bytes()), old_glyphs_unchanged=len(old_order), added_codepoints=CODEPOINTS,
                      donor_outline_and_metrics='PASS', original_outline_and_metrics='PASS')
        results.append(result)
        write_new(OUTPUT / 'fonts' / source.name, output)
        old.close()
        font.close()
        checked.close()
        donor.close()
    write_new(OUTPUT / 'fonts/NotoSansKR-OFL.txt', (WORK / 'font_smoke_01/fonts/OFL.txt').read_bytes())
    write_new(OUTPUT / 'fonts/NotoSans-OFL.txt', donor_license.read_bytes())
    report = dict(status='PASS', runtime='NOT_RUN', builder_sha256=sha(Path(__file__).read_bytes()),
                  donor_source=str(donor_path), donor_sha256=sha(donor_path.read_bytes()),
                  donor_license_sha256=sha(donor_license.read_bytes()),
                  donor_manifest_sha256=sha((UPSTREAM / 'source_manifest.json').read_bytes()), fonts=results,
                  scope='기존 한글·숫자·기타 모든 글리프 원시 윤곽과 폭 보존, 폴란드어 누락 14자만 추가')
    write_new(OUTPUT / 'build_report.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'status': 'PASS', 'fonts': [{k: r[k] for k in ('weight', 'sha256', 'missing', 'old_glyphs_unchanged')} for r in results]}))


if __name__ == '__main__':
    build()
