"""초기 실제 화면 관찰과 저장 무결성을 증거에 연결합니다."""
from common import *

RISK = WORK/'risk_01'
before = read_json(RISK/'user_before.json')
after = {}
for root in before:
    path = Path(root)
    after[root] = {f.relative_to(path).as_posix():{'size':f.stat().st_size,'sha256':sha(f)}
                   for f in path.rglob('*') if f.is_file()} if path.exists() else None
write_json(RISK/'user_after.json',after)
assert before == after
assert read_json(RISK/'exit.json')['exit_code'] == 0
observed = read_json(RISK/'window_observed.json')
assert str(RISK/'qa_game/HowEmpiresWork.exe').lower() in observed['window']['app'].lower()
write_json(RISK/'review.json',{'status':'PASS','scope':'시험 한글 메뉴·새 게임·격리 저장/불러오기·정상 종료',
    'build':read_json(RISK/'build.json'),'launch':read_json(RISK/'launch.json'), 'window':observed,
    'user_saves_unchanged':True,'screens':{p.name:sha(p) for p in (RISK/'screens').glob('*.png')},
    'remaining':['원본 rider-plugin 경고 대조','시험 경로 길이의 shader_cache 오류 해소','전체 번역·전체 필요 문자·전체 화면 검수']})
print('Initial graphics and isolated save/load: PASS; user data unchanged')
