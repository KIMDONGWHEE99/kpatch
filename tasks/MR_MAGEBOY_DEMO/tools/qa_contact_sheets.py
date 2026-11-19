"""실제 실행 캡처를 읽기 쉬운 검수판으로 모읍니다. 합격 판정은 생성하지 않습니다."""
import argparse
import hashlib
import json
import math
from PIL import Image, ImageDraw, ImageFont
from pck_tools import WORK

parser = argparse.ArgumentParser()
parser.add_argument('candidate')
parser.add_argument('group', choices=['menus', 'expanded', 'skills', 'prototypes'])
args = parser.parse_args()
stage = WORK / args.candidate
events = json.loads((stage / 'screens.json').read_text(encoding='utf-8'))
plan = json.loads((stage / f'plan_{args.group}.json').read_text(encoding='utf-8'))
identifiers = {row[0] for row in plan}
# 재촬영된 항목은 마지막 실제 기록을 사용하고 과거 시도는 별도 보존합니다.
latest = {event['id']: event for event in events if event['id'] in identifiers}
events = [latest[row[0]] for row in plan if row[0] in latest]
destination = stage / 'review_sheets' / args.group
destination.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 17)
per_page = 6 if args.group == 'skills' else 4
columns = 3 if args.group == 'skills' else 2
width, height = (520, 440) if args.group == 'skills' else (720, 392)
records = []
for page in range(math.ceil(len(events) / per_page)):
    batch = events[page * per_page: (page + 1) * per_page]
    canvas = Image.new('RGB', (width * columns, height * math.ceil(len(batch) / columns)), '#202328')
    draw = ImageDraw.Draw(canvas)
    for index, event in enumerate(batch):
        source = Image.open(event['image']).convert('RGB')
        assert hashlib.sha256(open(event['image'], 'rb').read()).hexdigest() == event['sha256']
        # 설명창은 실제 캡처의 글자 영역과 테두리를 확대하여 살핍니다.
        if args.group == 'skills' and event['id'].startswith('skill_'):
            rectangles = [record['rect'] for record in event['texts'] if '/ToolTip/' in record['path']]
            if rectangles:
                left = max(0, int(min(rect[0] for rect in rectangles) * 3 - 30))
                top = max(0, int(min(rect[1] for rect in rectangles) * 3 - 30))
                right = min(source.width, int(max(rect[0] + rect[2] for rect in rectangles) * 3 + 30))
                bottom = min(source.height, int(max(rect[1] + rect[3] for rect in rectangles) * 3 + 40))
                source = source.crop((left, top, right, bottom))
        source.thumbnail((width - 12, height - 34))
        x, y = (index % columns) * width, (index // columns) * height
        canvas.paste(source, (x + (width - source.width) // 2, y + 28))
        draw.text((x + 8, y + 5), event['id'], fill='white', font=font)
    target = destination / f'{page + 1:02}.png'
    canvas.save(target)
    records.append({'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                    'source_captures': [{'id': event['id'], 'sha256': event['sha256']} for event in batch]})
(destination / 'index.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'sheets': len(records), 'captures': len(events), 'directory': str(destination)}, ensure_ascii=False))
