"""분리 검수의 실제 프로세스·오류·저장 무결성을 모읍니다. 화면 PASS를 생성하지 않습니다."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from qa_runtime_observation import final_observation

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/COBALT_MINER'
RUNS = [
    ('qa_ko03_terminal_a', '통합 후보, 추가 입력 관측 포함'),
    ('qa_ko03_terminal_a_clean', '통합 후보, 추가 입력 관측 제외'),
    ('qa_ko03_terminal_a_settled', '통합 후보, 새 게임 뒤 약2분·이어하기 뒤87초 이상 대기'),
    ('qa_original_terminal_a_control', '원본 데이터·원본 실행 모듈'),
    ('qa_original_terminal_a_fast', '원본 데이터·원본 실행 모듈, 후보처럼 초반에 저장하고 상환'),
    ('qa_ko03_dat_only_a02', '후보 데이터·원본 실행 모듈'),
    ('qa_ko03_no_fonts_a01', '후보 데이터에서 글꼴 변경 제외·원본 실행 모듈'),
    ('qa_ko03_no_media_a01', '후보 데이터에서 이미지 변경 제외·원본 실행 모듈'),
    ('qa_ko03_no_objects_a01', '객체 자료 묶음만 원본 복원·원본 실행 모듈'),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rows = []
    for name, variant in RUNS:
        folder = WORK / name
        evidence = folder / 'evidence'
        needed = [evidence / n for n in ('prelaunch.json', 'rea_runtime.json', 'post_integrity.json')]
        if not all(p.exists() for p in needed):
            rows.append(dict(run=name, variant=variant, status='NOT_RUN'))
            continue
        pre, bundle, post = [json.loads(p.read_text(encoding='utf-8')) for p in needed]
        executable = folder / 'game/COBALT MINER.exe'
        last = final_observation(bundle, executable)
        state = last['normalized_result']
        assert state['state'] == 'detached' and not state['messages_truncated']
        assert post['status'] == 'PASS'
        for entry in pre['files']:
            assert digest(folder / 'game' / entry['path']) == entry['sha256']
        errors = [m for m in state['messages'] if m.get('type') == 'error'
                  or m.get('payload', {}).get('kind') in ('exception', 'native_exception')]
        probes = [m['payload'] for m in state['messages']
                  if m.get('payload', {}).get('kind') == 'qa_invalid_cleanup_object']
        rows.append(dict(run=name, variant=variant,
                         status='FAIL' if errors else 'PASS',
                         status_scope='이 실행에서 관측한 접근 오류 유무. 번역·전체 그래픽 게이트가 아님',
                         pid=state['pid'], actual_path=state['target'], session_id=state['session_id'],
                         evidence_id=last['evidence_id'], source=pre['source'],
                         dat_sha256=pre['qa_dat_sha256'], files=pre['files'], exceptions=errors,
                         probes=probes, user_files_unchanged=len(post['after']['files']),
                         dependencies=[dict(path=str(p.relative_to(ROOT)), sha256=digest(p)) for p in needed]))
    report = dict(game_id='COBALT_MINER', steam_build='24347666', status='FAIL',
                  generated_utc=datetime.now(timezone.utc).isoformat(),
                  trigger='마지막 상환 직전 새 게임→실제 저장→실제100달러 버튼→A엔딩→메뉴→실제 이어하기→WM_CLOSE',
                  observed_failure='COBALT MINER.exe RVA0xdd58에서 화면 객체의 sprite+0x1c 읽기 실패',
                  runs=rows,
                  limits=['마지막 상태를 준비한 검수 사본이며 전체 퀘스트 완주가 아님',
                          '초반 저장·빠른 엔딩 진입의 원본에서도 같은 RVA와 호출 경로 오류가 재현됨. 패치 고유 오류로 단정 불가',
                          '원본 대조1회의 무오류만으로 원본에 잠재 결함이 없다고 단정하지 않음',
                          '각 요소 제외 결과만으로 남은 요소의 원인을 확정하지 않음'])
    out = WORK / 'runtime_planning_01/close_failure_matrix.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({r['run']: r['status'] for r in rows}, ensure_ascii=False))


if __name__ == '__main__':
    main()
