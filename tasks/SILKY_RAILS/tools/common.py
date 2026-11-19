"""게임별 자산 해석과 경로를 공유합니다."""
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
def generator():
    g=GameGenerator('6000.3.19f1');g.load_local_game(str(BASE));return g
def load(path,g):
    env=UnityPy.load(str(path));env.typetree_generator=g;return env
def preserve_save(source,env):
    """원본 메타데이터를 보존하고 변경 객체만 뒤에 추가합니다."""
    import struct
    raw=Path(source).read_bytes();output=bytearray(raw);header=env.file.header
    assert header.version>=22 and header.endian=='<'
    original=UnityPy.load(raw)
    assert set(original.file.objects)==set(env.file.objects)
    for obj in env.objects:
        old=original.file.objects[obj.path_id];payload=obj.data if obj.data is not None else obj.get_raw_data()
        if payload==old.get_raw_data():continue
        needle=struct.pack('<qqIi',old.path_id,old.byte_start-header.data_offset,old.byte_size,old.type_id)
        assert raw[:header.data_offset].count(needle)==1,(obj.path_id,'목록 위치 불명확')
        pos=raw.index(needle);output.extend(b'\0'*(-len(output)%8));offset=len(output)
        output.extend(payload);struct.pack_into('<qI',output,pos+8,offset-header.data_offset,len(payload))
    struct.pack_into('>q',output,24,len(output))
    checked=UnityPy.load(bytes(output))
    for obj in env.objects:assert (obj.data if obj.data is not None else obj.get_raw_data())==checked.file.objects[obj.path_id].get_raw_data()
    return bytes(output)

