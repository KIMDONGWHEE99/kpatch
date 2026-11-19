"""한국어 표·직접 문구·글꼴을 적용하고 객체/필드 단위 기대 변경을 기록합니다."""
from common import *
from pathlib import Path
import json,copy,shutil,struct,collections,re,sys

CANDIDATE=ROOT/'build_candidate/THE_LOOPLER/ko_1.0.0_c04/game'
REPORT=WORK/'candidate_c04'

def field_set(tree,field,value):
    parts=field.split('/')[1:];current=tree
    for p in parts[:-1]:current=current[int(p)] if isinstance(current,list) else current[p]
    if isinstance(current,list):current[int(parts[-1])]=value
    else:current[parts[-1]]=value

def differences(a,b,path=''):
    if type(a)!=type(b):yield path,a,b
    elif isinstance(a,dict):
        assert set(a)==set(b),(path,set(a)^set(b))
        for key in a:yield from differences(a[key],b[key],path+'/'+key)
    elif isinstance(a,list):
        if len(a)!=len(b):yield path,a,b
        else:
            for i,(x,y) in enumerate(zip(a,b)):yield from differences(x,y,path+'/'+str(i))
    elif a!=b:yield path,a,b

def save_asset(env,dest):
    dest.write_bytes(env.file.save(packer='lz4'))

def build():
    if (REPORT/'build.json').exists():raise RuntimeError('기존 후보를 덮어쓰지 않습니다')
    REPORT.mkdir(parents=True,exist_ok=True);shutil.copytree(SOURCE,CANDIDATE,dirs_exist_ok=True)
    rows=json.loads((WORK/'review/classified_texts.json').read_text('utf-8'))
    pending=json.loads((WORK/'review/direct_pending.json').read_text('utf-8'))
    extras=json.loads((WORK/'translation_parts/direct_extra.json').read_text('utf-8'))
    extra_by_source={r['source']:extras[str(r['index'])] for r in pending}
    layout_fixes={'round and round it \ngoes':'돌고 또\n돌아갑니다','open\npitstop':'피트 스톱\n열기','exit \npitstop':'피트 스톱\n나가기','Disclaimer\n':'안내\n','round\n':'라운드\n','endless choices\n':'무한 선택지\n','inspect\ntrack':'트랙\n살펴보기'}
    for r in rows:
        if r['source'] in extra_by_source and r['classification']=='VISIBLE_TRANSLATE':r['translation']=extra_by_source[r['source']]
        if r['source'] in layout_fixes and r['classification']=='VISIBLE_TRANSLATE':r['translation']=layout_fixes[r['source']]
        if r['translation']==r['source']:
            r['classification']='VISIBLE_KEEP';r['reason']='언어 선택의 자칭·채널 기호·배율·예비 화면의 측정용 문자열·버전 표기'
    write_json(REPORT/'text_decisions.json',rows)
    direct=collections.defaultdict(list)
    for r in rows:
        if r['classification']=='VISIBLE_TRANSLATE' and '-korean(' not in r['id']:
            assert r['translation'] is not None,r
            direct[r['object_id']].append(r)
    canonical=json.loads((WORK/'translation_canonical.json').read_text('utf-8'));mapping={r['source']:r['translation'] for r in canonical}
    gen=generator();configure_references(gen);edits=[];boundaries=[];roundtrips=[]
    en_path=next((DATA/'StreamingAssets/aa/StandaloneWindows64').glob('localization-string-tables-english*'))
    en_env=UnityPy.load(str(en_path));en=next(o for o in en_env.objects if o.type.name=='MonoBehaviour').read_typetree()
    en_by_id={r['m_Id']:r for r in en['m_TableData']}
    for source in files():
        dest=CANDIDATE/source.relative_to(SOURCE);env=UnityPy.load(str(source));env.typetree_generator=gen;changed=False
        for obj in env.objects:
            key=f'{source.name}/{obj.assets_file.name}/{obj.path_id}'
            is_ko=source.name.startswith('localization-string-tables-korean') and obj.type.name=='MonoBehaviour'
            is_font=obj.type.name=='MonoBehaviour' and ((obj.assets_file.name=='sharedassets0.assets' and obj.path_id in range(11015,11020)) or (obj.assets_file.name=='resources.assets' and obj.path_id in (1443,1444)) or source.name.startswith('defaultlocalgroup') or source.name.startswith('localization-shared-fonts'))
            is_shared=source.name=='localization-assets-shared_assets_all.bundle' and obj.path_id==3335046104275354130
            is_language=source.name=='data.unity3d' and obj.assets_file.name=='level0' and obj.path_id in (23561,23325,25379,41316,46819)
            if key not in direct and not is_ko and not is_font and not is_shared and not is_language:continue
            before=read_tree(obj);after=copy.deepcopy(before)
            if is_ko:
                assert set(en_by_id)=={r['m_Id'] for r in after['m_TableData']}
                for r in after['m_TableData']:
                    e=en_by_id[r['m_Id']];r['m_Localized']=mapping[e['m_Localized']]
                    r['m_Metadata']=copy.deepcopy(e['m_Metadata'])
                after['m_Metadata']=copy.deepcopy(en['m_Metadata']);after['references']=copy.deepcopy(en['references'])
            for r in direct.get(key,[]):field_set(after,r['field'],r['translation'])
            if is_language:
                # 원본에 존재하는 태극기 버튼을 현재 설정 화면의 언어 목록으로 옮깁니다.
                if obj.path_id==23561:after['m_Children']=[p for p in after['m_Children'] if p['m_PathID']!=25379]
                elif obj.path_id==23325:after['m_Children'].append({'m_FileID':0,'m_PathID':25379})
                elif obj.path_id==25379:
                    after['m_Father']={'m_FileID':0,'m_PathID':23325}
                    after['m_AnchorMin']={'x':0.0,'y':1.0};after['m_AnchorMax']={'x':0.0,'y':1.0}
                    after['m_AnchoredPosition']={'x':47.0,'y':-90.0};after['m_SizeDelta']={'x':30.0,'y':24.0};after['m_Pivot']={'x':0.5,'y':0.5}
                elif obj.path_id==41316:
                    after['m_Navigation']['m_Mode']=3
                    for direction in ('Up','Down','Left','Right'):after['m_Navigation']['m_SelectOn'+direction]={'m_FileID':0,'m_PathID':0}
                    after['m_OnClick']['m_PersistentCalls']['m_Calls']=after['m_OnClick']['m_PersistentCalls']['m_Calls'][1:]
                elif obj.path_id==46819:after['canvasGroup']={'m_FileID':0,'m_PathID':0}
            if is_shared:
                # Steam 업적 표시 키 3개의 잘못된 끝 줄바꿈을 바로잡습니다. 숫자 ID는 유지합니다.
                for entry in after['m_Entries']:
                    if entry['m_Key'] in ('NEW_ACHIEVEMENT_8_10_NAME\n','NEW_ACHIEVEMENT_8_10_DESC\n','NEW_ACHIEVEMENT_8_11_NAME\n'):entry['m_Key']=entry['m_Key'].rstrip('\n')
            if is_font and 'm_CharacterTable' in after:
                if after['m_Name']=='LanaPixel SDF':
                    # 원본 SDF에 남은 다른 서체의 세로 치수를 실제 LanaPixel의 90pt 치수로 교정합니다.
                    metrics=json.loads((EXTRACT/'trees/data.unity3d/sharedassets0.assets/11017.json').read_text('utf-8'))['m_FaceInfo']
                    after['m_FaceInfo']=copy.deepcopy(metrics)
                if after['m_AtlasPopulationMode']==1:after['m_IsMultiAtlasTexturesEnabled']=1
                if obj.assets_file.name=='sharedassets0.assets':
                    if obj.path_id==11018:after['m_FallbackFontAssetTable']=[]
                    else:after['m_FallbackFontAssetTable']=[{'m_FileID':0,'m_PathID':11018}]
                elif obj.assets_file.name=='resources.assets':
                    assert obj.assets_file.externals[1].name=='sharedassets0.assets'
                    after['m_FallbackFontAssetTable']=[{'m_FileID':2,'m_PathID':11018}]
                elif source.name.startswith('defaultlocalgroup'):
                    if obj.path_id==-6961043223238358834:after['m_FallbackFontAssetTable']=[]
                    else:after['m_FallbackFontAssetTable']=[{'m_FileID':0,'m_PathID':-6961043223238358834}]
                # 영어 전용 공유 글꼴 묶음은 한국어 스타일에서 사용하지 않습니다.
            if obj.type.name=='MonoBehaviour' and 'm_FontData' in after and key in direct and any('\uac00'<=c<='\ud7a3' for r in direct[key] for c in r['translation']):
                external=0 if obj.assets_file.name=='sharedassets0.assets' else next(i+1 for i,x in enumerate(obj.assets_file.externals) if x.name=='sharedassets0.assets')
                after['m_FontData']['m_Font']={'m_FileID':external,'m_PathID':210}
            ds=list(differences(before,after))
            if not ds:continue
            raw=obj.get_raw_data();same=obj.save_typetree(before);assert same==raw,(key,len(raw),len(same))
            obj.set_raw_data(raw);roundtrips.append({'id':key,'sha256':__import__('hashlib').sha256(raw).hexdigest(),'status':'PASS'})
            obj.save_typetree(after);changed=True
            for f,b,a in ds:edits.append({'id':key+f,'object_id':key,'file':str(source.relative_to(SOURCE)),'field':f,'before':b,'after':a,'source_file_sha256':sha(source)})
        if changed:
            save_asset(env,dest);boundaries.append({'file':str(source.relative_to(SOURCE)),'original_sha256':sha(source),'candidate_sha256':sha(dest)})
            print('asset',source.name,'saved',flush=True)
    runtime=json.loads((WORK/'translation_parts/runtime_extra.json').read_text('utf-8'))
    metadata=SOURCE/'The Loopler_Data/il2cpp_data/Metadata/global-metadata.dat';original=metadata.read_bytes()
    assert struct.unpack_from('<II',original)==(0xfab11baf,39)
    # 메타데이터 39는 (시작 위치, 바이트 수, 항목 수)의 3항 머리말과
    # 다음 문자열 시작 위치로 길이를 계산하는 32비트 위치 표를 사용합니다.
    table,size,count,pool,poolsize,poolcount=struct.unpack_from('<6I',original,8)
    assert size==count*4
    offsets=struct.unpack_from('<'+str(count)+'I',original,table)
    assert offsets[0]==0 and offsets[-1]==poolsize and list(offsets)==sorted(offsets)
    newtable=bytearray();newpool=bytearray();literal_edits=[]
    seen=set()
    for i in range(count):
        offset=offsets[i];end=offsets[i+1] if i+1<count else poolsize;raw=original[pool+offset:pool+end];source=raw.decode('utf-8')
        target=runtime.get(source,source);encoded=target.encode('utf-8');newtable.extend(struct.pack('<I',len(newpool)));newpool.extend(encoded)
        if target!=source:literal_edits.append({'index':i,'before':source,'after':target});seen.add(source)
    assert seen==set(runtime),(set(runtime)-seen)
    output=bytearray(original);output.extend(b'\0'*((-len(output))%8));start=len(output)
    output.extend(newtable);output.extend(newpool)
    struct.pack_into('<6I',output,8,start,len(newtable),count,start+len(newtable),len(newpool),poolcount)
    (CANDIDATE/metadata.relative_to(SOURCE)).write_bytes(output)
    write_json(REPORT/'asset_edits.json',edits);write_json(REPORT/'asset_noop_roundtrips.json',roundtrips);write_json(REPORT/'literal_edits.json',literal_edits)
    write_json(REPORT/'build.json',{'candidate':str(CANDIDATE),'baseline_sha256':sha(EXTRACT/'baseline.json'),'translation_sha256':sha(WORK/'translation_canonical.json'),'direct_translation_sha256':sha(WORK/'translation_parts/direct_extra.json'),'runtime_translation_sha256':sha(WORK/'translation_parts/runtime_extra.json'),'files':boundaries,'asset_fields':len(edits),'literal_changes':len(literal_edits),'status':'CANDIDATE_NOT_VALIDATED'})
    print('fields',len(edits),'literals',len(literal_edits))

if __name__=='__main__':build()
