"""26365992 업데이트의 사본·차이·번역·배포 근거를 작성합니다."""
import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/THE_HORDE_OF_GORAK/update_20261104'
SOURCE = ROOT / 'source_original/THE_HORDE_OF_GORAK/steam_26365992'
GAME = Path('D:/steam/steamapps/common/The Horde of Gorak')
OLD_ZIP = ROOT / 'release_output/THE_HORDE_OF_GORAK_KOREAN_PATCH_1.0.0_r1.zip'
BACKUP = Path('C:/Users/PC/AppData/Local/TheHordeOfGorakKoreanPatch/working_private/35633642EDCA0C0A/build_26336311')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def baseline():
    assert not SOURCE.exists() and not WORK.exists()
    WORK.mkdir(parents=True)
    with zipfile.ZipFile(OLD_ZIP) as archive:
        manifest = json.loads(archive.read('manifest.json'))
    assert sha(OLD_ZIP) == '22b94d117534760284ae2d2d0f310d646465f0e21cd6058c3ff05f67a5981d2f'
    changes = {x['path']: (i, x) for i, x in enumerate(manifest['changes'])}
    assert {p.relative_to(GAME).as_posix() for p in GAME.rglob('*') if p.is_file()} == {r['path'] for r in manifest['baseline']}
    records = []
    installed = []
    for row in manifest['baseline']:
        rel = row['path']
        current = GAME / rel
        digest = sha(current)
        selected = current
        state = 'original'
        if digest != row['sha256']:
            if rel in changes and digest == changes[rel][1]['patched_sha256']:
                selected = BACKUP / 'cache' / str(changes[rel][0]) / 'original'
                assert sha(selected) == row['sha256']
                state = 'old_patch'
            else:
                assert rel == 'THOG.dat', ('예상 밖 변경', rel)
                state = 'updated_original'
        target = SOURCE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(selected, target)
        assert sha(selected) == sha(target) and sha(current) == digest
        records.append({'path': rel, 'size': target.stat().st_size, 'sha256': sha(target)})
        installed.append({'path': rel, 'size': current.stat().st_size, 'sha256': digest, 'state': state})
    old_dat = WORK / 'previous_original/THOG.dat'
    old_dat.parent.mkdir()
    original_cache = BACKUP / 'cache' / str(changes['THOG.dat'][0]) / 'original'
    assert sha(original_cache) == changes['THOG.dat'][1]['original_sha256']
    shutil.copy2(original_cache, old_dat)
    save(WORK / 'baseline_manifest.json', {'game_id': 'THE_HORDE_OF_GORAK', 'build_id': 'steam_26365992', 'steam_build': '26365992', 'files': records, 'copy_verification': 'PASS'})
    save(WORK / 'installed_before.json', installed)
    save(WORK / 'previous_package_manifest.json', manifest)
    shutil.copy2('D:/steam/steamapps/appmanifest_4911050.acf', WORK / 'steam_manifest.acf')
    print(json.dumps({'files':len(records),'updated':[r['path'] for r in installed if r['state']=='updated_original'],'remaining_old_patch_files':sum(r['state']=='old_patch' for r in installed),'status':'PASS'}))


def compare():
    from dat_container import DatFile
    old = DatFile.load(WORK / 'previous_original/THOG.dat')
    new = DatFile.load(SOURCE / 'THOG.dat')
    rows=[]
    for loc in sorted(set(old.by_location)|set(new.by_location)):
        a,b=old.by_location.get(loc),new.by_location.get(loc)
        if a is None or b is None or a.decoded != b.decoded:
            rows.append({'location':loc,'old_bytes':len(a.decoded) if a else None,'new_bytes':len(b.decoded) if b else None})
    objects=[]
    for key in range(max(len(old.objects),len(new.objects))):
        a=old.objects[key] if key<len(old.objects) else None
        b=new.objects[key] if key<len(new.objects) else None
        if a is None or b is None or a.decoded!=b.decoded:
            objects.append({'handle':key,'old_bytes':len(a.decoded) if a else None,'new_bytes':len(b.decoded) if b else None})
    assert new.serialize()==new.original
    report={'status':'PASS','roundtrip':'PASS','old_sha256':sha(WORK/'previous_original/THOG.dat'),'new_sha256':sha(SOURCE/'THOG.dat'),'changed_chunks':rows,'changed_objects':objects,'old_objects':len(old.objects),'new_objects':len(new.objects),'header_equal':old.header==new.header if hasattr(old,'header') else None}
    save(WORK/'dat_difference.json',report)
    print(json.dumps({'status':'PASS','changed_chunks':len(rows),'changed_objects':len(objects),'old_objects':len(old.objects),'new_objects':len(new.objects)}))


def inventory():
    import collections
    import inventory as inv
    from dat_container import DatFile, utf16z
    old=DatFile.load(WORK/'previous_original/THOG.dat')
    new=DatFile.load(SOURCE/'THOG.dat')
    previous=ROOT/'working_private/THE_HORDE_OF_GORAK/investigation_20261031/classification'
    old_rows=[json.loads(line) for line in (previous/'inventory.jsonl').read_text(encoding='utf-8').splitlines()]
    inv.SOURCE=SOURCE/'THOG.dat'
    inv.SEMANTIC=ROOT/'extracted_private/THE_HORDE_OF_GORAK/steam_26365992/nebula_01'
    inv.OUT=WORK/'classification'
    inv.EXT_PATH=WORK/'extension/extension_inventory.jsonl'
    inv.OUT.mkdir()
    original_classifier=inv.classify_event
    def classify(row):
        original_classifier(row)
        index=row['expression_index']
        if row['classification']=='UNKNOWN' and index is not None and index>0:
            previous_expression=row['expressions'][index-1]
            if (previous_expression['type'],previous_expression['num'])==(35,82):
                row.update(classification='INTERNAL',reason='동일 kcini 숫자 읽기 표현식82의 키 인수. 업데이트로 달라진 객체 번호 대신 확장 형식과 소비 연산을 확인')
    inv.classify_event=classify
    def reuse(records,dat,source_digest):
        reused=[]
        for row in records:
            if row['classification']!='UNKNOWN':
                continue
            matches=[r for r in old_rows if r['kind']==row['kind'] and r['source']==row['source'] and r['source_container_sha256']==row['source_container_sha256'] and r.get('offset')==row.get('offset') and r['classification']!='UNKNOWN']
            if matches and len({m['classification'] for m in matches})==1:
                row.update(classification=matches[0]['classification'],reason=matches[0]['reason'],evidence={'reference_location':matches[0]['location'],'reference_inventory_sha256':sha(previous/'inventory.jsonl'),'basis':'동일 객체 내용 지문·필드 오프셋·원문'})
                reused.append({'location':row['location'],'previous':matches[0]['location']})
            elif row['location']=='app/about' and row['source'].isdigit() and len(row['source'])==72:
                row.update(classification='VISIBLE_KEEP',reason='동일 실행기의 About 표시 필드. 업데이트된 숫자형 원문 메타데이터를 그대로 유지')
        controls=json.loads((previous.parent/'player_controls_225d.json').read_text(encoding='utf-8'))
        assert old.one(0x225D).decoded==new.one(0x225D).decoded
        for field in controls['strings']:
            prior=next(r for r in old_rows if r['location']==f"player_controls/{field['kind']}@{field['offset']}")
            row=dict(prior)
            assert utf16z(dat.by_location[row['target']].decoded,row['offset'])[0]==row['source']
            row['source_file_sha256']=source_digest
            row['evidence_path']=str(previous/'inventory.jsonl')
            records.append(row)
        evidence={'unchanged_controls_chunk':True,'reused_fields':reused,'reference_inventory_sha256':sha(previous/'inventory.jsonl')}
        save(WORK/'classification_reuse.json',evidence)
        return evidence
    inv.apply_native_findings=reuse
    inv.main()
    rows=[json.loads(line) for line in (inv.OUT/'inventory.jsonl').read_text(encoding='utf-8').splitlines()]
    translations=json.loads((ROOT/'working_private/THE_HORDE_OF_GORAK/translation_02/translations.json').read_text(encoding='utf-8'))
    known={r['source'] for r in translations}
    new_rows=[r for r in rows if r['classification']=='VISIBLE_TRANSLATE' and r['source'] not in known]
    unknown=[r for r in rows if r['classification']=='UNKNOWN']
    save(WORK/'new_text_review.json',new_rows)
    save(WORK/'unknown_review.json',unknown)
    print(json.dumps({'counts':dict(collections.Counter(r['classification'] for r in rows)),'new_sources':sorted({r['source'] for r in new_rows}),'unknown':[(r['location'],r['source']) for r in unknown]},ensure_ascii=False))


def translations():
    from dat_container import DatFile
    old_dir=ROOT/'working_private/THE_HORDE_OF_GORAK/investigation_20261031/classification'
    old_rows=[json.loads(x) for x in (old_dir/'inventory.jsonl').read_text(encoding='utf-8').splitlines()]
    new_rows=[json.loads(x) for x in (WORK/'classification/inventory.jsonl').read_text(encoding='utf-8').splitlines()]
    old_by_loc={x['location']:x for x in old_rows}
    prior=json.loads((ROOT/'working_private/THE_HORDE_OF_GORAK/translation_02/translations.json').read_text(encoding='utf-8'))
    prior_by_source={x['source']:x for x in prior}
    extensions=[json.loads(x) for x in (WORK/'extension/extension_inventory.jsonl').read_text(encoding='utf-8').splitlines()]
    ext_by_loc={x['id']:x for x in extensions}
    native_baseline=json.loads((WORK/'previous_package_manifest.json').read_text(encoding='utf-8'))
    for name in ('KcBoxA.mfx','Layer.mfx','AdvDir.mfx'):
        assert sha(SOURCE/name)==next(x['sha256'] for x in native_baseline['baseline'] if x['path']==name)
    for row in new_rows:
        if row['classification']=='UNKNOWN':
            ext=ext_by_loc[row['location']]
            assert (ext['object_type'],ext['blob_offset'],ext['source']) in {(32,0,'@ '),(34,4,'  '),(36,4,'  ')}
            row.update(classification='INTERNAL',reason='확장 자료의 너비·높이 숫자 필드. UTF-16 검색에 우연히 잡힌 64/32 또는32/32이며 표시 문구가 아님. 동일 KcBoxA·Layer·AdvDir 실행 코드와 기존 필드 판독 근거 재사용',evidence={'native_files_unchanged':True,'reference':'investigation_20261031/native_extra_findings.json','offset':ext['blob_offset'],'type':ext['object_type']})
    (WORK/'classification/inventory.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in new_rows),encoding='utf-8')
    additions={'Click to open!':'클릭하여 열기!', 'Gold Coins!\r\nYou can spend them at a shop on the map - once you unlock it':'금화!\r\n지도에서 상점을 해금하면 사용할 수 있습니다', 'Gold Coins:':'금화:', 'OGRES STORE':'오우거 상점', 'Ogres Store\r\n(Click to open)':'오우거 상점\r\n(클릭하여 열기)', 'Ogres Store\r\n(Destroy Castle 2 to unlock!)':'오우거 상점\r\n(성채 2를 파괴하면 해금!)', 'Purchased items have a permanent effect and remain with you even after a run ends.':'구매한 아이템의 효과는 영구적이며 원정이 끝나도 유지됩니다.'}
    for i in range(1,5):
        additions[f'Item {i}']=f'아이템 {i}'
        additions[f'Item {i} desc']=f'아이템 {i} 설명'
    worklist=json.loads((WORK/'classification/translation_worklist.json').read_text(encoding='utf-8'))
    overrides={}
    for tr in prior:
        for ov in tr.get('overrides',[]):
            old=old_by_loc[ov['location']]
            matches=[r for r in new_rows if r['kind']==old['kind'] and r['source']==old['source'] and r.get('object_name')==old.get('object_name') and r['location'].split('/')[-1]==old['location'].split('/')[-1]]
            assert len(matches)==1,(ov,matches)
            overrides[matches[0]['location']]=ov['translation']
    result=[]
    for group in worklist:
        source=group['source']
        text=prior_by_source[source]['translation'] if source in prior_by_source else additions[source]
        row={**group,'translation':text,'overrides':[{'location':o['location'],'translation':overrides[o['location']]} for o in group['occurrences'] if o['location'] in overrides]}
        result.append(row)
    save(WORK/'translations.json',result)
    save(WORK/'translation_migration.json',{'old_unique':len(prior),'new_unique':len(result),'locations':sum(len(r['occurrences']) for r in result),'new_sources':additions,'context_overrides_mapped':len(overrides),'unknown_remaining':0})
    print(json.dumps({'unique':len(result),'locations':sum(len(r['occurrences']) for r in result),'new_sources':len(additions),'overrides':len(overrides)}))


def media():
    from PIL import Image,ImageDraw,ImageFont
    from dat_container import DatFile
    from image_builder import ImageBank
    new_dir=ROOT/'extracted_private/THE_HORDE_OF_GORAK/steam_26365992/nebula_01'
    old=json.loads((WORK/'previous_semantic/media.json').read_text(encoding='utf-8'))
    new=json.loads((new_dir/'media.json').read_text(encoding='utf-8'))
    known={(r['source_sha256'],r['Width'],r['Height'],r['GraphicMode']) for r in old}
    fresh=[r for r in new if (r['source_sha256'],r['Width'],r['Height'],r['GraphicMode']) not in known]
    bank=ImageBank(DatFile.load(SOURCE/'THOG.dat'))
    folder=WORK/'media_new'
    folder.mkdir()
    unique={r['source_sha256']:r for r in fresh}
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
    groups=list(unique.values())
    for page in range(0,len(groups),36):
        canvas=Image.new('RGB',(1200,960),(45,48,55));draw=ImageDraw.Draw(canvas)
        for index,row in enumerate(groups[page:page+36]):
            record=bank.by_handle[row['handle']]
            img=Image.frombytes('RGBA',record.dimensions,record.pixels,'raw','BGRA')
            img.save(folder/f"{row['handle']:05d}.png")
            img.thumbnail((194,128))
            x=(index%6)*200;y=(index//6)*160
            canvas.paste(img,(x+(200-img.width)//2,y+22),img)
            draw.text((x+4,y+3),str(row['handle'])+' '+str(record.dimensions),font=font,fill='white')
        canvas.save(folder/f'contact_{page//36+1}.jpg')
    save(WORK/'media_difference.json',{'original_count':len(old),'new_count':len(new),'unchanged_count':len(new)-len(fresh),'new_or_changed':fresh,'new_unique':len(unique),'status':'REVIEW_REQUIRED'})
    print(json.dumps({'new_or_changed':len(fresh),'new_unique':len(unique),'sheets':(len(unique)+35)//36}))


def assemble():
    candidate=ROOT/'build_candidate/THE_HORDE_OF_GORAK/ko_1_0_1_c01'
    game=candidate/'game'
    assert not game.exists()
    shutil.copytree(SOURCE,game)
    shutil.copy2(candidate/'THOG.dat',game/'THOG.dat')
    old=json.loads((WORK/'previous_package_manifest.json').read_text(encoding='utf-8'))
    package=WORK/'previous_package'
    with zipfile.ZipFile(OLD_ZIP) as z:
        z.extractall(package)
    native=[]
    for row in old['changes']:
        if row['path']=='THOG.dat':continue
        assert sha(SOURCE/row['path'])==row['original_sha256']
        subprocess.run([str(package/'tools/xdelta3.exe'),'-d','-f','-s',str(SOURCE/row['path']),str(package/row['forward']),str(game/row['path'])],check=True,capture_output=True)
        assert sha(game/row['path'])==row['patched_sha256']
        native.append({'path':row['path'],'sha256':sha(game/row['path']),'reused_from':'1.0.0'})
    files=[{'path':p.relative_to(game).as_posix(),'size':p.stat().st_size,'sha256':sha(p)} for p in sorted(game.rglob('*')) if p.is_file()]
    save(WORK/'candidate_manifest.json',{'game_id':'THE_HORDE_OF_GORAK','steam_build':'26365992','candidate_id':'ko_1_0_1_c01','files':files,'native_reuse':native,'qa_overrides_included':False})
    media=json.loads((WORK/'media_difference.json').read_text(encoding='utf-8'))
    media.update(status='PASS',reviewed_sheets=['media_new/contact_1.jpg','media_new/contact_2.jpg'],detail_inspected=['media_new/02082.png'],decisions=[{'handle':r['handle'],'source_sha256':r['source_sha256'],'decision':'KEEP' if r['handle']==2082 else 'NO_TEXT','reason':'상점 그림의 숫자10을 보존' if r['handle']==2082 else '제작자가 새 이미지65종을 두 검수판에서 판독. 지형·장비·동물·장식·효과·빈 판넬·통화 기호'} for r in media['new_or_changed']],unchanged_reuse='기존 이미지의 픽셀 지문·크기·색상 형식이 같은 위치만 이전 판독 재사용. 기존 한글화 이미지4개도 지문 동일')
    save(WORK/'media_review.json',media)
    print(json.dumps({'files':len(files),'native_reused':len(native),'candidate_sha256':sha(game/'THOG.dat')}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['baseline','compare','inventory','translations','media','assemble'])
    args=parser.parse_args()
    globals()[args.action]()
