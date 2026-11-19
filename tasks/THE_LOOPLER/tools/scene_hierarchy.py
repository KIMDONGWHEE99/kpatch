"""장면의 객체와 부모 활성 상태를 조사합니다."""
from common import *
import json,collections
env=UnityPy.load(str(DATA/'data.unity3d'));level={o.path_id:o for o in env.objects if o.assets_file.name=='level0'}
gos={k:o.read_typetree() for k,o in level.items() if o.type.name=='GameObject'}
trs={k:o.read_typetree() for k,o in level.items() if o.type.name in ('Transform','RectTransform')}
trans_by_go={v['m_GameObject']['m_PathID']:k for k,v in trs.items()}
def ancestry(go):
    result=[]
    while go:
        g=gos[go];tr=trs[trans_by_go[go]];result.append({'id':go,'name':g['m_Name'],'active':g['m_IsActive'],'transform':trans_by_go[go],'position':tr.get('m_AnchoredPosition',tr['m_LocalPosition'])})
        parent=tr['m_Father']['m_PathID'];go=trs[parent]['m_GameObject']['m_PathID'] if parent else 0
    return result
selected=[]
for k,g in gos.items():
    if any(s in g['m_Name'].lower() for s in ('korean','survey','wishlist','patch','feedback','release','playtest','language')) or k==6813:
        selected.append({'id':k,'components':g['m_Component'],'ancestry':ancestry(k)})
write_json(WORK/'review/scene_hierarchy.json',selected)
for x in selected:print(x['id'],' / '.join(str(p['id'])+':'+p['name']+' active='+str(p['active']) for p in x['ancestry']))
button=json.loads((EXTRACT/'trees/data.unity3d/level0/41316.json').read_text('utf-8'))
go=button['m_GameObject']['m_PathID'];print('KOREAN BUTTON',go,gos[go],ancestry(go))
