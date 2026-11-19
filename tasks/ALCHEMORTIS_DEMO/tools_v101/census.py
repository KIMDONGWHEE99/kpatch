"""코드·자원·메타데이터·이미지를 원본 해시와 연결한 조사 장부를 만든다."""
from pck_tools import WORK,EXTRACTED,BASELINE
from pathlib import Path
import json,re,hashlib,collections
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
discovery=WORK/'discovery';root=EXTRACTED/'recovered';raw=EXTRACTED/'raw'
po=read(WORK/'translation/source.json');targets=read(WORK/'translation/ko_full.json');sources={x['text'] or x['forms'].get('0') for x in po}
pack=read(discovery/'pck_inventory.json');packmap={x['path']:x for x in pack}
code=read(discovery/'code_classification.json');assert all(x['classification']!='UNKNOWN' for x in code)
resources=[];unknown=[]
covered={(x['path'],x['line'],x['field']):x for x in read(WORK/'translation/resource_coverage.json')}
for r in read(discovery/'resource_strings.json'):
    f=r['field'];s=r['source'];key=(r['path'],r['line'],f);classification='UNKNOWN';reason=''
    if key in covered:classification=covered[key]['classification'];reason=covered[key]['reason']
    elif f in ['DisplayName','FlavorText','Description','Text','Title','Name','name'] and s in sources:
        classification='SOURCE_TEMPLATE';reason='원어 PO와 정확히 일치하는 자원 이름·설명; 각 Resource.Localized 속성이 번역 키를 조회'
    elif f in ['metadata/_custom_type_script','load_path','resource_name','UnlockResourceId','ArtifactId','CharacterId','UniqueCharacterId','BoardEffectId','name']:
        classification='INTERNAL';reason='자원·스크립트 참조, 등록 ID 또는 내부 자원 이름'
    elif re.fullmatch(r'tracks/\d+/type',f):classification='INTERNAL';reason='Godot 애니메이션 트랙 형식'
    elif f=='code':classification='INTERNAL';reason='내장 셰이더 코드; 화면 문자열을 출력하는 코드 아님'
    item=dict(r,classification=classification,reason=reason)
    resources.append(item)
    if classification=='UNKNOWN':unknown.append(item)
save(discovery/'resource_classification.json',resources)
attributes=[]
constants={r['name']:r['constant'] for t in read(discovery/'original_code.json.snapshot.json')['types'] for r in t['fields']}
for r in read(discovery/'original_code.json.attributes.json'):
    if 'TranslationStringAttribute' in r['constructor']:
        key=constants.get(r['owner']);valid=key in targets
        classification='SOURCE_TEMPLATE' if valid else 'UNKNOWN';reason='필드 이름과 원본 PO 번역 키 일치' if valid else '번역 키 미확인'
    else:classification='INTERNAL';reason='컴파일러·Godot 편집기·JSON 저장·장면 연결 속성; 실행 UI 문구 아님'
    item=dict(r,classification=classification,reason=reason);attributes.append(item)
    if classification=='UNKNOWN':unknown.append(item)
save(discovery/'attribute_classification.json',attributes)
# 이미지의 문자 검수 결과와 실제 참조 검색 결과를 기록합니다.
texts={653:'Stash; Sell',679:'Demo',680:'Alchemortis',699:'Alchemortis',836:'Alchemortis',760:'Inventory',761:'Sell',417:'Stash; Sell',710:'Stash; Sell; Booster I',432:'Life 형태의 장식 문자'}
textfiles=[]
for base in [root,EXTRACTED/'decompiled']:
    for p in base.rglob('*'):
        if p.suffix in ['.tscn','.tres','.gd','.cs','.gdshader']:
            textfiles.append((p,p.read_text(encoding='utf-8',errors='replace')))
images=[]
for r in read(WORK/'media/inventory.json'):
    path=root/r['path'];imp=Path(str(path)+'.import');imported=[];uid='';refs=[]
    if imp.exists():
        t=imp.read_text(encoding='utf-8');imported=re.findall(r'path="res://([^"]+)"',t);u=re.search(r'uid="([^"]+)"',t);uid=u[1] if u else ''
    if r['index'] in texts:
        for p,t in textfiles:
            if 'res://'+r['path'] in t or uid and uid in t:refs.append(str(p.relative_to(EXTRACTED)))
        reason='게임 고유명사·데모 버전 로고 유지' if r['index'] in [679,680,699,836] else '참조되지 않는 이전 제작 참고 이미지; 전체 복원 장면·자원·스크립트의 경로/UID 참조 검색 0건'
        if r['index'] not in [653,679,680,699,836] and refs:unknown.append(dict(r,reason='참고 이미지 실제 참조 발견',refs=refs))
        classification='MEDIA_KEEP_BRAND' if r['index'] in [679,680,699,836] else 'MEDIA_KEEP_UNUSED_REFERENCE'
        if r['index']==653:classification='MEDIA_TRANSLATE_NATIVE_UI';reason='실제 튜토리얼에서 Stash/Sell 확인. PlayerInventory._Ready에서 inventory_labels.tscn을 그림 위에 추가하며 한국어일 때 보관함/판매 표시; 그림 원본·다른 언어 보존'
    else:reason='전체 12개 검토판 판독 및 복합 이미지 원본 크기 재확인: 번역할 문자 없음';classification='MEDIA_NO_TEXT'
    images.append(dict(r,status='PASS',classification=classification,reason=reason,readable_text=texts.get(r['index'],''),references=refs,imported=[dict(path=x,sha256=packmap[x]['sha256']) for x in imported]))
save(WORK/'media/classification.json',images)
image_imports={x['path']:r for r in images for x in r['imported']}
for row in pack:
    ext=Path(row['path']).suffix;reason='';classification='UNKNOWN'
    if ext in ['.res','.scn']:classification='RESOURCE_AUDITED';reason='GDRE 복원 성공; resource_classification.json의 위치별 속성 조사 및 원어 PO 대조'
    elif ext=='.cs':classification='CODE_AUDITED';reason='내보낸 C# 스크립트 표식; 실제 실행 코드는 Alchemortis.dll 전체 ldstr·메타데이터·enum 조사'
    elif ext in ['.ctex','.dpitex','.png','.ico']:
        if row['path'] in image_imports:classification=image_imports[row['path']]['classification'];reason='media/classification.json의 해당 이미지·검토판·원본 해시'
        elif row['path'].endswith('.dpitex') or 'steam.svg' in row['path']:classification='MEDIA_KEEP_BRAND';reason='Sentry 또는 Steam SVG 상표 아이콘; SVG 원문에서 text 요소 없음 확인'
        elif row['path'] in ['client_icon.ico','client_icon.png']:classification='MEDIA_NO_TEXT';reason='게임 실행 아이콘의 원본 PNG 판독: 문자 없는 그림'
    elif ext in ['.sample','.oggvorbisstr','.mp3str']:classification='MEDIA_KEEP_AUDIO';reason='원본 효과음·배경음 자산 유지; 음원 번역·재녹음은 본 문자 패치 변경 대상 아님'
    elif ext=='.fontdata':classification='FONT_AUDITED';reason='fonts/config.json 및 engine_report.json에서 전체 10개 글꼴의 필요 문자·대체 글꼴 검사'
    elif ext=='.po':classification='TRANSLATION_AUDITED';reason='원본 전체 키 추출; 기존 언어 파일은 보존하고 ko.po 추가'
    elif ext=='.gdc':classification='SCRIPT_AUDITED';reason='전체 19개 GDScript 복원. 도구/애니메이션/피드백 제어; 표시 문구는 장면의 자동 번역 대상'
    elif ext in ['.gdshader','.gdshaderinc']:classification='INTERNAL';reason='GPU 색상·변형 셰이더; 문자열 표시 자원 없음'
    elif ext in ['.import','.remap','.cfg','.gdextension','.bin','.dat','.binary']:classification='INTERNAL';reason='Godot 가져오기/경로/확장 라이브러리/설정/UID 식별 자료; project.binary 변경 경계 독립 대조'
    row.update(classification=classification,reason=reason)
    if classification=='UNKNOWN':unknown.append(row)
save(discovery/'pck_classification.json',pack);save(discovery/'census_unknown.json',unknown)
report=dict(status='PASS' if not unknown else 'FAIL',code_locations=len(code),resource_fields=len(resources),attributes=len(attributes),images=len(images),pack_entries=len(pack),unknown=len(unknown),source_dll_sha256=sha(BASELINE/'data_Alchemortis_windows_x86_64/Alchemortis.dll'),source_pck_sha256=sha(BASELINE/'Alchemortis Demo.pck'))
save(discovery/'census_report.json',report);print(report)
for r in unknown:print(str(r)[:1000])
