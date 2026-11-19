"""재개방한 후보에서 위치별 기대값, 나머지 바이트, 글꼴 문자표를 독립 대조합니다."""
from common import *
from build_candidate import CANDIDATE,REPORT
import json,collections,copy,struct,re,io,unicodedata
from fontTools.ttLib import TTFont

edits=json.loads((REPORT/'asset_edits.json').read_text('utf-8'));by_object=collections.defaultdict(list)
for r in edits:by_object[r['object_id']].append(r)
def get(tree,path):
    current=tree
    for part in path.split('/')[1:]:current=current[int(part)] if isinstance(current,list) else current[part]
    return current
def put(tree,path,value):
    parts=path.split('/')[1:];current=tree
    for part in parts[:-1]:current=current[int(part)] if isinstance(current,list) else current[part]
    current[int(parts[-1]) if isinstance(current,list) else parts[-1]]=value
gen=generator();configure_references(gen);checked_objects=0;changed_objects=0;fonts=[];locations=[];glyphs={}
for src in files():
    dst=CANDIDATE/src.relative_to(SOURCE)
    if sha(src)==sha(dst):continue
    before=UnityPy.load(str(src));after=UnityPy.load(str(dst));before.typetree_generator=gen;after.typetree_generator=gen
    originals={(o.assets_file.name,o.path_id,o.type.name):o for o in before.objects}
    candidates={(o.assets_file.name,o.path_id,o.type.name):o for o in after.objects}
    assert set(originals)==set(candidates),src
    for key,obj in originals.items():
        cand=candidates[key];identity=f'{src.name}/{key[0]}/{key[1]}';checked_objects+=1
        if identity in by_object:
            a=read_tree(obj);b=read_tree(cand);reverted=copy.deepcopy(b)
            for r in by_object[identity]:
                assert get(a,r['field'])==r['before'],r['id']
                assert get(b,r['field'])==r['after'],r['id']
                put(reverted,r['field'],r['before']);locations.append({'id':r['id'],'status':'PASS'})
            assert reverted==a,identity
            changed_objects+=1
        else:assert obj.get_raw_data()==cand.get_raw_data(),('unplanned',identity)
        if cand.type.name=='Font':
            t=read_tree(cand);data=bytes(v&255 for v in t['m_FontData']);glyphs[identity]=set(TTFont(io.BytesIO(data)).getBestCmap())
        elif cand.type.name=='MonoBehaviour':
            try:
                t=read_tree(cand)
                if 'm_CharacterTable' in t:fonts.append({'id':identity,'name':t['m_Name'],'atlas_mode':t['m_AtlasPopulationMode'],'multi_atlas':t['m_IsMultiAtlasTexturesEnabled'],'source':t['m_SourceFontFile'],'fallbacks':t['m_FallbackFontAssetTable'],'material':t['m_Material'],'atlas':t['m_AtlasTextures'],'characters':[r['m_Unicode'] for r in t['m_CharacterTable']],'glyph_count':len(t['m_GlyphTable'])})
            except (ValueError,KeyError):
                # 다른 MonoBehaviour는 위의 원시 바이트 또는 필드 대조 대상입니다.
                if identity in by_object:raise
    print('verified',src.name,len(originals),'objects',flush=True)
metadata_path='The Loopler_Data/il2cpp_data/Metadata/global-metadata.dat'
orig=(SOURCE/metadata_path).read_bytes();cand=(CANDIDATE/metadata_path).read_bytes()
def literals(data):
    table,size,count,pool,psize,pcount=struct.unpack_from('<6I',data,8);assert count*4==size
    offsets=struct.unpack_from('<'+str(count)+'I',data,table);assert offsets[-1]==psize
    return [data[pool+a:pool+(offsets[i+1] if i+1<count else psize)].decode('utf-8') for i,a in enumerate(offsets)]
old=literals(orig);new=literals(cand);assert len(old)==len(new)
expected={r['index']:r for r in json.loads((REPORT/'literal_edits.json').read_text('utf-8'))}
for i,(a,b) in enumerate(zip(old,new)):
    assert b==(expected[i]['after'] if i in expected else a),i
assert orig[:8]==cand[:8] and orig[32:]==cand[32:len(orig)]
assert struct.unpack_from('<I',orig,16)==struct.unpack_from('<I',cand,16)
assert struct.unpack_from('<I',orig,28)==struct.unpack_from('<I',cand,28)

translations=json.loads((WORK/'translation_canonical.json').read_text('utf-8'))
translations += [{'source':r['before'],'translation':r['after']} for r in edits if isinstance(r['before'],str) and isinstance(r['after'],str) and '-korean(' not in r['id']]
translations += [{'source':r['before'],'translation':r['after']} for r in expected.values()]
need=set();token_errors=[]
for r in translations:
    a,b=r['source'],r['translation']
    if not isinstance(b,str):continue
    assert unicodedata.normalize('NFC',b)==b
    need.update(ord(c) for c in re.sub('<[^>]*>|\{[^}]*\}','',b) if c not in '\r\n\t')
    if re.findall('<[^>]*>',a)!=re.findall('<[^>]*>',b) or collections.Counter(re.findall(r'\{[^{}]*\}',a))!=collections.Counter(re.findall(r'\{[^{}]*\}',b)):
        token_errors.append((a,b))
    # 키 끝의 줄바꿈 교정은 화면 제어 줄바꿈과 구분해 명시 허용합니다.
    if not a.startswith('NEW_ACHIEVEMENT_') and (a.count('\n')!=b.count('\n') or a.count('\\n')!=b.count('\\n')):token_errors.append((a,b))
assert not token_errors,token_errors[:10]
hangul={x for x in need if 0xac00<=x<=0xd7a3}
lana=[(k,v) for k,v in glyphs.items() if k.endswith('/210') or k.endswith('/3149513003455590403')]
assert len(lana)==2
for key,chars in lana:assert not hangul-chars,(key,hangul-chars)
for font in fonts:
    if font['name']=='LanaPixel SDF':assert font['atlas_mode']==1 and font['multi_atlas']==1 and font['source']['m_PathID']!=0 and not font['fallbacks']
write_json(REPORT/'static_validation.json',{'status':'PASS','scope':'객체 ID/형식/개수·위치별 기대 필드·미허용 객체 바이트·16,116개 코드 리터럴·태그 순서·자리표시자·제어 줄바꿈','checked_objects':checked_objects,'changed_objects':changed_objects,'field_checks':len(locations),'metadata_literals':len(old),'literal_changes':len(expected),'required_hangul':len(hangul),'font_checks':fonts,'source_font_checks':[{'id':k,'missing_hangul':sorted(hangul-v),'coverage':len(v)} for k,v in lana],'candidate_inputs':[{'path':p.relative_to(CANDIDATE).as_posix(),'sha256':sha(p)} for p in sorted(CANDIDATE.rglob('*')) if p.is_file()]})
print('STATIC PASS',checked_objects,'objects',len(locations),'fields',len(hangul),'Hangul syllables')
