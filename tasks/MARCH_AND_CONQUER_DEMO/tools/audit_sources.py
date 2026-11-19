"""문자열·미디어의 전체 출처를 위치 및 원본 해시에 연결합니다."""
from common import *
import re
rows=json.loads((EXTRACT/'strings.json').read_text(encoding='utf-8'))
canonical={(r['file'],r['path_id'],r['field']):r for r in json.loads((WORK/'translation.json').read_text(encoding='utf-8'))}
ledger=[]
for r in rows:
    loc=(r['file'],r['path_id'],r['field'])
    if loc in canonical:ledger.append(canonical[loc]);continue
    kind='UNKNOWN';reason='미분류';field=r['field'].split('/')[-1]
    if r['file']=='sharedassets0.assets' and r['path_id']==1713:
        kind='VISIBLE_KEEP' if field in ['value','languageDisplayName'] else 'INTERNAL';reason='요청 대상은 영어 슬롯의 한국어 대체. 기존 독일어 슬롯의 값과 식별자는 유지'
    elif r['type']=='AudioClip' and field=='m_Name':kind='VISIBLE_KEEP';reason='음원 이름. MusicPlayer의 선택 목록은 원본 곡·효과음 식별 이름 유지'
    elif r['type']=='AudioClip' and r['field']=='/m_Resource/m_Source':kind='INTERNAL';reason='음성 데이터가 저장된 .resource 스트림 파일 경로'
    elif r['type']=='TextAsset':
        assert r['path_id'] in [211,212,213,214];kind='INTERNAL';reason='성능 측정 설정·실행 정보 JSON 또는 TMP 선행/후행 문장부호 문자표. 전체 4개 TextAsset 내용 확인'
    elif r['type']=='MonoBehaviour':
        allowed={'m_Name','key','m_Id','nodeId','m_NormalTrigger','m_HighlightedTrigger','m_PressedTrigger','m_SelectedTrigger','m_DisabledTrigger','m_Path','m_Action','id','m_Groups','m_MethodName','m_ObjectArgumentAssemblyTypeName','m_TargetAssemblyTypeName','unitId','idleStateName','moveStateName','attackStateName','hitStateName','deathStateName','burnedStateName','frozenStateName','victoryStateName','healStateName','textKey','m_ExpectedControlType','type','name','unitNodeId','automationNodeId','m_ControlPath','m_BindingGroup','m_OpeningDefinition','m_ClosingDefinition','m_ActionId','m_Version','m_FamilyName','m_StyleName','m_SourceFontFileGUID','sourceFontFileGUID','sortingLayerName','languageCode','characterSequence','referencedFontAssetGUID','Name','m_Interactions','starterBuildingNodeId','starterUnitNodeId','assetVersion','m_defaultFontAssetPath','m_defaultSpriteAssetPath','m_defaultColorGradientPresetsPath','saveFileName'}
        if field in allowed or re.fullmatch(r'/landNames/\d+',r['field']):kind='INTERNAL';reason='직렬화 필드 구조와 Assembly-CSharp 소비 코드 확인: 식별 키·입력 경로·애니메이션·메서드·글꼴 설정. 표시 필드는 별도 번역 위치에 연결'
    elif r['type'] in {'GameObject','MonoScript','Shader','Material','ComputeShader','Texture2D','Sprite','Font','Mesh','AnimatorController','AnimationClip','ParticleSystem','ParticleSystemRenderer','Transform','RectTransform','SpriteRenderer','MeshRenderer','PreloadData','PlayerSettings','InputManager','TagManager','AudioManager','ScriptMapper','MonoManager','GraphicsSettings','TimeManager','DelayedCallManager','PhysicsManager','BuildSettings','QualitySettings','ResourceManager','NavMeshProjectSettings','Physics2DSettings','RuntimeInitializeOnLoadManager','StreamingManager','VFXManager','Unknown (655991488)','RenderSettings','LightmapSettings','NavMeshSettings','Camera','AudioSource','AudioListener','MeshFilter','MeshCollider','BoxCollider2D','Animator','LineRenderer','Canvas','CanvasRenderer','CanvasGroup'}:
        kind='INTERNAL';reason='엔진 객체명·스크립트 클래스/어셈블리·셰이더/애니메이션/설정 데이터. 게임 표시 소비 코드는 displayName/description/언어표/TMP 필드를 사용하고 이름 참조는 자원 탐색·진단용임을 확인. 픽셀 문구는 미디어 대장 별도 검수'
    ledger.append(dict(r,classification=kind,reason=reason))
unknown=[r for r in ledger if r['classification']=='UNKNOWN'];save(WORK/'source_ledger.json',ledger);save(WORK/'source_unknown.json',unknown)
g=generator();review=json.loads((WORK/'media/review.json').read_text(encoding='utf-8'));reviewmap={r['file'][:-4]:r for r in review};media=[];envs={}
for r in json.loads((EXTRACT/'media.json').read_text(encoding='utf-8')):
    if r['type']=='Texture2D':
        key=f'{r["file"]}_{r["path_id"]}'
        if key in reviewmap:d=reviewmap[key];media.append(dict(r,disposition=d['disposition'],reason=d['reason'],review_image_sha256=d['sha256']))
        else:
            assert (r['file'],r['path_id']) in [('resources.assets',146)]+[('sharedassets0.assets',i) for i in [18,19,34,43,48]]
            media.append(dict(r,disposition='NO_TEXT',reason='실행 중 생성용 0×0 Font Texture. extraction_resolutions.json에 원본 해시·픽셀 크기 확인'))
    elif r['type']=='Sprite':
        if r['file'] not in envs:envs[r['file']]=load(BASE/DATA/r['file'],g)
        env=envs[r['file']];tree=env.file.objects[r['path_id']].read_typetree();ref=tree['m_RD']['texture']
        target=r['file'] if ref['m_FileID']==0 else Path(env.file.externals[ref['m_FileID']-1].path).name
        d=reviewmap[f'{target}_{ref["m_PathID"]}'];media.append(dict(r,disposition=d['disposition'],reason='스프라이트의 texture 참조가 육안 검토된 아틀라스와 일치: '+d['reason'],texture_file=target,texture_path_id=ref['m_PathID'],review_image_sha256=d['sha256']))
    else:raise AssertionError(r)
save(WORK/'media_ledger.json',media)
print('문자열',len(ledger),'미분류',len(unknown),'미디어',len(media));print([(r['type'],r['field'],r['source'][:120]) for r in unknown][:30])
assert not unknown
