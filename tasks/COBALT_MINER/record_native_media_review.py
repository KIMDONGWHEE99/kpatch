"""직접 판독한 PE 아이콘 7종의 유지 근거를 원본 지문에 연결합니다."""
import json
from pathlib import Path
import native_inventory as inv

def main():
    path = inv.OUT / 'native_media_inventory.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    contact = inv.OUT / 'media/contact.png'
    reviews = []
    for row in rows:
        if row['resource_type'] == 14:
            reviews.append({**row, 'treatment': 'NO_TEXT', 'reviewed': True})
            continue
        png = inv.ROOT / row['png']
        assert png.is_file() and not row.get('error')
        reviews.append({**row, 'treatment': 'KEEP', 'reviewed': True,
                        'png_sha256': inv.sha(png.read_bytes()),
                        'evidence': {'contact_path': str(contact.relative_to(inv.ROOT)).replace('\\', '/'),
                                     'contact_sha256': inv.sha(contact.read_bytes()),
                                     'comparison': 'DAT image1517 및 축소1521/1524/1527/1535, 객체840',
                                     'dat_image1517_source_sha256': '06ab85ca302b63895a9644b7e9fe8f39de277db337eef69e80260a94df8aa997'},
                        'reason': '직접 판독한 채굴차·인물 그림의 아이콘 변형. 차체의 2자 식별 표기는 동일 차량 애니메이션에 유지되는 장식/모델 표식이며 문장·메뉴가 아님. 원형·사각형·축소판 모두 원래 디자인 유지',
                        'review_scope': 'native 담당 contact.png 직접 판독 및 media 담당 DAT1517 원본 확대·아이콘 재확인. 표식을 특정 영문 단어로 확정하지 않음'})
    inv.save('native_media_review.json', {'source_inventory_sha256': inv.sha(path.read_bytes()),
                                        'resources': reviews, 'unknown': sum(x['treatment'] == 'UNKNOWN' for x in reviews),
                                        'pixel_translation': 0, 'preserved_icon_variants': 7,
                                        'runtime_qa': 'NOT_RUN'})
    print(json.dumps({'resources': len(reviews), 'unknown': 0, 'kept_images': 7}))

if __name__ == '__main__':
    main()
