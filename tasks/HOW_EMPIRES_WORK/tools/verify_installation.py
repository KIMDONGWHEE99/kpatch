"""실제 설치본·원본 백업·사용자 저장을 읽기 전용으로 검증합니다."""
from common import *
import datetime
root=Path('D:/steam/steamapps/common/How Empires Work')
# 설치기의 실제 출력 경로를 사용합니다. 샌드박스 환경의 LOCALAPPDATA 값과 구별합니다.
backup=Path('C:/Users/PC/AppData/Local/HowEmpiresWorkKoreanPatch/working_private/7A2EF6E46A4A4B0C/build_26482667')
receipt=read_json(backup/'receipt.json')
assert receipt['status']=='COMPLETE' and receipt['candidate']=='full_04'
records=[]
for r in read_json(WORK/'baseline.json')['files']:
    path=root/r['path'];expected=sha(ROOT/'build_candidate'/GAME/'full_04'/r['path'])
    assert sha(path)==expected,r['path']
    records.append({'path':r['path'],'sha256':expected,'size':path.stat().st_size,'changed':expected!=r['sha256']})
assert sum(r['changed'] for r in records)==1
original=backup/'cache/0/original'
assert sha(original)==sha(BASELINE/PCK)
before=read_json(WORK/'q/candidate_user_before.json');after={}
for folder in before:
    path=Path(folder)
    after[folder]={p.relative_to(path).as_posix():{'size':p.stat().st_size,'sha256':sha(p)} for p in path.rglob('*') if p.is_file()} if path.exists() else None
assert before==after
assert not list(root.glob('*.hew-korean-new'))
result={'status':'PASS','completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'game_directory':str(root),'candidate':'full_04','files':records,'receipt':receipt,'original_backup':str(original),'backup_sha256':sha(original),'user_saves_unchanged':True,'post_install_game_launch':'NOT_RUN: 같은 후보의 격리된 실제 GPU 실행을 검수했으며 Steam 설치본 실행은 사용자에게 남김','zip_sha256':read_json(WORK/'package_1.0.0_r2/package.json')['zip_sha256']}
write_json(WORK/'final_audit/installation.json',result)
print('설치 해시·원본 백업·사용자 저장 보존 PASS')
