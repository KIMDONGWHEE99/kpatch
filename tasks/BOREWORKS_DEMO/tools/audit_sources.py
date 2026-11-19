"""출처별 위치·해시·판정 근거를 보존하며 미분류는 실패로 남깁니다."""
from common import *
import re,collections

candidate_id='ko_v002'
english=json.loads((WORK/'english.json').read_text(encoding='utf-8'))
ko=json.loads((WORK/'translation/ko.json').read_text(encoding='utf-8'))
changes={(r['method'],r['offset']):r for r in json.loads((WORK/candidate_id/'code_changes.json').read_text(encoding='utf-8'))}
catalog=json.loads((WORK/'catalog.json').read_text(encoding='utf-8'))
def snake(name):
    result=''
    for c in name:
        if c.isalnum():result+=c.lower()
        elif c=='+':result=result.rstrip('_')+'_plus_'
        elif c in ' -:':result=result.rstrip('_')+'_'
    return result.strip('_')
recipes=[]
for r in catalog['recipes']:
    name='recipe.'+snake(r['name'])+'.name'
    desc='recipe.'+snake(r['name'])+'.desc'
    # 생성 로봇·시설은 L.RecipeDisplayName/Description에서 공용 명칭을 사용합니다.
    remapped=r['effect'] in ('SpawnBotEffect','SpawnAndRouteCargoBotEffect','SpawnPathfinderBotEffect','SpawnStationCrateEffect')
    assert remapped or name in ko,(r,name)
    assert remapped or r['effect'] in ('BotResearchEffect','StationResearchEffect') or desc in ko,(r,desc)
    recipes.append(dict(name=r['name'],effect=r['effect'],name_key=name if name in ko else 'L.BotTypeName/L.StationKindName',desc_key=desc if desc in ko else 'L.BotTypeDescription/L.StationKindDescription'))
assert len(recipes)==55
save_json(WORK/'recipe_coverage.json',dict(status='PASS',recipes=recipes,source_sha256=sha((BASE/'data_Boreworks_windows_x86_64/Game.Sim.dll').read_bytes())))

styles=set('font font_size font_color separation h_separation v_separation margin_left margin_right margin_top margin_bottom normal hover pressed disabled focus hover_pressed font_hover_color font_pressed_color font_disabled_color font_outline_color outline_size panel line_spacing modulate modulate:a normal_font bold_font italics_font bold_italics_font mono_font tint bw_base_font_size ui_control_wired slider grabber_area grabber_area_highlight background fill'.split())
controls=set('Panel PanelContainer Button OptionButton PopupMenu CheckBox Label RichTextLabel HSlider TooltipPanel TooltipLabel ProgressBar LineEdit TextEdit SpinBox MenuButton CheckButton LinkButton ItemList Tree TabBar TabContainer PopupPanel'.split())
inputs=set('move_up move_left move_down move_right move_to_cursor mark unmark vein_mine cancel_context boost drop_cargo recall grab_station_buffer quicksave quickload toggle_fullscreen toggle_both_panels toggle_research_panel toggle_fabricator_panel toggle_research_tree toggle_meta_tree'.split())
reviewed_nonui={
 'Game.GifEncoder':'GIF 부호화 헤더·인수 검사 예외. 사용자 안내는 번역표에서 표시',
 'Game.DemoMode':'실행 기능/인수/환경 변수 이름',
 'Game.SwarmRenderer':'그리기 시간 계측 이름과 GD 경고',
 'Game.PlayerController':'입력 동작 식별자',
 'Game.AsteroidRenderer':'텍스처 경로·계측명·생물군계 선택. DescribeAutotileAssets는 호출자 없는 내부 진단',
 'Game.BiomeSelector':'BiomeTheme 선택 식별자. 렌더러 분기에 사용',
 'Game.Blob47':'타일 연결 모양 진단명. AppendBlobLine의 내부 진단으로만 전달',
 'Game.CarryRenderer':'화물 그리기 계측·프레임 경로·위치 진단 문자열',
 'Game.BuildInfo':'빌드 식별 표시 및 로그용 고유 버전',
 'Game.ShotScript':'제작사 자동 검사의 로그·검사 이름',
}
ledger=[]
for assembly in ('Boreworks','Game.Sim','Game.Platform'):
    source_path=BASE/('data_Boreworks_windows_x86_64/'+assembly+'.dll')
    source_hash=sha(source_path.read_bytes())
    methods={m['method']:m for m in json.loads((EXTRACT/'code'/(assembly+'.il.json')).read_text(encoding='utf-8'))}
    for row in json.loads((WORK/(assembly+'.literals.json')).read_text(encoding='utf-8')):
        m,t=row['method'],row['text']; kind='UNKNOWN';reason='아직 검토하지 않은 위치'
        owner=m.split(' ',1)[1].split('::')[0].split('/')[0]
        leaf=m.split('::',1)[1].split('(')[0]
        if (m,row['offset']) in changes:
            kind='TRANSLATE';reason='ko_v002/code_changes.json의 정확한 메서드·명령 위치'
        elif t in english:
            kind='INTERNAL';reason='영어 Translation의 정확한 키. 표시 값은 ko.json에서 교체'
        elif any(s in m for s in ('/MethodName::','/PropertyName::','/SignalName::','GetGodot','InvokeGodot','HasGodot','SaveGodotObjectData','RestoreGodotObjectData')):
            kind='INTERNAL';reason='Godot C# 자동 생성 호출/속성 바인딩 이름'
        elif '::PrintMembers(' in m or '::ToString()' in m:
            kind='INTERNAL';reason='C# record 진단 표현. UI는 L/기능별 포매터를 사용'
        elif t=='' or re.fullmatch(r'\{[a-z_]+\}|[NFDP]\d+',t):
            kind='INTERNAL';reason='빈 초기값 또는 문자열 치환·숫자 서식 토큰'
        elif t in styles or t in controls or t in inputs:
            kind='INTERNAL';reason='검토한 Godot 테마 속성·컨트롤 종류·입력 동작 이름'
        elif t.startswith(('res://','user://','http://','https://')):
            kind='INTERNAL';reason='리소스·저장 위치 또는 열기 대상 URL'
        elif m.startswith('System.String Game.UI.Credits') and ':get_MenuId' not in m:
            pass
        if kind=='UNKNOWN':
            if 'Game.UI.CreditsScreenNode::' in m and (leaf=='.cctor' or t=='Asher'):
                kind='VISIBLE_KEEP';reason='제작진 실명·활동명·저작자 및 라이선스 표기'
            elif t.startswith('C:\\Users\\Player\\'):
                kind='VISIBLE_KEEP';reason='개발 화면의 GIF 저장 경로 견본. 경로 자체는 유지'
            elif leaf in ('get_MenuId','get_LayoutTestStates','get_TextScaleSweepStates','SetLayoutTestState','OpenForTest'):
                kind='INTERNAL';reason='메뉴 등록 식별자·검사 상태 선택 키. Synthetic 표시문은 별도 번역'
            elif not re.search('[A-Za-z가-힣]',t):
                kind='VISIBLE_KEEP';reason='숫자·수학 기호·방향 및 버튼 아이콘·구분자'
            elif owner.startswith('Game.AutoTestDriver'):
                kind='INTERNAL';reason='자동 검사 선택·파일 이름·로그. 표시문은 실제 메뉴/번역표를 호출'
            elif owner.startswith('Game.Localization.'):
                kind='INTERNAL';reason='L.cs의 표시명 키 조합·열거값 분기·내부 예외 또는 의사 번역 생성'
            elif owner.startswith('Game.Settings.'):
                kind='INTERNAL';reason='설정 직렬화 키·입력 동작 식별자. MouseDisplayName 표시문은 별도 번역'
            elif owner.startswith('Game.Sim.Crafting.Workbench'):
                kind='INTERNAL';reason='제작 항목 ID/원본 설명. 55개 전수 목록과 L.RecipeDisplayName/Description 대응 검증'
            elif owner.startswith('Game.Sim.'):
                kind='INTERNAL';reason='규칙/저장/진단 데이터. 표시용 열거값은 L의 명칭 분기와 505개 표로 연결; SaveOrchestrator 예외는 로그로만 전달'
            elif owner.startswith('Game.Platform.'):
                kind='INTERNAL';reason='저장 경로·진단 CSV·효과음 카탈로그·인수 예외. 사용자 UI 문자열을 직접 생성하지 않음'
            elif owner in reviewed_nonui:
                kind='INTERNAL';reason=reviewed_nonui[owner]
            elif owner.startswith(('Game.Steam.','Game.Scenes.SaveOrchestrator','Game.Bots.','Game.Audio.','Game.Animation.','Game.World.HeartCollapseOverlay','Game.UI.Debug.','Game.UI.Framework.')):
                kind='INTERNAL';reason='검토한 연결/저장/그리기/음향/애니메이션/테마/레이아웃 진단 및 리소스 식별자. 표시 오류 안내는 별도 번역 키'
            elif owner=='Game.Main' and leaf!='TickScreenshot':
                kind='INTERNAL';reason='Main의 실행 모드·입력·경로·진단 로그. HUD 출력은 Tr/L 및 번역한 Screenshot 접두어'
            elif t in ('M','k') and leaf=='FormatStockpileCount':
                kind='VISIBLE_KEEP';reason='자원 수량 단위 약자 k/M'
            elif t.endswith(('.png','.ogg','.wav','.gif')) or t.startswith(('hint.','bot:','station:','slot:','crate:','synth:')) or t in ('player','arrow.png','FrostedBackdrop','research_tree'):
                kind='INTERNAL';reason='검토한 파일 이름·힌트 중복 방지 ID·검사 선택 키'
            elif (owner,leaf) in {('Game.PlayerNode','LoadTex'),('Game.Main','TickScreenshot'),('Game.WorkbenchMenuNode','CapHintFor'),('Game.UI.HoverTooltipContent','BuildContentFor')}:
                kind='INTERNAL';reason='재검토한 텍스처 경고·스크린샷 파일 접미어·NotSupported/인수 검사 예외'
            elif owner=='Game.UI.IconCatalog':
                kind='INTERNAL';reason='자원 열거값에서 아이콘 파일 경로를 찾는 매핑. 자원 이름 UI는 L.MaterialName'
            elif owner=='Game.UI.TimelapseOverlayNode' and leaf=='ExportGif':
                kind='INTERNAL';reason='GIF 파일 접두어·타임스탬프 형식과 GD.PushError 진단'
        body=methods[m]['instructions'];idx=next(i for i,x in enumerate(body) if x['offset']==row['offset'])
        ledger.append(dict(assembly=assembly,source_sha256=source_hash,method=m,offset=row['offset'],source=t,classification=kind,reason=reason,evidence=body[max(0,idx-2):idx+8]))
save_json(WORK/'source_ledger.json',ledger)
unknown=[r for r in ledger if r['classification']=='UNKNOWN']
save_json(WORK/'source_unknown.json',unknown)
print('CODE',collections.Counter(r['classification'] for r in ledger))
for r in unknown:print(r['method'],repr(r['source']))

# 이미지 원본과 복원본을 .import 매핑으로 연결합니다.
pack=json.loads((WORK/'pck_inventory.json').read_text(encoding='utf-8'))
images=json.loads((WORK/'media/review.json').read_text(encoding='utf-8'))
save_json(WORK/'coverage_progress.json',dict(status='PASS' if not unknown else 'FAIL',code_strings=len(ledger),unknown=len(unknown),recipes=55,pck_entries=len(pack),translation_keys=len(ko)))
