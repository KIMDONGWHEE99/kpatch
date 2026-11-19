"""검수 사본의 회사명·제품명·로그·저장·Steam 연결만 격리합니다."""
from common import *
import shutil,subprocess

candidate=ROOT/'build_candidate/COMBOLANDS'/sys.argv[1]/'game'
folder=WORK/sys.argv[2];game=folder/'game'
assert not game.exists();shutil.copytree(candidate,game)
p=game/'Combolands_Data/globalgamemanagers';env=UnityPy.load(str(p))
changed=[]
for obj in env.objects:
    if obj.type.name=='PlayerSettings':
        a=obj.get_raw_data();assert a.count(b'Combolands')==1 and a.count(b'Crux Games')==1
        b=a.replace(b'Combolands',b'ComboQA_06').replace(b'Crux Games',b'Crux QAaaa');obj.set_raw_data(b)
        changed.append(obj.path_id)
p.write_bytes(env.file.save())
reopened=UnityPy.load(str(p))
unmodified=UnityPy.load(str(candidate/'Combolands_Data/globalgamemanagers'))
assert len(changed)==1
for obj in reopened.objects:
    expected=unmodified.file.objects[obj.path_id].get_raw_data()
    if obj.path_id in changed:expected=expected.replace(b'Combolands',b'ComboQA_06').replace(b'Crux Games',b'Crux QAaaa')
    assert obj.get_raw_data()==expected,(obj.path_id,'검수 사본 객체 불일치')
(game/'Combolands_Data/app.info').write_text('Crux QAaaa\nComboQA_06',encoding='utf8')
dll=game/'Combolands_Data/Managed/Assembly-CSharp.dll'
mode='qa-controls' if '--controls' in sys.argv else 'qa'
subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),mode,str(candidate/'Combolands_Data/Managed/Assembly-CSharp.dll'),str(dll),str(folder/'save')],check=True)
save_json(folder/'qa_manifest.json',dict(candidate=sys.argv[1],source_build_sha256=sha(candidate.parent/'build.json'),player_settings_object=changed,methods=json.loads(Path(str(dll)+'.qa.json').read_text(encoding='utf8')),files=[dict(path=p.relative_to(game).as_posix(),sha256=sha(p)) for p in game.rglob('*') if p.is_file()]))
print(game)
