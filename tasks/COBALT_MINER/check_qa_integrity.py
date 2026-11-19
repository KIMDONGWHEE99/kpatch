"""실행 전후 설치본·사용자 저장의 내용 지문을 비교합니다."""
import json
import sys
from prepare_qa import WORK, snapshot

for run in sys.argv[1:]:
    if not run.startswith('qa_') or not run.replace('_', '').isalnum():
        raise ValueError('잘못된 실행 ID')
    evidence = WORK / run / 'evidence'
    before = json.loads((evidence / 'prelaunch.json').read_text(encoding='utf-8'))['before']
    after = snapshot()
    report = {'status': 'PASS' if before == after else 'FAIL', 'after': after}
    (evidence / 'post_integrity.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(run, report['status'], len(after['files']))
    if before != after:
        raise SystemExit('감시한 설치본·저장 변경 감지')
