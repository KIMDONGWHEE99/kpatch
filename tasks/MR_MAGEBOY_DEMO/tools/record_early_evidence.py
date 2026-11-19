"""초기 위험 시험의 관찰 범위와 입력 지문을 묶습니다."""
import hashlib
import json
import sys
from pathlib import Path
from pck_tools import ROOT, WORK, BASELINE

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

risk = WORK/'risk_01'
tools = [ROOT/'tools/gdre_2.6.4/bin/gdre_tools.exe',ROOT/'tools/gdre_2.6.4/bin/gdre_tools.pck',ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf',Path(sys.executable)]
record={'game_id':'MR_MAGEBOY_DEMO','build_id':'25734075','G0':{'status':'PASS','baseline_manifest_sha256':sha(WORK/'baseline.json'),'pack_inventory_sha256':sha(WORK/'pck_inventory.json'),'source_pck_sha256':sha(BASELINE/'MR MAGEBOY DEMO.pck'),'tools':[{'name':p.name,'sha256':sha(p)} for p in tools]},
        'G1':{'status':'PASS','scope':'변경 없는 PCK 복사·스크립트 왕복·원본 정보 보존 장면 재저장·실제 GPU 한국어 글꼴 및 장면 문구 출력',
              'noop_pck_sha256':sha(WORK/'noop.pck'),'risk_report_sha256':sha(risk/'risk_report.json'),'resource_preservation_report_sha256':sha(risk/'resource_preservation_report.json'),
              'graphics':{'status':'PASS','image':str(risk/'main_menu.png'),'sha256':sha(risk/'main_menu.png'),'observations':'1440×720 실제 창에서 Steam 찜 목록에 추가해 주세요!가 정상 출력됨. 네모 글자·글자 누락·잘림 없음. 게임 제목 로고·아이콘 유지.',
                          'window_title':'MR_MAGEBOY_KO_QA_RISK_01','process_path':str(risk/'qa_game/MR MAGEBOY DEMO.exe'),'qa_pack_sha256':sha(risk/'qa_game/MR MAGEBOY DEMO.pck'),'device':'NVIDIA GeForce RTX 4060 Ti / Vulkan Forward+',
                          'executable_path_evidence':'실행 뒤 Get-Process Path 수집 및 computer-use 반환 창 app의 process 경로 확인'},
              'user_save_status':'PASS','before_sha256':sha(risk/'user_save_before.json'),'after_sha256':sha(risk/'user_save_after.json'),
              'limits':'소규모 장면·글꼴 시험이며 최종 전체 번역·대표 흐름의 G5를 대신하지 않음. Exit Confirm?은 이 시험에서 번역하지 않은 부모 코드의 기대 원문이며 최종 번역 목록에 별도 포함.'}}
assert json.loads((risk/'user_save_before.json').read_text(encoding='utf-8')) == json.loads((risk/'user_save_after.json').read_text(encoding='utf-8'))
assert record['G0']['source_pck_sha256']==record['G1']['noop_pck_sha256']
(WORK/'early_evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print('G0_PASS G1_PASS')
