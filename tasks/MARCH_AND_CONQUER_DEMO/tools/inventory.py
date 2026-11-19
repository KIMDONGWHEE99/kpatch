"""모든 Unity 객체와 문자열·글꼴·미디어 출처를 위치별로 추출합니다."""
from baseline import *
sys.path.insert(0,str(ROOT/'tools/python_deps'))
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
from UnityPy.helpers.TypeTreeNode import TypeTreeNode
class GameGenerator(TypeTreeGenerator):
    def get_nodes_up(self, assembly, fullname):
        key=(assembly,fullname)
        if key in self.cache: return self.cache[key]
        nodes=list(self.get_nodes(assembly if assembly.endswith('.dll') else assembly+'.dll',fullname)); fixed=[]
        for i,n in enumerate(nodes):
            kind=n.m_Type;flag=n.m_MetaFlag
            if n.m_Level==1 and n.m_Name=='m_Enabled': flag |= 0x4000
            if kind=='string' and i+3<len(nodes) and nodes[i+1].m_Name=='Array' and nodes[i+3].m_Type=='string': kind='vector'
            fixed.append(TypeTreeNode(n.m_Level,kind,n.m_Name,0,0,m_MetaFlag=flag))
        result=TypeTreeNode.from_list(fixed);self.cache[key]=result;return result
generator=GameGenerator('6000.3.9f1');generator.load_local_game(str(BASE))
def walk(value, path=''):
    if isinstance(value,dict):
        for k,v in value.items(): yield from walk(v,path+'/'+k)
    elif isinstance(value,list):
        for i,v in enumerate(value): yield from walk(v,path+'/'+str(i))
    elif isinstance(value,str) and value: yield path,value
rows=[]; errors=[]; objects=[]; fonts=[]; versions={}; media=[]
for p in sorted((BASE/DATA).iterdir()):
    if not (p.suffix=='.assets' or p.name in ('level0','globalgamemanagers')): continue
    env=UnityPy.load(str(p));env.typetree_generator=generator; versions[p.name]=env.file.unity_version
    counts=collections.Counter()
    for obj in env.objects:
        kind=obj.type.name; counts[kind]+=1
        loc=dict(file=p.name,path_id=obj.path_id,type=kind,source_sha256=sha(obj.get_raw_data()))
        try:
            tree=obj.read_typetree()
            objects.append(dict(loc,name=tree.get('m_Name'),script=tree.get('m_Script')))
            for field,value in walk(tree): rows.append(dict(loc,field=field,source=value,classification='UNKNOWN'))
            if kind=='Font' or 'm_CharacterTable' in tree or kind=='PlayerSettings':
                save(EXTRACT/'special'/f'{p.name}_{obj.path_id}.json',tree)
                fonts.append(dict(loc,name=tree.get('m_Name')))
            if kind in ('Texture2D','Sprite','VideoClip'):
                media.append(dict(loc,name=tree.get('m_Name'),classification='MEDIA',disposition='UNKNOWN'))
            if kind=='Texture2D':
                image=obj.read().image
                out=EXTRACT/'textures'/f'{p.name}_{obj.path_id}.png';out.parent.mkdir(exist_ok=True,parents=True);image.save(out)
            if kind=='MonoBehaviour': save(EXTRACT/'trees'/f'{p.name}_{obj.path_id}.json',tree)
        except Exception as exc: errors.append(dict(loc,error=str(exc),classification='UNKNOWN'))
    print(p.name,dict(counts))
save(EXTRACT/'strings.json',rows);save(EXTRACT/'objects.json',objects);save(EXTRACT/'errors.json',errors);save(EXTRACT/'fonts.json',fonts);save(EXTRACT/'media.json',media);save(EXTRACT/'versions.json',versions)
print('문자열',len(rows),'추출 오류',len(errors),'글꼴/설정',len(fonts),'미디어',len(media))
