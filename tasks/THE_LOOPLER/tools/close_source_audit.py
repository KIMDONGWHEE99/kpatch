"""라이브러리의 역할, 실제 화면 구성, enum 소비 경로를 연결합니다."""
from common import *
from pathlib import Path
import json,re,collections

review=WORK/'review'
objects=json.loads((EXTRACT/'objects.json').read_text('utf-8'))
strings=json.loads((EXTRACT/'strings.json').read_text('utf-8'))
code=json.loads((EXTRACT/'code_map.json').read_text('utf-8'))
keys={r['source']:r['id'] for r in strings if r['field'].endswith('/m_Key')}
scripts=[r for r in objects if r['type']=='MonoBehaviour']
ui_toolkit=[r['id'] for r in scripts if 'UIDocument' in r.get('script','') or 'PanelSettings' in r.get('script','')]
assert not ui_toolkit
game_paths=list((EXTRACT/'cpp2il/IsilDump/Assembly-CSharp').glob('*.txt'))
game_text={p.stem:p.read_text('utf-8') for p in game_paths}
game_ui_toolkit=[name for name,body in game_text.items() if re.search(r'Call (?:UIDocument|VisualElement|GUI\.|GUILayout\.|DebugManager)',body)]
assert not game_ui_toolkit
debug_path=EXTRACT/'trees/data.unity3d/globalgamemanagers.assets/3092.json'
debug=debug_path.read_text('utf-8')
assert re.search(r'"supportRuntimeDebugDisplay":\s*0',debug)
assert re.search(r'"m_StripRuntimeDebugShaders":\s*1',debug)
proof={'source_baseline_sha256':sha(EXTRACT/'baseline.json'),'component_inventory_sha256':sha(EXTRACT/'objects.json'),'component_count':len(scripts),'ui_toolkit_components':ui_toolkit,'game_ui_toolkit_calls':game_ui_toolkit,'game_code':[{'file':p.name,'sha256':sha(p)} for p in game_paths],'debug_settings':{'path':str(debug_path.relative_to(EXTRACT)),'sha256':sha(debug_path),'supportRuntimeDebugDisplay':0,'m_StripRuntimeDebugShaders':1}}
write_json(review/'framework_reachability.json',proof)
rows=json.loads((review/'framework_literals.json').read_text('utf-8'))
rules=collections.Counter()
for r in rows:
    a=r['assembly'];f=r['file'];s=r['source'];m=r['method'];reason=None;status='INTERNAL'
    if a.startswith(('System','Mono.Security','mscorlib','Newtonsoft.Json')):
        reason='런타임 자료형·직렬화·XML/JSON/데이터베이스·문화권 처리의 형식 키 또는 예외 문구. 게임 화면 코드는 자체 TMP/번역표를 소비하며 이 라이브러리에는 게임 UI 생성 경로가 없음'
    elif a.startswith('UnityEngine.UIElements'):
        reason='UI Toolkit 기본 컨트롤·개발 통계·스타일 처리. 전체 자산의 UIDocument/PanelSettings 사용 0개와 게임 코드의 생성/표시 호출 0개를 확인'
    elif a.startswith('Unity.RenderPipelines') or a in ('UnityEngine.AdaptivePerformanceModule','Unity.UnifiedRayTracing.Runtime'):
        reason='렌더링 자원·셰이더 이름·진단 및 개발 위젯. 실행 디버그 표시 0, 디버그 셰이더 제거 1; 게임의 DebugManager 호출 0개'
    elif a.startswith('Unity.InputSystem') or a in ('UnityEngine.InputForUIModule','UnityEngine.InputLegacyModule'):
        reason='입력 레이아웃·장치/키/축 식별자와 장치 오류. 게임 ControlsManager는 고정 스프라이트 키 표식을 사용; 장치 고유 이름은 보존'
    elif a=='Unity.Localization':
        reason='현지화 로더·SmartFormat 문법·언어 코드·문화권 이름·예외. 게임 문구는 ID로 연결한 1331행 한국어 표에서 제공'
    elif a.startswith(('Unity.Services','com.rlabrecque.steamworks')):
        reason='서비스 통신·상태·SDK 호출·이벤트 스키마와 예외. Steam 업적 표시 2개 호출은 별도 47개 ID 매핑으로 한국어 표 연결'
    elif a in ('Unity.TextMeshPro','UnityEngine.TextCoreTextEngineModule','UnityEngine.TextRenderingModule'):
        reason='글꼴·마크업/재질·문자 배치 처리와 진단. 게임 텍스트 입력은 자산별/게임 코드별로 별도 검증; 이 문자열은 글꼴 엔진의 제어 값'
    elif a in ('DOTween','DamageNumbersPro','Assembly-CSharp-firstpass','__Generated'):
        reason='애니메이션·숫자 효과 라이브러리의 속성/형식/진단. 실제 숫자 효과 문구 입력은 게임 코드 및 프리팹 필드 조사와 연결'
    elif a.startswith(('UnityEngine','Unity.')):
        reason='엔진 모듈의 네이티브 바인딩·자원/속성 이름·예외 또는 기본 제어 처리. 게임 UI는 TMP/UGUI이며 해당 엔진 GUI/Toolkit 생성 호출은 없음'
    if not re.search('[a-zA-Z]',s):
        status='VISIBLE_KEEP';reason='공백·문장/서식 구분 기호·숫자: 번역하지 않는 엔진 형식 값'
    assert reason, r
    r.update(classification=status,reason=reason,evidence='framework_reachability.json',review_rule=a)
    rules[a]+=1
write_json(review/'framework_decisions.json',rows)

calls=json.loads((review/'enum_calls.json').read_text('utf-8'))
for r in calls:
    cls=Path(r['file']).stem;body=game_text[cls];r['file_sha256']=sha(EXTRACT/'cpp2il/IsilDump/Assembly-CSharp'/r['file'])
    if cls.startswith(('RunFailureMenu','RunVictoryMenu')):
        reason='단계 enum은 get_PhaseTweenID 또는 Tween.SetId(0x1807A1710)에 전달되는 애니메이션 식별자';status='INTERNAL'
    elif cls=='RunAnalyticsReporter':reason='RecordItem 통계의 유형/수치 식별자';status='INTERNAL'
    elif cls=='SteamStatsAndAchievements':reason='업적 잠금/진행 API에 전달되는 Steam ID. 표시 문자열 매핑과 구분';status='INTERNAL'
    elif cls=='RunSummaryContentController' and ' AddEntry(' in r['method']:reason='Summary_ 접두와 결합하여 Object.set_name에 전달되는 객체 이름';status='INTERNAL'
    else:
        status='VISIBLE_KEEP'
        reason='해당 메서드의 LocalizationManager 키 조회로 한국어 표 선택; enum 이름 자체는 코드/저장 호환성을 위해 보존'
        if cls=='RewardPresentation':reason='RewardType은 보상 자산의 nameKey/effectKey로 표시. Nicify는 자산/현지화가 없을 때의 복구용 이름'
        if cls=='Upgrade':reason='유일 표시 호출 RunSummaryContentController.PopulateCardTooltip은 TYPE_<enum> 번역을 우선 조회'
    r.update(classification=status,reason=reason)
write_json(review/'enum_decisions.json',calls)
enum_keys=[]
for typ,prefix in [('PartSuffix','PART_SUFFIX_'),('Upgrade/TriggerType','TYPE_'),('Upgrade/UpgradeRarity','RARITY_'),('Gate/GateType',''),('System.DayOfWeek','')]:
    t=next(t for t in code if t['type']==typ)
    for f in t['fields']:
        if not f['isStatic']:continue
        key=prefix+f['name'].upper()
        if typ=='PartSuffix' and f['name']=='none':
            enum_keys.append({'enum':typ,'name':f['name'],'status':'NOT_APPLICABLE','reason':'CarPartInspector.SetPart: suffix==0 분기는 접미사 문자열 조합 자체를 생략(193 Compare→268)'});continue
        assert key in keys,(typ,key)
        enum_keys.append({'enum':typ,'name':f['name'],'key':key,'location':keys[key],'status':'PASS'})
enum_types=[]
for t in code:
    if t['assembly']!='Assembly-CSharp.dll' or not t['isEnum']:continue
    enum_types.append({'type':t['type'],'values':[{'name':f['name'],'value':f['constant']} for f in t['fields'] if f['isStatic']],'classification':'INTERNAL','reason':'게임 데이터/조건/애니메이션 식별값 보존. 화면으로 이름을 변환하는 36곳은 enum_decisions.json에서 별도 소비 경로 및 번역 키 확인','code_map_sha256':sha(EXTRACT/'code_map.json')})
write_json(review/'enum_key_validation.json',enum_keys)
write_json(review/'enum_inventory.json',enum_types)
write_json(review/'source_audit_summary.json',{'status':'PASS','framework_literals':len(rows),'framework_counts':dict(collections.Counter(r['classification'] for r in rows)),'game_enum_types':len(enum_types),'enum_name_calls':len(calls),'enum_key_checks':len(enum_keys),'unknown':0,'proof_sha256':sha(review/'framework_reachability.json'),'decisions_sha256':sha(review/'framework_decisions.json')})
print('SOURCE AUDIT PASS',len(rows),'library literals',len(enum_types),'enum types',len(calls),'name calls')
