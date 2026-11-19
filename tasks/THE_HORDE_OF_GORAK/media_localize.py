"""사용자가 승인한 픽셀 문구 교체. 원본 크기·배경·로고를 보존한다."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageChops

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'extracted_private/THE_HORDE_OF_GORAK/steam_26336311/nebula_01/images'
OUT = ROOT / 'working_private/THE_HORDE_OF_GORAK/media_ko_01'
FONT = ROOT / 'working_private/THE_HORDE_OF_GORAK/font_smoke_01/fonts/THOGNotoSansKR-700.ttf'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def center_mask(size, text, font_size, region, pixel=False):
    scale = 1 if pixel else 4
    mask = Image.new('L', (size[0] * scale, size[1] * scale))
    draw = ImageDraw.Draw(mask)
    font = ImageFont.truetype(str(FONT), font_size * scale)
    box = draw.textbbox((0, 0), text, font=font)
    left, top, right, bottom = [v * scale for v in region]
    assert box[2] - box[0] <= right - left and box[3] - box[1] <= bottom - top
    x = (left + right - box[2] + box[0]) / 2 - box[0]
    y = (top + bottom - box[3] + box[1]) / 2 - box[1]
    draw.text((x, y), text, font=font, fill=255)
    if pixel:
        return mask.point(lambda x: 255 if x >= 110 else 0)
    return mask.resize(size, Image.Resampling.LANCZOS)


def build():
    if OUT.exists():
        raise SystemExit('기존 미디어 결과를 덮어쓰지 않습니다.')
    OUT.mkdir(parents=True)
    candidates = json.loads((SOURCE.parent.parent / 'media_review_01/textual_image_candidates.json').read_text(encoding='utf-8'))
    metadata = {row['handle']: row for row in candidates}
    plans = [(215, '테스트', 12), (980, '끝', 26), (1512, '끝', 24), (1820, 'Steam에서\n찜하기!', 0)]
    results = []
    for handle, translated, font_size in plans:
        source_path = SOURCE / f'{handle:05}.png'
        assert digest(source_path) == metadata[handle]['png_sha256']
        original = Image.open(source_path).convert('RGBA')
        changed = original.copy()
        if handle != 1820:
            background, foreground = Counter(original.getdata()).most_common(2)
            for y in range(original.height):
                for x in range(original.width):
                    if original.getpixel((x, y)) == foreground[0]:
                        changed.putpixel((x, y), background[0])
            region = (2, 1, original.width - 2, original.height - 1)
            mask = center_mask(original.size, translated, font_size, region, pixel=True)
            changed.paste(foreground[0], (0, 0), mask)
        else:
            region = (510, 80, 1420, 435)
            for y in range(region[1], region[3]):
                background = original.getpixel((500, y))
                for x in range(region[0], region[2]):
                    changed.putpixel((x, y), background)
            for text, area, size in [('Steam에서', (510, 105, 1420, 240), 140), ('찜하기!', (510, 277, 1420, 412), 140)]:
                mask = center_mask(original.size, text, size, area)
                changed.paste((241, 242, 242, 255), (0, 0), mask)
            assert ImageChops.difference(original.crop((0, 0, 510, 510)), changed.crop((0, 0, 510, 510))).getbbox() is None
        assert changed.size == original.size
        assert ImageChops.difference(original.getchannel('A'), changed.getchannel('A')).getbbox() is None
        output = OUT / f'{handle:05}.png'
        changed.save(output)
        delta = ImageChops.difference(original.convert('RGB'), changed.convert('RGB'))
        results.append({'handle': handle, 'source': metadata[handle]['observed_text'], 'translation': translated,
                        'source_sha256': digest(source_path), 'output_sha256': digest(output), 'output': str(output),
                        'size': original.size, 'changed_bbox': delta.getbbox(), 'alpha_unchanged': True,
                        'logo_unchanged': True if handle == 1820 else None, 'review_status': 'NOT_RUN'})
    report = {'method': '사용자 승인 Python/Pillow 문구 정밀 교체', 'font_sha256': digest(FONT), 'images': results}
    (OUT / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'images': len(results), 'output': str(OUT)}))


if __name__ == '__main__':
    build()
