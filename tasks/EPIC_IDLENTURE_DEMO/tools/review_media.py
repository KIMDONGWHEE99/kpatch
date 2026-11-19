"""실제 판독한 검수판과 참조 근거를 모든 이미지 사용 위치에 연결합니다."""
from common import *
index=json.loads((WORK/'media/index.json').read_text(encoding='utf8'));lookup={};reviews=[]
mockup=json.loads((WORK/'media/mockup_refs.json').read_text(encoding='utf8'))
for item in index:
    i=item['id'];disposition='NO_TEXT';reason='검수판 육안 판독: 배경·효과·사물·아이콘·숫자/기능 기호. 문장 없음'
    if i in [7,643,644,645]:disposition='KEEP';reason='글꼴 문자표 또는 빈 동적 아틀라스. 문장 이미지가 아니며 실제 한글 글꼴은 별도로 검사'
    if i in [121,243,449,667,718]:disposition='KEEP';reason='게임 제목·Steam·Discord·제작사/진단 도구의 로고·브랜드 표기 유지'
    if i in [733,734,770,777,782]:
        reference=next(r for r in mockup if r['media_id']==i)
        consumers=[r for r in reference['references'] if 'gameobject_chain' in r]
        assert consumers and all(r['gameobject_chain'][0]['active']==False for r in consumers)
        disposition='KEEP';reason='비활성 Image 객체에 연결된 개발 화면 시안. 실제 동작 화면의 UI 문구는 개별 자산으로 번역. 활성화 참조/실행 코드 조사와 mockup_refs.json에 근거'
    review=dict(id=i,png_sha256=item['sha256'],sheet=f'sheet_{i//64:02}.png',sheet_sha256=sha((WORK/f'media/sheet_{i//64:02}.png').read_bytes()),disposition=disposition,reason=reason)
    reviews.append(review)
    for loc in item['locations']:lookup[(loc['file'],loc['path_id'])]=review
g=generator();envs={};result=[]
for row in json.loads((EXTRACT/'media.json').read_text(encoding='utf8')):
    key=(row['file'],row['path_id'])
    if row['type']=='Sprite':
        if row['file'] not in envs:envs[row['file']]=load(BASE/DATA/row['file'],g)
        e=envs[row['file']];t=e.file.objects[row['path_id']].read_typetree();p=t['m_RD']['texture'];name=row['file'] if not p['m_FileID'] else Path(e.file.externals[p['m_FileID']-1].path).name;key=(name,p['m_PathID'])
    if key in lookup:r=lookup[key]
    else:
        assert row['type']=='Texture2D',row
        e=envs.get(row['file']) or load(BASE/DATA/row['file'],g);t=e.file.objects[row['path_id']].read_typetree();assert t['m_Width']==t['m_Height']==0
        r=dict(disposition='NO_TEXT',reason='0×0 동적 빈 아틀라스, 이미지 데이터 없음')
    result.append(dict(row,disposition=r['disposition'],reason=r['reason'],review_id=r.get('id'),pixel_source=key))
for r in json.loads((EXTRACT/'builtin_media.json').read_text(encoding='utf8')):
    text=r['path_id'] in [10402,10406,10407,10409,10410,10413,15000]
    result.append(dict(r,disposition='KEEP' if text else 'NO_TEXT',reason='Unity 엔진 원본 알림·평가판/교육/개발 빌드 워터마크 및 로고. 게임 대사가 아니며 엔진 출처·라이선스 식별을 위해 유지' if text else '기본 UI 스킨·빈 글꼴 아틀라스. 픽셀 문장 없음',review_sheet_sha256=sha((WORK/'media/builtin_sheet.png').read_bytes())))
save(WORK/'media/reviews.json',reviews);save(WORK/'classified_media.json',result)
save(WORK/'media_summary.json',dict(status='PASS',objects=len(result),unique_game_images=len(index),builtin_images=37,unknown=0,video=0,dispositions=dict(collections.Counter(r['disposition'] for r in result))))
print('미디어',len(result),'분류 완료')
