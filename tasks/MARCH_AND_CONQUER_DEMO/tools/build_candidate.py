"""번역 위치와 글꼴 변경만 포함한 고유 후보를 생성합니다."""
from common import *
from fontTools.ttLib import TTFont
import io,subprocess
build_id=sys.argv[1];folder=ROOT/'build_candidate'/GAME/build_id;game=folder/'game'
assert not game.exists();shutil.copytree(BASE,game)
g=generator();translations=json.loads((WORK/'translation.json').read_text(encoding='utf-8'))
assert not json.loads((WORK/'translation_missing.json').read_text(encoding='utf-8'))
group=collections.defaultdict(lambda:collections.defaultdict(list))
for row in translations:
    if row['classification']=='VISIBLE_TRANSLATE':group[row['file']][row['path_id']].append(row)
font_bytes=(WORK/'NotoSansKR-Regular.ttf').read_bytes();changes=[]
for name in ('level0','resources.assets','sharedassets0.assets'):
    env=load(BASE/DATA/name,g)
    for obj in env.objects:
        rows=group[name].get(obj.path_id,[])
        if not rows and obj.type.name not in ('Font','MonoBehaviour'):continue
        try:tree=obj.read_typetree()
        except Exception:
            assert not rows;continue
        fields=[]
        for row in rows:
            parts=row['field'].split('/')[1:];parent=tree
            for part in parts[:-1]:parent=parent[int(part)] if isinstance(parent,list) else parent[part]
            key=int(parts[-1]) if isinstance(parent,list) else parts[-1]
            assert parent[key]==row['source'];parent[key]=row['target'];fields.append(row['field'])
        if obj.type.name=='Font' and (name=='resources.assets' or obj.path_id==336):
            tree['m_FontData']=list(font_bytes);tree['m_FontNames']=['Noto Sans KR'];fields+=['/m_FontData','/m_FontNames']
        elif obj.type.name=='Font' and name=='sharedassets0.assets':
            tree['m_FallbackFonts']=[{'m_FileID':0,'m_PathID':336}];fields.append('/m_FallbackFonts')
        if 'm_CharacterTable' in tree and tree['m_AtlasPopulationMode']==1:
            tree['m_IsMultiAtlasTexturesEnabled']=True;fields.append('/m_IsMultiAtlasTexturesEnabled')
            if obj.path_id==1415:
                tree['m_FallbackFontAssetTable']=[{'m_FileID':0,'m_PathID':1716}];fields.append('/m_FallbackFontAssetTable')
            elif obj.path_id==1716:
                for key in tree['m_FontFeatureTable']:tree['m_FontFeatureTable'][key]=[]
                fields.append('/m_FontFeatureTable')
        if 'm_UseModernHangulLineBreakingRules' in tree:
            tree['m_UseModernHangulLineBreakingRules']=True;fields.append('/m_UseModernHangulLineBreakingRules')
        if name=='level0' and obj.path_id in [931,949,951,955,970,979,993,996]:
            tree['m_TextWrappingMode']=0;fields.append('/m_TextWrappingMode')
        if fields:
            obj.save_typetree(tree);changes.append(dict(file=name,path_id=obj.path_id,fields=fields,source_sha256=sha(obj.get_raw_data()),candidate_sha256=sha(obj.data)))
    (game/DATA/name).write_bytes(preserve_save(BASE/DATA/name,env))
subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'patch',str(BASE/DATA/'Managed/Assembly-CSharp.dll'),str(game/DATA/'Managed/Assembly-CSharp.dll'),str(WORK/'code_translation.json')],check=True)
save(folder/'build.json',dict(game_id=GAME,build_id=build_id,baseline_sha256=sha((WORK/'baseline.json').read_bytes()),translation_sha256=sha((WORK/'translation.json').read_bytes()),code_translation_sha256=sha((WORK/'code_translation.json').read_bytes()),font_sha256=sha(font_bytes),changes=changes,files=[dict(path=p.relative_to(game).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in game.rglob('*') if p.is_file()]))
print('후보',build_id,'변경 객체',len(changes))
