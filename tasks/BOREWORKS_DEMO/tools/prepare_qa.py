"""후보와 검수 전용 변경을 구분하고 검수 사본을 만듭니다."""
from common import *
import shutil,sys
candidate_id,qa_name,mode=sys.argv[1:4]
candidate=ROOT/'build_candidate/BOREWORKS_DEMO'/candidate_id
qa=WORK/qa_name
if qa.exists(): raise RuntimeError('검수 사본 이름이 이미 있습니다.')
shutil.copytree(candidate,qa)
original=read_pack(candidate/'Boreworks.pck')[3]
isolation=read_pack(WORK/'qa_v001/Boreworks.pck')[3]['project.binary']['data']
patch_pack(candidate/'Boreworks.pck',qa/'Boreworks.pck',{'project.binary':isolation})
command=['dotnet',str(WORK/'toolchain/AssemblyPatch/AssemblyPatch.dll'),'qa',str(candidate/'data_Boreworks_windows_x86_64/Boreworks.dll'),str(qa/'data_Boreworks_windows_x86_64/Boreworks.dll')]
if mode!='normal':command.append(mode)
subprocess.run(command,check=True)
save_json(WORK/(qa_name+'_derivation.json'),dict(candidate=candidate_id,qa_name=qa_name,mode=mode,project_override_sha256=sha(isolation),allowed_files=['Boreworks.pck','data_Boreworks_windows_x86_64/Boreworks.dll'],pck_changed_entries=['project.binary']))
print(qa_name,mode)
