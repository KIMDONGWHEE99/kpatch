"""다른 자산 파일의 스프라이트까지 그림·표시 위치를 다시 연결합니다."""
from common import *
from collections import defaultdict

g = generator(); files = {}
for p in containers():
    e = UnityPy.load(str(p)); e.typetree_generator = g; files[p.name] = e.file
reviews = json.loads((EXTRACT/'media_review.json').read_text(encoding='utf8'))
media = {(r['file'], r['path_id']): r for r in reviews}
assert len(media) == len(reviews) == 265

def resolve(name, ref):
    if not ref['m_PathID']:return None
    other = name
    if ref['m_FileID']:
        other = files[name].externals[ref['m_FileID']-1].path.replace('\\','/').split('/')[-1]
    return other, ref['m_PathID']

def walk(v, path=()):
    if isinstance(v, dict):
        if set(v) == {'m_FileID', 'm_PathID'}:
            yield path, v
        else:
            for k, child in v.items():yield from walk(child, path+(k,))
    elif isinstance(v, list):
        if v and isinstance(v[0], int):return
        for i, child in enumerate(v):yield from walk(child, path+(i,))

sprites = {}
for name, f in files.items():
    for obj in f.objects.values():
        if obj.type.name != 'Sprite':continue
        t = obj.read_typetree(); ref = resolve(name, t['m_RD']['texture'])
        assert ref in media, (name, obj.path_id, ref)
        # 원래 그림 좌표(m_Rect)와 빌드에서 실제 사용하는 잘린 그림 좌표는 다를 수 있습니다.
        rect = t['m_RD']['textureRect']; m = media[ref]
        assert rect['width'] > 0 and rect['height'] > 0
        assert -0.0001 <= rect['x'] <= rect['x']+rect['width'] <= m['width']+0.0001, (name,obj.path_id,t['m_Name'],rect,ref,m['width'],m['height'])
        assert -0.0001 <= rect['y'] <= rect['y']+rect['height'] <= m['height']+0.0001, (name,obj.path_id,t['m_Name'],rect,ref,m['width'],m['height'])
        sprites[name,obj.path_id] = dict(file=name, path_id=obj.path_id, name=t['m_Name'], texture=ref, texture_sha256=m['raw_sha256'], source_rect=t['m_Rect'], rect=rect, pixel_top=m['height']-rect['y']-rect['height'], treatment=m['treatment'], source_raw_sha256=hashlib.sha256(obj.get_raw_data()).hexdigest(), uses=[])
assert len(sprites) == 1072
errors = []
for name, f in files.items():
    for obj in f.objects.values():
        if obj.type.name not in ['MonoBehaviour', 'SpriteAtlas', 'SpriteRenderer', 'Image', 'RawImage']:continue
        try:t = obj.read_typetree()
        except Exception as e:
            errors.append((name,obj.path_id)); continue
        for path, ref in walk(t):
            key = resolve(name, ref)
            if key in sprites:
                sprites[key]['uses'].append(dict(file=name, path_id=obj.path_id, field=path, type=script(obj)[0] if obj.type.name=='MonoBehaviour' else obj.type.name, object_sha256=hashlib.sha256(obj.get_raw_data()).hexdigest()))
resolved = json.loads((EXTRACT/'extraction_resolution.json').read_text(encoding='utf8'))
assert set(errors) <= {(r['file'],r['path_id']) for r in resolved if r['status']=='PASS'}
for m in reviews:
    assert m['treatment'] in ['TRANSLATE','KEEP','NO_TEXT']
    assert sha(EXTRACT/'media'/m['path']) == m['image_sha256']
special = [v for v in sprites.values() if v['name'] in ['AutoCompleteIcon','EndlessIcon','CrownDemo','ShopBorder','ShopBroken']]
assert {v['name'] for v in special} == {'AutoCompleteIcon','EndlessIcon','CrownDemo','ShopBorder','ShopBroken'}
assert all(v['treatment']=='TRANSLATE' for v in special)
assert all(v['uses'] for v in special if v['name']!='CrownDemo')
save_json(EXTRACT/'media_links_validation.json', dict(status='PASS', tool_sha256=sha(__file__), media_review_sha256=sha(EXTRACT/'media_review.json'), sprite_count=len(sprites), sprites=list(sprites.values()), resolved_parse_errors=errors, special=special))
print('PASS',len(sprites),'sprites',sum(len(v['uses']) for v in sprites.values()),'references',len(special),'translated sprite kinds')
