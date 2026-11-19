"""사람이 판독한 실제 GPU 화면을 후보 지문과 연결하고 설치 전 기준을 고정합니다."""
from common import *
import re
Q=WORK/'q';stage=WORK/'final_audit'
scenes=[]
groups=[('review_01/screens','full_01',['candidate_menu','settings_top','settings_middle','settings_bottom','settings_language','credits','newgame_dialogue','command_tooltip','pause','korean_save_name']),('APPDATA/candidate','full_03',['final_menu','final_load_list','final_load_confirmation','final_tooltip_fixed','loaded_advanced','trade','roads','exploration','provinces','aristocrats','institutions','production','country_tasks','production_options','production_line','advances_tree','glory_result','glory_result_bottom']),('APPDATA/candidate','full_04',['final04_loaded','final04_province','final04_reloaded','final04_result_top','final04_result_bottom'])]
for folder,candidate,names in groups:
    for name in names:
        path=Q/folder/(name+'.png');assert path.exists()
        scenes.append({'file':str(path.relative_to(WORK)),'sha256':sha(path),'candidate':candidate,'status':'PASS','review':'실제 표시 프레임을 열어 한국어·글리프·줄바꿈·버튼 배치를 판독. 스크롤 목록은 해당 캡처 범위.'})
known=[]
baseline=(Q/'baseline.stderr.log').read_text(encoding='utf8')
candidate=(Q/'candidate.stderr.log').read_text(encoding='utf8')
def diagnostic(line):
    return re.sub(r'\b\d+\b','<N>',line)
known={diagnostic(line) for line in baseline.splitlines() if line.startswith(('WARNING:','ERROR:'))}
actual={diagnostic(line) for line in candidate.splitlines() if line.startswith(('WARNING:','ERROR:'))}
assert actual<=known,actual-known
assert not re.search(r'missing glyph|glyph.+not found|unicode.+not found',candidate,re.I)
for folder in [Q,Q/'session_final_a',Q/'session_final_b']:
    result=read_json(folder/'candidate_exit.json')
    assert result['exit_code']==0 and result['user_saves_unchanged']
    assert read_json(folder/'candidate_user_before.json')==read_json(folder/'candidate_user_after.json')
launch=read_json(Q/'candidate_launch.json');boundary=read_json(Q/'candidate_boundary.json')
windows=read_json(Q/'final_window.json')
assert windows and all('q\\candidate\\HowEmpiresWork.exe' in w['app'] for w in windows)
assert launch['pck_sha256']==boundary['qa_sha256']==sha(Q/'candidate'/PCK)
assert boundary['source_sha256']==sha(ROOT/'build_candidate'/GAME/'full_04'/PCK)
log=(Q/'candidate.log').read_text(encoding='utf8')
assert 'D3D12 12_0 - Forward+' in log and 'NVIDIA GeForce RTX 4060 Ti' in log
report={'status':'PASS','scope':'기재된 대표 화면·초반 대화·기능 해금 후 관리 화면·본편/영광 결과·한글 저장/재실행/불러오기·정상 종료. 전체 회차·전체 분기 완주 검수는 아님.','candidate_sha256':boundary['source_sha256'],'qa_sha256':boundary['qa_sha256'],'observed_window':windows,'launch':launch,'graphics_device':'D3D12 Forward+ / NVIDIA GeForce RTX 4060 Ti','engine':'4.7.stable.official.5b4e0cb0f','screens':scenes,'screen_count':len(scenes),'candidate_specific_loading_errors':0,'missing_glyph_warnings':0,'user_saves_unchanged':True,'original_diagnostics':sorted(known),'fixes':[{'id':'QA-001','status':'PASS','issue':'일부 기본 설명창의 어두운 글자색','fix':'공통된 8개 테마의 TooltipLabel 글자색 지정','evidence':'final_tooltip_fixed.png + 8개 최종 테마 재열기'}, {'id':'QA-002','status':'PASS','issue':'주 이름 접두어와 지명 붙음','fix':'PROVINCE_INITIAL을 주: 와 공백으로 변경','evidence':'final04_province.png 및 final04_reloaded.png'}],'test_only_actions':'Steam 초기화 차단·저장/로그 격리·화면 상태 수집. 후반 표본은 원작 개발 명령으로 기능 해금 및 결과 조건 진입. 일부 초기 화면은 실제 UI 조작, 이후는 게임 메서드와 창 내부 입력으로 캡처. 운영체제 포인터 간섭 없음.','physical_korean_ime':'NOT_RUN: 자동 입력 도구가 Godot 입력란에 문자를 보내지 못해 엔진 입력란에 한글 이름을 지정하고 실제 저장 처리·로드 및 전체 한글 글리프 검사를 수행.','reuse_reason':'full_01→03은 기본 설명창 8개 테마와 보조 글꼴 변경만 추가되어 해당 부분 재검수. full_03→04는 PROVINCE_INITIAL 1개 값만 바뀌어 주 생성·저장·재실행·불러오기 재검수. 나머지 자원 바이트와 코드 지문을 비교함.'}
write_json(stage/'runtime_qa.json',report)
checks={name:read_json(stage/name)['status'] for name in ['static_summary.json','runtime_qa.json','install_preflight.json']}
assert all(x=='PASS' for x in checks.values())
write_json(stage/'install_readiness.json',{'status':'PASS','candidate_sha256':report['candidate_sha256'],'checks':checks,'zip_sha256':read_json(WORK/'package_1.0.0_r2/package.json')['zip_sha256'],'user_authorization':'화면 검수하고 문제없으면 한글패치 설치까지 요청; 지정 D: 설치본 적용 범위','publication':'NOT_REQUESTED'})
print('G5 PASS:',len(scenes),'reviewed captures; install readiness PASS')
