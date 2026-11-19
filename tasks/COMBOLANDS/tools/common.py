"""Combolands 전용 경로·해시·Unity 구조 보정 도구."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/python_deps'))
import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
from UnityPy.helpers.TypeTreeNode import TypeTreeNode

SOURCE = ROOT / 'source_original/COMBOLANDS/steam_20260906/game'
DATA = SOURCE / 'Combolands_Data'
EXTRACT = ROOT / 'extracted_private/COMBOLANDS/steam_24989173'
WORK = ROOT / 'working_private/COMBOLANDS/run_20260906'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

class GameGenerator(TypeTreeGenerator):
    def get_nodes_up(self, assembly, fullname):
        key = (assembly, fullname)
        if key in self.cache:
            return self.cache[key]
        nodes = list(self.get_nodes(assembly if assembly.endswith('.dll') else assembly + '.dll', fullname))
        fixed = []
        for i, n in enumerate(nodes):
            kind = n.m_Type
            flag = n.m_MetaFlag
            # 기본 컴포넌트의 활성 플래그 뒤에는 4바이트 정렬이 필요합니다.
            if n.m_Level == 1 and n.m_Name == 'm_Enabled':
                flag |= 0x4000
            # 생성기가 string[]을 string으로 잘못 표기하는 문제를 보정합니다.
            if kind == 'string' and i + 3 < len(nodes) and nodes[i+1].m_Name == 'Array' and nodes[i+3].m_Type == 'string':
                kind = 'vector'
            fixed.append(TypeTreeNode(n.m_Level, kind, n.m_Name, 0, 0, m_MetaFlag=flag))
        result = TypeTreeNode.from_list(fixed)
        self.cache[key] = result
        return result

def generator():
    result = GameGenerator('6000.0.66f2')
    result.load_local_game(str(SOURCE))
    return result

def containers(root=DATA):
    return sorted(p for p in Path(root).iterdir() if p.is_file() and
                  (p.suffix == '.assets' or p.name.startswith('level') or p.name == 'globalgamemanagers'))

def script(obj):
    head = obj.parse_monobehaviour_head()
    s = head.m_Script.deref_parse_as_object()
    return str(s.m_ClassName), str(s.m_Namespace), str(s.m_AssemblyName)
