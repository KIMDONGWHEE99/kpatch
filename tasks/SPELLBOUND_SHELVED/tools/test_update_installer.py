"""새 ZIP 설치기 전체 시험과 구 빌드 백업 공존 시험."""
from update_25274913 import ROOT,WORK,BASELINE,configure,read,write,sha
import shutil

configure()
source=(ROOT/'tasks/SPELLBOUND_SHELVED/tools/test_installer.py').read_text(encoding='utf-8')
source=source.replace("scratch=WORK/'package_1.0.0_r3'","scratch=WORK/'package_1.0.1'").replace('ko_1.0.0_c02','ko_1.0.1_c01').replace('SPELLBOUND_SHELVED_KOREAN_PATCH_1.0.0.zip','SPELLBOUND_SHELVED_KOREAN_PATCH_1.0.1.zip')
source=source.replace("/'SpellboundShelvedKoreanPatch/working_private'/key","/'SpellboundShelvedKoreanPatch/working_private'/key/'build_25274913'")
namespace={'__name__':'installer_test'};exec(compile(source,'test_installer.py','exec'),namespace)
folder=namespace['folder'];run=namespace['run'];state_for=namespace['state_for'];env=namespace['env'];change=namespace['change'];records=namespace['records']
old=WORK/'previous_package';old_manifest=read(old/'manifest.json');q=folder('previous_backup_coexistence')
shutil.copy2(ROOT/'source_original/SPELLBOUND_SHELVED/steam_25171813/windows/SpellboundShelved.pck',q/'SpellboundShelved.pck')
run('prepare_previous_release','Install',q,expected_hash=old_manifest['changes'][0]['patched_sha256'],package_path=old)
old_state=state_for(q).parent
before={p.relative_to(old_state).as_posix():sha(p) for p in old_state.rglob('*') if p.is_file()}
# Steam이 새 빌드를 설치한 상태를 사본에서 재현한다.
shutil.copy2(BASELINE/'windows/SpellboundShelved.pck',q/'SpellboundShelved.pck')
run('new_build_with_previous_backup','Install',q,expected_hash=change['patched_sha256'])
assert all(sha(old_state/p)==h for p,h in before.items())
run('remove_new_build_keep_old_backup','Uninstall',q,expected_hash=change['original_sha256'])
assert all(sha(old_state/p)==h for p,h in before.items())
q=folder('reject_previous_build_patch');shutil.copy2(ROOT/'build_candidate/SPELLBOUND_SHELVED/ko_1.0.0_c02/windows/SpellboundShelved.pck',q/'SpellboundShelved.pck')
run('reject_previous_build_patch','Install',q,1,old_manifest['changes'][0]['patched_sha256'])
result=read(WORK/'package_1.0.1/installer_tests.json');result['tests']=records;result['steam_build']='25274913';write(WORK/'package_1.0.1/installer_tests.json',result)
print('최종 시험 수',len(records))
