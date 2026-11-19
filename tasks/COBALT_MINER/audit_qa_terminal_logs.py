"""기존 검수 증거를 고치지 않고 종료 로그 선택의 누락 여부를 재검사합니다."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from qa_runtime_observation import final_observation

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/COBALT_MINER'


def main():
    rows = []
    for path in sorted(WORK.glob('qa_*/evidence/rea_runtime.json')):
        folder = path.parent.parent
        bundle = json.loads(path.read_text(encoding='utf-8'))
        row = dict(run=folder.name, bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        try:
            final = final_observation(bundle, folder / 'game/COBALT MINER.exe')
            n = final['normalized_result']
            errors = [m for m in n['messages'] if m.get('type') == 'error'
                      or m.get('payload', {}).get('kind') in ('exception', 'native_exception')]
            row.update(status='FAIL' if errors else 'PASS', terminal_evidence_id=final['evidence_id'],
                       messages=len(n['messages']), errors=errors, pid=n['pid'])
        except (ValueError, KeyError) as error:
            row.update(status='BLOCKED', reason=str(error))
        review = path.parent / 'screen_review.json'
        if review.exists():
            old = json.loads(review.read_text(encoding='utf-8'))
            row['existing_review'] = dict(status=old.get('status'), sha256=hashlib.sha256(review.read_bytes()).hexdigest(),
                                          evidence_id=old.get('runtime', {}).get('evidence_id'))
            row['review_requires_correction'] = old.get('status') == 'PASS' and row['status'] != 'PASS'
        rows.append(row)
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                  status='FAIL' if any(r.get('review_requires_correction') for r in rows) else 'PASS',
                  scope='기존 화면 PASS 기록에 숨은 종료 오류가 있는지 확인. 다른 화면·분기 검사를 대체하지 않음',
                  selection='동일 프로세스의 종료 관측 중 이전 메시지를 모두 포함하는 관측. 번들의 정렬 순서는 무시',
                  runs=rows)
    (WORK / 'runtime_planning_01/terminal_log_reaudit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=report['status'], runs=len(rows),
                          status_counts={s:sum(r['status']==s for r in rows) for s in ('PASS','FAIL','BLOCKED')},
                          corrections=[r['run'] for r in rows if r.get('review_requires_correction')]), ensure_ascii=False))


if __name__ == '__main__':
    main()
