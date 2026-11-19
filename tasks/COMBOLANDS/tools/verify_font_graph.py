"""모든 텍스트에서 글꼴·원본·이미지·재질·대체 글꼴 연결을 따라갑니다."""
from common import *
from collections import Counter

folder = ROOT/'build_candidate/COMBOLANDS'/sys.argv[1]
g = generator()
files = {}
for path in containers(folder/'game/Combolands_Data'):
    env = UnityPy.load(str(path)); env.typetree_generator = g
    files[path.name] = env.file

def resolve(file, ref):
    if not ref or not ref['m_PathID']:
        return None
    name = file
    if ref['m_FileID']:
        name = files[file].externals[ref['m_FileID']-1].path.replace('\\','/').split('/')[-1]
    assert name in files and ref['m_PathID'] in files[name].objects, (file, ref, name)
    return name, ref['m_PathID']

def tree(key):
    return files[key[0]].objects[key[1]].read_typetree()

fonts, texts, settings, native = {}, [], [], []
for name, file in files.items():
    for obj in file.objects.values():
        if obj.type.name == 'Font':
            native.append((name, obj.path_id))
        if obj.type.name != 'MonoBehaviour':
            continue
        cls = script(obj)[0]
        if cls == 'TMP_FontAsset':
            fonts[name, obj.path_id] = obj.read_typetree()
        elif cls in ['TextMeshProUGUI', 'TextMeshPro', 'Text']:
            texts.append((name, obj.path_id, cls, obj.read_typetree()))
        elif cls == 'TMP_Settings':
            settings.append((name, obj.path_id, obj.read_typetree()))
assert len(fonts) == 7 and len(native) == 7 and len(settings) == 1
default = resolve(settings[0][0], settings[0][2]['m_defaultFontAsset'])
assert default in fonts
global_fallback = [resolve(settings[0][0], v) for v in settings[0][2]['m_fallbackFontAssets']]
assert all(v in fonts for v in global_fallback if v)

def material_texture(key):
    t = tree(key)
    assert files[key[0]].objects[key[1]].type.name == 'Material'
    entries = t['m_SavedProperties']['m_TexEnvs']
    main = [v for k, v in entries if k == '_MainTex']
    assert len(main) == 1, key
    return resolve(key[0], main[0]['m_Texture'])

graph, report = {}, []
for key, t in fonts.items():
    source = resolve(key[0], t['m_SourceFontFile'])
    assert source in native
    atlases = [resolve(key[0], ref) for ref in t['m_AtlasTextures']]
    material = resolve(key[0], t['m_Material'])
    assert material_texture(material) == atlases[0]
    edges = [resolve(key[0], ref) for ref in t['m_FallbackFontAssetTable']+t['fallbackFontAssets']]
    for weight in t['m_FontWeightTable']:
        edges.extend(resolve(key[0], ref) for ref in weight.values())
    edges = [v for v in edges if v]
    assert all(v in fonts for v in edges)
    graph[key] = edges
    width, height = t['m_AtlasWidth'], t['m_AtlasHeight']
    used = t['m_UsedGlyphRects']
    for rect in used+t['m_FreeGlyphRects']:
        assert 0 <= rect['m_X'] <= rect['m_X']+rect['m_Width'] <= width
        assert 0 <= rect['m_Y'] <= rect['m_Y']+rect['m_Height'] <= height
    for i, a in enumerate(used):
        for b in used[i+1:]:
            assert a['m_X']+a['m_Width'] <= b['m_X'] or b['m_X']+b['m_Width'] <= a['m_X'] or a['m_Y']+a['m_Height'] <= b['m_Y'] or b['m_Y']+b['m_Height'] <= a['m_Y'], (key, '글자 이미지 영역 겹침')
    occupied = sum(r['m_Width']*r['m_Height'] for r in used)
    assert t['m_IsMultiAtlasTexturesEnabled'] and t['m_AtlasPopulationMode'] == 1
    report.append(dict(font=key, source=source, material=material, atlases=atlases, fallback=edges, capacity=[width,height], occupied_pixels=occupied, unoccupied_pixels=width*height-occupied, multi_atlas=True))

def visit(key, stack):
    assert key not in stack, ('대체 글꼴 순환', stack, key)
    for edge in graph[key]:
        visit(edge, stack+[key])
for key in graph:
    visit(key, [])

links = []
for name, pid, cls, t in texts:
    if cls == 'Text':
        font = resolve(name, t['m_FontData']['m_Font'])
        assert font in native, (name, pid, font)
        links.append(dict(file=name, path_id=pid, cls=cls, font=font))
        continue
    font = resolve(name, t['m_fontAsset']) or default
    assert font in fonts
    material = resolve(name, t['m_sharedMaterial'])
    if material:
        assert material_texture(material) in [resolve(font[0], ref) for ref in fonts[font]['m_AtlasTextures']], (name, pid, font, material, '텍스트 재질 불일치')
    links.append(dict(file=name, path_id=pid, cls=cls, font=font, material=material, text_sha256=hashlib.sha256(t['m_text'].encode()).hexdigest()))
save_json(folder/'font_graph_validation.json', dict(status='PASS', candidate=sys.argv[1], build_sha256=sha(folder/'build.json'), tool_sha256=sha(__file__), default=default, global_fallback=global_fallback, fonts=report, text_links=links, native_fonts=native))
print('PASS', len(fonts), 'TMP fonts', len(native), 'sources', len(links), 'text references')
