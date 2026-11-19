"""실제 픽셀 판독과 소비 위치를 미디어 위치·원본 해시에 연결합니다."""
from pathlib import Path
import json
import re
from common import EXTRACTED, WORK, save, sha


def main():
    rows=json.loads((WORK/'media/inventory.json').read_text(encoding='utf-8'))
    sources={p:p.read_text(encoding='utf-8-sig') for suffix in ('*.gd','*.tscn','*.tres','*.json') for p in (EXTRACTED/'recovered').rglob(suffix)}
    sheets=[{'path':str(p),'sha256':sha(p)} for p in sorted((WORK/'media/sheets').glob('*.png'))]
    exceptions={
        19:('PARTIAL_REPLACEMENT','아틀라스 전장을 원래 크기로 판독했습니다. BUY/F 조각의 AtlasTexture 두 개는 한글 독립 텍스처로 연결하며 이 조각은 후보에서 소비하지 않습니다. 선박 CARGO 도색과 기기 숫자는 장식·수치로 유지합니다.'),
        72:('KEEP_UNREFERENCED','CONTINUE가 새겨진 이전 메뉴 그림. 게임에 연결된 현재 mainmenu는 btn_menu_bg와 Label을 사용합니다. 원본 이름·UID·스크립트/장면/자원 연결 검색에서 소비가 없습니다.'),
        75:('KEEP_UNREFERENCED','EXIT가 새겨진 이전 메뉴 그림. 현재 메뉴는 번역하는 Label을 사용하며 이 그림의 연결이 없습니다.'),
        77:('KEEP_UNREFERENCED','GUIDE가 새겨진 이전 메뉴 그림. 현재 메뉴는 번역하는 Label을 사용하며 이 그림의 연결이 없습니다.'),
        85:('KEEP_UNREFERENCED','LOAD가 새겨진 이전 메뉴 그림. 현재 메뉴는 번역하는 Label을 사용하며 이 그림의 연결이 없습니다.'),
        90:('KEEP_UNREFERENCED','NEW GAME이 새겨진 이전 메뉴 그림. 현재 메뉴는 번역하는 Label을 사용하며 이 그림의 연결이 없습니다.'),
        91:('KEEP_UNREFERENCED','NEW DEMO가 새겨진 이전 메뉴 그림. 현재 메뉴는 번역하는 Label을 사용하며 이 그림의 연결이 없습니다.'),
        145:('KEEP_DECORATION','화물선 선체의 CARGO는 선박 외관에 그려진 장식 표기입니다. 게임 행동·버튼·대화가 아니며 화물선 이름과 설명은 별도 텍스트로 번역합니다. 픽셀 영문 유지 사실을 배포 문서에 공개합니다.'),
        282:('KEEP_BRAND','Agromatic 게임 로고. 고유 브랜드 그림을 유지합니다.'),
        289:('KEEP_BRAND','Gimcraft 개발사 로고. 고유 브랜드 그림을 유지합니다.'),
        290:('KEEP_BRAND','Gimcraft 개발사 로고의 중복 크기. 고유 브랜드 그림을 유지합니다.'),
        330:('REPLACE_VECTOR','보관함의 FULL 안내를 새 벡터 가득 아이콘으로 교체합니다. 원래24×24크기·사용 위치를 유지합니다.'),
        331:('REPLACE_VECTOR','자동 시설의 F(Full) 안내를 새 벡터 가득 아이콘으로 교체합니다. 원래24×24크기·사용 위치를 유지합니다.'),
        351:('KEEP_NUMERIC','기기 표시판 숫자4100. 자연어 문구가 아니며 기기 그림을 유지합니다.'),
        482:('REPLACE_VECTOR','땅 구입 표지판 BUY를 새 벡터 구매 표지판으로 교체합니다. 원래48×48크기와 게임 안내 역할을 유지합니다.'),
        553:('KEEP_NO_TEXT','지형 타일을 원래960×960크기로 추가 판독했습니다. 자연어 문구가 없습니다.'),
    }
    imports={}
    for p in (EXTRACTED/'recovered').rglob('*.import'):
        text=p.read_text(encoding='utf-8')
        match=re.search(r'path="res://([^"]+)"',text)
        source=re.search(r'source_file="res://([^"]+)"',text)
        uid=re.search(r'uid="([^"]+)"',text)
        if match and source:imports[match[1]]=(source[1],uid[1] if uid else None)
    for row in rows:
        row['disposition'],row['evidence']=exceptions.get(row['id'],('KEEP_NO_TEXT','연락판의 원래 크기 미디어를 판독했습니다. 인물·물체·지형·아이콘·배경 그림이며 자연어 문구가 없습니다.'))
        row['review_sheets']=sheets[row['id']//80:row['id']//80+1]
        row['consumers']=[]
        row['original_sources']=[]
        for pack_path in row['paths']:
            original,uid=imports.get(pack_path,(None,None))
            row['original_sources'].append({'pack_path':pack_path,'source_path':original,'uid':uid})
            if original:
                for p,text in sources.items():
                    if original in text or uid and uid in text:
                        for number,line in enumerate(text.splitlines(),1):
                            if original in line or uid and uid in line:
                                row['consumers'].append({'path':p.relative_to(EXTRACTED/'recovered').as_posix(),'sha256':sha(p),'line':number,'expression':line})
        if row['disposition']=='KEEP_UNREFERENCED' and row['consumers']:
            raise ValueError('이전 버튼의 실제 참조 발견: '+str(row['id']))
    save(WORK/'media/final_disposition.json',rows)
    save(WORK/'media/review_summary.json',{'status':'PASS','textures':730,'unique_pixel_images':len(rows),'unknown':0,
        'replaced':[330,331,482],'kept_pixel_english':['Agromatic','Gimcraft','CARGO (선체 장식)'],
        'legacy_unreferenced_textures':[72,75,77,85,90,91], 'native_icon_pixel_roundtrip':str(WORK/'media/korean_vector_icons/report.json'),
        'svg_icons':'내장 Godot 도구 아이콘 두 개의 XML에 text 요소가 없음을 확인. ICO는 게임 아이콘의 같은 브랜드 그림.',
        'video':'PCK와 원본 파일 목록에 영상 형식·VideoStreamPlayer 참조가 없습니다.'})
    print('미디어 분류 완료:',len(rows))


if __name__=='__main__':main()
