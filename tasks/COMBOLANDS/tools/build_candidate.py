"""원본 사본에서 위치가 확정된 번역과 글꼴만 적용합니다."""
from common import *
from collections import defaultdict
import shutil,subprocess,copy
from fontTools.ttLib import TTFont

def remap_glyphs(tree,font):
    # 원래 글자 그림·폭은 유지하되, 동적 생성에 사용할 새 글꼴의 번호와 맞춥니다.
    if not tree['m_CharacterTable']:
        assert not tree['m_GlyphTable']
        # 빈 동적 글꼴의 옛 글자 간격 표는 새 글꼴에서 다시 생성해야 합니다.
        for key in tree['m_FontFeatureTable']:tree['m_FontFeatureTable'][key]=[]
        return
    cmap=font.getBestCmap();mapping={};used=set()
    for char in tree['m_CharacterTable']:
        old=char['m_GlyphIndex'];u=char['m_Unicode']
        if old not in mapping:
            new=font.getGlyphID(cmap[u]) if u in cmap else old+65536
            if new in used:new=old+65536
            assert new not in used
            mapping[old]=new;used.add(new)
        char['m_GlyphIndex']=mapping[old]
    for glyph in tree['m_GlyphTable']:glyph['m_Index']=mapping[glyph['m_Index']]
    def update(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='m_GlyphIndex':value[key]=mapping[item]
                else:update(item)
        elif isinstance(value,list):
            for item in value:update(item)
    update(tree['m_FontFeatureTable'])

def at(tree,path):
    for key in path:tree=tree[key]
    return tree

def assign(tree,path,value):
    for key in path[:-1]:tree=tree[key]
    tree[path[-1]]=value

def main():
    candidate_id=sys.argv[1]
    out=ROOT/'build_candidate/COMBOLANDS'/candidate_id/'game'
    assert not out.exists(),out
    canon=json.loads((WORK/'canonical_translation.json').read_text(encoding='utf8'))
    byfile=defaultdict(lambda:defaultdict(list))
    for r in canon:byfile[r['file']][r['path_id']].append(r)
    shutil.copytree(SOURCE,out)
    font_path=WORK/'NotoSansKR-SemiBold.ttf';font_bytes=font_path.read_bytes();font=TTFont(font_path)
    g=generator();report=[]
    material_fixes={'level0':{3219:(2,15),3253:(2,16)},'level3':{2943:(3,16),3008:(4,11),3011:(4,11),3091:(3,16)},'sharedassets0.assets':{854:(0,16),976:(0,16)}}
    for p in containers():
        file_hash=sha(p)
        env=UnityPy.load(str(p));env.typetree_generator=g
        sources=[o.path_id for o in env.objects if o.type.name=='Font']
        atlas_ids=set()
        for font_obj in env.objects:
            if font_obj.type.name=='MonoBehaviour' and script(font_obj)[0]=='TMP_FontAsset':
                font_tree=font_obj.read_typetree()
                for ref in font_tree['m_AtlasTextures']:
                    assert ref['m_FileID']==0
                    if ref['m_PathID']:atlas_ids.add(ref['m_PathID'])
        changed=[]
        for obj in env.objects:
            rows=byfile[p.name].get(obj.path_id,[])
            cls=script(obj)[0] if obj.type.name=='MonoBehaviour' else obj.type.name
            fix_material=obj.path_id in material_fixes.get(p.name,{})
            if not rows and cls not in ['Font','TMP_FontAsset'] and obj.path_id not in atlas_ids and not fix_material:continue
            tree=obj.read_typetree();obj.save_typetree(tree)
            assert obj.data==obj.get_raw_data(),(p.name,obj.path_id,'무변경 재저장')
            paths=[]
            if fix_material:
                # 원본의 잘못된 다른 글꼴 재질 연결을 실제 글꼴의 기본 재질에 맞춥니다.
                file_id,path_id=material_fixes[p.name][obj.path_id]
                assert tree['m_sharedMaterial']=={'m_FileID':file_id,'m_PathID':path_id}
                assert tree['m_fontAsset']['m_PathID']==582
                tree['m_sharedMaterial']={'m_FileID':tree['m_fontAsset']['m_FileID'],'m_PathID':2}
                paths.append(['m_sharedMaterial'])
            for r in rows:
                assert r['file_sha256']==file_hash
                assert at(tree,r['field'])==r['source'],r
                if r['target']!=r['source']:
                    assign(tree,r['field'],r['target']);paths.append(r['field'])
            if cls=='Font':tree['m_FontData']=list(font_bytes);paths.append(['m_FontData'])
            if obj.path_id in atlas_ids:
                assert cls=='Texture2D'
                # 읽기 가능한 동적 글꼴은 픽셀을 CPU에서도 읽어야 하므로 본문에 저장합니다.
                if tree['m_StreamData']['size']:
                    image_bytes=obj.read().get_image_data()
                    assert len(image_bytes)==tree['m_CompleteImageSize']
                    tree['image data']=bytes(image_bytes);paths.append(['image data'])
                    tree['m_StreamData']={'offset':0,'size':0,'path':''};paths.append(['m_StreamData'])
                if not tree['m_IsReadable']:tree['m_IsReadable']=True;paths.append(['m_IsReadable'])
            if cls=='TMP_FontAsset':
                before=copy.deepcopy(tree)
                remap_glyphs(tree,font)
                for key in ['m_GlyphTable','m_CharacterTable','m_FontFeatureTable']:
                    if tree[key]!=before[key]:paths.append([key])
                assert sources
                if not tree['m_SourceFontFile']['m_PathID']:
                    tree['m_SourceFontFile']={'m_FileID':0,'m_PathID':sources[0]};paths.append(['m_SourceFontFile'])
                tree['m_AtlasPopulationMode']=1;paths.append(['m_AtlasPopulationMode'])
                tree['m_IsMultiAtlasTexturesEnabled']=1;paths.append(['m_IsMultiAtlasTexturesEnabled'])
                if not tree['m_FaceInfo']['m_UnitsPerEM']:
                    tree['m_FaceInfo']['m_UnitsPerEM']=1000;paths.append(['m_FaceInfo','m_UnitsPerEM'])
            if paths:
                obj.save_typetree(tree)
                changed.append(dict(path_id=obj.path_id,cls=cls,fields=paths,source_sha256=hashlib.sha256(obj.get_raw_data()).hexdigest(),target_sha256=hashlib.sha256(obj.data).hexdigest()))
        if changed:
            target=out/'Combolands_Data'/p.name;target.write_bytes(env.file.save())
            report.append(dict(file=p.name,source_sha256=sha(p),target_sha256=sha(target),objects=changed))
    assembly=out/'Combolands_Data/Managed/Assembly-CSharp.dll'
    support=WORK/'korean_support/Combolands.KoreanSupport.dll'
    shutil.copy2(support,assembly.parent/support.name)
    subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'patch',str(DATA/'Managed/Assembly-CSharp.dll'),str(assembly),str(WORK/'canonical_code.json'),str(support)],check=True)
    subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'patch',str(DATA/'Managed/AeLa.EasyFeedback.dll'),str(assembly.parent/'AeLa.EasyFeedback.dll'),str(WORK/'canonical_feedback.json')],check=True)
    save_json(out.parent/'build.json',dict(candidate_id=candidate_id,canonical_sha256=sha(WORK/'canonical_translation.json'),code_sha256=sha(WORK/'canonical_code.json'),font_sha256=sha(font_path),files=report,assembly_sha256=sha(assembly),support_sha256=sha(support),feedback_sha256=sha(assembly.parent/'AeLa.EasyFeedback.dll')))
    print(out)

if __name__=='__main__':main()
