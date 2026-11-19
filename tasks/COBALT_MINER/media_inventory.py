"""이미지를 원본 지문별로 묶고 실제 판독할 접촉판을 만듭니다."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01'
OUT = SOURCE.parent / 'media_review_01'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    OUT.mkdir(exist_ok=False)
    media = json.loads((SOURCE / 'media.json').read_text(encoding='utf-8-sig'))
    groups = {}
    for item in media:
        groups.setdefault(item['source_sha256'], []).append(item)
    groups = sorted(groups.values(), key=lambda g: g[0]['handle'])
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 14)
    columns, rows, width, height = 8, 8, 192, 164
    sheets = []
    for start in range(0, len(groups), columns * rows):
        canvas = Image.new('RGB', (columns * width, rows * height), (48, 50, 55))
        draw = ImageDraw.Draw(canvas)
        refs = []
        for slot, group in enumerate(groups[start:start + columns * rows]):
            item = group[0]
            image = Image.open(SOURCE / item['path']).convert('RGBA')
            image.thumbnail((width - 8, height - 30), Image.Resampling.LANCZOS)
            x, y = slot % columns * width, slot // columns * height
            canvas.paste(image, (x + (width - image.width) // 2, y + 2), image)
            draw.text((x + 4, y + height - 25), f"#{item['handle']} {item['Width']}x{item['Height']}", font=font, fill='white')
            refs.append({'slot': slot, 'handles': [g['handle'] for g in group], 'source_sha256': item['source_sha256'],
                         'png_sha256': item['sha256'], 'path': item['path'], 'width': item['Width'], 'height': item['Height'],
                         'classification': 'MEDIA', 'media_action': 'UNKNOWN', 'visual_review': 'NOT_RUN'})
        path = OUT / f'contact_{start // (columns * rows):02d}.png'
        canvas.save(path)
        sheets.append({'path': path.name, 'sha256': digest(path), 'items': refs})
    (OUT / 'contact_index.json').write_text(json.dumps(sheets, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {'image_count': len(media), 'unique_source_images': len(groups), 'contact_sheets': len(sheets),
               'source_media_manifest_sha256': digest(SOURCE / 'media.json'), 'visual_review': 'NOT_RUN'}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary))

if __name__ == '__main__':
    main()
