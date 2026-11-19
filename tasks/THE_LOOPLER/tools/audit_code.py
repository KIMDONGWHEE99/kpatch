"""코드 문구의 사용 위치와 명시적인 소비 경로를 연결합니다. 남은 항목은 미확인입니다."""
from common import *
from pathlib import Path
import json,re,collections

review=WORK/'review'
rows=json.loads((review/'code_context.json').read_text('utf-8'))
assets=json.loads((EXTRACT/'strings.json').read_text('utf-8'))
keys={r['source'] for r in assets if r['field'].endswith('/m_Key')}
ids={r['source'] for r in assets if r['field'].split('/')[-1] in ('gateID','upgradeID','charmID','partID','infID','unlockID','itemID','specialID','modifierID','challengeID')}
canon=json.loads((WORK/'translation_canonical.json').read_text('utf-8'))
def norm(s):return re.sub(r'\s+',' ',s.replace('\\n','\n')).strip().casefold()
table={norm(r['source']):r['translation'] for r in canon}
runtime=json.loads((WORK/'translation_parts/runtime_extra.json').read_text('utf-8'))
internals=('AccountSaveStorage','SaveSystem','SaveFileIO','SaveIntegrity','SaveSecurity','RunAnalyticsReporter','RunResultAnalyticsEvent','RunLoadoutItemAnalyticsEvent','ClientIntegrity','LeaderboardPlausibility','LeaderboardRunProof','ControlsManager')
ui_build_methods={'ChallengeChoice':('AutoBind','FindSelector','FindLoadedSprite'),'CreditsManager':('BuildCredits','CreateLogo','EnsureRuntimeView','CreateControlsOverlay'),'RunSummaryContentController':('Initialize','ConfigureTabFeedback','AddEntry','CreateGateTooltip','CreateCardTooltip','CreateCharmTooltip','SetStat'),'RunSummaryMenu':('DiscoverReworkedLayout','ResetMenu'),'SettingsMenu':('ConfigureCRTStrengthNavigation','SetupCreditsButton','DisableBackButtonNavigation','IsBackButton'),'TrackSelectMenu':('DisableControllerOnlyButtons',),'TutorialDirector':('BuildUI','BuildOffer','EnsureInputBlockers','EnsurePauseProxy','FindSnailmer','ApplyWindowSprite'),'RoundSelectMenu':('EnsureRewardControlHints','CreateRewardHint')}
key_parts=set('RARITY_ TYPE_ _NAME PART_SUFFIX_ CHALLENGE_ _DESCRIPTION _MODIFIER _EFFECT _TITLE _BODY COLOUR_ PATTERN_ DIFF_NAME_{0} TRACK_NAME_{0} RUN_FAILURE_QUOTE_{0:00} RUN_VICTORY_QUOTE_{0:00}'.split())
units={'x','X','k','m','s','{0}x','{0}X','{0:F2}e{1}','{0}e{1}','0.00e+0','N0','mm\\:ss','\\:mm\\:ss'}
dates={'yyyy-MM-dd','yyyyMMdd','{0}-W{1}'}
animation_ids=set('runsummary packopening cardupgrademat carpartexchange pausing TooltipClose DriveCar TurnOnTrail FadeButton OpenRoundSelect CheckBreakpoints'.split())
reviewed_internal={
 'Alchemist_Upgrade':('Alchemist',), 'AspectRatioController':('Left','Right','Top','Bottom'),
 'BraceletOpeningMenu':('extracharm',),'ChallengeCatalog':('ChallengeCatalog',),'ChallengeChoice':('DoubleRewards',),
 'CreditsManager':('CreditsData',),'GateBuffOrbitIndicator':('Gate Buff Indicator {0}',),
 'GateGourmet_Upgrade':('Gate Gourmet',),'GateManager':('Track_Image',),'GlobalVariables':('Selected: ','PlayerID'),
 'HUDGarageMenu':('stat',),'Jackpot_Gate':('Jackpot gate',),
 'LoadoutMenu':('tempCard{0}','tempCard','tempCharm{0}','tempCharm','tempGate{0}','tempGate','LPL1|'),
 'MenuLeaderboard':('BoardLeaderboard',),'OptionsData':('en',),'OptionsManager':('masterVol','musicVol','sfxVol'),
 'PitStop':('endlessupgrade',),'Profile':('PlayerID',),'ProfileMenu':('Achievements',),
 'RoundModifierCatalog':('RoundModifierCatalog',),'RoundNodeUI':('Icon','Boss_Name_Body','Boss_Effect_Body','Hazard_Name_Body','Hazard_Effect_Body'),
 'RunEffectRecorder':('Mirror Gate',),'RunSummaryMenu':('ITEM_LEVELS','FIRST_BONUS'),
 'RunXPBreakdown':('Empty',),'SimulationManager':('Exploding Car','Speed is zero','While loop'),
 'SteamAvatarTest':('[unknown]',),'Track_Item':('Empty',),'Track_Item_NestedType___c':('Track_Image','Track_Extra_Image'),
 'TrackChoice':('Arrow_',),'TutorialDirector':('Label',),'UnlockMenu':('back',),
 'UnlockNotificationManager':tuple('ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE'.split()),
 'WeeklyRunModifierCatalog':('WeeklyRunModifierCatalog',),'WeeklyRunModifierRuntime_NestedType___c':('Empty',)
}
reviewed_reasons={
 'Alchemist_Upgrade':'Jackpot_Gate.RollAndGrant→GrantReward→ScoreBig에 전달되는 출처 인수',
 'GateGourmet_Upgrade':'Jackpot_Gate.RollAndGrant→GrantReward→ScoreBig에 전달되는 출처 인수',
 'Jackpot_Gate':'GrantReward의 점수 출처 인수이며 ScoreBigInternal에서 표시하지 않음',
 'RunEffectRecorder':'Jackpot/점수 효과 재생의 source 인수',
 'SimulationManager':'SoundManager.DriftCar의 미사용 caller 인수. 사운드 볼륨만 제어',
 'SteamAvatarTest':'Steam 이름이 미확정 문자열 [unknown]인지 비교하는 입력 판정',
 'UnlockNotificationManager':'COLOUR_/PATTERN_와 합쳐 번역 키를 만드는 숫자 단어 배열',
 'RunSummaryMenu':'존재하지 않는 원본 예비 키. Localize의 fallback 문구를 메타데이터에서 한국어로 교체',
 'LoadoutMenu':'임시 객체 이름 및 장비 구성 내보내기 LPL1| 형식 머리말',
 'GlobalVariables':'PlayerPrefs 키 또는 선택된 객체의 개발 로그',
 'Profile':'PlayerPrefs의 동일 PlayerID 키',
 'PitStop':'상점 플래시 세일 분기에서 항목 ID를 비교하는 키',
 'BraceletOpeningMenu':'CharmManager.HasCharm의 부적 조회 ID',
}
cache={}
for r in rows:
    s=r['source'];cls=Path(r['file']).stem;method=r['method'];calls='\n'.join(r['calls']);status='UNKNOWN';reason='';evidence=[]
    key=(r['file'],method)
    if key not in cache:
        sections=(EXTRACT/r['file']).read_text('utf-8').split('Method: ')
        cache[key]=next(x for x in sections[1:] if x.splitlines()[0]==method).split('ISIL:')[-1]
    body=cache[key]
    if s in runtime:
        status='VISIBLE_TRANSLATE';reason='런타임 리터럴 위치를 보존하여 메타데이터 번역 적용';r['translation']=runtime[s]
    elif s in keys:
        status='INTERNAL';reason='원본 SharedTableData에 존재하는 번역 조회 키';evidence=[x['id'] for x in assets if x['source']==s and x['field'].endswith('/m_Key')]
    elif s in ids:
        status='INTERNAL';reason='자산에 연결된 게임 항목 식별자';evidence=[x['id'] for x in assets if x['source']==s and x['field'].split('/')[-1].endswith('ID')]
    elif re.search(r'Call (Debug\.Log|ClientIntegrity\.(AddReason|ReportMemoryTampering)|LeaderboardPlausibility.LogRejection)',next((x for x in r['calls'] if not re.search(r'Call (String\.(Concat|Format)|(?:Boolean|Byte|Int32|Int64)\.ToString)',x)),'')):
        status='INTERNAL';reason='기록 출력 또는 무결성 진단 경로';evidence=r['calls']
    elif cls.startswith(internals):
        status='INTERNAL';reason='저장 파일·소유자·통계 이벤트·입력 장치 판별의 내부 스키마';evidence=[method]
    elif not re.search('[a-zA-Z]',re.sub(r'<[^>]*>|\{[^{}]*\}','',s)) or s in ('<b><color=#','<color=green>(','<color=green>(+','<color=green>(-'):
        status='VISIBLE_KEEP';reason='숫자 조합·서식 태그·빈 값·구분 기호';evidence=[method]
    elif norm(s) in table and ('Localiz' in body or cls.startswith(('TutorialDirector','ChallengeCatalog','CreditsManager'))):
        status='VISIBLE_KEEP';reason='같은 메서드의 현지화 호출 또는 튜토리얼 Page의 번역 키가 완성된 한국어 표를 선택함';r['resolved_translation']=table[norm(s)];evidence=[line.strip() for line in body.splitlines() if 'Call ' in line and ('Localiz' in line or 'TutorialDirector.L,' in line)]
    elif re.search(r'Call (GameObject\.\.ctor|Object\.set_name|Transform\.Find|Shader\.Find|Shader\.PropertyToID|InputActionMap\.FindAction|Material\.Set|Animator\.)',calls):
        status='INTERNAL';reason='게임 객체·입력·그리기 속성의 조회 이름';evidence=r['calls']
    elif s.startswith(('https://','Loopler.','Save.')):
        status='INTERNAL';reason='외부 링크 주소 또는 성능 측정 표식';evidence=[method]
    elif 'ScoringManager.Score' in calls:
        status='INTERNAL';reason='ScoringManager.ScoreBigInternal의 caller 인수. 해당 구현에서 표시 소비 없이 소거됨';evidence=['ScoringManager.ScoreBigInternal: 입력 r9(caller)를 저장·사용하지 않음',*r['calls']]
    if status=='UNKNOWN':
        if s in units:
            status='VISIBLE_KEEP';reason='배율·천/백만·초 단위와 숫자 및 시간 형식';evidence=[method]
        elif s in dates:
            status='INTERNAL';reason='일일·주간 저장과 순위표 회차의 날짜 식별 형식';evidence=[method]
        elif s in key_parts:
            status='INTERNAL';reason='항목 ID·열거값·인덱스로 완성되는 번역 키 조각';evidence=[x for x in keys if x.startswith(s.split('{')[0]) or x.endswith(s)][:40]
        elif s in animation_ids:
            status='INTERNAL';reason='Tween 또는 Invoke의 애니메이션 그룹·메서드 이름';evidence=[method,*r['calls']]
        elif cls.startswith('__f__AnonymousType'):
            status='INTERNAL';reason='컴파일러 자동 익명 형식의 진단용 ToString';evidence=[method]
        elif s in ('_DissolveAmount','_ColorA'):
            status='INTERNAL';reason='재질 속성 읽기의 고정 키';evidence=r['calls']
        elif any(token in method for owner,methods in ui_build_methods.items() if cls.startswith(owner) for token in methods):
            status='INTERNAL';reason='화면 구성 보조 함수가 객체를 생성·찾는 계층 이름';evidence=[method,*r['calls']]
        elif cls.startswith('TutorialTypewriter') or cls=='Hungry_Gate' and s=='\\n':
            status='INTERNAL';reason='줄바꿈 입력 정규화의 구분자';evidence=[method]
        elif cls.startswith('TutorialDirector') and ('On' in method or 'StartBossMapLesson' in method or 'TryShow' in method or 'RunFirstRoundHudTour' in cls):
            linked=[x for x in keys if '"'+x+'"' in body and x.startswith('TUTORIAL_')]
            if linked:status='VISIBLE_KEEP';reason='TutorialDirector.Page 제목/본문 fallback. L(key)로 한국어 표를 우선 조회';evidence=linked
        elif cls=='ChallengeChoice' and 'ApplyDefinition' in method and ' ' in s:
            status='VISIBLE_KEEP';reason='ChallengeLocalization.Get/GetFormatted의 번역 키와 함께 전달되는 fallback';evidence=[x for x in keys if '"'+x+'"' in body and x.startswith('CHALLENGE_')]
        elif cls=='ChallengeCatalog' and 'CreateRuntimeDefault' in method and ' ' in s:
            status='VISIBLE_KEEP';reason='ChallengeCatalog.Create가 CHALLENGE_<ID>_NAME/_DESCRIPTION/_MODIFIER 키를 생성하며 해당 한국어 행 존재';evidence=[x for x in keys if x.startswith('CHALLENGE_')]
        elif cls=='RewardPresentation' and 'GetEffectText' in method:
            status='VISIBLE_KEEP';reason='보상 종류별 효과 키와 fallback 쌍. Resolve의 GetStringByKeyOrFallback이 번역 표 선택';evidence=[x for x in keys if '"'+x+'"' in body]
        elif cls=='ProfileMenu' and 'RefreshStats' in method:
            status='VISIBLE_KEEP';reason='BindStat에 PROFILE_STAT_* 키와 함께 전달되며 ProfileMenu.Localize가 한국어 표 조회';evidence=[x for x in keys if '"'+x+'"' in body]
        elif cls=='RoundSelectMenu' and 'UpdateRewardControlHints' in method:
            status='VISIBLE_KEEP';reason='ApplyRewardHint의 MAP_PEEK_REWARDS/MAP_REWARD_DETAILS 번역 키 fallback';evidence=['MAP_PEEK_REWARDS','MAP_REWARD_DETAILS']
        elif cls=='Upgrade' and 'FormatTriggerType' in method:
            status='VISIBLE_KEEP';reason='유일 호출자 RunSummaryContentController.PopulateCardTooltip이 TYPE_<enum> 한국어 키를 우선 조회';evidence=[x for x in keys if x.startswith('TYPE_')]
        if status=='UNKNOWN':
            if s in ('F0','F2','E2','D2','b','\n<color=#'):
                status='VISIBLE_KEEP';reason='숫자 출력 형식·십억 축약·이어 붙이는 색 태그';evidence=r['calls']
            elif s in reviewed_internal.get(cls,()):
                status='INTERNAL';reason=reviewed_reasons.get(cls,'검토한 객체·자산 조회 이름 또는 상태 식별자');evidence=[method,*r['calls']]
            elif cls.startswith('LeaderboardManager'):
                status='INTERNAL';reason='Steam 순위표 이름·종류·접두/접미 키 또는 [Leaderboard] 기록 접두';evidence=[method,*r['calls']]
            elif cls.startswith('LocalizationManager'):
                status='INTERNAL';reason='언어·표·글꼴 스타일 조회 키 또는 언어 전환 진단 로그';evidence=[method,*r['calls']]
            elif cls=='SteamStatsAndAchievements':
                status='INTERNAL';reason='Steam 통계 키·업적 display 속성 name/desc 또는 초기화 상태';evidence=[method,*r['calls']]
            elif cls=='ChallengeMenu' and 'Initialize' in method and s.startswith('Challenge'):
                status='INTERNAL';reason='누락된 장면 컴포넌트에 대한 Debug.LogError. Initialize 오류 분기 확인';evidence=[x.strip() for x in body.splitlines() if 'Debug.Log' in x]
            elif cls=='RunSummaryContentController' and 'PopulateStats' in method and s.endswith('_Stat'):
                status='INTERNAL';reason='통계 값 SetStat가 찾는 장면 객체 이름';evidence=[method,*r['calls']]
    r.update(classification=status,reason=reason,evidence=evidence)
write_json(review/'code_decisions.json',rows)
unknown=[r for r in rows if r['classification']=='UNKNOWN']
write_json(review/'code_unknown.json',unknown)
print(dict(collections.Counter(r['classification'] for r in rows)))
groups=collections.defaultdict(list)
for r in unknown:groups[r['source']].append(Path(r['file']).stem+': '+r['method'])
for i,(s,where) in enumerate(groups.items()):print(i,repr(s),' | '.join(dict.fromkeys(where)))
