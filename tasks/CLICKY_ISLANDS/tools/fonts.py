"""한글 글꼴(Noto Sans KR) 보통·굵게 두 벌을 만듭니다.

원본은 tasks/TFC2/third_party/NotoSansKR 의 가변 글꼴(굵기를 조절할 수 있는 글꼴, OFL 라이선스)입니다.
게임이 일본어·중국어에 Noto Sans JP/SC/TC 보통·굵게를 쓰므로 같은 계열로 맞춥니다.
섬 이름을 한글로 직접 입력할 수 있어야 하므로 글자를 줄이지 않고 전부 넣습니다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, WORK, save, sha

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

SOURCE = ROOT / 'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf'
OUT = WORK / 'fonts'
WEIGHTS = {'NotoSansKR-Regular': 400, 'NotoSansKR-Bold': 700}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'source': SOURCE.relative_to(ROOT).as_posix(), 'source_sha256': sha(SOURCE), 'fonts': []}
    for name, weight in WEIGHTS.items():
        target = OUT / (name + '.ttf')
        if not target.exists():
            font = TTFont(SOURCE)
            # updateFontNames: 글꼴 안의 이름표도 Regular/Bold로 맞춥니다(안 하면 기본값 Thin으로 남음).
            font = instantiateVariableFont(font, {'wght': weight}, inplace=True, updateFontNames=True)
            font.recalcTimestamp = False
            font.save(target)
        reopened = TTFont(target)
        cmap = reopened.getBestCmap()
        hangul = sum(1 for code in range(0xAC00, 0xD7A4) if code in cmap)
        report['fonts'].append({'name': name, 'weight': weight, 'path': target.relative_to(ROOT).as_posix(),
                                'size': target.stat().st_size, 'sha256': sha(target), 'codepoints': len(cmap),
                                'hangul_syllables': hangul, 'has_fvar': 'fvar' in reopened,
                                'os2_weight': reopened['OS/2'].usWeightClass})
        assert hangul == 11172 and 'fvar' not in reopened, name
    save(OUT / 'fonts_report.json', report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
