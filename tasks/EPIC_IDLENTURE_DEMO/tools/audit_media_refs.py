"""문구가 있는 화면 시안의 실제 참조·활성 상태를 조사합니다."""
from common import *
g=generator();envs={n:load(BASE/DATA/n,g) for n in ['level0','level1','resources.assets','sharedassets0.assets','sharedassets1.assets']}
def target(name,ptr):
    if ptr['m_FileID']==0:return name,ptr['m_PathID']
    return Path(envs[name].file.externals[ptr['m_FileID']-1].path).name,ptr['m_PathID']
def refs(tree,path=''):
    if isinstance(tree,dict):
        if set(tree)=={'m_FileID','m_PathID'}:yield path,tree
        else:
            for k,v in tree.items():yield from refs(v,path+'/'+k)
    elif isinstance(tree,list):
        for i,v in enumerate(tree):yield from refs(v,path+'/'+str(i))
trees={};edges=[]
for name,e in envs.items():
    for obj in e.objects:
        if obj.type.name not in ['GameObject','Transform','RectTransform','MonoBehaviour','Sprite','SpriteRenderer','Material']:continue
        dest=EXTRACT/'trees'/f'{name}_{obj.path_id}.json'
        if dest.exists():t=json.loads(dest.read_text(encoding='utf8'))
        else:
            try:t=obj.read_typetree()
            except Exception:continue
        trees[(name,obj.path_id)]=t
        if obj.type.name not in ['GameObject','Transform','RectTransform']:
            for field,ptr in refs(t):
                if ptr['m_PathID']:edges.append(dict(source=(name,obj.path_id),type=obj.type.name,field=field,target=target(name,ptr)))
def chain(name,pid):
    t=trees[(name,pid)];go=target(name,t['m_GameObject']);result=[]
    while go in trees:
        gt=trees[go];result.append(dict(file=go[0],path_id=go[1],name=gt.get('m_Name'),active=gt.get('m_IsActive')))
        trans=next((target(go[0],c['component']) for c in gt['m_Component'] if target(go[0],c['component']) in trees and 'm_Father' in trees[target(go[0],c['component'])]),None)
        if not trans:break
        parent=target(trans[0],trees[trans]['m_Father'])
        if parent not in trees:break
        go=target(parent[0],trees[parent]['m_GameObject'])
    return result
index=json.loads((WORK/'media/index.json').read_text(encoding='utf8'));report=[]
for i in [733,734,770,777,782]:
    loc=index[i]['locations'][0];front={(loc['file'],loc['path_id'])};seen=set(front);found=[]
    while front:
        following=set()
        for e in edges:
            if e['target'] not in front:continue
            r=dict(e);t=trees[e['source']]
            if 'm_GameObject' in t and t['m_GameObject']['m_PathID']:r['gameobject_chain']=chain(*e['source'])
            found.append(r)
            if e['source'] not in seen:following.add(e['source']);seen.add(e['source'])
        front=following
    report.append(dict(media_id=i,name=loc['name'],references=found))
save(WORK/'media/mockup_refs.json',report)
for r in report:print(r['media_id'],r['name'],[(e['source'],e['field'],e.get('gameobject_chain')) for e in r['references']])
