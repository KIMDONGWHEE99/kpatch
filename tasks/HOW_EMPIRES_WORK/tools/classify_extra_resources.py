"""추가 이진 자원의 표시 소비자와 내부 자료 구조를 구분합니다."""
from common import *
import re,collections,base64
rows=read_json(WORK/'census/extra_strings.json')
area_ids={}
for path in (RECOVERED/'Data/GeographyDefines/AreaDefines').rglob('*.tres'):
    match=re.search(r'^area_id = "([^"]+)"',path.read_text(encoding='utf8'),re.M)
    if match:area_ids[match[1]]={'file':path.relative_to(RECOVERED).as_posix(),'sha256':sha(path)}
assert not any(r['source'] in ['Label','RichTextLabel','Label3D','LineEdit','TextEdit','text','tooltip_text','placeholder_text'] for r in rows if r['file'].endswith('.scn'))
fields={'2d','aabb','attribute_data','format','index_count','index_data','primitive','uv_scale','vertex_count','vertex_data','conn_count','conns','editable_instances','id_paths','node_count','node_ids','node_paths','nodes','variants','version','times','transitions','update','values','names'}
for r in rows:
    if r['classification']!='UNKNOWN':continue
    s,c,p=r['source'],r['context'],r['prefix']
    reason=None
    if 'PackedByteArray(' in p:
        base64.b64decode(s,validate=True)
        reason='지형 메시의 정점·색상·인덱스 이진 바이트 배열; Base64 해독 확인'
    elif c.startswith('"names": PackedStringArray('):
        reason='PackedScene의 노드 이름·클래스·속성 이름 표; 전체 표에서 텍스트 표시 노드와 text/tooltip 속성 없음 확인'
    elif c.startswith(('batch_names = PackedStringArray(', 'group_variant = PackedStringArray(')):
        reason='지도 장식 일괄 렌더링의 배치 노드 이름·그룹 변형 ID; 화면 문구 소비 없음'
    elif s in fields and c.startswith('"'+s+'":'):
        reason='Animation·ArrayMesh·PackedScene의 직렬화 필드 이름'
    elif re.search(r'tracks/\d+/type =',c) and s=='value':
        reason='애니메이션 트랙 형식'
    elif c.startswith('"variants":') and re.fullmatch(r'[0-9a-f]{64}',s):
        reason='지도 장식 소스의 변경 추적 SHA-256'
    elif p.endswith('&') and s in ['Wheat_main_menu','RESET','Cloud_01_animation']:
        reason='AnimationLibrary의 애니메이션 식별자'
    elif c.startswith('resource_name =') and s=='Cloud_01_animation':
        reason='구름 장식 Animation 자원의 내부 이름'
    elif c.startswith('"variants":') and r['file'].endswith('/india_map_workfile.scn') and s in area_ids:
        reason='지도 배치의 area_id; 정의 자료의 같은 ID와 일치. 화면 이름은 별도 area_name 번역'
        r['linked_definition']=area_ids[s]
    elif c.startswith('"variants":') and s=='Cloud_01_animation':
        reason='VFX/Scenes/cloud_animation.tscn의 AnimationLibrary 이름·autoplay 값과 일치'
        r['linked_definition']={'file':'VFX/Scenes/cloud_animation.tscn','sha256':sha(RECOVERED/'VFX/Scenes/cloud_animation.tscn')}
    if reason:r.update(classification='INTERNAL',evidence=reason)
pending=[r for r in rows if r['classification']=='UNKNOWN']
write_json(WORK/'census/extra_classified.json',rows)
write_json(WORK/'census/extra_pending.json',pending)
print('remaining',len(pending),'unique',len({r['source'] for r in pending}))
unique={r['source']:r for r in pending}
for r in list(unique.values())[:65]:print(r['file'],repr(r['source'])[:130],r['context'][:90])
