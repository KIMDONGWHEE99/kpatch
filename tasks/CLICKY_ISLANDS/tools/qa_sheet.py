"""검수 캡처에서 필요한 영역만 잘라 한 장으로 모읍니다(판독용). 원본 캡처는 그대로 둡니다.

사용: python qa_sheet.py <run_id> <출력 이름> <캡처 이름>:x0,y0,x1,y1 [...] [--scale=1.0] [--columns=2]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, WORK

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from PIL import Image, ImageDraw


def main():
    run_id, out_name = sys.argv[1], sys.argv[2]
    scale = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--scale=')), 1.0))
    columns = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--columns=')), 2))
    states = WORK / 'qa' / run_id / 'states'
    crops = []
    for spec in [a for a in sys.argv[3:] if not a.startswith('--')]:
        name, box = spec.rsplit(':', 1)
        image = Image.open(states / (name + '.png')).convert('RGB').crop(tuple(int(v) for v in box.split(',')))
        if scale != 1.0:
            image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
        crops.append((name, image))
    width = max(image.width for _, image in crops)
    height = max(image.height for _, image in crops) + 16
    rows = (len(crops) + columns - 1) // columns
    sheet = Image.new('RGB', (width * columns, height * rows), (60, 60, 70))
    draw = ImageDraw.Draw(sheet)
    for index, (name, image) in enumerate(crops):
        x, y = (index % columns) * width, (index // columns) * height
        sheet.paste(image, (x, y + 16))
        draw.text((x + 3, y + 2), name, fill=(255, 255, 0))
    sheets = WORK / 'qa' / run_id / 'sheets'
    sheets.mkdir(exist_ok=True)
    sheet.save(sheets / (out_name + '.png'))
    print(sheets / (out_name + '.png'), sheet.size)


if __name__ == '__main__':
    main()
