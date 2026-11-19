"""추가로 실제 열어 본 픽셀과 객체 문맥을 지문에 연결합니다."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01'
REVIEW = SOURCE.parent / 'media_review_01'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    package = json.loads((SOURCE / 'package.json').read_text(encoding='utf-8-sig'))
    events = json.loads((SOURCE / 'frames/07.json').read_text(encoding='utf-8-sig'))
    row = next(json.loads(line) for line in (REVIEW / 'media_review.jsonl').read_text(encoding='utf-8').splitlines() if json.loads(line)['handle'] == 1123)
    report = {'handle': 1123, 'original_transcription': None, 'original_transcription_status': 'UNKNOWN',
              'source_dat_sha256': row['source_dat_sha256'], 'source_image_sha256': row['source_image_sha256'],
              'original_png': str(SOURCE / 'images/01123.png'), 'original_png_sha256': digest(SOURCE / 'images/01123.png'),
              'full_dimensions': [256, 256], 'sign_region_xyxy': [47, 197, 187, 236], 'bright_stroke_bbox_xyxy': [56, 204, 180, 228],
              'expanded_evidence': str(REVIEW / '1123_original_region_enlarged.png'),
              'expanded_evidence_sha256': digest(REVIEW / '1123_original_region_enlarged.png'),
              'comparison_image': str(SOURCE / 'images/01127.png'), 'comparison_png_sha256': digest(SOURCE / 'images/01127.png'),
              'visual_observation': '원본 전체·6배 확대·미건설 상태1127을 실제 열어 확인. 전면 간판은 기하학 획으로 되어 있으나 연속된 Latin 철자나 원문 뜻을 확정할 수 없음. ARTHUR 판독 철회 유지. 원문을 추측 번역하거나 장식이라고 단정하지 않음.',
              'references': row['references'],
              'object': {'handle': 506, 'name': package['FrameItems']['Items']['506']['Name'],
                         'animations': package['FrameItems']['Items']['506']['Properties']['ObjectAnimations'],
                         'movement': package['FrameItems']['Items']['506']['Properties']['ObjectMovements'],
                         'paragraph_count': 0, 'counter_display_type': 0},
              'function_context': {'description_object': 514, 'description_name': 'power station desc',
                                   'paragraphs': [p['Value'] for p in package['FrameItems']['Items']['514']['Properties']['ObjectParagraphs']['Paragraphs']],
                                   'events': [e for e in events if e['ev'] in (1219, 1220, 1228)]},
              'static_sign_reason': '건설 조건 A>=1에서 애니메이션1(단일 이미지1123)을 표시. 간판은 고정 그림이고 별도 텍스트·카운터·조작키가 없으며 전력/패널 수치는 object514 문단으로 따로 표시함. 이미지의 명칭 영역만 교체해도 행동·조건·수치가 바뀌지 않음.',
              'decision': {'method': 'MEDIA_REPLACE', 'replacement_text': '발전소', 'status': 'ASSET_CREATED',
                           'reason': '원문 판독은 불확실한 채로 기록하고 확인된 객체 기능명으로 표지를 교체하는 부모 작업자 결정(2026-11-01). 직역이나 원문 판독 완료로 표시하지 않음.',
                           'asset': str(ROOT / 'working_private/COBALT_MINER/media_ko_02/01123.png'),
                           'asset_sha256': digest(ROOT / 'working_private/COBALT_MINER/media_ko_02/01123.png'),
                           'manifest_sha256': digest(ROOT / 'working_private/COBALT_MINER/media_ko_02/manifest.json'),
                           'png_visual_status': 'PASS', 'png_visual_observation': '140×39 축소 패널과256×256 완성 이미지 모두 view_image로 실제 열어 발전소 판독 확인.',
                           'requires': '후보 독립 재추출·실제 화면 검수'},
              'package_sha256': digest(SOURCE / 'package.json'), 'event_source_sha256': digest(SOURCE / 'frames/07.json'),
              'runtime_status': 'NOT_RUN'}
    (REVIEW / '1123_rereview.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    media = ROOT / 'working_private/COBALT_MINER/media_ko_01'
    manifest = json.loads((media / 'manifest.json').read_text(encoding='utf-8'))
    visual = {'status': 'PASS', 'method': '2026-11-01 view_image로 PNG 11개를 각각 실제 열어 문구 판독',
              'manifest_sha256': digest(media / 'manifest.json'),
              'observed_text': '아름다움과\n평온', 'retained_identifier': 'MJ-1000',
              'observation': '11개 모두 2줄 한글 문구가 판독되고 영역 안에 들어감. 원래의 색 변화가 각 이미지에 남음.',
              'images': [{'handle': r['handle'], 'png_sha256': digest(media / f"{r['handle']:05d}.png"), 'visual_status': 'PASS'} for r in manifest['files']],
              'runtime_qa': 'NOT_RUN'}
    (media / 'visual_review_11.json').write_text(json.dumps(visual, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'rereview_1123': 'UNKNOWN 원문과 MEDIA_REPLACE 계획을 구분 기록', 'billboards_viewed': len(visual['images'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
