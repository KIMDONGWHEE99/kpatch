"""사본의 자산·문자열·글꼴·미디어 위치와 해석 실패를 기록합니다."""
from extract_localization import ROOT, BASE, OUT, save
from pathlib import Path
from collections import Counter
import hashlib
import json
import sys
import UnityPy
from UnityPy.helpers import TypeTreeHelper
from UnityPy.streams import EndianBinaryReader
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
from UnityPy.helpers.TypeTreeNode import TypeTreeNode

EXTRACT = OUT.parent / 'asset_scan'

def configure_reader(gen):
    def reference_node(value, asset):
        info = value['type']
        if not info['class'] or not info['asm']:
            return None
        node = gen.get_nodes_up(info['asm'], (info['ns'] + '.' + info['class']).lstrip('.'))
        if node.m_Children and node.m_Children[0].m_Name == 'm_GameObject':
            node.m_Children = tuple(node.m_Children[4:])
        return node
    TypeTreeHelper.get_ref_type_node = reference_node
    original = TypeTreeHelper.read_value
    def bounded_read(node, reader, config):
        if node.m_Children and node.m_Children[0].m_Type == 'Array' and node.m_Type not in TypeTreeHelper.FUNCTION_READ_MAP:
            position = reader.Position
            count = reader.read_int()
            reader.Position = position
            if count < 0 or count > reader.Length - position:
                raise ValueError('객체 크기를 초과하는 배열: ' + node.m_Name + ' count=' + str(count))
        return original(node, reader, config)
    TypeTreeHelper.read_value = bounded_read

def read_bounded(obj):
    if obj.type.name != 'MonoBehaviour':
        return obj.read_typetree()
    boost = TypeTreeHelper.read_typetree_boost
    TypeTreeHelper.read_typetree_boost = None
    try:
        reader = EndianBinaryReader(obj.get_raw_data(), endian=obj.reader.endian)
        return TypeTreeHelper.read_typetree(obj._get_typetree_node(), reader, byte_size=obj.byte_size, assetsfile=obj.assets_file)
    finally:
        TypeTreeHelper.read_typetree_boost = boost

class GameGenerator(TypeTreeGenerator):
    def get_nodes_up(self, assembly, fullname):
        key = (assembly, fullname)
        if key in self.cache:
            return self.cache[key]
        nodes = list(self.get_nodes(assembly if assembly.endswith('.dll') else assembly + '.dll', fullname))
        fixed = []
        for index, node in enumerate(nodes):
            kind, flag = node.m_Type, node.m_MetaFlag
            if node.m_Level == 1 and node.m_Name == 'm_Enabled':
                flag |= 0x4000
            if kind == 'string' and index + 3 < len(nodes) and nodes[index + 1].m_Name == 'Array' and nodes[index + 3].m_Type == 'string':
                kind = 'vector'
            fixed.append(TypeTreeNode(node.m_Level, kind, node.m_Name, 0, 0, m_MetaFlag=flag))
        result = TypeTreeNode.from_list(fixed)
        registry = [c for c in result.m_Children if c.m_Name == 'references' and c.m_Type == 'ManagedReferencesRegistry']
        if len(registry) > 1:
            excluded = {id(c) for c in registry[:-1]}
            result.m_Children = tuple(c for c in result.m_Children if id(c) not in excluded)
        self.cache[key] = result
        return result

def strings(value, field=''):
    if isinstance(value, str):
        if value:
            yield field, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings(item, field + '/' + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings(item, field + '/' + str(index))

def json_default(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'byte_count': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
    raise TypeError(type(value).__name__)

def main():
    EXTRACT.mkdir(parents=True, exist_ok=True)
    source_root = Path('\\\\?\\' + str(BASE))
    gen = GameGenerator('6000.0.62f1')
    gen.load_local_dll_folder(str(OUT.parent / 'code/dummy'))
    configure_reader(gen)
    data_dir = source_root / 'Alaska Gold Fever_Data'
    paths = sorted((data_dir / 'StreamingAssets/aa/StandaloneWindows64').glob('*.bundle'), key=lambda p: p.stat().st_size)
    paths += sorted([p for p in data_dir.iterdir() if p.suffix == '.assets' or p.name == 'globalgamemanagers' or (p.name.startswith('level') and p.suffix == '')])
    errors, summaries = [], []
    outputs = {name: (EXTRACT / (name + '.jsonl')).open('w', encoding='utf-8') for name in ('objects','strings','media','fonts','texts')}
    def emit(name, value):
        outputs[name].write(json.dumps(value, ensure_ascii=False, default=json_default) + '\n')
    for path in paths:
        relative = path.relative_to(source_root).as_posix()
        try:
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            env = UnityPy.load(raw)
            env.path = str(BASE / 'Alaska Gold Fever_Data')
            env.typetree_generator = gen
            count = Counter()
            for obj in env.objects:
                kind = obj.type.name
                count[kind] += 1
                asset_name = obj.assets_file.name if path.suffix == '.bundle' else path.name
                object_id = relative + '|' + asset_name + '|' + str(obj.path_id)
                row = {'object_id': object_id, 'file': relative, 'sha256': digest, 'asset': asset_name,
                       'path_id': obj.path_id, 'type': kind, 'bytes': obj.byte_size}
                selected = ('MonoBehaviour','MonoScript','GameObject','TextAsset','PlayerSettings','Font','Texture2D','Sprite','VideoClip')
                if kind in selected:
                    try:
                        (EXTRACT / 'current_object.json').write_text(json.dumps(row), encoding='utf-8')
                        tree = read_bounded(obj)
                        row['name'] = tree.get('m_Name', '')
                        if kind == 'MonoBehaviour':
                            try:
                                script = obj.parse_monobehaviour_head().m_Script.deref_parse_as_object()
                                row['script'] = script.m_AssemblyName + ':' + script.m_Namespace + '.' + script.m_ClassName
                            except Exception as exc:
                                row['script_error'] = str(exc)
                        if kind in ('MonoBehaviour','TextAsset','PlayerSettings'):
                            for field, value in strings(tree):
                                emit('strings', {**row, 'field':field, 'text':value, 'classification':'UNKNOWN'})
                        if kind in ('Texture2D','Sprite','VideoClip'):
                            emit('media', {**row,'classification':'MEDIA','treatment':'UNKNOWN','width':tree.get('m_Width'),'height':tree.get('m_Height')})
                        if kind == 'Font' or 'm_CharacterTable' in tree:
                            emit('fonts', {**row,'tree':tree})
                        if any(key in tree for key in ('m_text','m_Text','m_FontAsset','m_fontAsset','m_fontSharedMaterial')):
                            emit('texts', {**row,'tree':tree})
                    except Exception as exc:
                        errors.append({**row,'status':'UNKNOWN','error':str(exc)})
                emit('objects', row)
            summaries.append({'file':relative,'sha256':digest,'objects':dict(count)})
            save(EXTRACT / 'files.json', summaries)
            save(EXTRACT / 'errors.json', errors)
            print(path.name, sum(count.values()), 'errors',len(errors), flush=True)
        except Exception as exc:
            errors.append({'file':relative,'status':'UNKNOWN','error':str(exc)})
    for stream in outputs.values():
        stream.close()
    save(EXTRACT / 'files.json', summaries)
    save(EXTRACT / 'errors.json', errors)
    print('files',len(summaries),'errors',len(errors))

if __name__ == '__main__':
    main()
