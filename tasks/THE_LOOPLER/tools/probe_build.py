"""소규모 글꼴·재저장 시험 사본을 만들고 모든 변경 위치를 기록합니다."""
from common import *
import json, shutil, struct, io
from fontTools.ttLib import TTFont

QA = WORK / 'risk_probe/game'
def save_bundle(env, dest):
    data = env.file.save(packer='lz4')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    check = UnityPy.load(str(dest))
    assert {(o.assets_file.name,o.path_id,o.type.name) for o in check.objects} == {(o.assets_file.name,o.path_id,o.type.name) for o in env.objects}

if __name__ == '__main__':
    assert not (QA.parent/'overrides.json').exists(), '완성된 검수 사본 보존'
    shutil.copytree(SOURCE, QA, dirs_exist_ok=True)
    reports=[]
    data_path=QA/'The Loopler_Data/data.unity3d'
    env=UnityPy.load(str(data_path))
    player=next(o for o in env.objects if o.type.name=='PlayerSettings')
    raw=player.get_raw_data()
    pos = raw.index(b'The Loopler')
    assert raw[pos-4:pos] == struct.pack('<I', 11)
    assert player.read_typetree(check_read=False)['productName'] == 'The Loopler'
    player.set_raw_data(raw[:pos] + b'LooplerKQA1' + raw[pos+11:])
    save_bundle(env,data_path)
    reports.append({'asset':'globalgamemanagers/1','field':'productName','before':'The Loopler','after':'LooplerKQA1'})
    code=json.loads((EXTRACT/'code_map.json').read_text('utf-8'))
    binary=bytearray((QA/'GameAssembly.dll').read_bytes())
    def method(cls,name):
        t=next(t for t in code if t['type']==cls)
        m=next(m for m in t['methods'] if m['name']==name)
        a=next(a['fields'] for a in m['attributes'] if a['type'].endswith('AddressAttribute'))
        return m, {k:int(v,16) for k,v in a.items()}
    def patch(cls,name,new):
        m,a=method(cls,name)
        offset=a['Offset'];before=bytes(binary[offset:offset+len(new)])
        binary[offset:offset+len(new)]=new
        reports.append({'method':m['fullName'],'offset':offset,'rva':a['RVA'],'before':before.hex(),'after':new.hex()})
    patch('SteamManager','Awake',b'\xc3')
    patch('SteamManager','get_Initialized',b'\x31\xc0\xc3')
    patch('RunAnalyticsReporter','Bootstrap',b'\xc3')
    patch('RunAnalyticsReporter','InitializeAnalytics',b'\xc3')
    patch('RunAnalyticsReporter','RequestDataCollectionEnabled',b'\xc3')
    _,src=method('UnityEngine.Application','get_persistentDataPath')
    _,dst=method('UnityEngine.Application','get_dataPath')
    patch('UnityEngine.Application','get_persistentDataPath',b'\xe9'+struct.pack('<i',dst['RVA']-src['RVA']-5))
    (QA/'GameAssembly.dll').write_bytes(binary)
    bundles=QA/'The Loopler_Data/StreamingAssets/aa/StandaloneWindows64'
    font_bundle=next(bundles.glob('defaultlocalgroup*'))
    env=UnityPy.load(str(font_bundle))
    font_report=[]
    for obj in env.objects:
        if obj.type.name=='Font':
            t=obj.read_typetree();raw=bytes((v&255 for v in t['m_FontData']))
            f=TTFont(io.BytesIO(raw));cmap=f.getBestCmap()
            font_report.append({'path_id':obj.path_id,'name':t['m_Name'],'characters':len(cmap),'hangul':sum(0xac00<=x<=0xd7a3 for x in cmap),'probe_missing':sorted(set(map(ord,'시작설정종료새주행계속'))-set(cmap))})
        elif obj.type.name=='MonoBehaviour':
            t=obj.read_typetree()
            if 'm_CharacterTable' in t:
                t['m_IsMultiAtlasTexturesEnabled']=1
                obj.save_typetree(t)
    save_bundle(env,font_bundle)
    en_bundle=next(bundles.glob('localization-string-tables-english*'))
    env=UnityPy.load(str(en_bundle));obj=next(o for o in env.objects if o.type.name=='MonoBehaviour')
    t=obj.read_typetree()
    mapping={'PLAY':'시작','SETTINGS':'설정','QUIT':'종료','NEW RUN':'새 주행','CONTINUE':'계속'}
    for row in t['m_TableData']:
        if row['m_Localized'] in mapping:row['m_Localized']=mapping[row['m_Localized']]
    obj.save_typetree(t);save_bundle(env,en_bundle)
    # 시험에서 영어 슬롯에 한국어 스타일을 연결합니다. 정식 후보에는 포함하지 않습니다.
    style_bundle=next(bundles.glob('localization-assets-english*'))
    env=UnityPy.load(str(style_bundle));obj=next(o for o in env.objects if o.type.name=='MonoBehaviour')
    t=obj.read_typetree();original=dict(t)
    kt=json.loads(next((EXTRACT/'probe').glob('localization-assets-korean*')).read_text('utf-8'))
    print('STYLE_EXT', [(e.path) for e in obj.assets_file.externals],flush=True)
    # 원래 영어 스타일의 참조 파일을 기존 한국어 글꼴 묶음으로 연결합니다.
    ko_env=UnityPy.load(str(next(bundles.glob('localization-assets-korean*'))))
    ko_obj=next(o for o in ko_env.objects if o.type.name=='MonoBehaviour')
    t['font']=kt['font'];t['switchBefore']=1;t['autoSize']=1
    obj.assets_file.externals=ko_obj.assets_file.externals
    obj.save_typetree(t);save_bundle(env,style_bundle)
    write_json(WORK/'risk_probe/overrides.json',reports)
    write_json(WORK/'risk_probe/font_probe.json',font_report)
    print(json.dumps(font_report,ensure_ascii=False))
    overlay=WORK/'risk_probe/overlay';overlay.mkdir(parents=True)
    for p in [font_bundle,en_bundle,style_bundle]:shutil.copy2(p,overlay/p.name)
