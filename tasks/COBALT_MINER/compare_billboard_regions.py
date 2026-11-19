"""미디어 수정 전 광고판의 동일 문구 영역을 원시 픽셀로 비교합니다."""
import hashlib
import json
from collections import Counter

from PIL import Image

from media_inventory import SOURCE, OUT, digest
from record_media_review import BILLBOARDS

def main():
    rect = (234, 99, 375, 166)
    rows, groups = [], {}
    base = Image.open(SOURCE / 'images/01374.png').convert('RGBA').crop(rect)
    base_pixels = list(base.get_flattened_data())
    for handle in sorted(BILLBOARDS):
        path = SOURCE / f'images/{handle:05d}.png'
        image = Image.open(path).convert('RGBA').crop(rect)
        raw = image.tobytes()
        value = hashlib.sha256(raw).hexdigest()
        groups.setdefault(value, []).append(handle)
        pairs = Counter((x, y) for x, y in zip(base_pixels, image.get_flattened_data()) if x != y)
        rows.append({'handle': handle, 'source_png_sha256': digest(path), 'rgba_region_sha256': value,
                     'different_pixels_from_1374': sum(pairs.values()),
                     'color_changes': [{'from_rgba': x, 'to_rgba': y, 'pixels': count} for (x, y), count in pairs.items()],
                     'background_identical': set(pairs) <= {((255,255,255,255),(255,219,187,255))}})
    original = Image.open(SOURCE / 'images/01123.png')
    crop = original.crop((47, 197, 187, 236))
    crop.resize((840, 234), Image.Resampling.NEAREST).save(OUT / '1123_original_region_enlarged.png')
    result = {'rectangle_xyxy': rect, 'size': base.size, 'images': len(rows), 'distinct_region_count': len(groups),
              'groups': groups, 'items': rows, 'pixel_edit_status': 'NOT_RUN',
              'rule': '영역 지문이 같은 원본에만 동일 생성 영역을 무조건 재사용 가능. 서로 다르면 차이를 분석하고 별도 검증.'}
    (OUT / 'billboard_region_comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
