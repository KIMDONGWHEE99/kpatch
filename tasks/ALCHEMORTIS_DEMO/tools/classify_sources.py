"""원본 출처·실행 경로 근거를 함께 기록하고 남은 미분류를 출력한다."""
from pck_tools import WORK,EXTRACTED,BASELINE
import json,re,hashlib,collections
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
folder=WORK/'discovery'
rows=read(folder/'code_strings.json');po=read(WORK/'translation/source.json');keys={r['key'] for r in po};keys|={r['plural_key'] for r in po if r['plural_key']}
resource=read(folder/'resource_strings.json');snap=read(folder/'original_code.json.snapshot.json');methods={r['method']:r for r in snap['methods']}
member_names=set()
for t in snap['types']:
    member_names.add(t['name'].split('.')[-1].split('/')[-1])
    for f in t['fields']:member_names.add(f['name'].split('::')[-1])
    for p in t['properties']:member_names.add(p.split('::')[-1].split('(')[0])
for m in snap['methods']:member_names.add(m['method'].split('::')[-1].split('(')[0])
paths=list((EXTRACTED/'recovered').rglob('*'));stems={p.stem for p in paths if p.is_file()}
source_hash=hashlib.sha256((BASELINE/'data_Alchemortis_windows_x86_64/Alchemortis.dll').read_bytes()).hexdigest()
translated={(r['method'],r['offset']) for r in read(WORK/'translation/code_changes.json')}
generated=('GetGodot','SetGodot','InvokeGodot','HasGodot','SaveGodot','RestoreGodot','RaiseGodot','MethodName::.cctor','PropertyName::.cctor','SignalName::.cctor')
results=[];unknown=[]
for row in rows:
    m=row['method'];s=row['source'];context='\n'.join(row['context']);classification='UNKNOWN';reason=''
    if (m,row['offset']) in translated:classification='VISIBLE_TRANSLATE';reason='위치별 코드 변경 명세 또는 한국어 기본 언어 선택'
    elif s in keys:classification='VISIBLE_TRANSLATE';reason='원본 PO에 존재하는 번역 키; 후보 위치 대조 및 실행 번역표 검사'
    elif any(x in m for x in generated):classification='INTERNAL';reason='Godot 자동 생성 바인딩의 메서드·속성·신호 식별자'
    elif 'WireNodes(' in m:classification='INTERNAL';reason='장면 객체 연결 검색어와 연결 실패 진단; WireNodes 원본 호출 흐름'
    elif 'Sentry.Generated.' in m:classification='INTERNAL';reason='오류 보고 라이브러리의 빌드 속성 초기화; 사용자 UI 아님'
    elif '::PrintMembers(' in m:classification='INTERNAL';reason='C# record 컴파일러 생성 진단 문자열; 필드 이름 출력'
    elif 'Game.Util.GameConstants::.cctor' in m or 'Game.Util.GameDebug::.cctor' in m:classification='INTERNAL';reason='입력 행동 이름·색상 상수·시작 인자 식별자 초기화'
    elif 'Game.Util.Keywords' in m and '.ctor(' in m or 'Game.Util.Keywords::.cctor' in m:classification='SOURCE_TEMPLATE';reason='Keyword의 원어 단어·활용형. WordLocalized 및 한국어 Format 분기에서 KEYWORD_ 번역 사용'
    elif 'DescriptionUtils::' in m and any(x in m for x in ['ApplySecondsSingular','SecondsKeySuffix','GetParameterFormatSpecifiers','.cctor']):classification='SOURCE_TEMPLATE';reason='번역표 작성 및 원어 템플릿 처리의 정규식·키 접미사'
    elif 'DescriptionUtils::' in m and any(x in m for x in ['CreateIconString','WrapColor','FloatToPercent','ToLocalizedNumber','ToRomanNumeral']):classification='VISIBLE_KEEP';reason='BBCode 서식·숫자 형식 코드·로마 숫자; 한국어에서도 의미 보존'
    elif 'Game.Util.Keyword::' in m and any(x in m for x in ['get_TextTranslationKey','get_KeywordPrefix']):classification='INTERNAL';reason='번역 키 또는 키워드 마크업 식별자의 접두·접미사'
    elif '.cctor(' in m and any(x in '\n'.join(i['operand'] for i in methods[m]['instructions']) for x in ['Godot.StringName::op_Implicit','Godot.StringName::.ctor']) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',s):classification='INTERNAL';reason='StringName 정적 초기화의 셰이더·테마·애니메이션·노드 식별자; 원본 메서드 전체 IL 참조'
    elif 'Game.UI.Tutorial.TutorialGuide::' in m or 'Game.UI.Tutorial.TutorialGuide/' in m:classification='INTERNAL';reason='튜토리얼 상태 전환 ID 또는 아이템 묶음 노드 그룹 검색; 표시 문구는 별도 PO 키'
    elif 'Game.Data.' in m and any(x in m for x in ['::GetId(','::get_EffectId(','::IdForTag(']):classification='INTERNAL';reason='저장·등록 조회용 안정 식별자 접근자'
    elif 'Game.Data.' in m and any(x in m for x in ['::GetDescriptionTemplate(','g__GetDescriptionTemplate','::ToQueryStringTemplate(']):classification='SOURCE_TEMPLATE';reason='원어 능력 설명 템플릿 생성; 번역 키를 통해 번역문을 조회하는 부모 클래스 경로'
    elif 'Game.Data.BoardEffect.' in m and any(x in m for x in ['get_Description(','OrientationKey(','LeadInKey(','GetSharedTooltipTranslationEntries','GetTooltipTranslationEntries']):classification='SOURCE_TEMPLATE';reason='행·열 효과 번역 키 및 원어 템플릿 생성; BaseBoardEffect 번역 항목 생성·조회 경로'
    elif m.startswith(('System.Void Test.','System.String Test.','System.Boolean Test.')) or 'Test.' in m.split('::')[0]:classification='INTERNAL';reason='내장 자동 시험의 입력·기댓값·실패 메시지; 일반 게임 표시 경로 아님'
    elif s.startswith(('res://','uid://','user://','http://','https://')):classification='INTERNAL';reason='자원·파일 또는 외부 링크 주소; 경로를 번역하면 참조 변경'
    elif not re.search('[A-Za-z가-힣]',s):classification='VISIBLE_KEEP';reason='공백·수치·문장 부호·서식 구분자'
    elif re.fullmatch(r'(?:UI|CARD|ABILITY|ARTIFACT|CHARACTER|KEYWORD|EVENT|UNLOCK|LORE|MAP_NODE_EFFECT|DIFFICULTY|CHALLENGE|OBELISK|ENCHANT|BUFF)_[A-Z0-9_]*',s):classification='INTERNAL';reason='동적 번역 키의 접두부 또는 키 구성 요소; 실행 카드 목록과 번역 키 대조'
    elif s in member_names and ('StringName' in context or 'Godot' in m or s[0].isupper()):classification='INTERNAL';reason='원본 형식·필드·메서드 목록과 일치하는 코드 식별자'
    elif ('Game.Data.' in m and ('.ctor(' in m or 'get_DescriptionTemplate(' in m or 'b__' in m or '.cctor(' in m) and not any(x in m for x in ['Save.','Statistics.','Run.','Json.'])):
        classification='SOURCE_TEMPLATE';reason='데이터 정의의 원어 템플릿·능력/자원 ID. BaseComposedAbility.GetDescription 및 각 Resource의 Localized 속성에서 번역 키 조회; 275종×5등급 실행 검사에 연결'
    elif ('Game.Component.BoardInventoryComponent/QueryOptions::ToQueryStringTemplate' in m):classification='SOURCE_TEMPLATE';reason='능력 원어 템플릿 생성용 조각; 실행 시 생성한 DescriptionTranslationKey의 PO 번역을 표시'
    elif 'Game.Tool.' in m or 'Game.Autoload.CheatHelper' in m:
        classification='INTERNAL';reason='개발 편집·내보내기·치트 도구. 배포 실행에서 IsDebugBuild=false 및 IsCheatsBuild=false 확인; 원본 GameDebug.IsCheatsEnabled와 도구 진입 경로'
    elif any(x in context for x in ['Game.Util.Log::','::PushError(','::PushWarning(','Exception::.ctor(','Console::Write']):classification='INTERNAL';reason='해당 IL 위치에서 진단 로그 또는 예외 생성으로 전달'
    elif 'GetConfigurationWarnings(' in m:classification='INTERNAL';reason='Godot 편집기 설정 경고 전용 반환값'
    elif ('/Json.' in m or '.Json.' in m or 'JsonConverter' in m or 'JsonSerializer' in m):classification='INTERNAL';reason='저장 형식의 속성 이름·파싱 검증·예외 메시지'
    elif re.fullmatch(r'[a-z0-9_]+',s) and (s in stems or any(x in m for x in ['get_Id(','get_Key(','Factory::','Registry::'])):classification='INTERNAL';reason='원본 자원 파일 이름 또는 ID/Key 접근자·등록/검색 함수의 조회 식별자'
    elif any(x in m for x in ['Game.Util.Log::','Game.Util.SentrySink::','DataInitializer::','Game.Data.Save.Migration.']):classification='INTERNAL';reason='저장·설정·이전 처리 및 로그 기록의 파일 경로와 진단 문구'
    elif 'Game.UI.LanguageSelectionDialog::.cctor' in m:classification='VISIBLE_KEEP';reason='기존 언어의 자국어 이름과 표준 언어 코드 보존; 한국어 별도 추가'
    elif 'ButtonPrompt::GetIconTextureForText' in m or 'InputEvent' in m and 'GetText' in m:classification='VISIBLE_KEEP';reason='물리 키·컨트롤러 버튼 식별 표기와 아이콘 선택 토큰'
    elif re.fullmatch(r'[A-Za-z0-9_./%:\\-]+',s) and (any(x in s for x in ['/','\\','.']) or s.startswith('%')):classification='INTERNAL';reason='객체·설정·파일 경로 형태의 참조 토큰; 표시 문구와 별도 조사'
    elif any(x in m for x in ['Game.Util.CardBoardUtils::','OptionsUtils::set_Locale','UnlockMenu/','MapDecorationPlacer','SelectableCharacter::SetCharacter','TagLabel::SetTag','TagLabel::SetSecondaryTag','ArtifactManager::AccumulateModifier','BoardManager::AddBoardPlacementLock','BoardManager::RemoveBoardPlacementLock','CardMouseEventsManager::ExhaustivelyFindDisplacementPositionForCard','CardMouseEventsManager::ChangeCardInputState','FocusManager::TryGrabPendingResumeTarget','FocusManager::OnFocusOwnerVisibilityChanged','RunSaveManager::','StateUtils::GetStateMachineForEvent','CardFactory::Derive','SeededRun::','RunMapGenerator::AssignNodeTypes','MapNodeEffectFactory::FromSaveModel','BaseEnchant::FromSaveModel','CombatConfiguration::Generate','BaseCard::','BaseCard/','BuffApplicator`1::Execute','BoardCombatComponent::Damage','TurnExecutorComponent::DoTurnTick','CharacterPlatform::Setup','AudioHelper::OnNotorietyRegionEntered','AudioHelper::OnShopExited']) and any('Game.Util.Log::' in i['operand'] for i in methods[m]['instructions']):
        classification='INTERNAL';reason='검토한 해당 메서드의 문자열 조립 결과가 Log 진단 함수로 전달됨; 원본 전체 IL 호출 근거'
    elif 'MapDecorationPlacer::DecidePlacementsForDefinition' in m or 'MapDecorationPlacer/RoadGrid::CreateRoadGrid' in m:classification='INTERNAL';reason='지도 생성 소요 시간 진단; 조건부 Debug.Print 원본 소스 경로'
    elif 'FocusManager::DescribeFocusFailure' in m or 'FocusContextBoundaryManager::get_ActiveScopeDescription' in m:classification='INTERNAL';reason='TryGrabPendingResumeTarget의 Log.Warning 실패 사유로만 연결'
    elif 'Game.Util.Input.InputChords::' in m:classification='INTERNAL';reason='복합 입력 행동 이름 생성·등록 규칙'
    elif 'OptionsUtils::CreateCulture' in m:classification='INTERNAL';reason='지원하지 않는 숫자 문화권 처리 시 숫자 형식 폴백 코드'
    elif 'SentrySink/' in m:classification='INTERNAL';reason='오류 기록에 첨부하는 메타데이터 속성 이름'
    elif s in ['CardTooltipSecondary','EnemyDefeated','BloodCurrencyTarget','ResurrectionStoneCurrencyTarget','TutorialFirstBoosterGroup']:classification='INTERNAL';reason='해당 원본 메서드의 노드 그룹 이름 조회·등록'
    elif 'Game.Steam.SteamService::' in m:classification='INTERNAL';reason='GodotSteam 싱글턴 이름과 원격 함수 이름; 화면 문구 아님'
    elif 'Game.UI.Map.MapNodeTooltip::' in m:classification='INTERNAL';reason='IsDebugShowMapNodeTooltipsEnabled 분기 내부 개발용 점수·판 크기 표시; 원본 조건 확인'
    elif 'RunStatisticsManager::' in m or 'Game.Data.Statistics.RunStatistics::' in m or 'Game.Data.Unlock.Challenge.' in m:classification='INTERNAL';reason='통계 카운터 저장·조회 키 또는 번역 키 접미사; 사용자 표시 설명은 PO 키로 별도 조회'
    elif 'Game.UI.RunOverview.RunOverview::' in m:classification='INTERNAL';reason='결과 화면 통계·도전 조회 ID, 테마 속성, BBCode 서식 또는 제거 정규식; 표시 문구는 PO 조회'
    elif 'Game.UI.Prompt.ButtonPrompt::.cctor' in m:classification='VISIBLE_KEEP';reason='플랫폼 이름 및 Ctrl/Shift/Alt 등 실제 물리 키 표기'
    elif 'Game.UI.PauseMenu::OnQuitToMenuPressed' in m and s=='T':classification='VISIBLE_KEEP';reason='DateTime.ToString의 긴 시간 형식 지정 코드'
    elif s in ['position:x','position:y','screenshot_','boss_alchemy_added_ability']:classification='INTERNAL';reason='애니메이션 속성·스크린샷 파일 접두사·보상 능력 ID'
    elif 'DifficultyTiers/DifficultyTierEntry::' in m:classification='SOURCE_TEMPLATE';reason='난이도 원어 이름과 번역 키 접미사; DifficultyOption에서 NameTranslationKey 조회'
    elif 'Game.Data.Run.Tutorial.TutorialRunBlueprint/' in m:classification='INTERNAL';reason='튜토리얼 지도에 넣을 행·열 효과 및 마법 부여 ID'
    elif 'Game.Data.Run.Blueprint.RunBlueprint::' in m:classification='INTERNAL';reason='지도 제작 자료의 Validate 계열 진단 결과 목록; 플레이 설명 아님'
    elif 'Game.Data.CombatStats.LogLabelUtils::PrintTable' in m:classification='VISIBLE_KEEP';reason='표 열의 오른쪽 정렬 BBCode 태그'
    elif '::ToString()' in m and any(x in m for x in ['LogStatRow`1','BoardEffectModifierKey`1','ArtifactModifierKey`1','ArtifactEvent`1']):classification='INTERNAL';reason='컴파일러 생성 record ToString의 형식 이름'
    elif 'ArtifactResource::Initialize' in m and s=='_ADDENDUM':classification='INTERNAL';reason='보물의 부연 설명 번역 키 접미사'
    elif 'BoardInventoryComponent/QueryOptions::<ToQueryStringTemplate>' in m:classification='SOURCE_TEMPLATE';reason='원어 능력 번역 항목을 만드는 목록 접속어; 표시 단계에서 최종 키로 번역 조회'
    elif 'CombatLogGroup::GetAggregatedSummary' in m and s==' (x':classification='VISIBLE_KEEP';reason='효과 횟수의 수학적 곱셈 표기'
    item=dict(row,classification=classification,reason=reason,source_file='data_Alchemortis_windows_x86_64/Alchemortis.dll',source_file_sha256=source_hash)
    results.append(item)
    if classification=='UNKNOWN':unknown.append(item)
(folder/'code_classification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
(folder/'code_unknown.json').write_text(json.dumps(unknown,ensure_ascii=False,indent=2),encoding='utf-8')
print(collections.Counter(r['classification'] for r in results),'미분류 고유 문자열',len({r['source'] for r in unknown}))
for r in unknown[:120]:print(r['method']+' @'+str(r['offset'])+' '+repr(r['source']))
