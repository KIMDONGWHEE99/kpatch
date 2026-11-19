"""게임 안내용 아이콘을 한글 글자 윤곽을 가진 새 벡터로 만듭니다."""
from pathlib import Path
import sys
from common import ROOT, WORK, save, run_gdre

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen


def letters(text, size, width, baseline):
    font = TTFont(ROOT / 'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf')
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = size / font['head'].unitsPerEm
    total = sum(glyphs[cmap[ord(c)]].width for c in text) * scale
    x = (width - total) / 2
    shapes = []
    for char in text:
        glyph = glyphs[cmap[ord(char)]]
        pen = SVGPathPen(glyphs)
        glyph.draw(pen)
        shapes.append('<path fill="#fff7e8" transform="translate(%g %g) scale(%g -%g)" d="%s"/>' % (x, baseline, scale, scale, pen.getCommands()))
        x += glyph.width * scale
    return ''.join(shapes)


def prepare(stage):
    stage.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, size, color, text in [('full_red', 24, '#9d342c', '가득'), ('full_green', 24, '#437142', '가득'), ('purchase', 48, '#765139', '구매')]:
        if size == 24:
            shape = '<rect x="1" y="3" width="22" height="18" rx="3" fill="%s" stroke="#271c17" stroke-width="2"/>' % color
            shape += letters(text, 10, size, 15.5)
        else:
            shape = '<path d="M22 30h5v17h-5z" fill="#553925" stroke="#30241c"/>'
            shape += '<path d="M3 8h42v25H3z" fill="%s" stroke="#30241c" stroke-width="3"/>' % color
            shape += '<path d="M6 11h36v19H6z" fill="#986d47"/>' + letters(text, 17, size, 25.5)
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">%s</svg>' % (size, size, size, size, shape)
        source = stage / (name + '.svg')
        source.write_text(svg, encoding='utf-8')
        entries.append({'source': str(source), 'output': str(stage / (name + '.ctex')), 'png': str(stage / (name + '.png'))})
    save(stage / 'config.json', {'entries': entries, 'report': str(stage / 'report.json')})
    run_gdre(['--path', str(WORK / 'tool_runtime'), '--script', str(Path(__file__).with_name('vector_icons.gd')), '--', str(stage / 'config.json')], 'vector_icons')
    return {entry['source']: Path(entry['output']).read_bytes() for entry in entries}


if __name__ == '__main__':
    prepare(WORK / 'media/korean_vector_icons')
