"""다시 연 후보를 원본·공식 번역과 독립적으로 대조합니다."""
from common import *
from build_candidate import at,assign
from prepare_translation import validate_tokens
from collections import defaultdict
from fontTools.ttLib import TTFont
import io,subprocess,copy

def main():
    folder=ROOT/'build_candidate/COMBOLANDS'/sys.argv[1];out=folder/'game';g=generator()
    build=json.loads((folder/'build.json').read_text(encoding='utf8'))
    rows=json.loads((WORK/'canonical_translation.json').read_text(encoding='utf8'))
    assert build['canonical_sha256']==sha(WORK/'canonical_translation.json')
    byfile=defaultdict(list)
    for row in rows:byfile[row['file']].append(row)
    allowed={f['file']:{o['path_id']:o['fields'] for o in f['objects']} for f in build['files']}
    seen=0;fonts=[];objects_checked=0;changes=0;noop=0
    required=set(json.loads((WORK/'required_characters.json').read_text(encoding='utf8')))
    # 줄바꿈·공백·폭 없는 공백은 표시할 글리프가 필요하지 않습니다.
    required-=set([0x200b,0xfeff])
    for p in containers():
        original=UnityPy.load(str(p));original.typetree_generator=g
        candidate=UnityPy.load(str(out/'Combolands_Data'/p.name));candidate.typetree_generator=g
        a=original.file.objects;b=candidate.file.objects
        assert list(a)==list(b),(p.name,'객체 삭제·순서 변경')
        for row in byfile[p.name]:
            assert row['source_sha256']==hashlib.sha256(row['source'].encode()).hexdigest()
            expected=row['target'];actual=at(b[row['path_id']].read_typetree(),row['field'])
            assert actual==expected,(p.name,row['path_id'],row['field'],'위치별 번역 불일치')
            assert actual.strip(),(p.name,row['path_id'],'빈 번역')
            validate_tokens(row['source'],actual);seen+=1
        for pid,obj in a.items():
            objects_checked+=1
            assert obj.type==b[pid].type
            if obj.get_raw_data()==b[pid].get_raw_data():noop+=1;continue
            assert pid in allowed.get(p.name,{}),(p.name,pid,'허용하지 않은 객체 변경')
            t=obj.read_typetree();u=b[pid].read_typetree()
            for path in allowed[p.name][pid]:assign(u,path,at(t,path))
            assert t==u,(p.name,pid,'허용 필드 밖 변경')
            changes+=1
        for obj in candidate.objects:
            if obj.type.name=='Font':
                data=obj.read_typetree();ft=TTFont(io.BytesIO(bytes(data['m_FontData'])))
                cmap=ft.getBestCmap();missing=required-set(cmap)
                assert not missing,(p.name,obj.path_id,sorted(missing))
                fonts.append(dict(file=p.name,path_id=obj.path_id,type='Font',font_sha256=hashlib.sha256(bytes(data['m_FontData'])).hexdigest(),required=len(required),missing=[]))
            elif obj.type.name=='MonoBehaviour' and script(obj)[0]=='TMP_FontAsset':
                t=obj.read_typetree();assert t['m_AtlasPopulationMode']==1 and t['m_IsMultiAtlasTexturesEnabled']
                old=a[obj.path_id].read_typetree()
                glyphs={v['m_Index']:v for v in t['m_GlyphTable']};old_glyphs={v['m_Index']:v for v in old['m_GlyphTable']}
                assert len(glyphs)==len(t['m_GlyphTable'])==len(old_glyphs)
                assert len(t['m_CharacterTable'])==len(old['m_CharacterTable'])
                sf=TTFont(io.BytesIO(bytes(b[t['m_SourceFontFile']['m_PathID']].read_typetree()['m_FontData'])))
                cmap=sf.getBestCmap();index_map={}
                for ca,cb in zip(old['m_CharacterTable'],t['m_CharacterTable']):
                    u=cb['m_Unicode'];expected=sf.getGlyphID(cmap[u]) if u in cmap else None
                    assert cb['m_GlyphIndex']==expected or cb['m_GlyphIndex']>=65536
                    if cb['m_GlyphIndex']>=65536 and expected is not None:assert expected in glyphs
                    x=copy.deepcopy(cb);x['m_GlyphIndex']=ca['m_GlyphIndex'];assert x==ca
                    x=copy.deepcopy(glyphs[cb['m_GlyphIndex']]);x['m_Index']=ca['m_GlyphIndex'];assert x==old_glyphs[ca['m_GlyphIndex']],(p.name,obj.path_id,u,'기존 글자 그림·폭 변경')
                    index_map[cb['m_GlyphIndex']]=ca['m_GlyphIndex']
                def restore_features(value):
                    if isinstance(value,dict):
                        for k,v in value.items():
                            if k=='m_GlyphIndex':value[k]=index_map[v]
                            else:restore_features(v)
                    elif isinstance(value,list):
                        for v in value:restore_features(v)
                feature=copy.deepcopy(t['m_FontFeatureTable'])
                if old['m_CharacterTable']:
                    restore_features(feature);assert feature==old['m_FontFeatureTable']
                else:assert not any(feature.values()),'빈 글꼴에 옛 글자 번호의 간격 표 잔존'
                assert t['m_SourceFontFile']['m_PathID'] in b and b[t['m_SourceFontFile']['m_PathID']].type.name=='Font' and t['m_SourceFontFile']['m_FileID']==0
                for ref in t['m_AtlasTextures']:
                    assert ref['m_FileID']==0 and ref['m_PathID'] in b
                    texture=b[ref['m_PathID']].read_typetree()
                    assert texture['m_IsReadable'],(p.name,obj.path_id,'동적 아틀라스가 읽기 불가')
                    assert not texture['m_StreamData']['size'] and len(texture['image data'])==texture['m_CompleteImageSize']>0,(p.name,obj.path_id,'CPU 글꼴 픽셀 누락')
                    assert bytes(texture['image data'])==a[ref['m_PathID']].read().get_image_data(),(p.name,obj.path_id,'글꼴 픽셀 변경')
                assert t['m_FaceInfo']['m_UnitsPerEM']>0
                fonts.append(dict(file=p.name,path_id=obj.path_id,type='TMP_FontAsset',config=t))
        print(p.name,flush=True)
    assert seen==len(rows)
    code=json.loads((WORK/'canonical_code.json').read_text(encoding='utf8'))+json.loads((WORK/'canonical_feedback.json').read_text(encoding='utf8'))
    helper_counts=defaultdict(int)
    for name in ['Assembly-CSharp.dll','AeLa.EasyFeedback.dll']:
        for root,label in [(DATA,'original'),(out/'Combolands_Data','candidate')]:
            subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'dump',str(root/'Managed'/name),str(folder/f'{name}_{label}_il.json')],check=True)
            subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'metadata',str(root/'Managed'/name),str(folder/f'{name}_{label}_metadata.json')],check=True)
        assert (folder/f'{name}_original_metadata.json').read_bytes()==(folder/f'{name}_candidate_metadata.json').read_bytes(),(name,'클래스·필드·메서드 구조 변경')
        left=json.loads((folder/f'{name}_original_il.json').read_text(encoding='utf8'));right=json.loads((folder/f'{name}_candidate_il.json').read_text(encoding='utf8'))
        assert len(left)==len(right)
        expect={(r['method'],r['offset']):r for r in code if r['file']=='Managed/'+name};matched=set()
        for a,b in zip(left,right):
            assert a['method']==b['method']
            kept=[]
            for n,j in enumerate(b['instructions']):
                if j['op']=='call' and j['operand']=='System.Void CombolandsKorean.KoreanSupport::SetMechanicSprite(UnityEngine.UI.Image,UnityEngine.Sprite)':
                    assert a['method']=='System.Void UI.EndingScreens.VictoryScreenGenericUnlockPopup::Init(Entities.Data.GameMechanicUnlock)'
                    helper_counts[j['operand']]+=1
                    j['op']='callvirt';j['operand']='System.Void UnityEngine.UI.Image::set_sprite(UnityEngine.Sprite)';kept.append(j)
                elif j['op']=='call' and j['operand'] and 'CombolandsKorean.KoreanSupport::' in j['operand']:
                    if j['operand']=='System.Void CombolandsKorean.KoreanSupport::Initialize()':
                        assert a['method']=='System.Void Shared.SceneOrchestrator::Start()' and n==len(b['instructions'])-2
                    else:
                        assert j['operand']=='System.String CombolandsKorean.KoreanSupport::CategoryName(System.String)'
                        assert any(t in a['method'] for t in ['Utils.BuildingCategoryVisualization::CircleCategories(', 'UI.EndingScreens.UnlockScreenGuild::EditorInit()'])
                        assert '::ToString()' in b['instructions'][n-1]['operand'] and '::set_text(System.String)' in b['instructions'][n+1]['operand']
                    helper_counts[j['operand']]+=1
                else:kept.append(j)
            assert len(a['instructions'])==len(kept)
            remap={j['offset']:i['offset'] for i,j in zip(a['instructions'],kept)}
            for j in kept:
                j['offset']=remap[j['offset']]
                if j['operand'] and j['operand'].startswith('IL_') and (j['op'].startswith(('br','beq','bne','bgt','bge','blt','ble','leave')) or j['op']=='switch'):
                    j['operand']=','.join('IL_'+format(remap[int(v[3:],16)],'04X') for v in j['operand'].split(','))
            for h in b['handlers']:
                for k in ['start','end','handler','handlerEnd']:
                    if h[k] is not None:h[k]=remap[h[k]]
            b['instructions']=kept
            for i,j in zip(a['instructions'],b['instructions']):
                key=(a['method'],i['offset'])
                if key in expect:
                    assert i['operand']==expect[key]['source'] and j['operand']==expect[key]['target']
                    j['operand']=i['operand'];matched.add(key)
            assert a==b,(a['method'],'허용하지 않은 코드 변경')
        assert matched==set(expect)
    assert sorted(helper_counts.values())==[1,1,2],helper_counts
    # 바뀐 파일의 경계를 원본 전체 목록과 대조합니다.
    baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf8'))['files']
    expected_files=set(allowed)|{'Managed/Assembly-CSharp.dll','Managed/AeLa.EasyFeedback.dll'}
    actual_changed=[]
    for row in baseline:
        p=out/row['path'];assert p.exists()
        if sha(p)!=row['sha256']:
            rel=p.relative_to(out/'Combolands_Data').as_posix();assert rel in expected_files,rel
            actual_changed.append(rel)
    support=out/'Combolands_Data/Managed/Combolands.KoreanSupport.dll'
    assert sha(support)==build['support_sha256']==sha(WORK/'korean_support/Combolands.KoreanSupport.dll')
    assert {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}=={r['path'] for r in baseline}|{support.relative_to(out).as_posix()}
    save_json(folder/'font_audit.json',fonts)
    save_json(folder/'static_validation.json',dict(status='PASS',canonical_sha256=sha(WORK/'canonical_translation.json'),locations_checked=seen,objects_checked=objects_checked,unchanged_objects=noop,changed_objects=changes,code_locations=len(code),changed_files=actual_changed,missing_glyphs=0))
    print('PASS',seen,objects_checked,changes)

if __name__=='__main__':main()
