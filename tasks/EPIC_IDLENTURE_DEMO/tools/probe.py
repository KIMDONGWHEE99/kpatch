"""원본 구조 보존·한글 글꼴·격리 그래픽 실행을 소규모 시험합니다."""
from common import *
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import subprocess,copy,os,winreg,datetime
RUN=WORK/'probe_001';GAME=RUN/'game'
def snapshot():
    folders=[Path(os.environ['USERPROFILE'])/'AppData/LocalLow/impulse9/Epic Idlenture']
    steam=Path('D:/steam/userdata')
    if steam.exists():folders.extend(x/'4114020' for x in steam.iterdir() if x.is_dir())
    files=[dict(path=str(p),size=p.stat().st_size,sha256=sha(p.read_bytes())) for d in folders if d.exists() for p in sorted(d.rglob('*')) if p.is_file()]
    values=[]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\impulse9\Epic Idlenture') as key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                n,v,t=winreg.EnumValue(key,i);values.append([n,v.hex() if isinstance(v,bytes) else v,t])
    except FileNotFoundError:pass
    return dict(files=files,registry=values)
if sys.argv[1]=='prepare':
    assert not GAME.exists();shutil.copytree(BASE,GAME);g=generator();report=[]
    for name in ('globalgamemanagers','globalgamemanagers.assets','level0','level1','resources.assets','sharedassets0.assets','sharedassets1.assets'):
        e=load(BASE/DATA/name,g);out=preserve_save(BASE/DATA/name,e)
        assert out==(BASE/DATA/name).read_bytes();report.append(dict(file=name,status='PASS',sha256=sha(out),objects=len(e.objects)))
    save(RUN/'roundtrip.json',report)
    font=instantiateVariableFont(TTFont(ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf'),{'wght':400},inplace=True)
    font.save(WORK/'NotoSansKR-Regular.ttf');fontbytes=(WORK/'NotoSansKR-Regular.ttf').read_bytes()
    e=load(BASE/DATA/'resources.assets',g)
    for pid in (677,5208,5212,5090):
        o=e.file.objects[pid];t=o.read_typetree()
        if pid==677:t['m_FontData']=list(fontbytes);t['m_FontNames']=['Noto Sans KR']
        if pid==5208:
            assert t['m_AtlasPopulationMode']==1 and not t['m_CharacterTable'];t['m_IsMultiAtlasTexturesEnabled']=True
        if pid==5212:t['m_fallbackFontAssets']=[{'m_FileID':0,'m_PathID':5208}]
        if pid==5090:t['settings']['path']=str(RUN/'saves/SaveFile_v2.es3')
        o.save_typetree(t)
    (GAME/DATA/'resources.assets').write_bytes(preserve_save(BASE/DATA/'resources.assets',e))
    e=load(BASE/DATA/'level0',g)
    for pid,value in {425:'클릭하여 시작...',426:'저장 데이터 삭제',427:'STEAM 찜 목록에 추가!'}.items():
        o=e.file.objects[pid];t=o.read_typetree();t['m_text']=value;o.save_typetree(t)
    (GAME/DATA/'level0').write_bytes(preserve_save(BASE/DATA/'level0',e))
    e=load(BASE/DATA/'globalgamemanagers',g);o=e.file.objects[1];raw=o.get_raw_data()
    assert raw.count(b'impulse9')==raw.count(b'Epic Idlenture')==1
    patched=raw.replace(b'impulse9',b'EPIC_QA1').replace(b'Epic Idlenture',b'Epic_KoreanQA1');assert len(patched)==len(raw)
    o.set_raw_data(patched);(GAME/DATA/'globalgamemanagers').write_bytes(preserve_save(BASE/DATA/'globalgamemanagers',e))
    (GAME/DATA/'app.info').write_text('EPIC_QA1\nEpic_KoreanQA1',encoding='utf8')
    managed=GAME/DATA/'Managed';shutil.copy2(WORK/'qa_support/KoreanQA.dll',managed/'KoreanQA.dll')
    subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'isolate',str(BASE/DATA/'Managed/Assembly-CSharp.dll'),str(managed/'Assembly-CSharp.dll'),str(managed/'KoreanQA.dll')],check=True)
    save(RUN/'user_before.json',snapshot());save(RUN/'files.json',[dict(path=p.relative_to(GAME).as_posix(),sha256=sha(p.read_bytes())) for p in GAME.rglob('*') if p.is_file()])
elif sys.argv[1]=='launch':
    assert snapshot()==json.loads((RUN/'user_before.json').read_text(encoding='utf8'))
    command=[str(GAME/'Epic Idlenture.exe'),'-screen-fullscreen','0','-screen-width','1280','-screen-height','720','-logFile',str(RUN/'Player.log')]
    p=subprocess.Popen(command,cwd=GAME,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    save(RUN/'launch.json',dict(pid=p.pid,expected_executable=command[0],command=command,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()));print('PID',p.pid)
elif sys.argv[1]=='verify':
    after=snapshot();save(RUN/'user_after.json',after);assert after==json.loads((RUN/'user_before.json').read_text(encoding='utf8'));print('사용자 저장·설정 동일')
