"""PCK·미디어·상수·문자 지원 근거를 하나의 빌드에 연결합니다."""
from common import *
import re,sys,collections
sys.path.insert(0,str(ROOT/'tools/python_deps'))
from fontTools.ttLib import TTFont

pack=json.loads((WORK/'pck_inventory.json').read_text(encoding='utf-8'))
raw=EXTRACT/'raw';index={r['path']:r for r in pack}
images=json.loads((WORK/'media/review.json').read_text(encoding='utf-8'))
image_map={};imports={}
for p in raw.rglob('*.import'):
    match=re.search(r'^path="res://([^"]+)"',p.read_text(encoding='utf-8'),re.M)
    if match:imports[match[1]]=p.relative_to(raw).as_posix()[:-7]
for row in images:
    rel=Path(row['file']).relative_to(EXTRACT/'recovered').as_posix()
    linked=[name for name,value in imports.items() if value==rel]
    assert linked,(row['id'],rel)
    for name in linked:
        image_map[name]=row
    row['original_resources']=[dict(path=name,sha256=index[name]['sha256'],import_path=rel+'.import',import_sha256=index[rel+'.import']['sha256']) for name in linked]
save_json(WORK/'media/provenance.json',images)
ledger=[]
for r in pack:
    name=r['path'];suffix=Path(name).suffix;kind='UNKNOWN';disposition='UNKNOWN';reason='미분류'
    if name in image_map:
        v=image_map[name];kind='MEDIA';disposition=v['disposition'];reason=v['reason']+'; '+v['review']
    elif name in ('Art/Assets/UI/Brand/boot_splash.png','icon.png','icon.ico'):
        kind='MEDIA';disposition='KEEP';reason='시작 로고/게임 아이콘 원본. 대응 이미지 육안 검토 146/189에 연결'
    elif suffix=='.oggvorbisstr':
        assert name in imports
        kind='MEDIA';disposition='KEEP_AUDIO';reason='음악·환경음·효과음은 원음을 유지. 화면 글자와 글꼴 패치이며 더빙 없음. SfxCatalog와 Audio/sfx-picks.json 용도에 연결'
    elif suffix=='.fontdata':
        kind='FONT';disposition='REPLACE';reason='Noto Sans KR 400/700; ko_v002/font_report.json과 실제 Theme 사용 위치'
    elif suffix=='.translation':
        kind='TRANSLATE';disposition='REPLACE';reason='505개 키를 모두 복원하여 ko_v002/actual_ko.json과 대조'
    elif suffix=='.cs':
        assert (raw/name).read_bytes()==b'\n'
        kind='INTERNAL';disposition='KEEP';reason='C# 리소스의 빈 자리표시자. 실제 코드는 3개 어셈블리 전체를 ILSpy/Cecil로 조사'
    elif suffix=='.scn':
        kind='INTERNAL';disposition='KEEP';reason='유일한 Main 장면. Node2D와 C# 스크립트 참조만 존재. recovered/Scenes/Main.tscn 재확인'
    elif suffix in ('.import','.remap','.cfg','.bin','.binary','.gdshader','.json'):
        kind='INTERNAL';disposition='KEEP';reason={'.import':'Godot 가져오기 경로와 형식 정보','.remap':'장면 리소스 경로 대응','.cfg':'빈 global_script_class_cache','.bin':'Godot UID와 리소스 경로 대응','.binary':'project 설정(주 장면·언어 파일·화면/음향 설정)','.gdshader':'화면 배경 그리기 코드, 표시 문자열 없음','.json':'로봇 동작 설정·타일 좌표·음원 선택/권리/음량 설정. 화면 문구가 아닌 데이터'}[suffix]
    # 공유 보고서에는 원본 자산을 넣지 않고 비공개 증거를 참조합니다.
    ledger.append(dict(r,classification=kind,disposition=disposition,reason=reason,source_asset=imports.get(name)))
unknown=[r for r in ledger if 'UNKNOWN' in (r['classification'],r['disposition'])]
assert not unknown,unknown
save_json(WORK/'asset_ledger.json',ledger)

source_ledger=json.loads((WORK/'source_ledger.json').read_text(encoding='utf-8'))
metadata=json.loads((WORK/'Boreworks.metadata.json').read_text(encoding='utf-8'))
constant_rows=[]
values={r['source']:r for r in source_ledger if r['assembly']=='Boreworks'}
english=json.loads((WORK/'english.json').read_text(encoding='utf-8'))
for type_row in metadata:
    for f in type_row['fields']:
        value=f.get('constant')
        if not isinstance(value,str):continue
        matched=values.get(value)
        if matched:kind='INTERNAL';reason='C# 컴파일 시 상수. 사용 위치는 source_ledger의 대응 ldstr 위치에서 판정'
        elif value in english:kind='INTERNAL';reason='복원한 번역 키'
        elif f['name'].startswith('System.String Game.Localization.L::'):kind='INTERNAL';reason='예약된 번역 키. 직접 표시하지 않는 컴파일 시 상수'
        elif value.startswith(('res://','https://')):kind='INTERNAL';reason='파일/URL 참조'
        elif value in ('HEAD','v1.0.5'):kind='VISIBLE_KEEP';reason='게임 빌드 고유 식별자'
        else:kind='UNKNOWN';reason='추가 조사 필요'
        constant_rows.append(dict(f,classification=kind,reason=reason,ldstr_reference=matched['method'] if matched else None))
unknown_constants=[r for r in constant_rows if r['classification']=='UNKNOWN']
save_json(WORK/'constant_ledger.json',constant_rows)
print('CONSTANT_UNKNOWN',unknown_constants)
assert not unknown_constants

# 원래 기호용 대체 글꼴을 포함하여 유지할 표시 문자까지 모두 대조합니다.
characters=set((WORK/'ko_v002/required_characters.txt').read_text(encoding='utf-8'))
for r in source_ledger:
    if r['classification']=='VISIBLE_KEEP':characters.update(r['source'])
characters-=set('\n\r\t')
fonts=[WORK/'ko_v002/Korean400.ttf',WORK/'ko_v002/Korean700.ttf',Path('C:/Windows/Fonts/seguisym.ttf'),Path('C:/Windows/Fonts/seguiemj.ttf'),Path('C:/Windows/Fonts/segoeui.ttf')]
coverage=[];union=set()
for path in fonts:
    cmap=set(TTFont(path).getBestCmap());union|=cmap
    coverage.append(dict(path=str(path),sha256=sha(path.read_bytes()),supported=sorted(ord(c) for c in characters if ord(c) in cmap)))
missing=sorted(ord(c) for c in characters if ord(c) not in union)
assert not missing,missing
save_json(WORK/'font_graph.json',dict(status='PASS',required_characters=len(characters),fonts=coverage,missing=missing,fontdata_resources=[r['path'] for r in pack if r['path'].endswith('.fontdata')],rendering='Godot FontFile/FreeType의 동적 글리프 캐시. 고정 TMP 아틀라스 없음. 실제 글자는 GPU에서 검사',paths=['BoreworksTheme.Populate','BoreworksTheme.BuildSystemFont','BoreworksTheme.TryLoadFontWithFallback','PlayerNode.DrawOverflowBadge'],fallback_boundary='ResearchBadgeChevronButton은 숫자와 +만 사용'))
save_json(WORK/'asset_coverage_report.json',dict(status='PASS',pck_entries=len(pack),counts=dict(collections.Counter(r['classification'] for r in ledger)),media_dispositions=dict(collections.Counter(r['disposition'] for r in ledger if r['classification']=='MEDIA')),constants=len(constant_rows),unknown=0,unresolved_extraction_errors=0,resolved_errors=[dict(tool='GDRE',failure='C# decompiler failed',resolution='ILSpy로 3개 DLL 전체 복원, Cecil로 9371개 문자열 위치 독립 대조'),dict(tool='GDRE',failure='OptimizedTranslation keys missing',resolution='실제 리소스 get_message 조회로 505/505개 키 복원')]))
print('ASSET_COVERAGE_PASS',len(pack),len(constant_rows),len(characters))
