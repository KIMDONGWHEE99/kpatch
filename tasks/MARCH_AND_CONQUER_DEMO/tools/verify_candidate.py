"""후보를 다시 열어 위치·구조·글꼴을 독립 대조합니다."""
from common import *
from checks import check_entry,check_characters
from fontTools.ttLib import TTFont
import io,re,subprocess
build=sys.argv[1];folder=ROOT/'build_candidate'/GAME/build;game=folder/'game';g=generator()
translations=json.loads((WORK/'translation.json').read_text(encoding='utf-8')); expected={(r['file'],r['path_id'],r['field']):r for r in translations}
def value_at(d,path):
    for part in path.split('/')[1:]:d=d[int(part)] if isinstance(d,list) else d[part]
    return d
def diffs(a,b,path=''):
    if type(a)!=type(b):
        if isinstance(a,(bool,int)) and isinstance(b,(bool,int)) and a==b:return
        yield path;return
    if isinstance(a,dict):
        assert a.keys()==b.keys(),('삭제/추가 필드',path)
        for k in a:yield from diffs(a[k],b[k],path+'/'+k)
    elif isinstance(a,list):
        if len(a)!=len(b):yield path
        else:
            for i,(x,y) in enumerate(zip(a,b)):yield from diffs(x,y,path+'/'+str(i))
    elif a!=b:yield path
def tokens(text):return re.findall(r'\{[^{}]+\}|</?[^>]+>',text)
baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf-8'))
files={p.relative_to(game).as_posix():p for p in game.rglob('*') if p.is_file()}
assert set(files)=={r['path'] for r in baseline['files']}
modified={DATA+'/'+x for x in ['level0','resources.assets','sharedassets0.assets','Managed/Assembly-CSharp.dll']}
for r in baseline['files']:
    if r['path'] not in modified:assert sha(files[r['path']].read_bytes())==r['sha256']
changes=[];seen=set();fonts={};tmpfonts={};textrefs=[];envs={}
for name in ['level0','resources.assets','sharedassets0.assets']:
    original=load(BASE/DATA/name,g);candidate=load(game/DATA/name,g);envs[name]=candidate
    assert list(original.file.objects)==list(candidate.file.objects)
    assert [x.path for x in original.file.externals]==[x.path for x in candidate.file.externals]
    for obj in candidate.objects:
        src=original.file.objects[obj.path_id]
        assert obj.type==src.type
        try:after=obj.read_typetree();before=src.read_typetree()
        except Exception:
            assert src.get_raw_data()==obj.get_raw_data();continue
        for loc,row in expected.items():
            if loc[:2]!=(name,obj.path_id):continue
            assert value_at(before,loc[2])==row['source'];check_entry(row['source'],value_at(after,loc[2]),row['target'])
            seen.add(loc)
        allowed=[p for fn,pid,p in expected if fn==name and pid==obj.path_id and expected[(fn,pid,p)]['classification']=='VISIBLE_TRANSLATE']
        if name=='level0' and obj.path_id in [931,949,951,955,970,979,993,996]:
            assert after['m_TextWrappingMode']==0;allowed+=['/m_TextWrappingMode']
        if obj.type.name=='Font':
            fonts[(name,obj.path_id)]=after
            allowed+=['/m_FontData','/m_FontNames'] if name=='resources.assets' or obj.path_id==336 else ['/m_FallbackFonts']
        if 'm_CharacterTable' in after:
            tmpfonts[(name,obj.path_id)]=after
            if obj.path_id==1415:allowed+=['/m_IsMultiAtlasTexturesEnabled','/m_FallbackFontAssetTable']
            if obj.path_id==1716:allowed+=['/m_IsMultiAtlasTexturesEnabled','/m_FontFeatureTable']
        if 'm_UseModernHangulLineBreakingRules' in after:
            assert after['m_UseModernHangulLineBreakingRules'];allowed+=['/m_UseModernHangulLineBreakingRules']
        for diff in diffs(before,after):assert any(diff==p or diff.startswith(p+'/') for p in allowed),(name,obj.path_id,diff)
        if obj.get_raw_data()!=src.get_raw_data():changes.append((name,obj.path_id))
        if 'm_fontAsset' in after:textrefs.append((name,obj.path_id,after['m_fontAsset']))
assert seen==set(expected),(len(seen),len(expected))
text=''.join(r['target'] for r in translations)+''.join(r['target'] for r in json.loads((WORK/'code_translation.json').read_text(encoding='utf-8')))+'대기준비출전전투중승리패배전환금화부족마나배치공간미해금알수없음0123456789%/+-:.,!'
required=sorted({ord(c) for c in text if not c.isspace()})
for loc in [('resources.assets',298),('sharedassets0.assets',336)]:
    font=TTFont(io.BytesIO(bytes(fonts[loc]['m_FontData'])));cmap=font.getBestCmap();check_characters(required,cmap)
for loc,d in tmpfonts.items():
    if d['m_AtlasPopulationMode']==1:
        assert d['m_IsMultiAtlasTexturesEnabled'] and d['m_SourceFontFile']['m_PathID']!=0
        assert all(ref['m_PathID'] in envs[loc[0]].file.objects for ref in d['m_AtlasTextures'])
    if loc[1] in [1415,1717]:assert any(p['m_PathID']==1716 for p in d['m_FallbackFontAssetTable'])
assert tmpfonts[('sharedassets0.assets',1716)]['m_SourceFontFile']['m_PathID']==336
for name,pid,ref in textrefs:
    target=name if ref['m_FileID']==0 else Path(envs[name].file.externals[ref['m_FileID']-1].path).name
    assert (target,ref['m_PathID']) in tmpfonts,(name,pid,ref,target)
subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'verify',str(BASE/DATA/'Managed/Assembly-CSharp.dll'),str(game/DATA/'Managed/Assembly-CSharp.dll'),str(WORK/'code_translation.json')],check=True)
save(folder/'static_validation.json',dict(game_id=GAME,build_id=build,status='PASS',baseline_sha256=sha((WORK/'baseline.json').read_bytes()),build_manifest_sha256=sha((folder/'build.json').read_bytes()),translation_sha256=sha((WORK/'translation.json').read_bytes()),positions=len(seen),modified_objects=len(changes),tmp_text_references=len(textrefs),font_assets=len(tmpfonts),required_characters=len(required),missing_characters=0,unexpected_changes=0,blank_translations=0,required_codepoints=required))
print('PASS',len(seen),'위치',len(changes),'객체',len(textrefs),'텍스트 글꼴 참조',len(required),'필요 문자')
