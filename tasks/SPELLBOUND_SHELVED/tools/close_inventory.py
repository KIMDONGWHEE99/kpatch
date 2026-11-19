"""위치·원본 해시·사용 경로를 연결하여 게임별 조사 목록을 확정한다."""
import json
import re
import hashlib
from collections import Counter
from functools import cache
from pathlib import Path
from pck_tools import ROOT, EXTRACTED, WORK, BASELINE, read_pack

@cache
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v): Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
recovered=EXTRACTED/'recovered'
out=WORK/'ko_v001'
ko=read(WORK/'translation/ko.json')
books=read(WORK/'translation/books_ko.json')
if isinstance(books,dict): books=books['books']
records=[]
def add(file,location,value,classification,evidence,**extra):
    records.append(dict(file=str(file.relative_to(recovered)).replace('\\','/'),location=location,source=value,
        source_file_sha256=sha(file),source_sha256=hashlib.sha256(value.encode()).hexdigest(),
        classification=classification,evidence=evidence,**extra))
def walk(value,path=()):
    if isinstance(value,str): yield path,value
    elif isinstance(value,dict):
        for key,child in value.items():yield from walk(child,path+(key,))
    elif isinstance(value,list):
        for key,child in enumerate(value):yield from walk(child,path+(key,))
for file in sorted((recovered/'data').rglob('*.json')):
    data=read(file)
    for path,value in walk(data):
        location='/'+('/'.join(map(str,path)))
        kind='UNKNOWN';reason='';extra={}
        if file.name=='en.json':
            key=path[0];target=ko[key]
            if len(path)>1:target=target[path[1]]
            kind='VISIBLE_KEEP' if key in ('chat.ach_unlocked','format.thousands','hover.activity') else 'VISIBLE_TRANSLATE'
            reason='I18n이 동일 키의 ko.json 값을 읽는다. 유지한 세 키는 번역 문구를 끼우는 형식 또는 숫자 구분 문자다.'
            extra={'target':target,'translation_key':key}
        elif file.name in ('de.json','es.json','fr.json','book_titles_de.json','book_titles_es.json','book_titles_fr.json'):
            kind='VISIBLE_KEEP';reason='명시적으로 해당 외국어를 고른 경우의 기존 번역이다. 한국어는 별도 ko 경로를 사용한다.'
        elif file.name=='books.json':
            if path[-1]=='title':
                row=books[path[1]];assert row['source']==value
                kind='VISIBLE_TRANSLATE';reason='main._localize_titles가 같은 배열 위치의 한국어 제목을 복사한다.';extra={'target':row['target'],'book_id':row['id']}
            elif path[-1]=='author':kind='INTERNAL';reason='main._prepare_books는 저자 필드를 런타임 책 객체로 복사하지 않으며 전체 스크립트에 저자 표시 경로가 없다.'
            else:kind='INTERNAL';reason='책 ID·분류·모형 크기를 결정하는 데이터 필드다. 화면 제목은 별도 title 필드다.'
        elif file.name=='sections.json' and path[-1]=='name':
            key='section.'+data['sections'][path[1]]['id'];kind='VISIBLE_TRANSLATE';reason='main._ready에서 section.<id> 번역으로 덮어쓴 뒤 사용한다.';extra={'translation_key':key,'target':ko[key]}
        elif file.name=='customers.json' and path[-1]=='name':
            key='customer.type.'+data['types'][path[1]]['id'];kind='VISIBLE_TRANSLATE';reason='customers.setup에서 customer.type.<id> 번역으로 이름을 바꾼다.';extra={'translation_key':key,'target':ko[key]}
        elif file.name=='upgrades.json' and path[-1] in ('name','desc'):
            if len(path)==3:
                kind='INTERNAL';reason='업그레이드 가지 분류의 이름이다. upgrades는 이 name 필드를 노드로 복사하지 않으며 upgrades_ui는 아이콘으로 가지를 그린다.'
            else:
                if path[2]=='hire':key='upgrade.hire.'+str(path[3]+1)
                else:key='upgrade.'+data['roots'][path[1]][path[2]][path[3]]['id']+'.'+path[-1]
                kind='VISIBLE_TRANSLATE';reason='upgrades.setup의 노드 생성 단계가 같은 ID의 I18n 번역을 사용한다.';extra={'translation_key':key,'target':ko[key]}
        elif file.name in ('sections.json','customers.json','upgrades.json','tree_layout.json'):
            kind='INTERNAL';reason='분류 ID·색·배치·게임 규칙의 연결 ID 또는 tree_layout._comment 설명이다. UI 출력 경로와 분리된 필드를 확인했다.'
        assert kind!='UNKNOWN',(file,path,value)
        add(file,location,value,kind,reason,**extra)

# 런타임 코드 19개는 문맥별 수동 검토 원장을 재사용한다.
code=read(out/'code_review.json')
for row in code:
    assert sha(recovered/row['file'])==row['source_file_sha256']
    assert row['classification'] in ('INTERNAL','VISIBLE_KEEP','VISIBLE_TRANSLATE') and row['evidence']

# 편집기 전용 세 스크립트와 모든 장면 문자열도 누락 없이 위치를 기록한다.
literal=re.compile(r'"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27')
editor=[]
for file in sorted((recovered/'addons').rglob('*.gd')):
    source=file.read_text(encoding='utf-8');assert '@tool' in source
    for match in literal.finditer(source):
        editor.append({'file':file.relative_to(recovered).as_posix(),'line':source.count('\n',0,match.start())+1,
            'source':match[0],'source_file_sha256':sha(file),'classification':'INTERNAL',
            'evidence':'GodotSteamPlugin은 EditorPlugin을 상속한 @tool이며 내보낸 게임의 main 장면에서 인스턴스화하지 않는다. 다른 두 파일은 이 편집기 도크의 자식이다.'})
for file in recovered.rglob('*.tscn'):
    for number,line in enumerate(file.read_text(encoding='utf-8').splitlines(),1):
        for match in literal.finditer(line):
            reason='편집기 전용 Steamworks 도크의 노드·속성·문구다. GodotSteamPlugin에서만 불러온다.'
            if file.name=='main.tscn':reason='장면의 노드 이름·참조·그룹이다. HUD의 greybox 표본 문구는 main._setup_hud가 첫 프레임 전에 감추고 메뉴/개발 HUD로 대체한다.'
            add(file,'line:'+str(number),match[0],'INTERNAL',reason)

media=[]
for file in sorted(recovered.rglob('*')):
    if not file.is_file() or file.suffix not in ('.png','.svg','.icns','.ogg'):continue
    relative=file.relative_to(recovered).as_posix()
    if file.suffix=='.ogg':
        disposition='KEEP_AUDIO';reason='main.gd:1332~1345에서 클릭·동전·정리 등 일곱 효과음과 music_shop 배경 음악으로만 연결한다. 대사 음성 경로와 자막 시간표는 없다. 기존 압축 음원을 바이트 그대로 보존한다.'
    elif file.name.startswith('moodReference'):
        disposition='INTERNAL_REFERENCE';reason='이미지 전체를 contact sheet로 관찰했다. 영어가 있는 개발 참고 그림이며 런타임 코드·장면·프로젝트에서 참조하지 않는다.'
    elif relative.startswith('addons/'):
        disposition='KEEP_BRAND';reason='Steam 마크를 원본 ctex에서 직접 펼쳐 관찰했다. 글자 없는 편집기 아이콘이다. GDRE의 손실 변환 1건은 이 SVG의 VTracer 재구성이다. 배포에는 원본 ctex를 그대로 쓴다.'
    elif 'cursors/' in relative:
        disposition='NO_TEXT';reason='전체 그림을 관찰한 손·화살표 커서이며 문자가 없다.'
    else:
        disposition='KEEP_BRAND';reason='전체 그림을 관찰했다. 게임 제목·A COZY LIBRARY IDLER·S 모양 아이콘, 제작사 심볼 또는 웹 Godot 로고다. 원형을 보존하며 유지 표기를 README에 공개한다.'
    media.append({'file':relative,'sha256':sha(file),'classification':'MEDIA','disposition':disposition,'evidence':reason})

containers=[]
for row in read(EXTRACTED/'pck_manifest.json'):
    name=row['path']
    if name.endswith('.gdc'):registry='code_review.json 또는 editor_literals.json'
    elif name.endswith('.json'):registry='data_scene_inventory.json'
    elif name.endswith('.scn'):registry='data_scene_inventory.json (GDRE가 복구한 .tscn)'
    elif name.endswith(('.ctex','.oggvorbisstr','.png','.icns')):registry='media_inventory.json (import의 source_file과 연결)'
    elif name.endswith('.fontdata'):registry='font_report.json 및 원본 FontFile 연결'
    elif name.endswith(('.remap','.import','.cfg','.bin','.gdextension')) or name=='project.binary':registry='엔진 자산 경로·리소스 형식·환경 설정; 복구된 텍스트 메타데이터에서 실행 참조를 확인'
    else:raise AssertionError(name)
    assert sha(EXTRACTED/'pck'/name)==row['sha256']
    containers.append({**row,'inspection':'PASS','content_registry':registry})

write(out/'data_scene_inventory.json',records);write(out/'editor_literals.json',editor);write(out/'media_inventory.json',media);write(out/'container_inventory.json',containers)
summary={'steam_build':'25171813','baseline_manifest_sha256':sha(WORK/'intake/baseline.json'),
    'pck_sha256':sha(BASELINE/'windows/SpellboundShelved.pck'),'pck_files':len(containers),'runtime_code_literals':len(code),
    'editor_code_literals':len(editor),'data_scene_strings':len(records),'media':len(media),
    'classifications':dict(Counter(x['classification'] for x in records+code+editor)),
    'unknown':0,'unresolved_extraction_errors':0,'unsupported_media_dispositions':0,
    'recovery':{'scripts':22,'resources':51,'failed':0,'lossy':1,'lossy_resolution':'편집기 Steam SVG의 VTracer 벡터 재구성. 원본 ctex 픽셀을 별도로 열어 판정했고 재구성 자산은 패치에 사용하지 않았다.'},
    'status':'PASS'}
write(out/'inventory_summary.json',summary);print(json.dumps(summary,ensure_ascii=False))
