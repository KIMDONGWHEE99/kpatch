"""필드의 실제 역할을 명시한 규칙으로 분류하며 나머지는 미확인으로 둡니다."""
from common import *
import json,re,collections

texts=json.loads((EXTRACT/'strings.json').read_text('utf-8'))
objects={r['id']:r for r in json.loads((EXTRACT/'objects.json').read_text('utf-8'))}
canonical=json.loads((WORK/'translation_canonical.json').read_text('utf-8'))
exact={r['source']:r['translation'] for r in canonical}
def normalize(s):return re.sub(r'\s+',' ',s).strip().casefold()
norm=collections.defaultdict(set)
for s,t in exact.items():norm[normalize(s)].add(t)
visible_fields=set('gateName gateEffect upgradeName upgradeEffect upperText lowerText endlessName endlessDescription charmName charmDesc descriptionFallback modifierTooltipFallback titleFallback bannerTitle infinityTitle duraFireString bannerString fallbackEffect fallbackName rewardText itemName unlockEffect unlockName trackName difficultyName difficultyDescription'.split())
internal_fields=set('gateID upgradeID infID charmID partID challengeID descriptionKey modifierTooltipKey titleKey specialID modifierID rewardKey itemID unlockID effectKey nameKey reqIds unlockedMetaIDs fromGuid toGuid guid languageCode currentLocale fontKey styleKey assetTableName spamGroup'.split())
rows=[];pending=collections.defaultdict(list);unknown=collections.defaultdict(list)
for r in texts:
    o=objects[r['object_id']];script=o.get('script',o['type']);f=r['field'];parts=f.split('/')[1:];leaf=parts[-1];s=r['source']
    status='UNKNOWN';why='';tr=None
    if 'localization-string-tables-' in o['file']:
        if f.endswith('/m_Localized'):
            if '-korean(' in o['file']:
                status='VISIBLE_TRANSLATE';why='한국어 StringTable 행: 영어와 같은 항목 ID로 번역 연결'
            else:status='INTERNAL';why='한국어 선택 시 비활성인 다른 언어 번역표; 영어는 fallback 입력으로 보존'
        else:status='INTERNAL';why='번역표 객체 이름·언어코드·직렬화 참조의 형식 정의'
    elif f=='/m_Name':status='INTERNAL';why='Unity 객체 식별 이름; 실제 표시용 필드와 분리'
    elif any(p in ('m_TableReference','m_TableEntryReference') for p in parts):status='INTERNAL';why='Unity Localization 표·항목을 찾는 키 참조'
    elif any(p in ('m_AnimationTriggers','m_OnClick','m_UpdateString','exitEvent','hoverEvent','onSelectHover','onDeselectHover','onValueChanged','rightClickEvent','skipEvent','m_Delegates','m_ActionEvents') for p in parts):
        if leaf in ('m_TargetAssemblyTypeName','m_MethodName','m_ObjectArgumentAssemblyTypeName'):status='INTERNAL';why='UnityEvent의 대상 코드 형식·메서드 이름'
        elif leaf=='m_StringArgument' and s in ('SFX','Music','Master'):status='INTERNAL';why='오디오 볼륨 콜백의 믹서 채널 식별자'
    elif script.startswith('Unity.InputSystem:'):status='INTERNAL';why='InputSystem 입력 맵·장치 바인딩과 동작 GUID'
    elif leaf in internal_fields or any(p in ('connections','nodes','reqIds','unlockedMetaIDs','trackProgress') for p in parts) and script.startswith('Assembly-CSharp:'):
        status='INTERNAL';why='게임 상태·저장·기능 조회의 고정 식별자 및 맵 연결 ID'
    elif script.endswith('TextMeshProUGUI') and f=='/m_text' or script.endswith('UI.Text') and f=='/m_Text':
        status='VISIBLE_TRANSLATE';why='장면 또는 프리팹의 실제 텍스트 필드'
    elif script.startswith('Assembly-CSharp:') and (leaf in visible_fields or parts[0]=='quotes'):
        status='VISIBLE_TRANSLATE';why='게임 UI의 이름·설명·예비 문구·결과 인용문'
    elif script=='Assembly-CSharp:.CreditsData' and 'names' in parts:
        status='VISIBLE_KEEP';why='제작 참여자의 이름·계정명·소프트웨어 고유명사'
    if status=='UNKNOWN':
        if '/m_PersistentCalls/' in f and leaf in ('m_TargetAssemblyTypeName','m_MethodName','m_ObjectArgumentAssemblyTypeName'):
            status='INTERNAL';why='직렬화된 UnityEvent 코드 연결'
        elif 'm_AnimationTriggers' in parts:
            status='INTERNAL';why='UI 애니메이션 상태 전환 키'
        elif script.startswith('Unity.InputSystem:'):
            status='INTERNAL';why='InputSystem 동작·장치 바인딩 식별자'
        elif leaf=='m_StringArgument' and s in ('de','en','es','fr','it','ja','ko','meow','pl','pt','pt-BR','ru','sv','tr','zh','zh-Hant'):
            status='INTERNAL';why='언어 선택 버튼의 ISO 언어 코드 인수'
        elif script=='Assembly-CSharp:.MenuLeaderboard' and f=='/leaderboardName':
            status='INTERNAL';why='Steam 순위표 검색 이름 BoardLeaderboard'
        elif script.startswith('DamageNumbersPro:'):
            status='VISIBLE_KEEP';why='수치의 부호·소수점·K/M/B/T와 배율·초 단위 축약 기호'
        elif parts[0] in ('m_CreationSettings','m_FaceInfo','m_SourceFontFileGUID','m_Version','m_fontInfo'):
            status='INTERNAL';why='글꼴 원본 식별자·제작 문자표·서체 정보'
        elif f=='/m_LocaleName':
            status='VISIBLE_KEEP';why='언어 라이브러리 고유 언어명. 실제 선택 버튼은 각 언어 자칭으로 별도 표시'
        elif leaf in ('m_Code','m_CustomFormatCultureCode','m_TableCollectionName','m_TableCollectionNameGuidString','m_Key','m_TypeString','m_CommentText') or 'm_TableCodes' in parts:
            status='INTERNAL';why='로케일 코드·표 키·형식 이름·제작 메모'
        elif '/type/' in f and leaf in ('asm','class','ns'):
            status='INTERNAL';why='관리 참조 직렬화의 어셈블리·클래스·네임스페이스'
        elif script=='MonoBehaviour' and re.fullmatch(r'/m_TableData/\d+/m_Localized',f) and re.fullmatch('[0-9a-f]{32}',s):
            status='INTERNAL';why='AssetTable의 글꼴 자산 GUID. 표시 문자열이 아님'
        elif script=='PlayerSettings':
            status='INTERNAL';why='제품·저장 경로·빌드 버전·엔진 품질 프로파일의 식별 설정'
        elif script=='TextAsset' and o['asset']=='resources.assets' and o['path_id'] in (30,31):
            status='INTERNAL';why='Unity 성능시험 설정·엔진 패키지 버전 JSON. 화면 콘텐츠 없음'
        elif script=='TextAsset' and o['asset']=='resources.assets' and o['path_id'] in (32,33):
            status='INTERNAL';why='TMP 줄 처음·끝 금지 구두점 표. 한글 줄바꿈에도 필요한 제어 자료'
        elif script.endswith('LocalizationSettings'):
            if leaf=='m_NoTranslationFoundMessage':
                status='VISIBLE_TRANSLATE';why='번역 실패 시 표시되는 예비 오류 문구';tr="'{key}'의 번역을 {table.TableCollectionName}에서 찾을 수 없습니다"
            elif leaf=='m_NullDisplayString':status='VISIBLE_KEEP';why='값 부재를 나타내는 기술 기호 (null)'
            else:status='INTERNAL';why='SmartFormat 이름·연산자와 언어 선택기의 제어 설정'
        elif script.startswith('Unity.RenderPipelines.'):
            status='INTERNAL';why='렌더링 디버그 UI 형식 참조 또는 빛 혼합·렌더링 계층 설정 이름'
        elif script.endswith('TMP_Settings'):
            status='INTERNAL';why='TMP 기본 자산 검색 경로·설정 버전'
        elif script.endswith('TMP_SpriteAsset'):
            status='INTERNAL';why='아이콘 태그가 찾는 그림 문자 이름과 버전'
        elif script.endswith('TMP_StyleSheet'):
            status='INTERNAL';why='TMP 스타일 이름과 태그·장식 구문'
    if status=='VISIBLE_TRANSLATE' and '-korean(' not in o['file']:
        if s in exact:tr=exact[s]
        elif len(norm[normalize(s)])==1:tr=next(iter(norm[normalize(s)]))
        if not re.search('[a-zA-Z가-힣]',re.sub('<[^>]*>','',s)):
            status='VISIBLE_KEEP';why='기호·숫자·아이콘만 표시하는 문구'
        elif tr is None:pending[s].append(r['id'])
        if tr==s:status='VISIBLE_KEEP';why='유지하기로 검토한 기호·언어 자칭·고유명사'
    if status=='UNKNOWN':unknown[(script,re.sub(r'/\d+(?=/|$)','/*',f))].append(s)
    rows.append({**r,'classification':status,'reason':why,'translation':tr,'script':script})
write_json(WORK/'review/classified_texts.json',rows)
write_json(WORK/'review/direct_pending.json',[{'index':i,'source':s,'translation':None,'locations':loc} for i,(s,loc) in enumerate(pending.items())])
lines=[]
for (script,field),values in sorted(unknown.items()):
    values=list(dict.fromkeys(values));lines.append(f'{script} {field} ({len(values)})\n'+'\n'.join(json.dumps(v,ensure_ascii=False) for v in values))
(WORK/'review/unknown_fields.txt').write_text('\n\n'.join(lines),encoding='utf-8')
print('classifications',dict(collections.Counter(r['classification'] for r in rows)),'pending',len(pending),'unknown groups',len(unknown))

code=[]
for path in sorted((EXTRACT/'cpp2il/IsilDump/Assembly-CSharp').glob('*.txt')):
    t=path.read_text('utf-8');method=''
    for line in t.splitlines():
        if line.startswith('Method:'):method=line[8:]
        if re.match(r'\s*\d+ (?:Move|LoadAddress) [^,]+, "',line):
            value=line[line.index('"')+1:line.rindex('"')]
            code.append({'file':str(path.relative_to(EXTRACT)),'file_sha256':sha(path),'method':method,'line':line.strip(),'source':value,'classification':'UNKNOWN'})
write_json(WORK/'review/code_strings.json',code)
groups=collections.defaultdict(list)
for r in code:groups[r['source']].append(r['file'].split('/')[-1]+': '+r['method'])
(WORK/'review/code_unique.txt').write_text('\n'.join(f'{i} '+json.dumps(s,ensure_ascii=False)+' | '+', '.join(dict.fromkeys(m)) for i,(s,m) in enumerate(groups.items())),encoding='utf-8')
print('code locations',len(code),'unique',len(groups))
