"""아직 원본을 수정하지 않고 번역 영역·검증 조건을 기록합니다."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from media_inventory import ROOT, SOURCE, OUT, digest

REGIONS = {
    252: [245, 146, 334, 162], 262: [980, 584, 1336, 648],
    1100: [980, 584, 1336, 648], 1333: [67, 347, 159, 363],
    1466: [33, 173, 80, 182], 1470: [33, 173, 80, 182],
    1123: [47, 197, 187, 236], 1129: [5, 29, 180, 75],
}

def main():
    targets = json.loads((OUT / 'media_translation_targets.json').read_text(encoding='utf-8'))
    plan = []
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 15)
    canvas = Image.new('RGB', (1056, len(targets) * 125), '#303237')
    draw = ImageDraw.Draw(canvas)
    for index, item in enumerate(targets):
        handle = item['handle']
        image = Image.open(SOURCE / f'images/{handle:05d}.png').convert('RGB')
        rect = REGIONS.get(handle, [234, 99, 375, 166])
        crop = image.crop(rect)
        factor = max(1, min(5, 475 // crop.width, 100 // crop.height))
        crop = crop.resize((crop.width * factor, crop.height * factor), Image.Resampling.NEAREST)
        y = index * 125
        draw.text((5, y + 3), f'#{handle} {image.width}x{image.height} | {item["source_text"]}', font=font, fill='white')
        canvas.paste(crop, (5, y + 22))
        source_text = item['source_text'] or ''
        category = 'functional_sign' if handle == 1123 else 'advertisement' if 'BEAUTY' in source_text else 'harvester' if 'HARVESTER' in source_text else 'shop_sign'
        suggestions = {'advertisement': '아름다움과 / 평온', 'harvester': 'HX9 하베스터', 'shop_sign': '아이언 모터스', 'functional_sign': '발전소'}
        plan.append({'handle': handle, 'category': category, 'source_png_sha256': item['png_sha256'],
                     'source_image_sha256': item['source_image_sha256'], 'source_text': item['source_text'],
                     'suggested_text': suggestions[category], 'text_status': '본문 용어집과 대조 후 확정',
                     'allowed_pixel_region_xyxy': rect,
                     'orientation': '원본 좌우 반전 구도' if handle in {1333,1466,1470} else '정방향',
                     'transparency': '원본 마젠타 색상키와 픽셀 크기 유지',
                     'verification': ['영역 밖 픽셀 동일', '크기·알파·색상키 보존', '각 변형의 원본 지문 연결',
                                      '게임 재추출 이미지와 결과 픽셀 일치', '실제 장면 크기에서 읽힘 확인'],
                     'status': 'NOT_RUN'})
    canvas_path = OUT / 'text_region_evidence.png'
    canvas.save(canvas_path)
    (OUT / 'localization_plan.json').write_text(json.dumps({'items': plan, 'evidence_crop_sha256': digest(canvas_path),
        'status': 'NOT_RUN', 'scope': '원문 판독용 확대와 영역 계획만 생성. 게임 이미지 수정 없음.'}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'targets': len(plan), 'evidence': str(canvas_path)}))

if __name__ == '__main__':
    main()
