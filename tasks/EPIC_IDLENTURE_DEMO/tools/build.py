"""원본 사본에서 번역 후보를 만들고 객체·필드 변경 경계를 대조합니다."""
from common import *
import copy,re,subprocess,io
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset
def get(tree,path):
    for k in path.strip('/').split('/'):tree=tree[int(k)] if isinstance(tree,list) else tree[k]
    return tree
def put(tree,path,value):
    keys=path.strip('/').split('/')
    for k in keys[:-1]:tree=tree[int(k)] if isinstance(tree,list) else tree[k]
    k=keys[-1];tree[int(k) if isinstance(tree,list) else k]=value
def controls(source,target):
    assert target.strip() or target==source
    assert collections.Counter(re.findall(r'\{[^{}]*\}',source))==collections.Counter(re.findall(r'\{[^{}]*\}',target))
    tags=r'</?(?:size|color|b|i|u|s|nobr|sprite|style|font|align|br)(?:=[^>]*| [^>]*)?>'
    assert re.findall(tags,source,re.I)==re.findall(tags,target,re.I),(source,target,'태그')
    assert re.findall(r'\r\n|\r|\n|\\n',source)==re.findall(r'\r\n|\r|\n|\\n',target),(source,target,'줄바꿈')
def main():
    build_id=sys.argv[1];candidate=ROOT/'build_candidate/EPIC_IDLENTURE_DEMO'/build_id
    assert not candidate.exists();shutil.copytree(BASE,candidate)
    translations=json.loads((WORK/'translation.json').read_text(encoding='utf8'));lookup={r['id']:r for r in translations}
    code=json.loads((WORK/'code_translation.json').read_text(encoding='utf8'));labels=json.loads((WORK/'runtime_labels.json').read_text(encoding='utf8'))
    debug=json.loads((WORK/'debug_translation.json').read_text(encoding='utf8'))
    for r in translations+code+debug:controls(r['source'],r['target'])
    chars={ord(c) for c in ''.join(r['target'] for r in translations+code+debug)+''.join(labels.values()) if c not in '\r\n\t\u200b'}|set(range(32,127))
    font=instantiateVariableFont(TTFont(ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf'),{'wght':400},inplace=True)
    assert chars<=set(font.getBestCmap()),chars-set(font.getBestCmap())
    options=subset.Options();options.name_IDs=['*'];options.name_languages=['*'];ss=subset.Subsetter(options=options);ss.populate(unicodes=chars);ss.subset(font)
    font_path=WORK/(build_id+'_NotoSansKR.ttf');font.save(font_path);font_bytes=font_path.read_bytes()
    expected=[];group=collections.defaultdict(lambda:collections.defaultdict(list))
    for r in json.loads((WORK/'translation_occurrences.json').read_text(encoding='utf8')):
        item=lookup[r['translation_id']];target=item['target'];reason=item['reason']
        if r['field']=='/Name':target=r['source'];reason='기술 이름은 저장 키에도 사용됨. 원본 값 보존, 화면 소비 3곳에서 한국어 변환'
        row=dict(r,target=target,reason=reason);expected.append(row)
        if target!=r['source']:group[r['file']][r['path_id']].append(row)
    g=generator();changes=[]
    for name in ('level0','level1','resources.assets','sharedassets0.assets','sharedassets1.assets'):
        e=load(BASE/DATA/name,g);edits={}
        for obj in e.objects:
            rows=group[name].get(obj.path_id,[])
            font_target=name=='resources.assets' and (obj.type.name=='Font' or obj.path_id in (5208,5212,6565,6655,6768,6862,6994,7146))
            if not rows and not font_target:continue
            t=obj.read_typetree();before=copy.deepcopy(t)
            for r in rows:assert get(t,r['field'])==r['source'];put(t,r['field'],r['target'])
            if font_target:
                if obj.type.name=='Font':t['m_FontData']=list(font_bytes);t['m_FontNames']=['Noto Sans KR']
                if obj.path_id==5208:
                    assert t['m_AtlasPopulationMode']==1 and not t['m_CharacterTable'];t['m_IsMultiAtlasTexturesEnabled']=True
                if obj.path_id==5212:t['m_fallbackFontAssets']=[{'m_FileID':0,'m_PathID':5208}]
                if obj.path_id in (6565,6655,6768,6862,6994,7146):
                    assert t['m_FontData']['m_Font']=={'m_FileID':2,'m_PathID':10102}
                    t['m_FontData']['m_Font']={'m_FileID':0,'m_PathID':673}
            if t!=before:
                obj.save_typetree(t);edits[obj.path_id]=t;changes.append(dict(file=name,path_id=obj.path_id,fields=[k for k in t if before[k]!=t[k]]))
        (candidate/DATA/name).write_bytes(preserve_save(BASE/DATA/name,e))
        reopened=load(candidate/DATA/name,g);original=load(BASE/DATA/name,g)
        assert set(reopened.file.objects)==set(original.file.objects)
        for obj in reopened.objects:
            if obj.path_id in edits:assert obj.read_typetree()==edits[obj.path_id]
            else:assert obj.get_raw_data()==original.file.objects[obj.path_id].get_raw_data()
        print(name,'변경 객체',len(edits),flush=True)
    assembly=Path(DATA)/'Managed/Assembly-CSharp.dll';tool=WORK/'assembly_tool/AssemblyTool.dll'
    subprocess.run(['dotnet',str(tool),'patch',str(BASE/assembly),str(candidate/assembly),str(WORK/'code_translation.json'),str(WORK/'runtime_labels.json')],check=True)
    sidecar=Path(str(candidate/assembly)+'.labels.json');shutil.move(str(sidecar),str(WORK/(build_id+'_code_calls.json')))
    subprocess.run(['dotnet',str(tool),'verify',str(BASE/assembly),str(candidate/assembly),str(WORK/'code_translation.json')],check=True)
    auxiliary=Path(DATA)/'Managed/StompyRobot.SRDebugger.dll'
    subprocess.run(['dotnet',str(tool),'literal_patch',str(BASE/auxiliary),str(candidate/auxiliary),str(WORK/'debug_translation.json')],check=True)
    subprocess.run(['dotnet',str(tool),'literal_verify',str(BASE/auxiliary),str(candidate/auxiliary),str(WORK/'debug_translation.json')],check=True)
    files=[dict(path=p.relative_to(candidate).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(candidate.rglob('*')) if p.is_file()]
    save(WORK/(build_id+'_expected.json'),expected);save(WORK/(build_id+'.json'),dict(candidate=str(candidate),baseline_sha256=sha((WORK/'baseline.json').read_bytes()),translation_sha256=sha((WORK/'translation.json').read_bytes()),files=files,changes=changes,font_characters=sorted(chars),font_sha256=sha(font_bytes)))
if __name__=='__main__':main()
