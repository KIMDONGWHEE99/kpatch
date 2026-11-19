"""직접 관찰한 그림과 Sprite→Texture 참조를 전체 목록에 연결합니다."""
from common import *
import json,collections
textures=json.loads((WORK/'review/media_index.json').read_text('utf-8'))
rows=json.loads((EXTRACT/'media.json').read_text('utf-8'))
decisions=[];by_id={r['id']:r for r in textures}
for r in textures:
    r=dict(r);n=r['review_index']
    if r['extraction']=='EMPTY_RUNTIME_TEXTURE':
        r.update(treatment='KEEP_RUNTIME_GLYPH',reason='원본 크기 0×0인 Font Texture. 런타임 글꼴 래스터 저장 공간',evidence=[r['id']])
    else:
        assert r['extraction']=='PASS'
        r.update(treatment='KEEP_NO_LANGUAGE',reason='제작자가 원본 크기 이미지·연락 시트를 관찰: 배경·아이콘·패턴·수치 문양',evidence=[r['image'],r['image_sha256']])
        if 'Atlas' in r['name'] or r['name']=='DebugFont':r.update(treatment='KEEP_GLYPH_RESOURCE',reason='문자 조각을 담은 글꼴 아틀라스. 사용 글꼴은 별도 글리프 검사')
        if n in (0,19):r.update(treatment='KEEP_BRAND',reason='Unity·개발사 시작 로고. 고유 브랜드 표기 유지')
        if n==59:
            r.update(treatment='KEEP_MIXED_BRAND_AND_ART',reason='전체 원본 2000×1280 및 4개 확대 구역 직접 관찰. 게임·제작사·게임잼 로고, 키보드 표식, 묘비 RIP RAIN, 설계도 작은 Engine/Wheel/Door 등 장식 글자 유지. 이전 데모 홍보 그림은 장면의 개별 버튼이 비활성. 현재 텍스트 설명은 한국어로 별도 제공.',kept_text=['THE LOOPLER','MADE BY MHEEP','GMTK GAME JAM','SHIFT','ALT','RIP RAIN','Engine','Wheel','Door','Boot','PRICING SURVEY','V0.1.5 PATCH NOTES','WISHLIST ON STEAM','FEEDBACK FORM','RELEASE CONTENT','NEW FORM PLAYTEST'])
            r['evidence']+=['review/sprite_detail_0_0.png','review/sprite_detail_1000_0.png','review/sprite_detail_0_640.png','review/sprite_detail_1000_640.png','review/scene_hierarchy.json']
    decisions.append(r)
envs={};sprite_links=[]
for r in rows:
    if r['type']!='Sprite':continue
    if r['file'] not in envs:
        e=UnityPy.load(str(SOURCE/r['file']));envs[r['file']]={(o.assets_file.name,o.path_id):o for o in e.objects}
    obj=envs[r['file']][(r['asset'],r['path_id'])];t=obj.read_typetree();ptr=t['m_RD']['texture'];asset=obj.assets_file.name
    if ptr['m_FileID']:asset=obj.assets_file.externals[ptr['m_FileID']-1].name
    target=f"{(SOURCE/r['file']).name}/{asset}/{ptr['m_PathID']}"
    assert target in by_id,(r['id'],target)
    texture=by_id[target]
    sprite_links.append({**r,'treatment':'KEEP_AS_REVIEWED_TEXTURE_REGION','texture_id':target,'texture_sha256':texture.get('image_sha256'),'region':t['m_RD']['textureRect'],'reason':'참조 그림의 해당 영역을 전체 및 확대 이미지에서 검토함','evidence':[texture.get('image',target)]})
decisions+=sprite_links
assert len(decisions)==len(rows) and all(r['treatment']!='UNKNOWN' for r in decisions)
write_json(WORK/'review/media_decisions.json',decisions)
write_json(WORK/'review/media_summary.json',{'status':'PASS','texture_count':len(textures),'sprite_count':len(sprite_links),'pixel_translation':'로고·키 표식·일러스트 속 작은 글자와 비활성 이전 홍보 그림은 유지. 픽셀 전면 번역으로 주장하지 않음','input_sha256':sha(EXTRACT/'media.json'),'counts':dict(collections.Counter(r['treatment'] for r in decisions))})
print('MEDIA classified',len(decisions),'sprite references',len(sprite_links))
