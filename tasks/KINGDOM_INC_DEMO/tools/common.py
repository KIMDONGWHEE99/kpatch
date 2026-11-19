"""Kingdom Inc. Demo의 경로·해시·자료 읽기 공통 도구."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
GAME_ID = "KINGDOM_INC_DEMO"
BUILD = "steam_25631786"
INSTALL = Path(r"D:\steam\steamapps\common\Kingdom Inc. Demo")
SOURCE = ROOT / "source_original" / GAME_ID / BUILD / "game"
EXTRACT = ROOT / "extracted_private" / GAME_ID / BUILD
WORK = ROOT / "working_private" / GAME_ID
DATA_NAME = "KingdomInc_Data"
DATA = SOURCE / DATA_NAME
sys.path.insert(0, str(ROOT / "tools/python_deps"))

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def asset_files(root=SOURCE):
    data = root / DATA_NAME
    return sorted(p for p in data.iterdir() if p.is_file() and
                  (p.suffix == ".assets" or p.name == "globalgamemanagers" or
                   (p.name.startswith("level") and p.suffix == "")))

def load_asset(path):
    import UnityPy
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
    from UnityPy.helpers.TypeTreeNode import TypeTreeNode
    class GameGenerator(TypeTreeGenerator):
        def get_nodes_up(self, assembly, fullname):
            key = (assembly, fullname)
            if key in self.cache:
                return self.cache[key]
            nodes = list(self.get_nodes(assembly if assembly.endswith(".dll") else assembly + ".dll", fullname))
            fixed = []
            for i, node in enumerate(nodes):
                kind, flag = node.m_Type, node.m_MetaFlag
                if node.m_Level == 1 and node.m_Name == "m_Enabled":
                    flag |= 0x4000
                if kind == "string" and i + 3 < len(nodes) and nodes[i + 1].m_Name == "Array" and nodes[i + 3].m_Type == "string":
                    kind = "vector"
                fixed.append(TypeTreeNode(node.m_Level, kind, node.m_Name, 0, 0, m_MetaFlag=flag))
            result = TypeTreeNode.from_list(fixed)
            registries = [c for c in result.m_Children if c.m_Name == "references" and c.m_Type == "ManagedReferencesRegistry"]
            if len(registries) > 1:
                excluded = {id(c) for c in registries[:-1]}
                result.m_Children = tuple(c for c in result.m_Children if id(c) not in excluded)
            self.cache[key] = result
            return result
    env = UnityPy.load(str(path))
    gen = GameGenerator("6000.3.2f1")
    gen.load_local_dll_folder(str(DATA / "Managed"))
    env.typetree_generator = gen
    return env

def preserve_save(source, env):
    """객체 위치·원본 메타데이터를 보존하며 수정한 객체만 뒤에 기록합니다."""
    import struct
    import UnityPy
    raw = Path(source).read_bytes()
    output = bytearray(raw)
    header = env.file.header
    assert header.version >= 22 and header.endian == "<"
    original = UnityPy.load(raw)
    assert set(original.file.objects) == set(env.file.objects)
    for obj in env.objects:
        old = original.file.objects[obj.path_id]
        payload = obj.data if obj.data is not None else obj.get_raw_data()
        if payload == old.get_raw_data():
            continue
        needle = struct.pack("<qqIi", old.path_id, old.byte_start - header.data_offset, old.byte_size, old.type_id)
        assert raw[:header.data_offset].count(needle) == 1, obj.path_id
        pos = raw.index(needle)
        output.extend(b"\0" * (-len(output) % 8))
        offset = len(output)
        output.extend(payload)
        struct.pack_into("<qI", output, pos + 8, offset - header.data_offset, len(payload))
    struct.pack_into(">q", output, 24, len(output))
    checked = UnityPy.load(bytes(output))
    for obj in env.objects:
        expected = obj.data if obj.data is not None else obj.get_raw_data()
        assert expected == checked.file.objects[obj.path_id].get_raw_data()
    return bytes(output)

def read_tree(obj):
    """Unity 6.3 설정 꼬리값과 관리 참조를 실제 어셈블리에 맞춰 읽습니다."""
    if obj.type.name == "PlayerSettings":
        from UnityPy.helpers.TypeTreeNode import TypeTreeNode
        from UnityPy.helpers import TypeTreeHelper
        node = obj._get_typetree_node()
        if node.m_Children[-1].m_Name != "preservedUnity6000_3Tail":
            node.m_Children = tuple(node.m_Children) + (TypeTreeNode(1, "int", "preservedUnity6000_3Tail", 4, 1),)
        boost = TypeTreeHelper.read_typetree_boost
        try:
            TypeTreeHelper.read_typetree_boost = None
            return obj.read_typetree(nodes=node)
        finally:
            TypeTreeHelper.read_typetree_boost = boost
    if obj.assets_file.name == "globalgamemanagers.assets" and obj.path_id == 2641:
        from UnityPy.helpers import TypeTreeHelper
        gen = obj.assets_file.environment.typetree_generator
        def reference_node(value, asset):
            info = value["type"]
            if not info["class"] or not info["asm"]:
                return None
            node = gen.get_nodes_up(info["asm"], (info["ns"] + "." + info["class"]).lstrip("."))
            if node.m_Children and node.m_Children[0].m_Name == "m_GameObject":
                node.m_Children = tuple(node.m_Children[4:])
            return node
        boost, old = TypeTreeHelper.read_typetree_boost, TypeTreeHelper.get_ref_type_node
        original_read = TypeTreeHelper.read_value
        def bounded_read(node, reader, config):
            if node.m_Children and node.m_Children[0].m_Type == "Array" and node.m_Type not in TypeTreeHelper.FUNCTION_READ_MAP:
                pos = reader.Position
                count = reader.read_int()
                reader.Position = pos
                if count < 0 or count > reader.Length - pos:
                    raise ValueError(f"객체 크기 초과 배열 {node.m_Name}: {count} at {pos}")
            return original_read(node, reader, config)
        try:
            TypeTreeHelper.read_typetree_boost = None
            TypeTreeHelper.get_ref_type_node = reference_node
            TypeTreeHelper.read_value = bounded_read
            return obj.read_typetree()
        finally:
            TypeTreeHelper.read_typetree_boost, TypeTreeHelper.get_ref_type_node = boost, old
            TypeTreeHelper.read_value = original_read
    return obj.read_typetree()
