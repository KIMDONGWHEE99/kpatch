"""모든 글꼴 묶음을 다시 열어 원본 글꼴과 대체 글꼴 경로를 확인합니다."""
from common import *
from build_candidate import CANDIDATE,REPORT
from fontTools.ttLib import TTFont
import json,io,re,collections
gen=generator();configure_references(gen)
envs={};objects={};fonts={};tmp={};consumers=[]
for src in files():
    e=UnityPy.load(str(CANDIDATE/src.relative_to(SOURCE)));e.typetree_generator=gen
    for o in e.objects:
        identity=f'{src.name}/{o.assets_file.name}/{o.path_id}';objects[identity]=o
        if o.type.name=='Font':
            t=read_tree(o);raw=bytes(x&255 for x in t['m_FontData']);font=TTFont(io.BytesIO(raw));fonts[identity]={'name':t['m_Name'],'characters':sorted(font.getBestCmap()),'data_sha256':__import__('hashlib').sha256(raw).hexdigest()}
        if o.type.name!='MonoBehaviour':continue
        try:t=read_tree(o)
        except (ValueError,KeyError):continue
        if 'm_CharacterTable' in t:tmp[identity]=(o,t)
        if 'm_fontAsset' in t:consumers.append({'id':identity,'font':t['m_fontAsset'],'material':t.get('m_sharedMaterial')})
def resolve(o,p):
    if p['m_PathID']==0:return None
    asset=o.assets_file.name if not p['m_FileID'] else o.assets_file.externals[p['m_FileID']-1].name
    matches=[k for k in objects if k.endswith('/'+asset+'/'+str(p['m_PathID']))]
    assert len(matches)==1,(o.path_id,p,matches)
    return matches[0]
canonical=json.loads((WORK/'translation_canonical.json').read_text('utf-8'))
values=[r['translation'] for r in canonical]
values += list(json.loads((WORK/'translation_parts/runtime_extra.json').read_text('utf-8')).values())
values += [r['translation'] for r in json.loads((REPORT/'text_decisions.json').read_text('utf-8')) if isinstance(r.get('translation'),str)]
needed={ord(c) for s in values for c in re.sub(r'<[^>]*>|\{[^}]*\}','',s) if c not in '\r\n\t'}
lana=[k for k,v in fonts.items() if v['name']=='LanaPixel'];assert len(lana)==2
for k in lana:assert not needed-set(fonts[k]['characters']),(k,[chr(x) for x in needed-set(fonts[k]['characters'])])
report=[]
for identity,(o,t) in tmp.items():
    source=resolve(o,t['m_SourceFontFile']);fallbacks=[resolve(o,p) for p in t['m_FallbackFontAssetTable']]
    material=resolve(o,t['m_Material']);atlas=[resolve(o,p) for p in t['m_AtlasTextures']]
    glyphids={x['m_Index'] for x in t['m_GlyphTable']}
    assert all(x['m_GlyphIndex'] in glyphids for x in t['m_CharacterTable']),identity
    if t['m_Name']=='LanaPixel SDF':assert t['m_AtlasPopulationMode']==1 and source in lana and t['m_IsMultiAtlasTexturesEnabled']==1 and not fallbacks
    mat=read_tree(objects[material]);textures=mat['m_SavedProperties']['m_TexEnvs'];main=[x for x in textures if x[0]=='_MainTex']
    assert main,identity
    rendered_atlas=resolve(objects[material],main[0][1]['m_Texture']);note='재질과 선언 아틀라스 일치'
    if rendered_atlas not in atlas:
        assert identity=='data.unity3d/sharedassets0.assets/11015' and rendered_atlas=='data.unity3d/sharedassets0.assets/50' and atlas==['data.unity3d/sharedassets0.assets/80'] and t['m_AtlasPopulationMode']==0
        note='원본 AnonReadableBorder의 정적 재질은 글자가 있는 50번 그림을 사용. 선언 80번 그림은 비어 있음. 066_50.png/096_80.png 직접 비교했고 이 원본 재질을 보존함'
    report.append({'id':identity,'source':source,'fallbacks':fallbacks,'material':material,'atlases':atlas,'rendered_atlas':rendered_atlas,'material_note':note,'dynamic':t['m_AtlasPopulationMode'],'multi_atlas':t['m_IsMultiAtlasTexturesEnabled'],'characters':len(t['m_CharacterTable']),'glyphs':len(t['m_GlyphTable']),'free_rects':t.get('m_FreeGlyphRects'),'atlas_size':[t['m_AtlasWidth'],t['m_AtlasHeight']]})
by_font={r['id']:r for r in report}
def reachable(identity,seen):
    assert identity not in seen,('fallback_cycle',identity)
    f=by_font[identity]
    if f['dynamic']==1 and f['source'] in lana:return [identity]
    for k in f['fallbacks']:
        path=reachable(k,seen|{identity})
        if path:return [identity]+path
    return []
for c in consumers:
    o=objects[c['id']];f=resolve(o,c['font']);assert f in by_font,c
    path=reachable(f,set());assert path,('uncovered_consumer',c['id'],f)
    c['resolved_font']=f;c['hangul_fallback_path']=path
    c['resolved_material']=resolve(o,c['material']) if c['material'] else None
write_json(REPORT/'font_validation.json',{'status':'PASS','required_codepoints':sorted(needed),'required_count':len(needed),'source_font_count':len(fonts),'tmp_font_count':len(tmp),'consumer_count':len(consumers),'consumer_fallback_reachability':'PASS','all_hangul_syllables':all(set(range(0xac00,0xd7a4))<=set(fonts[k]['characters']) for k in lana),'fonts':report,'consumers':consumers,'inputs':{'candidate_build':sha(REPORT/'build.json'),'translation':sha(WORK/'translation_canonical.json'),'runtime':sha(WORK/'translation_parts/runtime_extra.json')}})
print('FONT PASS',len(needed),'characters',len(tmp),'TMP fonts',len(consumers),'consumers')
