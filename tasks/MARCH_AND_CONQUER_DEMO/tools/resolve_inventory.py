"""실패했던 자산의 대체 해석과 위치별 조사 근거를 보관합니다."""
from common import *
from UnityPy.helpers import TypeTreeHelper
import re
g=generator();TypeTreeHelper.read_typetree_boost=None
def ref(v,a):
    t=v['type'];c=t['class'];ns=t['ns'];asm=t['asm']
    if not c:return None
    nodes=list(g.get_nodes(asm if asm.endswith('.dll') else asm+'.dll',(ns+'.' if ns else '')+c));result=[];skip=False
    for n in nodes:
        if n.m_Level<=1:skip=n.m_Level==1 and n.m_Name in ['m_GameObject','m_Enabled','m_Script','m_Name']
        if not skip:result.append(TypeTreeNode(n.m_Level,n.m_Type,n.m_Name,0,0,m_MetaFlag=n.m_MetaFlag))
    return TypeTreeNode.from_list(result)
TypeTreeHelper.get_ref_type_node=ref
resolutions=[]
env=load(BASE/DATA/'globalgamemanagers.assets',g);o=env.file.objects[2324];tree=o.read_typetree()
save(EXTRACT/'trees/globalgamemanagers.assets_2324.json',tree)
resolutions.append(dict(file='globalgamemanagers.assets',path_id=2324,status='PASS',sha256=sha(o.get_raw_data()),reason='13종 참조 형식의 실제 C# 필드 구조로 복원. 비 Unity 객체에 잘못 추가된 MonoBehaviour 헤더를 제외하여 전체 2644바이트 해석',tree_sha256=sha((EXTRACT/'trees/globalgamemanagers.assets_2324.json').read_bytes())))
env=load(BASE/DATA/'globalgamemanagers',g);o=env.file.objects[1];tree=o.read_typetree(check_read=False)
save(EXTRACT/'special/globalgamemanagers_1_partial.json',tree)
assert o.get_raw_data()[-4:]==b'\x03\x00\x00\x00'
resolutions.append(dict(file='globalgamemanagers',path_id=1,status='PASS',sha256=sha(o.get_raw_data()),reason='PlayerSettings의 944바이트 필드 해석과 후행 4바이트 값 03000000 직접 조사. 후행 값에는 길이 지정 문자열이 들어갈 수 없으며 원본 전체 바이트를 보존. 회사/제품명은 app.info와 대조',unparsed_tail_hex='03000000'))
for name,ids in [('resources.assets',[146]),('sharedassets0.assets',[18,19,34,43,48])]:
    env=load(BASE/DATA/name,g)
    for pid in ids:
        o=env.file.objects[pid];d=o.read_typetree();assert d['m_Width']==d['m_Height']==d['m_CompleteImageSize']==d['m_StreamData']['size']==0 and not d['image data']
        resolutions.append(dict(file=name,path_id=pid,status='PASS',sha256=sha(o.get_raw_data()),reason='글꼴의 실행 중 생성용 빈 텍스처. 0×0, 픽셀 크기 0, 외부 스트림 없음. 이미지 추출 대상 없음'))
assert len(resolutions)==len(json.loads((EXTRACT/'errors.json').read_text(encoding='utf-8')))
save(WORK/'extraction_resolutions.json',resolutions)
media=json.loads((EXTRACT/'media.json').read_text(encoding='utf-8'))
index=json.loads((WORK/'media/index.json').read_text(encoding='utf-8'))
review=[]
for r in index:
    kind='NO_TEXT';reason='7개 검수판에서 제작자가 확인: 배경·캐릭터·효과·UI 아이콘. 읽을 문장 없음'
    if r['id'] in [1,162]:kind='KEEP';reason='글꼴 아틀라스의 기본 문자표. 문장이 아니며 한글은 검증된 동적 글꼴로 추가'
    if r['id'] in [20,157,160]:kind='KEEP';reason='Unity / March and Conquer / 이전 1000 Battles 게임 브랜드 로고 유지'
    if r['id']==62:kind='KEEP';reason='UV 시험 격자의 숫자 좌표 0.0~1.0 유지'
    if r['id']==116:kind='KEEP';reason='표정 아이콘의 물음표 기호 유지'
    review.append(dict(r,disposition=kind,reason=reason,sheet=f'sheet_{r["id"]//24:02d}.png'))
save(WORK/'media/review.json',review)
print('해석 오류 해소',len(resolutions),'텍스처 육안 판정',len(review))
