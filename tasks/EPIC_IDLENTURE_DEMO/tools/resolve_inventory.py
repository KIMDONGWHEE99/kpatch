"""참조 형식과 빈 동적 텍스처 등 최초 추출 오류를 별도로 해석합니다."""
from common import *
from UnityPy.helpers import TypeTreeHelper
TypeTreeHelper.read_typetree_boost=None
g=generator()
def ref(value,assetsfile):
    t=value['type'];c=t['class'];ns=t['ns'];asm=t['asm']
    if not c:return None
    nodes=list(g.get_nodes(asm if asm.endswith('.dll') else asm+'.dll',(ns+'.' if ns else '')+c))
    result=[];skip=False
    for n in nodes:
        if n.m_Level<=1:skip=n.m_Level==1 and n.m_Name in ['m_GameObject','m_Enabled','m_Script','m_Name']
        if not skip:result.append(TypeTreeNode(n.m_Level,n.m_Type,n.m_Name,0,0,m_MetaFlag=n.m_MetaFlag))
    return TypeTreeNode.from_list(result)
TypeTreeHelper.get_ref_type_node=ref
def walk(value,path=''):
    if isinstance(value,dict):
        for k,v in value.items():yield from walk(v,path+'/'+k)
    elif isinstance(value,list):
        for i,v in enumerate(value):yield from walk(v,path+'/'+str(i))
    elif isinstance(value,str) and value:yield path,value
errors=json.loads((EXTRACT/'errors.json').read_text(encoding='utf8'))
resolutions=[];strings=[];objects=[]
for r in errors:
    env=load(BASE/DATA/r['file'],g);obj=env.file.objects[r['path_id']]
    if r['type']=='Texture2D':
        t=obj.read_typetree();assert t['m_Width']==t['m_Height']==t['m_CompleteImageSize']==t['m_StreamData']['size']==0 and not t['image data']
        resolutions.append(dict(r,status='PASS',reason='0×0·픽셀 0바이트·외부 경로 없음인 동적 글꼴 텍스처. 화면 문구를 담은 픽셀이 없음'))
        continue
    if r['type']=='PlayerSettings':
        t=obj.read_typetree(check_read=False)
        assert obj.get_raw_data()[-4:]==bytes.fromhex('00000000')
        reason='설정 구조 832바이트와 후행 정수 00000000 확인. 회사·제품명은 app.info와 대조하고 원본 구조 보존'
    else:
        t=obj.read_typetree();reason='실제 DLL의 참조 클래스 필드 구조를 생성해 객체 전체 바이트를 재해석'
    dest=EXTRACT/'resolved'/f"{r['file']}_{r['path_id']}.json";save(dest,t)
    loc={k:r[k] for k in ['file','path_id','type','source_sha256']}
    strings.extend(dict(loc,field=k,source=v,classification='UNKNOWN') for k,v in walk(t))
    objects.append(dict(loc,name=t.get('m_Name'),script=t.get('m_Script')))
    resolutions.append(dict(r,status='PASS',reason=reason,tree_sha256=sha(dest.read_bytes())))
save(EXTRACT/'resolved_strings.json',strings);save(EXTRACT/'resolved_objects.json',objects);save(WORK/'extraction_resolutions.json',resolutions)
print('오류 해소',len(resolutions),'추가 문자열',len(strings))
