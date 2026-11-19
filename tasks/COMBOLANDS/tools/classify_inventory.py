"""검토한 구조·참조 근거를 위치별로 연결하고 새 항목은 미분류로 남깁니다."""
from common import *
from collections import Counter
import re

def field_rule(r):
    cls=r['class'];path=r['field_path'];field='.'.join(str(x) for x in path);s=r['source']
    if path==['m_Name']:return 'INTERNAL','Unity 객체 식별 이름; 화면 값은 별도 표시 필드·LocalizedString.GetText에서 반환'
    if 'm_AnimationTriggers' in path:return 'INTERNAL','Selectable의 Animator 상태 전환 식별자'
    if path[-1] in ['m_MethodName','m_TargetAssemblyTypeName','m_ObjectArgumentAssemblyTypeName']:return 'INTERNAL','UnityEvent의 메서드·어셈블리 연결 식별자'
    if cls=='LocalizedStringAsset' and path[0] in ['Key','_explanationText']:return 'INTERNAL','GetText는 _originalString만 반환; Key는 검색 키, explanation은 제작 설명'
    if cls in ['TextMeshProUGUI','TextMeshPro','Text','TextAnimator_TMP'] and path in [['m_text'],['m_Text'],['_text']] and not re.search('[A-Za-z가-힣]',s):return 'VISIBLE_KEEP','숫자·계산 기호·가려진 이름 표시·공백; 언어 문구 없음'
    if cls=='EFConfig' and (path[0]=='Token' or (path[0]=='Board' and path[1] in ['Id','CategoryIds','ListIds','ListNames','Labels'])):return 'INTERNAL','FeedbackForm/Trello는 서비스 ID·색상·내부 목록으로 전송; 표시 분류·중요도 이름은 별도 번역 위치'
    if path==['SectionTitle'] and cls in ['GraphicsInfoCollector','PlayerInfoCollector','SystemInfoCollector','VersionCollector','TextField']:return 'INTERNAL','FormSubmitted에서 보고서 섹션의 키로 사용; 양식의 표시 제목은 Text/TMP 필드에서 번역'
    if path[-1]=='tagID' or (cls=='TextAnimator_TMP' and path[0] in ['defaultAppearancesTags','defaultBehaviorsTags','defaultDisappearancesTags']) or (cls=='TextAnimatorSettings' and path[0]=='controlTags'):return 'INTERNAL','TextAnimator의 동작 태그·제어 코드; 번역된 본문의 태그와 연결'
    if cls=='InputActionAsset':return 'INTERNAL','입력 바인딩의 동작·장치·경로·GUID; 게임 SettingsMenu는 재매핑 명칭 UI를 제공하지 않음'
    if cls=='StandaloneInputModule':return 'INTERNAL','입력 처리기의 Unity InputManager 축·버튼 키'
    if cls in ['TMP_FontAsset','TMP_Settings','TMP_SpriteAsset','TMP_StyleSheet']:return 'INTERNAL','글꼴 생성·자원 검색·아이콘·태그 스타일 메타데이터; 모든 표시 문자열은 별도 위치 대조'
    if cls=='DebugUIHandlerCanvas' and path[0]=='prefabs':return 'INTERNAL','렌더링 진단 UI의 컴포넌트 형식 연결; 이름은 CLR 형식 문자열'
    if cls=='Renderer2DData' and path[0]=='m_LightBlendStyles':return 'INTERNAL','렌더러 빛 혼합 설정 이름; 씬·UI 표시 문구 아님'
    return 'UNKNOWN','추가 검토 필요'

def main():
    inv=json.loads((EXTRACT/'inventory_fixed.json').read_text(encoding='utf8'))
    canon=json.loads((WORK/'canonical_translation.json').read_text(encoding='utf8'))
    translated={(r['file'],r['path_id'],tuple(r['field'])):r for r in canon}
    classified=[]
    for f in inv['files']:
        for r in f['strings']:
            key=(f['relative_path'],r['path_id'],tuple(r['field_path']))
            if key in translated:status,reason=translated[key]['classification'],translated[key]['reason']
            else:status,reason=field_rule(r)
            classified.append(dict(file=f['relative_path'],file_sha256=f['sha256'],path_id=r['path_id'],field=r['field_path'],source_sha256=hashlib.sha256(r['source'].encode()).hexdigest(),classification=status,reason=reason))
    # 기본 엔진 객체의 문자열은 확인한 네이티브 속성별로만 판정합니다.
    native_rules={
        'InputManager':'입력 축·키 바인딩 이름', 'TagManager':'레이어·정렬 그룹 식별자', 'BuildSettings':'장면 경로·엔진 버전·빌드 식별 정보',
        'QualitySettings':'렌더링 품질 프로필 이름; 게임 설정은 자체 해상도·동기화 UI 사용', 'NavMeshProjectSettings':'길찾기 영역 식별자',
        'Material':'셰이더 재질·키워드·패스', 'ComputeShader':'GPU 계산 커널·버퍼·매개변수 식별자', 'MonoScript':'스크립트 클래스·이름공간·어셈블리 연결',
        'GameObject':'장면 계층에서 객체를 찾는 이름; UI는 TMP/LocalizedString에서 표시', 'VideoPlayer':'영상을 넣는 재질 속성명',
        'AnimationClip':'애니메이션 자산 식별 이름','AnimatorController':'애니메이션 제어 자산 이름', 'RenderTexture':'렌더링 결과 텍스처 식별 이름',
        'Cubemap':'환경 맵 이름·데이터 경로', 'AudioMixerController':'오디오 믹서 식별 이름','AudioMixerGroupController':'오디오 채널 그룹 식별 이름','AudioMixerSnapshotController':'오디오 상태 식별 이름'
    }
    native=json.loads((EXTRACT/'extra_native_strings.json').read_text(encoding='utf8'))
    for r in native:
        classified.append(dict(file=r['file'],file_sha256=r['file_sha256'],path_id=r['path_id'],field=r['field'],source_sha256=hashlib.sha256(r['source'].encode()).hexdigest(),classification='INTERNAL' if r['type'] in native_rules else 'UNKNOWN',reason=native_rules.get(r['type'],'추가 검토 필요')))
    save_json(EXTRACT/'classification.json',classified)
    print(Counter(r['classification'] for r in classified))
    for r in classified:
        if r['classification']=='UNKNOWN':print(r)
    # 그림은 실제로 본 검토판과 동일한 원본 지문에만 판정을 연결합니다.
    media=json.loads((EXTRACT/'media_manifest.json').read_text(encoding='utf8'))
    text_indices={0,8,167,168,179,189,196,197,198,204,206,207,216,235,240,242}
    for r in media:
        assert sha(EXTRACT/'media'/r['path'])==r['image_sha256']
        r['evidence']=f"media/sheet_{r['index']//24:02}.jpg"
        r['classification']='MEDIA';r['treatment']='NO_TEXT';r['reason']='검토판에서 도형·지도·건물·아이콘·배경·효과 확인, 언어 문구 없음'
        if r['index'] in [0,204,216,240]:r.update(treatment='KEEP',reason='제작사·게임 제목·Steam의 고유 로고')
        if r['index'] in [8,167,168,196,197,198,206,207]:r.update(treatment='KEEP',reason='개별 글리프 아틀라스; 글꼴·동적 한글 생성은 별도 전수 검증')
        if r['index'] in [179,235,242]:r.update(treatment='TRANSLATE',reason='LoadingSequence/ShopBorder/ShopBroken Image 위의 기능 문구를 KoreanSupport의 한국어 UI로 교체; 원본 그림 보존')
        if r['index']==189:r.update(treatment='TRANSLATE',reason='CrownDemo→체험판, resources.assets의 교차 파일 Sprite AutoCompleteIcon→자동 완료, EndlessIcon→무한 모드. 실행 중 생성되는 기능 해금 팝업의 Image 지정도 번역 연결. 과거 미사용 판정은 다른 파일의 Sprite 참조 누락으로 폐기.')
    save_json(EXTRACT/'media_review.json',media)
    video=json.loads((EXTRACT/'video/manifest.json').read_text(encoding='utf8'))
    save_json(EXTRACT/'video_review.json',dict(video_sha256=video['video_sha256'],classification='MEDIA',treatment='KEEP',reason='전체 180프레임에서 별 배경·Crux Games 제작사 로고만 확인',frames=len(video['frames']),evidence=[f'video/sheet_{i}.jpg' for i in range(5)]))

if __name__=='__main__':main()
