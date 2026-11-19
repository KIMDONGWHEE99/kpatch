"""실행 중인 검수 사본에 요청을 보내고 화면 상태와 캡처를 기록합니다.

사용: python qa_control.py <run_id> <이름> '<요청 JSON>'
  예) python qa_control.py risk_01 first '{"action":"dump"}'
요청 JSON의 action: dump / press(node) / call(node, method, args) / set / locale / click / hover / quit
캡처는 항상 <이름>.png 로 저장합니다. HOW_EMPIRES_WORK의 qa_control.py를 고쳐 썼습니다.
"""
import collections
import datetime
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import WORK, save, load, sha


def main():
    run_id, name = sys.argv[1], sys.argv[2]
    request = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {'action': 'dump'}
    run = WORK / 'qa' / run_id
    userdata = Path(load(run / 'launch.json')['userdata'])
    if str(request.get('node', '')).startswith('*'):
        # '*끝부분' 으로 적으면 직전 상태에서 경로가 그 글자로 끝나는 노드를 찾아 전체 경로로 바꿉니다.
        previous = load(userdata / 'qa_state.json')
        matches = [n['path'] for n in previous['nodes'] if n['path'].endswith(request['node'][1:])]
        assert len(matches) == 1, f'노드 {len(matches)}개 일치: {matches[:3]}'
        request['node'] = matches[0]
    request.update(token=datetime.datetime.now().isoformat(), capture=name)
    path = userdata / 'qa_request.json'
    assert not path.exists(), '앞선 요청 처리 대기 중'
    path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
    limit = time.monotonic() + 40
    state = {}
    while time.monotonic() < limit:
        try:
            state = load(userdata / 'qa_state.json')
        except (OSError, ValueError):
            state = {}
        if state.get('request') == request:
            break
        time.sleep(0.2)
    if request['action'] == 'quit':
        # 종료 요청은 응답 상태를 남기지 않으므로 요청 파일이 사라졌는지만 봅니다.
        print('quit requested', 'accepted' if not path.exists() else 'pending')
        return
    assert state.get('request') == request, '검수 프로세스가 요청을 처리하지 않음'
    states = run / 'states'
    states.mkdir(exist_ok=True)
    capture = userdata / (name + '.png')
    if capture.exists():
        shutil.copy2(capture, states / (name + '.png'))
        state['capture_sha256'] = sha(states / (name + '.png'))
    save(states / (name + '.json'), state)
    nodes = state['nodes']
    missing = [n for n in nodes if n.get('missing_glyphs')]
    clipped = [n['path'] for n in nodes if n.get('clipped')]
    hangul = sum(1 for n in nodes if any('가' <= c <= '힣' for c in n.get('shown', '')))
    latin_only = [n['shown'][:40] for n in nodes if n.get('shown') and not any('가' <= c <= '힣' for c in n['shown']) and any(c.isalpha() for c in n['shown'])]
    mode = sys.argv[4] if len(sys.argv) > 4 else ''
    if 'buttons' in mode:
        # 다음 요청에 쓸 버튼 경로를 찾을 때만 씁니다(뒤쪽 90자).
        for n in nodes:
            if 'disabled' in n:
                print('BTN', n['path'][-90:], '|', n.get('shown', '')[:24], '|', n.get('tooltip', '')[:20], '|', [round(v) for v in n['rect']])
    if 'texts' in mode:
        for n in nodes:
            if n.get('shown'):
                print('TXT', n['class'][:5], n['path'][-46:], '|', n['shown'][:70].replace(chr(10), ' / '))
    print(json.dumps({'name': name, 'note': state.get('note'), 'scene': state['current_scene'], 'locale': state['locale'],
                      'text_nodes': len(nodes), 'hangul_nodes': hangul, 'missing_glyph_nodes': [(n['path'][-60:], n['missing_glyphs']) for n in missing][:10],
                      'clipped': [c[-70:] for c in clipped][:10], 'non_korean_texts': list(collections.Counter(latin_only))[:40],
                      'capture': str(states / (name + '.png')) if capture.exists() else None}, ensure_ascii=False))


if __name__ == '__main__':
    main()
