"""전체 원본 텍스처 목록과 해시별 검수판을 생성합니다."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pck_tools import ROOT, BASELINE, WORK

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from PIL import Image, ImageDraw, ImageFont

media = WORK / 'media'
media.mkdir(exist_ok=True)
pixels = media / 'pixels'
pixels.mkdir(exist_ok=True)
inventory = json.loads((WORK / 'pck_inventory.json').read_text(encoding='utf-8'))
entries = []
for item in inventory:
    path = item.get('path', item.get('name'))
    if not path.endswith('.ctex'):
        continue
    entries.append({'path': path, 'output': str(pixels / ('%04d.png' % len(entries))), 'source_sha256': item.get('sha256')})
config = {'entries': entries, 'report': str(media / 'export_report.json')}
(media / 'config.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
runtime = media / 'runtime'
runtime.mkdir(exist_ok=True)
(runtime / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="MR Media Inspection"\n', encoding='utf-8')
command = [str(ROOT/'tools/gdre_2.6.4/bin/gdre_tools.exe'), '--headless', '--path', str(runtime), '--log-file', str(media/'export.log'), '--script', str(Path(__file__).with_name('export_media.gd')), '--', str(BASELINE/'MR MAGEBOY DEMO.pck'), str(media/'config.json')]
if not (media/'export_report.json').exists():
    with (media/'stdout.log').open('wb') as out:
        process = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT, timeout=300)
    assert process.returncode == 0, process.returncode
report = json.loads((media/'export_report.json').read_text(encoding='utf-8'))
assert len(report) == len(entries) and all(x['status'] == 'PASS' for x in report)
by_hash = defaultdict(list)
for row in report:
    digest = hashlib.sha256(Path(row['output']).read_bytes()).hexdigest()
    row['pixels_sha256'] = digest
    row['source_sha256'] = next(x['source_sha256'] for x in entries if x['path'] == row['path'])
    by_hash[digest].append(row)
unique = []
for digest, rows in by_hash.items():
    first = rows[0]
    unique.append({'id': len(unique), 'sha256': digest, 'output': first['output'], 'width': first['width'], 'height': first['height'], 'paths': [x['path'] for x in rows], 'source_sha256': [x['source_sha256'] for x in rows], 'classification': 'MEDIA', 'disposition': 'UNKNOWN'})
(media/'inventory.json').write_text(json.dumps(unique, ensure_ascii=False, indent=2), encoding='utf-8')
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 12)
sheets = media/'sheets'
sheets.mkdir(exist_ok=True)
per_page = 120
for start in range(0, len(unique), per_page):
    batch = unique[start:start+per_page]
    canvas = Image.new('RGB', (1600, ((len(batch)+9)//10)*120), '#484858')
    draw = ImageDraw.Draw(canvas)
    for offset, row in enumerate(batch):
        x, y = offset%10*160, offset//10*120
        pic = Image.open(row['output']).convert('RGBA')
        pic.thumbnail((154, 94), Image.Resampling.NEAREST)
        canvas.paste(pic, (x+(160-pic.width)//2, y+2), pic)
        draw.text((x+2,y+97), '%04d %dx%d' % (row['id'],row['width'],row['height']), font=font, fill='white')
    canvas.save(sheets/('%03d.png' % (start//per_page)))
(media/'summary.json').write_text(json.dumps({'textures':len(entries),'unique_pixels':len(unique),'sheets':(len(unique)+per_page-1)//per_page,'export_errors':0,'command':command},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'textures':len(entries),'unique_pixels':len(unique),'sheets':(len(unique)+per_page-1)//per_page}))
