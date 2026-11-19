"""별도 구조 생성으로 추출 오류를 해소하고 바이트 재저장을 대조합니다."""
from common import *
from inventory import strings
import json
from UnityPy.helpers import TypeTreeHelper

gen=generator()
base_ref=TypeTreeHelper.get_ref_type_node
def reference_node(value, asset):
    t=value['type']
    cls,ns,asm=t['class'],t['ns'],t['asm']
    if not cls or not asm:return None
    node = gen.get_nodes_up(asm, f'{ns}.{cls}'.lstrip('.'))
    if node.m_Children and node.m_Children[0].m_Name == 'm_GameObject':
        node.m_Children = tuple(node.m_Children[4:])
    return node

TypeTreeHelper.get_ref_type_node=reference_node
TypeTreeHelper.read_typetree_boost=None
base_write=TypeTreeHelper.write_value
def write_value(value,node,writer,config):
    if node.m_Type=='ReferencedObject' and not value['type']['class']:
        for child in node.m_Children:
            if child.m_Type!='ReferencedObjectData':
                base_write(value[child.m_Name],child,writer,config)
        return
    return base_write(value,node,writer,config)
TypeTreeHelper.write_value=write_value
env=UnityPy.load(str(DATA/'data.unity3d'));env.typetree_generator=gen
records=json.loads((EXTRACT/'objects.json').read_text('utf-8'))
texts=json.loads((EXTRACT/'strings.json').read_text('utf-8'))
errors=json.loads((EXTRACT/'extraction_errors.json').read_text('utf-8'))
for row in errors:
    obj=next(o for o in env.objects if o.assets_file.name==row['asset'] and o.path_id==row['path_id'])
    raw=obj.get_raw_data()
    try:
        if obj.type.name=='PlayerSettings':
            node=obj._get_typetree_node()
            node.m_Children=tuple(node.m_Children)+(TypeTreeNode(1,'int','preservedUnity6000_3Tail',4,1),)
            tree=obj.read_typetree(nodes=node)
            rewritten=obj.save_typetree(tree,nodes=node)
            row['preserved_tail']='기존 구조표 뒤의 32비트 설정값 3을 추가 필드로 읽어 그대로 보존. 문자열 영역 아님.'
        else:
            tree=obj.read_typetree()
            rewritten=obj.save_typetree(tree)
        assert rewritten==raw,(len(raw),len(rewritten))
        obj.set_raw_data(raw)
        row['status']='PASS';row['resolution']='코드에서 생성한 상속 구조와 참조 구조로 해석; 내용·참조·재저장 바이트 일치'
        dest=EXTRACT/'trees/data.unity3d'/obj.assets_file.name/f'{obj.path_id}.json';write_json(dest,tree)
        record=next(r for r in records if r['id']==row['id']);record['tree']=str(dest.relative_to(EXTRACT));record['name']=tree.get('m_Name','')
        if obj.type.name=='MonoBehaviour':
            s=obj.parse_monobehaviour_head().m_Script.deref_parse_as_object();record['script']=f'{s.m_AssemblyName}:{s.m_Namespace}.{s.m_ClassName}'
        for field,value in strings(tree):texts.append({'id':row['id']+field,'object_id':row['id'],'field':field,'source':value,'classification':'UNKNOWN','file_sha256':row['file_sha256']})
        print(row['path_id'],'PASS',flush=True)
    except Exception as e:
        row['resolution_error']=str(e);print(row['path_id'],'FAIL',str(e),flush=True)
write_json(EXTRACT/'objects.json',records)
write_json(EXTRACT/'strings.json',texts)
write_json(EXTRACT/'extraction_errors_resolved.json',errors)
