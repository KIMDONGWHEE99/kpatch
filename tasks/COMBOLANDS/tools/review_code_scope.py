"""라이브러리별 장면 참조와 표시 호출을 모아 검토 대상을 좁힙니다."""
from common import *
from collections import Counter,defaultdict
import re
folder=EXTRACT/'code_scope'
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
components=json.loads((EXTRACT/'component_instances.json').read_text(encoding='utf8'))
counts=Counter(x['assembly'].removesuffix('.dll') for x in components)
incoming=defaultdict(list)
data={}
for row in manifest['assemblies']:
    name=Path(row['file']).stem
    data[name]=json.loads((folder/(name+'.json')).read_text(encoding='utf8'))
    for t in data[name]['types']:
        for m in t['methods']:
            for c in m['calls']:
                scope=c['scope'].removesuffix('.dll')
                if scope!=name:incoming[scope].append(dict(assembly=name,method=m['method'],target=c['target']))
display=re.compile(r'(UnityEngine\.(GUI|GUILayout)::(Label|Box|Button|TextField|TextArea|Window)|::set_(text|Text)\(|DebugUI.*::(set_displayName|\.ctor)|GUIContent::\.ctor)')
reviews=[]
for row in manifest['assemblies']:
    name=Path(row['file']).stem
    sinks=[]
    for t in data[name]['types']:
        for m in t['methods']:
            ui=[c for c in m['calls'] if display.search(c['target'])]
            if ui:sinks.append(dict(type=t['type'],method=m['method'],calls=ui,literals=m['literals']))
    r=dict(**row,components=counts[name],external_callers=incoming[name],display_methods=sinks,classification='UNKNOWN')
    reviews.append(r)
    if not name.startswith(('System','UnityEngine','Unity.')) and name not in ['mscorlib','netstandard','Mono.Security']:
        print(name,'components',r['components'],'callers',len(r['external_callers']),'init',len(r['initializers']),'display',len(sinks),'literals',r['literals'])
save_json(folder/'scope_review.json',reviews)
save_json(folder/'display_candidates.json',[dict(assembly=r['file'],**s) for r in reviews for s in r['display_methods']])
