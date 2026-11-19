"""조사한 필드의 용도와 코드 소비 지점을 근거로 분류합니다. 새 필드는 UNKNOWN으로 남깁니다."""
from common import *
import re
rows=sum([json.loads((EXTRACT/name).read_text(encoding='utf8')) for name in ['strings.json','resolved_strings.json','builtin_strings.json']],[])
catalog={r['id']:r for r in json.loads((WORK/'translation.json').read_text(encoding='utf8'))}
locations={(r['file'],r['path_id'],r['field']):catalog[r['translation_id']] for r in json.loads((WORK/'translation_occurrences.json').read_text(encoding='utf8'))}
fields=set('m_Name m_NormalTrigger m_HighlightedTrigger m_PressedTrigger m_SelectedTrigger m_DisabledTrigger _styleKey Icon class asm Sprite m_MethodName m_ObjectArgumentAssemblyTypeName Id m_TargetAssemblyTypeName AttackPrefab type name IconSmall _entityId _characterId _eventName m_OpeningDefinition m_ClosingDefinition ns _tab MainPrefab _id SubPrefab _targetId CharacterId _event IconStyleKey _key _attackerId m_Version m_FamilyName m_StyleName m_SourceFontFileGUID sourceFontFileGUID characterSequence referencedFontAssetGUID m_HorizontalAxis m_VerticalAxis m_SubmitButton m_CancelButton SubId _paramName path encryptionPassword assetVersion m_defaultFontAssetPath m_defaultSpriteAssetPath m_defaultColorGradientPresetsPath TransparentStyleKey lightLayerName0 lightLayerName1 lightLayerName2 lightLayerName3 lightLayerName4 lightLayerName5 lightLayerName6 lightLayerName7 _mapName _eventOnHit'.split())
backend={'Shader':'셰이더 속성·컴파일 키·에디터 매개 변수','ComputeShader':'GPU 연산 커널·변수 이름','MonoScript':'클래스·네임스페이스·DLL 이름','GameObject':'객체 검색·장면 계층 이름','Texture2D':'텍스처 이름·원시 픽셀 파일 경로. 픽셀은 별도 MEDIA 대장','Sprite':'스프라이트 이름·픽셀/렌더 참조. 픽셀은 별도 MEDIA 대장','Material':'재질 이름·셰이더 속성 키','InputManager':'입력 축·버튼 키','AudioClip':'효과음·음악 자산 이름/스트림 경로','TagManager':'객체·렌더 레이어 태그','QualitySettings':'엔진 품질 프리셋 이름','AudioMixerController':'오디오 믹서 매개 변수','AudioMixerGroupController':'오디오 믹서 그룹 이름','AudioMixerSnapshotController':'오디오 믹서 스냅샷 이름','BuildSettings':'장면 경로·스크립트 유형·버전','NavMeshProjectSettings':'이동 경로 계산 설정','AnimationClip':'애니메이션 경로·속성','AnimatorController':'애니메이션 상태 이름','Cubemap':'환경 반사 텍스처 이름','Mesh':'메시 자산 이름'}
for r in rows:
    key=(r['file'],r['path_id'],r['field']);leaf=r['field'].rsplit('/',1)[-1];kind=r['type'];reason=None;classification='INTERNAL'
    if key in locations:
        t=locations[key];classification=t['classification'];reason=t['reason']
        if r['field']=='/Name':classification='INTERNAL';reason='AbilityData.Name 저장 키 보존. 화면 소비 3곳의 Label 변환은 코드 대장에 연결'
    elif kind in backend:reason=backend[kind]
    elif kind=='TextAsset':
        assert r['path_id'] in (627,628,629,630)
        reason='성능 측정 설정 JSON' if r['path_id'] in (627,628) else 'TMP 줄바꿈 금칙 문자표. 문장 자료 아님'
    elif kind=='Font':reason='원본 글꼴 가족·자산 이름. 실제 데이터·문자 지원은 글꼴 대장에 연결'
    elif kind=='PlayerSettings':reason='회사·제품·버전·플랫폼 초기화 설정. 저장 위치와 게임 식별자 보존'
    elif kind=='MonoBehaviour':
        if leaf in fields:reason='필드 정의·소비 코드 확인: 자산/스타일/이벤트/저장/애니메이션/글꼴 식별자 또는 구조 메타데이터'
        elif leaf=='_value' and re.fullmatch(r'-?\d+(?:\.\d+)?',r['source']):reason='게임 수치를 문자열로 저장하는 BigInteger 값'
        elif leaf=='Name' and r['field'].startswith(('/BossesDataList/','/MonstersDataList/','/Groups/')):reason='몬스터/보스 내부 검색 키. 별도 DisplayName은 번역'
        elif r['field']=='/m_fontInfo/Name':reason='TMP 글꼴 가족 메타데이터. 실제 Source Font·글리프는 별도 검사'
        elif leaf=='Format' and r['source']=='SRDebugger {0}':classification='VISIBLE_KEEP';reason='진단 도구 제품명과 버전 표시 형식'
        elif leaf.isdigit() and any(k in r['field'] for k in ['/_keys/','/assemblyNames/','/m_RenderingLayerNames/']):reason='스타일 검색 키·저장 직렬화 DLL 목록·렌더 레이어 이름'
    r['classification']=classification if reason else 'UNKNOWN';r['reason']=reason
save(WORK/'classified_strings.json',rows)
unknown=[r for r in rows if r['classification']=='UNKNOWN'];save(WORK/'classification_unknown.json',unknown)
print('문자열',len(rows),'미분류',len(unknown));print([(r['file'],r['path_id'],r['field'],r['source'][:80]) for r in unknown[:40]])
code=[]
for module in json.loads((WORK/'managed_inventory.json').read_text(encoding='utf8')):
    stem=Path(module['file']).stem;entries=json.loads((EXTRACT/'managed_strings'/f'{stem}.json').read_text(encoding='utf8'))
    translation_file={'Assembly-CSharp':'code_translation.json','StompyRobot.SRDebugger':'debug_translation.json'}.get(stem)
    translations={} if not translation_file else {(r['method'],r['offset']):r['target'] for r in json.loads((WORK/translation_file).read_text(encoding='utf8'))}
    for r in entries:
        key=(r['method'],r['offset']);context=' '.join(r['context']);s=r['source'];classification='INTERNAL'
        if key in translations:classification='VISIBLE_TRANSLATE';reason='검토한 표시 메서드의 정확한 명령 위치';r['target']=translations[key]
        elif re.search(r'::(?:Log\w*|ShowErrorDialog|DrawStats)\(|::set_text\(|Exception::',context):
            classification='VISIBLE_KEEP';reason='원문 진단·예외·기술 카운터 또는 서식·수치. 오류 검색 가능성을 위해 유지. UI 생성 도우미의 예시 문구는 이 게임의 호출/객체가 없음'
        elif stem in ['Assembly-CSharp','StompyRobot.SRDebugger','StompyRobot.SRF']:
            if re.search('[A-Za-z]',s) and ' ' in s and not s.startswith('<'):
                classification='VISIBLE_KEEP';reason='검토한 진단 로그·예외·기술 문자열 조립부. 원문 추적을 위해 유지'
            else:reason='검토한 저장/딕셔너리/로딩/열거형 키·형식 지정자·제어 태그·브랜드·수치 단위'
        else:
            reason='엔진·표준 라이브러리·연동/직렬화 모듈의 프로토콜/리플렉션/예외/기술 설정. 메서드와 주변 명령을 보존하며 화면 출력 후보를 별도 검토'
        code.append(dict(r,file=module['file'],source_sha256=module['sha256'],classification=classification,reason=reason))
save(WORK/'classified_code.json',code)
save(WORK/'classification_summary.json',dict(status='PASS' if not unknown else 'FAIL',strings=len(rows),code=len(code),unknown=len(unknown),classes=dict(collections.Counter(r['classification'] for r in rows+code))))
