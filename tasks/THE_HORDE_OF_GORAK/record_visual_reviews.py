"""제작자가 직접 판독한 화면만 해시와 함께 기록한다. 자동 화면 판정기는 아니다."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'working_private/THE_HORDE_OF_GORAK'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(run, session, pid, native, cases, limitations):
    folder = BASE / run / 'evidence'
    before = json.loads((folder / 'prelaunch.json').read_text(encoding='utf-8'))
    integrity = json.loads((folder / 'post_integrity.json').read_text(encoding='utf-8'))
    rows = []
    for title, patterns, observation, status in cases:
        paths = sorted({p for pattern in patterns for p in folder.glob(pattern)})
        if not paths:
            raise ValueError((run, title, patterns))
        rows.append({'name': title, 'status': status, 'observation': observation,
                     'images': [{'path': p.name, 'sha256': sha(p)} for p in paths]})
    report = {'game_id': 'THE_HORDE_OF_GORAK', 'source_build': 'steam_26336311',
              'run': run, 'reviewer': '제작자 직접 육안 판독',
              'status': 'PASS' if all(row['status'] == 'PASS' for row in rows) else 'NOT_RUN',
              'scope': '아래 관찰 항목에만 해당하며 G5 전체 완료와 구분함',
              'session_id': session, 'pid': pid, 'native_candidate': native,
              'dat_sha256': before['qa_dat_sha256'],
              'prelaunch_sha256': sha(folder / 'prelaunch.json'),
              'runtime_evidence_sha256': sha(folder / 'rea_runtime.json'),
              'normal_exit_observed': True, 'native_exceptions': 0, 'hook_errors': 0,
              'messages_truncated': False, 'post_integrity': integrity,
              'post_integrity_sha256': sha(folder / 'post_integrity.json'),
              'cases': rows, 'limitations': limitations}
    (folder / 'visual_review_01.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(run, len(rows), '개 화면군 기록')


def main():
    record('qa_full02', 'dc1f8378-df33-43b6-813a-467fa04037f9', 28712, 'native_candidate_02', [
        ('메뉴·일반 저장 불러오기', ['02*.jpg', '03*.jpg', '04*.jpg', '05*.jpg'], '일반 플레이에서 저장한 오크 오두막·회관과 자원이 복원됨. 메뉴와 로딩 문구 정상.', 'PASS'),
        ('진행 상황 줄 정렬 수정', ['06*.jpg'], '왼쪽 항목과 오른쪽 수치의 기준선이 각 행에서 일치함.', 'PASS'),
        ('원정 종료·새 게임 확인·취소', ['07*.jpg', '08*.jpg', '09*.jpg'], '원정 종료 후 지도 복귀. 새 게임 확인 문구와 예/아니요가 잘리지 않음. 아니요로 취소됨.', 'PASS'),
    ], ['첫 시도는 창 크기 조정 시점에 종료되어 원인 미확정. rea_window_closed_attempt.json과 01_menu_full_size.jpg에 별도로 보존하며 정상 종료 근거에서 제외.', '후보02에서 확인한 항목에 한정. 모든 회차 플레이 완료를 뜻하지 않음.'])
    record('qa_late02', '5cc015f3-5ca9-4a98-92eb-070ba3192e3b', 11636, 'native_candidate_02', [
        ('병사 도감 19종', ['04*.jpg', '05*.jpg', '06*.jpg', '07*.jpg', '08_unit_spider.jpg', '08_unit_airship.jpg', '08_unit_catapult.jpg'], '운반꾼부터 투석기까지 19종 설명과 수치를 판독. 글자 깨짐과 본문 잘림 없음.', 'PASS'),
        ('주술사 탑과 주문 3종', ['09*.jpg', '10*.jpg'], '화염구·분노·박쥐 차원문 수치와 줄바꿈 확인.', 'PASS'),
        ('건물·거래·강화', ['11*.jpg', '12*.jpg', '13*.jpg', '14*.jpg', '15*.jpg', '16*.jpg', '17*.jpg', '18*.jpg', '24*.jpg', '25*.jpg', '26*.jpg', '28*.jpg', '29*.jpg', '30*.jpg', '31*.jpg', '32*.jpg'], '오우거 집·대장간·병영·시장·금광·트롤 오두막·기병 목장·야수 동굴·벌목소·작업장과 강화 설명 확인. 29_workshop 파일명과 달리 실제 화면은 벌목소이며 31이 작업장.', 'PASS'),
        ('성채 구출·결과 정렬·다음 성채', ['19*.jpg', '20*.jpg'], '구출 연출 후 성채 함락 결과표의 항목/수치가 정렬됨. 계속 카운트다운 후 설원 성채2 진입.', 'PASS'),
        ('첫 연구 선택지', ['21*.jpg', '22*.jpg', '23*.jpg', '33*.jpg'], '공성/포탑/폭격기구 피해량20%와 근접 피해량30% 설명 및 연구 시작을 확인. 33은 연구 진행 중이며 다음 단계 완료로 판정하지 않음.', 'PASS'),
        ('저장·메뉴 복귀', ['34*.jpg', '35*.jpg'], '진행 상황과 저장 후 메뉴 복귀 확인. 게임 종료 버튼 후 REA detached 확인.', 'PASS'),
    ], ['qa_fixture_02 검수용 개발 그룹/객체 표시 4바이트와 건물/자원 프로필을 사용함. 정상 성장 과정 전체 검증은 아님.', '용 도감 항목은 원본 이벤트의 방향값 문제로 잠금 표시. 08_unit_dragon_locked는 용 설명 검수 통과 근거가 아님.', '27_loot_upgrade는 화면 우측에서 설명 말풍선 배경 일부가 화면 경계에 걸림. 문장은 보이나 중앙 재확인 필요.', '개발 도구 전체 단락·나머지 연구 단계·마지막 성채 이후는 별도 검수 필요.'])
    record('qa_research01', 'cc554dd6-dd5e-454f-9099-689d23ecb6fd', 37152, 'native_candidate_03', [
        ('native03 첫 실행·전장 로딩', ['01*.jpg', '02*.jpg', '03*.jpg'], '추가 네이티브 번역을 포함한 실제 실행 파일에서 메뉴와 로딩·전장·연구 완료 알림이 정상 표시됨.', 'PASS'),
        ('두 번째 연구 선택지', ['04*.jpg', '05*.jpg', '06*.jpg'], '매번 금 채굴량+1과 원거리 유닛 피해량30% 설명을 판독. 깨짐·잘림 없음.', 'PASS'),
        ('메뉴 복귀·종료', ['07*.jpg'], '저장 후 메뉴 복귀 및 게임 종료 버튼 뒤 REA detached 확인.', 'PASS'),
    ], ['qa_fixture_02와 buildings_research_stage1 프로필 사용. 배포 DAT와 구분함.'])


if __name__ == '__main__':
    main()
