"""빌드별 백업을 사용하는 새 배포본을 만들고 이전 백업을 보존한다."""
import json
import zipfile
import shutil
import subprocess
from update_25274913 import ROOT,WORK,BASELINE,CANDIDATE,sha,read,write

old_zip=ROOT/'release_output/SPELLBOUND_SHELVED_KOREAN_PATCH_1.0.0.zip'
assert sha(old_zip)=='71d1b36782453483a966254cc8571a9d371af8ba525f566f54684cc1d40c8f59'
old=WORK/'previous_package';old.mkdir(exist_ok=True)
allow={'Install.cmd','Remove.cmd','Patch.ps1','ChooseGame.ps1','README.txt','manifest.json','tools/xdelta3.exe','licenses/xdelta3-APACHE-2.0.txt','licenses/NotoSansKR-OFL.txt','patches/00.forward.xdelta','patches/00.reverse.xdelta'}
with zipfile.ZipFile(old_zip) as z:
    assert set(z.namelist())==allow;z.extractall(old)
previous_manifest=read(old/'manifest.json')
for row in previous_manifest['payload']:assert sha(old/row['path'])==row['sha256']
release=ROOT/'release_output/SPELLBOUND_SHELVED_KOREAN_PATCH_1.0.1';scratch=WORK/'package_1.0.1'
assert not release.exists() and not scratch.exists()
shutil.copytree(old,release);scratch.mkdir()
script=(old/'Patch.ps1').read_text(encoding='utf-8-sig').replace("'25171813'","'25274913'").replace("'1.0.0'","'1.0.1'")
needle="('SpellboundShelvedKoreanPatch\\working_private\\'+$rootKey)"
assert needle in script
script=script.replace(needle,"('SpellboundShelvedKoreanPatch\\working_private\\'+$rootKey+'\\build_'+$manifest.steam_build)")
# 기존 기록은 같은 게임 경로 아래 그대로 두고 새 빌드의 기록만 별도 생성한다.
assert "$journal.phase -in @('APPLYING','COMPLETE')" in script
(release/'Patch.ps1').write_text(script,encoding='utf-8-sig')
chooser=(old/'ChooseGame.ps1').read_text(encoding='utf-8-sig').replace('1.0.0','1.0.1');(release/'ChooseGame.ps1').write_text(chooser,encoding='utf-8-sig')
readme=(old/'README.txt').read_text(encoding='utf-8-sig').replace('1.0.0','1.0.1').replace('25171813','25274913').replace('306개','311개')
readme=readme.replace('게임 경로별로 보관됩니다.','게임 경로 및 Steam 빌드별로 보관됩니다. 이전 버전의 백업은 그대로 남습니다.')
readme=readme.replace('Wanderbots, Aliensrock, SplatterCat, Flotidus, CG Grows)', 'Wanderbots, Aliensrock, SplatterCat, Flotidus, CG Grows, JustPatrick, MikhailMysfit, UnkiePlays, LiamsiL)')
readme+='\n1.0.1 변경: Steam 업데이트 대응. 노움 잡담 숨기기·추가 통계·바닥 책 수·서가 채움 비율을 한글화했습니다.\n구 빌드용 1.0.0 백업은 새 빌드 복원에 사용하지 않습니다.\n'
(release/'README.txt').write_text(readme,encoding='utf-8-sig')
original=BASELINE/'windows/SpellboundShelved.pck';candidate=CANDIDATE/'windows/SpellboundShelved.pck';encoder=release/'tools/xdelta3.exe'
for kind,a,b in [('forward',original,candidate),('reverse',candidate,original)]:
    delta=release/f'patches/00.{kind}.xdelta'
    subprocess.run([str(encoder),'-f','-e','-9','-s',str(a),str(b),str(delta)],check=True,capture_output=True)
    rebuilt=scratch/(kind+'.pck');subprocess.run([str(encoder),'-d','-s',str(a),str(delta),str(rebuilt)],check=True,capture_output=True);assert sha(rebuilt)==sha(b)
baseline=[{'path':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in sorted((BASELINE/'windows').iterdir()) if p.is_file()]
payload=[{'path':p.relative_to(release).as_posix(),'size':p.stat().st_size,'sha256':sha(p)} for p in sorted(release.rglob('*')) if p.is_file() and p.name!='manifest.json']
manifest={'game_id':'SPELLBOUND_SHELVED','steam_build':'25274913','version':'1.0.1','candidate':CANDIDATE.name,'baseline':baseline,
    'changes':[{'path':'SpellboundShelved.pck','original_sha256':sha(original),'patched_sha256':sha(candidate),'forward':'patches/00.forward.xdelta','reverse':'patches/00.reverse.xdelta'}],'payload':payload}
write(release/'manifest.json',manifest)
assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}==allow
archive=release.parent/(release.name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in sorted(release.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(release).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None and set(z.namelist())==allow;z.extractall(scratch/'from_final_zip')
for name in allow:assert sha(release/name)==sha(scratch/'from_final_zip'/name)
write(scratch/'package.json',{'candidate':CANDIDATE.name,'steam_build':'25274913','zip_sha256':sha(archive),'manifest_sha256':sha(release/'manifest.json'),
    'allowed_files':sorted(allow),'roundtrip_forward':'PASS','roundtrip_reverse':'PASS','final_zip_tests':'NOT_RUN'})
print('최종 ZIP',sha(archive))
