"""이미지·영상·소리 파일을 해시와 함께 목록화하고, 이미지 검수판(작은 그림을 모은 판)을 만듭니다(G2 미디어).

판정은 media_review.json에 파일 해시별로 남깁니다. 새 항목의 기본값은 UNKNOWN입니다.
검수판 개수는 고정하지 않고 실제 이미지 수에 따라 정해집니다.
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, RECOVERED, WORK, save, load, sha

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from PIL import Image, ImageDraw

OUT = WORK / 'media'
KINDS = {'.png': 'image', '.svg': 'image', '.ogv': 'video', '.wav': 'audio', '.mp3': 'audio', '.ogg': 'audio'}
PER_SHEET, CELL = 48, 200


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    review_path = OUT / 'media_review.json'
    decided = {r['sha256']: r for r in load(review_path)} if review_path.exists() else {}
    rows = []
    for path in sorted(RECOVERED.rglob('*')):
        rel = path.relative_to(RECOVERED).as_posix()
        if not path.is_file() or path.suffix not in KINDS or rel.startswith('.godot/'):
            continue
        digest = sha(path)
        row = {'file': rel, 'kind': KINDS[path.suffix], 'size': path.stat().st_size, 'sha256': digest,
               'classification': 'MEDIA', 'handling': 'UNKNOWN', 'evidence': None}
        if path.suffix == '.png':
            with Image.open(path) as image:
                row['pixels'] = list(image.size)
        if digest in decided:
            row.update(handling=decided[digest]['handling'], evidence=decided[digest]['evidence'])
        rows.append(row)
    save(OUT / 'media_inventory.json', rows)
    images = [r for r in rows if r['file'].endswith('.png')]
    sheets = []
    for start in range(0, len(images), PER_SHEET):
        group = images[start:start + PER_SHEET]
        columns = 8
        sheet = Image.new('RGB', (columns * CELL, ((len(group) + columns - 1) // columns) * (CELL + 14)), (40, 40, 48))
        draw = ImageDraw.Draw(sheet)
        for index, row in enumerate(group):
            with Image.open(RECOVERED / row['file']) as image:
                image = image.convert('RGBA')
                scale = min(CELL / image.width, CELL / image.height)
                size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
                image = image.resize(size, Image.NEAREST if scale > 1 else Image.LANCZOS)
                x, y = (index % columns) * CELL, (index // columns) * (CELL + 14)
                sheet.paste(image, (x + (CELL - size[0]) // 2, y + (CELL - size[1]) // 2), image)
                draw.text((x + 2, y + CELL), f'{start + index}', fill=(255, 255, 0))
        name = f'sheet_{start // PER_SHEET:02}.png'
        sheet.save(OUT / name)
        sheets.append({'sheet': name, 'first': start, 'files': [r['file'] for r in group]})
    save(OUT / 'sheets.json', sheets)
    summary = {'by_kind': dict(collections.Counter(r['kind'] for r in rows)),
               'handling': dict(collections.Counter(r['handling'] for r in rows)), 'image_sheets': len(sheets),
               'unique_hashes': len({r['sha256'] for r in rows})}
    save(OUT / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
