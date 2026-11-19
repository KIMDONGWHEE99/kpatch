"""PE 아이콘·비트맵을 위치·지문과 함께 검수용으로 추출합니다."""
import io
import json
import struct
from pathlib import Path
from PIL import Image, ImageDraw
import native_inventory as inventory

ROOT, BASE, OUT = inventory.ROOT, inventory.BASE, inventory.OUT

def main():
    records = [json.loads(x) for x in (OUT / 'native_resources.jsonl').read_text(encoding='utf-8').split('\n') if x]
    rows, unique = [], {}
    dest = OUT / 'media'
    dest.mkdir(exist_ok=True)
    for row in records:
        typ = row['type'].get('id')
        if typ not in (2, 3, 14):
            continue
        path = BASE / row['file']
        data = path.read_bytes()
        payload = row['payload']
        offset, size = payload['location']['offset'], payload['location']['bytes']
        raw = data[offset:offset + size]
        assert inventory.sha(raw) == payload['sha256']
        result = {'file': row['file'], 'file_sha256': row['file_sha256'], 'resource_type': typ,
                  'resource_name': row['name'], 'resource_language': row['language'],
                  'offset': offset, 'bytes': size, 'sha256': payload['sha256'], 'classification': 'MEDIA', 'treatment': 'UNKNOWN'}
        if typ == 14:
            result['treatment'] = 'NO_TEXT'
            result['reason'] = 'GRPICONDIR 아이콘 이미지 참조·크기 표. 픽셀은 RT_ICON 각 자산에 별도로 연결'
            result['icon_ids'] = [struct.unpack_from('<H', raw, 6 + i * 14 + 12)[0] for i in range(struct.unpack_from('<H', raw, 4)[0])]
        else:
            try:
                if typ == 3:
                    if raw.startswith(b'\x89PNG'):
                        image = Image.open(io.BytesIO(raw)).convert('RGBA')
                    else:
                        width, height = struct.unpack_from('<ii', raw, 4)
                        height //= 2
                        icon = struct.pack('<HHHBBBBHHII', 0, 1, 1, width % 256, height % 256, 0, 0, 1,
                                           struct.unpack_from('<H', raw, 14)[0], len(raw), 22) + raw
                        image = Image.open(io.BytesIO(icon)).convert('RGBA')
                else:
                    header_size = struct.unpack_from('<I', raw)[0]
                    bits = struct.unpack_from('<H', raw, 14)[0]
                    palette = struct.unpack_from('<I', raw, 32)[0] or (2 ** bits if bits <= 8 else 0)
                    bitmap = b'BM' + struct.pack('<III', 14 + len(raw), 0, 14 + header_size + palette * 4) + raw
                    image = Image.open(io.BytesIO(bitmap)).convert('RGBA')
                label = payload['sha256'][:16]
                png = dest / (label + '.png')
                if not png.exists():
                    image.save(png)
                result.update(png=str(png.relative_to(ROOT)).replace('\\', '/'), width=image.width, height=image.height)
                unique.setdefault(payload['sha256'], (image.copy(), label, row['file'], typ))
            except Exception as exc:
                result['error'] = str(exc)
        rows.append(result)
    items = list(unique.values())
    cell_w, cell_h, cols = 270, 310, 4
    sheet = Image.new('RGB', (cols * cell_w, ((len(items) + cols - 1) // cols) * cell_h), '#bbbbbb')
    draw = ImageDraw.Draw(sheet)
    for i, (image, label, name, typ) in enumerate(items):
        x, y = (i % cols) * cell_w, (i // cols) * cell_h
        image.thumbnail((256, 256))
        sheet.paste(image, (x + (cell_w - image.width) // 2, y + 35), image)
        draw.text((x + 5, y + 4), label, fill='black')
        draw.text((x + 5, y + 17), f'{Path(name).name} RT{typ}', fill='black')
    sheet.save(dest / 'contact.png')
    inventory.save('native_media_inventory.json', rows)
    print(json.dumps({'resources': len(rows), 'unique_images': len(unique), 'errors': sum('error' in x for x in rows), 'contact': str(dest / 'contact.png')}))

if __name__ == '__main__':
    main()
