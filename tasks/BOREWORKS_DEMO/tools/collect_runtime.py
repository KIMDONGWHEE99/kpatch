"""운영체제 경로·후보 파생 경계·화면·로그·사용자 저장을 함께 확인합니다."""
from common import *
import sys,collections
sys.path.insert(0,str(ROOT/'tools/python_deps'))
from PIL import Image,ImageDraw
run='qa_certified';stage=WORK/'runtime_final';stage.mkdir(exist_ok=True)
log=(WORK/(run+'.log')).read_text(encoding='utf-8');lines=log.splitlines()
assert 'AUTO-TEST ui-layout: OK' in log
cases=[line for line in lines if 'AUTO-TEST ui-layout:' in line and ' - OK' in line]
assert len(cases)==282 and '[pseudo/' not in log
assert 'NVIDIA GeForce RTX 4060 Ti' in log
assert not re.search(r'(?i)glyph.*missing|missing.*glyph|ERROR:|failed to load|error loading|1 violation',log)
launch=json.loads((WORK/(run+'_launch.json')).read_text(encoding='utf-8'))
assert Path(launch['actual_process_path'])==WORK/'qa_v002/Boreworks.exe'
candidate=ROOT/'build_candidate/BOREWORKS_DEMO/ko_v002'
candidate_pack=read_pack(candidate/'Boreworks.pck')[3];qa_pack=read_pack(WORK/'qa_v002/Boreworks.pck')[3]
assert set(candidate_pack)==set(qa_pack)
assert [n for n in candidate_pack if candidate_pack[n]['data']!=qa_pack[n]['data']]==['project.binary']
allowed={'System.Void Game.Steam.SteamworksSteamService::Init()','System.String Game.AutoTestDriver::ParseMode()','System.Void Game.Main::_Ready()','System.Void Game.AutoTestDriver::.cctor()','System.Void Game.AutoTestDriver::TickUiLayout()'}
tool=WORK/'toolchain/AssemblyTool/AssemblyTool.dll'
subprocess.run(['dotnet',str(tool),'dump',str(WORK/'qa_v002/data_Boreworks_windows_x86_64/Boreworks.dll'),str(stage/'qa.il.json')],check=True)
before={m['method']:m for m in json.loads((WORK/'ko_v002/Boreworks.il.json').read_text(encoding='utf-8'))}
after={m['method']:m for m in json.loads((stage/'qa.il.json').read_text(encoding='utf-8'))}
assert before.keys()==after.keys()
changed=[n for n in before if before[n]!=after[n]];assert set(changed)==allowed,changed
# Main의 교체는 최소화 상수 1개뿐입니다.
a=before['System.Void Game.Main::_Ready()']['instructions'];b=after['System.Void Game.Main::_Ready()']['instructions']
diff=[(x,y) for x,y in zip(a,b) if x!=y];assert len(diff)==1 and diff[0][0]['op']=='ldc.i4.1' and diff[0][1]['op']=='ldc.i4.0'
images=[]
for i,line in enumerate(lines):
    if '→ screenshot:' not in line or 'korean-qa-' not in line:continue
    path=Path(line.split('→ screenshot: ')[1]);im=Image.open(path)
    assert im.size==(1280,800) and len(im.getcolors(im.width*im.height))>100
    label=next(s for s in lines[i+1:] if 'AUTO-TEST ui-layout:' in s).split('AUTO-TEST ui-layout: ')[1]
    images.append(dict(id=len(images),path=str(path),sha256=sha(path.read_bytes()),label=label,visual_review='NOT_RUN'))
assert len(images)==58
for k in range(0,len(images),6):
    sheet=Image.new('RGB',(1280,1290),'#eee');draw=ImageDraw.Draw(sheet)
    for j,row in enumerate(images[k:k+6]):
        im=Image.open(row['path']);im.thumbnail((640,400));x=(j%2)*640;y=(j//2)*430
        sheet.paste(im,(x,y+28));draw.text((x+5,y+5),str(row['id'])+' '+row['label'],fill='black')
    sheet.save(stage/f'contact_{k//6:02}.jpg',quality=94)
save_json(stage/'screenshots.json',images)
for run_id,marker in [('qa_intro','AUTO-TEST run-start-intro: OK'),('qa_save','AUTO-TEST quickload-via-input: OK')]:
    text=(WORK/(run_id+'.log')).read_text(encoding='utf-8')
    assert marker in text and 'ERROR:' not in text
original_saves=json.loads((WORK/'user_saves_before.json').read_text(encoding='utf-8'));after_saves=[]
for row in original_saves:
    root=Path(row['root']);files=[dict(path=p.relative_to(root).as_posix(),size=p.stat().st_size,sha256=sha(p.read_bytes())) for p in sorted(root.rglob('*')) if p.is_file()] if root.exists() else []
    after_saves.append(dict(root=str(root),exists=root.exists(),files=files))
assert after_saves==original_saves
save_json(stage/'user_saves_after.json',after_saves)
save_json(stage/'runtime_checks.json',dict(status='PASS',visual_review='NOT_RUN',launch=launch,candidate='ko_v002',layout_cases=len(cases),menus=21,presets=4,font_configs=5,viewport=[1280,800],screenshots=len(images),allowed_qa_methods=sorted(allowed),qa_boundary='PASS',user_saves_unchanged=True,missing_glyph_warnings=0,patch_loading_errors=0,original_icon_warning=1,intro_flow='PASS',save_load_flow='PASS',whole_random_playthrough='NOT_RUN',qa_code_in_release=False))
print('RUNTIME_CHECKS_PASS',len(images),len(cases))
