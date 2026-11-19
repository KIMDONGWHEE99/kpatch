"""후보에서 저장·외부 연동을 분리한 실행 검수 사본을 준비합니다."""
from common import *
import subprocess,os,datetime
args=sys.argv[:];sys.argv=['probe.py','import'];from probe import snapshot
sys.argv=args
RUN=WORK/sys.argv[2];GAME=RUN/'game'
if sys.argv[1]=='prepare':
    candidate=BASE if sys.argv[3]=='baseline' else ROOT/'build_candidate/EPIC_IDLENTURE_DEMO'/sys.argv[3]
    assert not GAME.exists();shutil.copytree(candidate,GAME);g=generator()
    e=load(candidate/DATA/'globalgamemanagers',g);o=e.file.objects[1];raw=o.get_raw_data()
    patched=raw.replace(b'impulse9',b'EPIC_QA1').replace(b'Epic Idlenture',b'Epic_KoreanQA1');assert len(raw)==len(patched)
    o.set_raw_data(patched);(GAME/DATA/'globalgamemanagers').write_bytes(preserve_save(candidate/DATA/'globalgamemanagers',e))
    (GAME/DATA/'app.info').write_text('EPIC_QA1\nEpic_KoreanQA1',encoding='utf8')
    e=load(candidate/DATA/'resources.assets',g);o=e.file.objects[5090];t=o.read_typetree();t['settings']['path']=str(RUN/'saves/SaveFile_v2.es3');o.save_typetree(t)
    (GAME/DATA/'resources.assets').write_bytes(preserve_save(candidate/DATA/'resources.assets',e))
    assembly=Path(DATA)/'Managed/Assembly-CSharp.dll';managed=GAME/DATA/'Managed'
    shutil.copy2(WORK/'qa_support/KoreanQA.dll',managed/'KoreanQA.dll')
    subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'isolate',str(candidate/assembly),str(GAME/assembly),str(managed/'KoreanQA.dll')],check=True)
    (RUN/'full_qa.txt').write_text('격리 검수',encoding='utf8')
    dialogues=[]
    for name,ids in [('resources.assets',[5071,5073,5075,5077,5079]),('sharedassets0.assets',[656,657])]:
        e=load(candidate/DATA/name,g)
        for pid in ids:
            t=e.file.objects[pid].read_typetree();dialogues.append(dict(name=t['m_Name'],Dialogs=t['Dialogs']))
    save(RUN/'dialogues.json',dict(blocks=dialogues))
    if sys.argv[3]!='baseline':
        (RUN/'font_characters.txt').write_text(''.join(chr(c) for c in json.loads((WORK/(sys.argv[3]+'.json')).read_text(encoding='utf8'))['font_characters']),encoding='utf8')
    save(RUN/'user_before.json',snapshot());save(RUN/'manifest.json',dict(candidate=sys.argv[3],candidate_manifest_sha256=sha((WORK/(sys.argv[3]+'.json')).read_bytes()),overrides=['PlayerSettings.companyName/productName','app.info','ES3Defaults.settings.path','SteamHelper.Initialize','검수 드라이버'],files=[dict(path=p.relative_to(GAME).as_posix(),sha256=sha(p.read_bytes())) for p in GAME.rglob('*') if p.is_file()]))
elif sys.argv[1]=='launch':
    assert snapshot()==json.loads((RUN/'user_before.json').read_text(encoding='utf8'))
    command=[str(GAME/'Epic Idlenture.exe'),'-screen-fullscreen','0','-screen-width','1280','-screen-height','720','-logFile',str(RUN/'Player.log')]
    p=subprocess.Popen(command,cwd=GAME,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);save(RUN/'launch.json',dict(pid=p.pid,expected_executable=command[0],command=command,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()));print('검수 PID',p.pid)
elif sys.argv[1]=='verify':
    after=snapshot();save(RUN/'user_after.json',after);assert after==json.loads((RUN/'user_before.json').read_text(encoding='utf8'));print('사용자 저장·설정 동일')
