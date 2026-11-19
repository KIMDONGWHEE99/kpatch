"""새 프로세스로 후보를 재열어 원본 위치별 기대값과 변경 경계를 독립 대조합니다."""
from common import *
import io,re,subprocess,datetime
from fontTools.ttLib import TTFont
build=sys.argv[1];candidate=ROOT/'build_candidate/EPIC_IDLENTURE_DEMO'/build;manifest=json.loads((WORK/(build+'.json')).read_text(encoding='utf8'))
def value(t,path):
    for k in path.strip('/').split('/'):t=t[int(k)] if isinstance(t,list) else t[k]
    return t
def leaves(a,b,path=''):
    if type(a)!=type(b):yield path,a,b
    elif isinstance(a,dict):
        assert set(a)==set(b),(path,'키 집합')
        for k in a:yield from leaves(a[k],b[k],path+'/'+k)
    elif isinstance(a,list):
        if len(a)!=len(b):yield path,a,b
        else:
            for i,(x,y) in enumerate(zip(a,b)):yield from leaves(x,y,path+'/'+str(i))
    elif a!=b:yield path,a,b
baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf8'));assert {p.relative_to(candidate).as_posix() for p in candidate.rglob('*') if p.is_file()}=={r['path'] for r in baseline}
for r in manifest['files']:assert sha((candidate/r['path']).read_bytes())==r['sha256']
for r in baseline:assert sha((BASE/r['path']).read_bytes())==r['sha256']
catalog={r['id']:r for r in json.loads((WORK/'translation.json').read_text(encoding='utf8'))};occurrences=json.loads((WORK/'translation_occurrences.json').read_text(encoding='utf8'))
expected={(r['file'],r['path_id'],r['field']):(r['source'] if r['field']=='/Name' else catalog[r['translation_id']]['target']) for r in occurrences};assert len(expected)==len(occurrences)
g=generator();seen=set();boundary=[];font_rows=[];object_count=0
for name in ['globalgamemanagers','globalgamemanagers.assets','level0','level1','resources.assets','sharedassets0.assets','sharedassets1.assets','Resources/unity default resources','Resources/unity_builtin_extra']:
    a=load(BASE/DATA/name,g);b=load(candidate/DATA/name,g);assert set(a.file.objects)==set(b.file.objects)
    assert [(x.path,x.guid) for x in a.file.externals]==[(x.path,x.guid) for x in b.file.externals]
    for pid,old in a.file.objects.items():
        new=b.file.objects[pid];object_count+=1
        positions=[k for k in expected if k[:2]==(name,pid)]
        if positions:
            tree=new.read_typetree()
            for key in positions:assert value(tree,key[2])==expected[key],key;seen.add(key)
        if old.get_raw_data()==new.get_raw_data():continue
        at=old.read_typetree();bt=new.read_typetree()
        if name=='resources.assets' and old.type.name=='Font':
            assert set(k for k in at if at[k]!=bt[k])=={'m_FontData','m_FontNames'}
            font=TTFont(io.BytesIO(bytes(bt['m_FontData'])));missing=set(manifest['font_characters'])-set(font.getBestCmap());assert not missing
            font_rows.append(dict(file=name,path_id=pid,sha256=sha(bytes(bt['m_FontData'])),required=len(manifest['font_characters']),missing=0));continue
        for path,x,y in leaves(at,bt):
            if (name,pid,path) in expected:assert y==expected[(name,pid,path)]
            elif name=='resources.assets' and pid==5212:assert path=='/m_fallbackFontAssets' and y==[{'m_FileID':0,'m_PathID':5208}]
            elif name=='resources.assets' and pid in [6565,6655,6768,6862,6994,7146]:assert path in ['/m_FontData/m_Font/m_FileID','/m_FontData/m_Font/m_PathID'] and bt['m_FontData']['m_Font']=={'m_FileID':0,'m_PathID':673}
            else:raise AssertionError((name,pid,path))
            boundary.append(dict(file=name,path_id=pid,field=path))
assert seen==set(expected);assert len(font_rows)==7
resource=load(candidate/DATA/'resources.assets',g);fallback=resource.file.objects[5208].read_typetree();assert fallback['m_AtlasPopulationMode']==1 and fallback['m_IsMultiAtlasTexturesEnabled'] and fallback['m_SourceFontFile']['m_PathID']==677
for module,sheet,mode in [('Assembly-CSharp.dll','code_translation.json','verify'),('StompyRobot.SRDebugger.dll','debug_translation.json','literal_verify')]:
    subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),mode,str(BASE/DATA/'Managed'/module),str(candidate/DATA/'Managed'/module),str(WORK/sheet)],check=True)
    out=WORK/(build+'_'+module+'_strings.json');subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'dumpall',str(candidate/DATA/'Managed'/module),str(out)],check=True)
    extracted=json.loads(out.read_text(encoding='utf8'))
    if module=='Assembly-CSharp.dll':
        pairs=[r['source'] for r in extracted if r['method']=='System.String KoreanPatchText::Label(System.String)'];assert dict(zip(pairs[::2],pairs[1::2]))==json.loads((WORK/'runtime_labels.json').read_text(encoding='utf8'))
inputs={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in [WORK/'baseline.json',WORK/'translation.json',WORK/'translation_occurrences.json',WORK/'code_translation.json',WORK/'debug_translation.json',WORK/'runtime_labels.json',WORK/(build+'.json'),Path(__file__)]}
report=dict(status='PASS',build=build,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),inputs=inputs,files=len(baseline),objects=object_count,positions=len(seen),field_changes=len(boundary),fonts=font_rows,missing=0,unexpected_changes=0)
save(WORK/(build+'_independent.json'),report);print('독립 대조 통과',object_count,len(seen),len(boundary))
