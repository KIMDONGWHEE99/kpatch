"""모든 자산의 위치, 문자열, 해석 오류를 보존합니다."""
from common import *
from collections import Counter
import json

def strings(value, field=''):
    if isinstance(value, str):
        if value:
            yield field, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings(item, field + '/' + key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from strings(item, field + '/' + str(i))

if __name__ == '__main__':
    gen = generator()
    records, errors, texts, media, fonts = [], [], [], [], []
    tree_dir = EXTRACT / 'trees'
    for path in files():
        env = UnityPy.load(str(path))
        env.typetree_generator = gen
        digest = sha(path)
        count = Counter()
        for obj in env.objects:
            kind = obj.type.name
            count[kind] += 1
            key = f'{path.name}/{obj.assets_file.name}/{obj.path_id}'
            row = {'id':key,'file':str(path.relative_to(SOURCE)), 'file_sha256':digest,'asset':obj.assets_file.name,'path_id':obj.path_id,'type':kind,'bytes':obj.byte_size}
            if kind in ('MonoBehaviour','MonoScript','GameObject','TextAsset','PlayerSettings','Font','Texture2D','Sprite','VideoClip'):
                try:
                    tree = obj.read_typetree()
                    row['name'] = tree.get('m_Name','')
                    if kind == 'MonoBehaviour':
                        try:
                            s = obj.parse_monobehaviour_head().m_Script.deref_parse_as_object()
                            row['script'] = f'{s.m_AssemblyName}:{s.m_Namespace}.{s.m_ClassName}'
                        except Exception as e:
                            row['script_error'] = str(e)
                    if kind in ('MonoBehaviour','TextAsset','PlayerSettings'):
                        dest = tree_dir / path.name / obj.assets_file.name / f'{obj.path_id}.json'
                        write_json(dest, tree)
                        row['tree'] = str(dest.relative_to(EXTRACT))
                        for field, value in strings(tree):
                            texts.append({'id':key+field,'object_id':key,'field':field,'source':value,'classification':'UNKNOWN','file_sha256':digest})
                    if kind in ('Texture2D','Sprite','VideoClip'):
                        media.append({**row,'classification':'MEDIA','treatment':'UNKNOWN','width':tree.get('m_Width'),'height':tree.get('m_Height')})
                    if kind == 'Font' or 'm_CharacterTable' in tree:
                        fonts.append({**row,'font_info':{k:v for k,v in tree.items() if k not in ('m_FontData','m_GlyphTable','m_CharacterTable','m_FontFeatureTable')}})
                except Exception as e:
                    errors.append({**row,'status':'UNKNOWN','error':str(e)})
            records.append(row)
        print(path.name, dict(count), flush=True)
    write_json(EXTRACT/'objects.json',records)
    write_json(EXTRACT/'strings.json',texts)
    write_json(EXTRACT/'extraction_errors.json',errors)
    write_json(EXTRACT/'media.json',media)
    write_json(EXTRACT/'fonts.json',fonts)
    print(json.dumps({'objects':len(records),'strings':len(texts),'errors':len(errors),'media':len(media),'fonts':len(fonts)}))
