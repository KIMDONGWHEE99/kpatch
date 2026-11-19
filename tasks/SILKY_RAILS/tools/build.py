"""번역표·직접 문구·한글 대체 글꼴로 후보를 생성하고 변경 경계를 대조합니다."""
from common import *
import csv,io,re,subprocess,copy
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset
build_id=sys.argv[1];candidate=ROOT/'build_candidate/SILKY_RAILS'/build_id
assert not candidate.exists();shutil.copytree(BASE,candidate)
ko=json.loads((WORK/'ko.json').read_text());direct=json.loads((WORK/'direct_translation.json').read_text());code=json.loads((WORK/'code_translation.json').read_text())
chars={ord(c) for c in ''.join(ko.values())+''.join(r['target'] for r in direct+code) if c not in '\r\n\t'}|set(range(32,127))
f=TTFont(ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf');assert chars<=set(f.getBestCmap())
f=instantiateVariableFont(f,{'wght':400},inplace=True);opt=subset.Options();opt.name_IDs=['*'];opt.name_languages=['*'];ss=subset.Subsetter(options=opt);ss.populate(unicodes=chars);ss.subset(f);f.save(WORK/'NotoSansKR-Regular.ttf');font_bytes=(WORK/'NotoSansKR-Regular.ttf').read_bytes()
assert chars<=set(TTFont(io.BytesIO(font_bytes)).getBestCmap())
g=generator();changes=[];expected={};group=collections.defaultdict(lambda:collections.defaultdict(list))
for r in direct:group[r['file']][r['path_id']].append(r)
font_assets=json.loads((EXTRACT/'fonts.json').read_text());font_ids=collections.defaultdict(set)
for r in font_assets:
 if r['type']=='MonoBehaviour':font_ids[r['file']].add(r['path_id'])
for name in ['resources.assets','sharedassets0.assets','level0']:
 env=load(BASE/DATA/name,g);edits={}
 for obj in env.objects:
  rows=group[name].get(obj.path_id,[]);isfont=obj.path_id in font_ids[name];is_source=name=='sharedassets0.assets' and obj.path_id==800
  if not(rows or isfont or is_source or (name=='resources.assets' and obj.type.name=='TextAsset')):continue
  tree=obj.read_typetree();before=copy.deepcopy(tree)
  for r in rows:tree[r['field'][1:]]=r['target']
  if name=='resources.assets' and obj.type.name=='TextAsset':
   raw=tree['m_Script'];table=list(csv.reader(io.StringIO(raw.lstrip('\ufeff'))))
   if table and 'key' in table[0] and 'pt-BR' in table[0]:
    col=table[0].index('pt-BR');table[0][col]='ko';ki=table[0].index('key')
    for row in table[1:]:
     if not row or not row[ki] or row[ki].startswith(('#','//')):continue
     row[col]=ko[row[ki]]
    out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(table);tree['m_Script']=out.getvalue()
  if is_source:tree['m_FontData']=list(font_bytes);tree['m_FontNames']=['Noto Sans KR']
  if isfont:
   if name=='sharedassets0.assets' and obj.path_id==116083:
    assert not tree['m_GlyphTable'] and not tree['m_CharacterTable']
    tree['m_FallbackFontAssetTable']=[]
    for k in tree['m_FontFeatureTable']:tree['m_FontFeatureTable'][k]=[]
    tree['m_GetFontFeatures']=False
   else:
    ptr={'m_FileID':2 if name=='resources.assets' else 0,'m_PathID':116083}
    tree['m_FallbackFontAssetTable']=[ptr]+[v for v in tree['m_FallbackFontAssetTable'] if v!=ptr]
   tree['m_IsMultiAtlasTexturesEnabled']=True
  if tree!=before:
   fields=[k for k in tree if tree[k]!=before[k]];obj.save_typetree(tree);edits[obj.path_id]=(before,tree)
   changes.append(dict(file=name,path_id=obj.path_id,fields=fields))
 (candidate/DATA/name).write_bytes(preserve_save(BASE/DATA/name,env))
 # 후보를 새로 열어 각 변경 객체의 모든 필드를 대조합니다.
 checked=load(candidate/DATA/name,g);original=load(BASE/DATA/name,g)
 assert set(checked.file.objects)==set(original.file.objects)
 for obj in checked.objects:
  if obj.path_id in edits:assert obj.read_typetree()==edits[obj.path_id][1],(name,obj.path_id)
  else:assert obj.get_raw_data()==original.file.objects[obj.path_id].get_raw_data(),(name,obj.path_id)
 print(name,'객체 변경',len(edits),flush=True)
assembly=Path(DATA)/'Managed/Assembly-CSharp.dll';tool=WORK/'assembly_tool/AssemblyTool.dll'
for mode in ['patch','verify']:subprocess.run(['dotnet',str(tool),mode,str(BASE/assembly),str(candidate/assembly),str(WORK/'code_translation.json')],check=True)
files=[dict(path=p.relative_to(candidate).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(candidate.rglob('*')) if p.is_file()]
save(WORK/(build_id+'.json'),dict(candidate=str(candidate),baseline_sha256=sha((WORK/'baseline.json').read_bytes()),translation_sha256=sha((WORK/'ko.json').read_bytes()),files=files,changes=changes,table_count=len(ko),direct_count=len(direct),code_count=len(code),font_characters=len(chars),font_sha256=sha(font_bytes),static_validation='PASS'))
print('후보 완성',build_id,len(chars),'문자')

