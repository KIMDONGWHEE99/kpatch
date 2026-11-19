"""격리된 그래픽 검수 사본에 한 가지 화면 요청을 보내고 완료를 확인합니다."""
import argparse
import json
import time
from pck_tools import WORK

parser = argparse.ArgumentParser()
parser.add_argument('candidate')
parser.add_argument('id')
parser.add_argument('operation')
parser.add_argument('--values', default='{}')
args = parser.parse_args()
stage = WORK / args.candidate
assert stage.resolve().parent == WORK.resolve()
command = json.loads(args.values)
try:
    previous_count = len(json.loads((stage / 'screens.json').read_text(encoding='utf-8')))
except (FileNotFoundError, json.JSONDecodeError):
    previous_count = 0
command.update(id=args.id, operation=args.operation)
temporary = stage / 'command_next.json'
temporary.write_text(json.dumps(command, ensure_ascii=False), encoding='utf-8')
temporary.replace(stage / 'command.json')
deadline = time.monotonic() + command.get('wait', 1.2) + 15
while time.monotonic() < deadline:
    if (stage / 'screens.json').exists():
        try:
            events = json.loads((stage / 'screens.json').read_text(encoding='utf-8'))
            matching = [e for e in events[previous_count:] if e['id'] == args.id]
            if matching:
                event = matching[-1]
                print(json.dumps(event, ensure_ascii=False))
                assert event['status'] == 'PASS' and event['capture_error'] == 0
                break
        except json.JSONDecodeError:
            pass
    time.sleep(0.2)
else:
    raise TimeoutError('게임이 검수 요청을 완료하지 못했습니다: ' + args.id)
