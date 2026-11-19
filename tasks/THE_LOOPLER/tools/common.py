"""The Loopler의 비공개 작업 경로와 자산 구조 읽기."""
from baseline import ROOT, SOURCE, EXTRACT, sha, write_json
import sys
sys.path.insert(0, str(ROOT / 'tools/python_deps'))
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
from UnityPy.helpers.TypeTreeNode import TypeTreeNode

DATA = SOURCE / 'The Loopler_Data'
WORK = ROOT / 'working_private/THE_LOOPLER'

class GameGenerator(TypeTreeGenerator):
    def get_nodes_up(self, assembly, fullname):
        key = (assembly, fullname)
        if key in self.cache:
            return self.cache[key]
        nodes = list(self.get_nodes(assembly if assembly.endswith('.dll') else assembly + '.dll', fullname))
        fixed = []
        for i, node in enumerate(nodes):
            kind, flag = node.m_Type, node.m_MetaFlag
            if node.m_Level == 1 and node.m_Name == 'm_Enabled':
                flag |= 0x4000
            if kind == 'string' and i + 3 < len(nodes) and nodes[i+1].m_Name == 'Array' and nodes[i+3].m_Type == 'string':
                kind = 'vector'
            fixed.append(TypeTreeNode(node.m_Level, kind, node.m_Name, 0, 0, m_MetaFlag=flag))
        result = TypeTreeNode.from_list(fixed)
        # 생성기가 상속 계층마다 붙인 참조 저장소는 객체 끝의 하나만 남깁니다.
        registry = [c for c in result.m_Children if c.m_Name == 'references' and c.m_Type == 'ManagedReferencesRegistry']
        if len(registry) > 1:
            excluded = {id(c) for c in registry[:-1]}
            result.m_Children = tuple(c for c in result.m_Children if id(c) not in excluded)
        self.cache[key] = result
        return result

def generator():
    result = GameGenerator('6000.3.16f1')
    result.load_local_dll_folder(str(EXTRACT / 'dummy'))
    return result

def files():
    return [DATA / 'data.unity3d', *sorted((DATA / 'StreamingAssets/aa/StandaloneWindows64').glob('*.bundle'))]

def configure_references(gen):
    """IL2CPP에서 생성한 관리 참조 구조와 빈 참조를 처리합니다."""
    from UnityPy.helpers import TypeTreeHelper
    def reference_node(value, asset):
        t=value['type'];cls,ns,asm=t['class'],t['ns'],t['asm']
        if not cls or not asm:return None
        node=gen.get_nodes_up(asm,f'{ns}.{cls}'.lstrip('.'))
        if node.m_Children and node.m_Children[0].m_Name=='m_GameObject':node.m_Children=tuple(node.m_Children[4:])
        return node
    TypeTreeHelper.get_ref_type_node=reference_node
    TypeTreeHelper.read_typetree_boost=None
    if not getattr(TypeTreeHelper.write_value,'handles_null_reference',False):
        original=TypeTreeHelper.write_value
        def write_value(value,node,writer,config):
            if node.m_Type=='ReferencedObject' and not value['type']['class']:
                for child in node.m_Children:
                    if child.m_Type!='ReferencedObjectData':original(value[child.m_Name],child,writer,config)
                return
            return original(value,node,writer,config)
        write_value.handles_null_reference=True
        TypeTreeHelper.write_value=write_value

def read_tree(obj):
    if obj.type.name=='PlayerSettings':
        node=obj._get_typetree_node()
        if node.m_Children[-1].m_Name!='preservedUnity6000_3Tail':node.m_Children=tuple(node.m_Children)+(TypeTreeNode(1,'int','preservedUnity6000_3Tail',4,1),)
        return obj.read_typetree(nodes=node)
    return obj.read_typetree()
