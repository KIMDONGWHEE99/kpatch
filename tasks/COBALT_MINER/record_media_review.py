"""실제 판독한 접촉판과 확대 원본에만 미디어 판정을 연결합니다."""
import collections
import json
from pathlib import Path

from media_inventory import ROOT, SOURCE, OUT, digest

# 각 페이지는 2026-11-01 도구 view_image로 실제 열어 보았다.
PAGE_OBSERVATIONS = {
    0: '인물·암석·건물·채굴 도구·화살표와 비어 있는 배경/상태 막대.',
    1: '컨베이어 방향 화살표 애니메이션·수목·기계·아이콘·상태 막대.',
    2: '컨베이어 방향 화살표·인물·벽·차량. 차량 차체의 짧은 식별 표기는 별도 유지.',
    3: '충전기·바닥·건물·축소 홍보 배경·채굴기. 제작사 로고와 채굴기 글자는 별도 판정.',
    4: '진행 막대·차량·아이콘·수로·로고 변형. 브랜드 로고·차체 식별자는 별도 유지.',
    5: '제작사 로고·건물·수목·인물 걷기/작업 동작. 로고와 차체 식별자는 별도 유지.',
    6: '인물의 이동·회전·작업 자세 프레임. 글자 없음.',
    7: '인물·차량의 회전/이동 애니메이션과 풍경·도구. 차체 식별자는 별도 유지.',
    8: '제작사 로고 변형·광부·깃발·표지 구조물·지형. 로고는 별도 유지.',
    9: '지형·인물·동작 효과·라디오·화살표. 게임 제목 로고는 별도 유지.',
    10: '지형·건물·인물·토끼·충전기·채굴 효과. 문자 없음.',
    11: '인물·충전기·방향별 채굴 먼지 프레임. 문자 없음.',
    12: '방향별 채굴 먼지 애니메이션 프레임. 문자 없음.',
    13: '지형·기계·아이콘·드론·방향 화살표. 녹색 숫자 표지는 별도 유지.',
    14: '드론·토끼·인물·지형·회전 화살표. 문자 없음.',
    15: '회전 화살표·인물·토끼·지형 프레임. 문자 없음.',
    16: '재료 수량 아이콘·건물·간판·채굴기·로고·동물. 숫자/로고 유지 및 간판 번역 별도.',
    17: '동물 애니메이션·재료 수량 아이콘·배터리·충전기·수로. 숫자 별도 유지.',
    18: '지도·수목·지형·아이콘·수송선·양 애니메이션. 지도 원본 확대에서 판독 가능한 문구 없음.',
    19: '행성·수송선·비행 장치·폭발·저장 아이콘. 축소 합성의 채굴기 표기는 별도 판정.',
    20: '폭발·홍보 이미지·광고판·아이콘·행성. 제목/기호 유지, 광고 문구 번역 별도.',
    21: '아이콘·제작사 로고·기계 합성·차량·모닥불·광고판. 글자·숫자·기호 별도 판정.',
    22: '광고판 변형·기계·차량·효과·차량 회전 프레임. 광고 문구/차체 식별자 별도 판정.',
}
LOGOS = {271, 282, 320, 337, 344, 347, 351, 486, 543, 544, 545, 547, 1114, 1136, 1459}
TITLES = {612, 1363}
VEHICLE_CODES = {187,194,195,197,198,199,201,287,288,289,290,295,296,297,298,326,352,366,
                 485,487,492,495,500,501,502,503,504,505,506,507,508,509,510,511,512,514,515,
                 516,518,519,520,521,522,523,530,531,532,533,534,1517,1521,1524,1527,1535,
                 241,246,257}
NUMBERS = {914,915,916,917,918,1081,1085,1086,1087,1139,1141,1186,1187,1188,1190,1192,
           1196,1197,1198,1214,1218,1219,1220,1436,1437}
SYMBOLS = {1093,1229,1318,1414,1416,1438,1439,1467,1493,1494}
HARVESTERS = {252,262,1100,1333,1466}
BILLBOARDS = {1374,1486,1491,1492,1498,1499,1500,1501,1503,1504,1513}
SIGN_TEXT = {1129: 'Iron Motors'}
EXPANDED = {252,262,1100,1123,1129,1374,187,1333,1466,1517,1521,1524,1527,1535,1225,1132,1326,1363}

def image_references(value, path=''):
    if isinstance(value, dict):
        kind = value.get('ChunkName')
        if kind in {'ObjectDirection', 'ObjectCounter'}:
            for index, handle in enumerate(value.get('Frames', [])):
                yield handle, f'{path}/Frames/{index}'
        if kind in {'ObjectBackdrop', 'ObjectShape'} and value.get('Image', 0):
            yield value['Image'], f'{path}/Image'
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                yield from image_references(item, f'{path}/{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from image_references(item, f'{path}/{index}')

def main():
    index = json.loads((OUT / 'contact_index.json').read_text(encoding='utf-8'))
    assert len(index) == len(PAGE_OBSERVATIONS) == 23
    assert sum(len(page['items']) for page in index) == 1472
    package = json.loads((SOURCE / 'package.json').read_text(encoding='utf-8-sig'))
    refs = collections.defaultdict(list)
    for key, obj in package['FrameItems']['Items'].items():
        for handle, field in image_references(obj['Properties'], 'Properties'):
            refs[handle].append({'object_handle': int(key), 'object_name': obj['Name'], 'field': field})
    placements = collections.defaultdict(list)
    for i, frame in enumerate(package['Frames']):
        for instance in frame['FrameInstances']['Instances']:
            placements[instance['ObjectInfo']].append({'frame_index': i, 'frame_name': frame['FrameName'],
                'instance_handle': instance['Handle'], 'x': instance['PositionX'], 'y': instance['PositionY']})
    source_sha = digest(ROOT / 'source_original/COBALT_MINER/steam_24347666/COBALT MINER.dat')
    rows = []
    for page_number, page in enumerate(index):
        assert digest(OUT / page['path']) == page['sha256']
        for item in page['items']:
            h = item['handles'][0]
            action, text, reason = 'NO_TEXT', None, PAGE_OBSERVATIONS[page_number]
            if h in LOGOS:
                action, reason = 'KEEP', '제작사/배급사 브랜드 로고이므로 원형 보존. 조작 안내·서술 문장이 아님.'
            elif h in TITLES:
                action, text, reason = 'KEEP', 'COBALT MINER', '게임의 고유 제목 로고를 원형 보존.'
            elif h in VEHICLE_CODES:
                action, text, reason = 'KEEP', '차체의 2자 식별 표기', '차량 도트 그림에 붙은 짧은 모델/장식 식별 표기. 단어나 조작 안내가 아니므로 보존.'
            elif h in NUMBERS:
                action, reason = 'KEEP', '수량·단계를 나타내는 아라비아 숫자이므로 의미와 도형을 보존.'
            elif h in SYMBOLS:
                action, reason = 'KEEP', '통화·물음표 및 함께 있는 수량 숫자로 언어에 독립적인 아이콘 표기.'
            elif h in HARVESTERS:
                action, text, reason = 'KEEP', 'HX9 HARVESTER', '차량에 새긴 모델명. 본문에 The HX-9 Harvester consumes... 등 동일 모델 참조가 있어 고유 식별 표기로 보존하고 본문은 HX-9 하베스터로 대응. 합성·축소·좌우 반전본도 동일 판정. 부모 작업자 2026-11-01 판정.'
            elif h in BILLBOARDS:
                action, text, reason = 'TRANSLATE', 'MJ-1000 / BEAUTY & CALM', '게임 안 광고판 문장 BEAUTY & CALM을 번역하고 모델명 MJ-1000은 보존. 빛 변화 11개 변형을 각각 확인.'
            elif h == 1123:
                action, text, reason = 'TRANSLATE', None, 'MEDIA_REPLACE: 원문 판독 불가 표지를 확인된 객체 기능명 발전소로 교체. ARTHUR 판독은 철회하고 원문 뜻은 UNKNOWN으로 별도 기록. object506·설명514·frame7 event1219/1220으로 확인한 기능명 표지를 imagegen으로 제작하는 명시적 대체이며 직역으로 표시하지 않음. 1123_rereview.json 참조.'
            elif h in SIGN_TEXT:
                action, text, reason = 'KEEP', SIGN_TEXT[h], 'Iron Motors는 전용 도트 간판의 상호이므로 원형 보존. 안내 문장이 아닌 상점 고유 명칭으로 분리하고 최종 유지 표기에 보고. 부모 작업자 2026-11-01 판정.'
            for handle in item['handles']:
                path = SOURCE / f'images/{handle:05d}.png'
                occurrence_refs = []
                for ref in refs[handle]:
                    occurrence_refs.append({**ref, 'placements': placements[ref['object_handle']]})
                rows.append({'location': f'image:{handle}', 'handle': handle, 'source_dat_sha256': source_sha,
                    'source_image_sha256': item['source_sha256'], 'png_sha256': digest(path), 'classification': 'MEDIA',
                    'media_action': action, 'source_text': text, 'reason': reason,
                    'review_status': 'BLOCKED' if action == 'UNKNOWN' else 'PASS', 'review_date': '2026-11-01',
                    'evidence': {'contact_sheet': page['path'], 'contact_sheet_sha256': page['sha256'], 'slot': item['slot'],
                                 'expanded_original_view': h in EXPANDED, 'review_method': '제작자 이미지 육안 판독'},
                    'references': occurrence_refs, 'runtime_status': 'NOT_RUN',
                    'translation_status': 'BLOCKED' if action == 'UNKNOWN' else 'NOT_RUN' if action == 'TRANSLATE' else 'NOT_APPLICABLE'})
                if handle == 1123:
                    rows[-1].update({'translation_method': 'MEDIA_REPLACE', 'replacement_text': '발전소',
                                     'original_transcription_status': 'UNKNOWN', 'handling_resolution_status': 'PASS',
                                     'handling_evidence': '1123_rereview.json',
                                     'handling_evidence_sha256': digest(OUT / '1123_rereview.json')})
    rows.sort(key=lambda x: x['handle'])
    assert len(rows) == 1550 and len({row['handle'] for row in rows}) == len(rows)
    (OUT / 'media_review.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
    translations = [row for row in rows if row['media_action'] == 'TRANSLATE']
    (OUT / 'media_translation_targets.json').write_text(json.dumps(translations, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {'images': len(rows), 'unique_source_images': 1472, 'sheets_viewed': len(index),
               'classification_counts': dict(collections.Counter(row['media_action'] for row in rows)),
               'translation_handles': [row['handle'] for row in translations], 'unknown': sum(row['media_action'] == 'UNKNOWN' for row in rows),
               'image_visual_classification': 'BLOCKED' if any(row['media_action'] == 'UNKNOWN' for row in rows) else 'PASS', 'pixel_translation': 'NOT_RUN', 'runtime_qa': 'NOT_RUN',
               'source_dat_sha256': source_sha, 'contact_index_sha256': digest(OUT / 'contact_index.json'),
               'review_manifest_sha256': digest(OUT / 'media_review.jsonl'),
               'scope': 'Nebula가 추출한 이미지 1550개만의 판정. 실행 파일 아이콘·외부 미디어·음성 검수를 포함하지 않음.'}
    (OUT / 'review_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    main()
