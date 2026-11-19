"""정렬된 REA 기록에서 해당 실행의 종료 관측과 전체 메시지 범위를 고릅니다."""
import json


def final_observation(bundle, executable):
    canonical = lambda value: str(value).replace('\\', '/').casefold()
    matched = [r for r in bundle['records'] if r['operation'] == 'frida_session_status'
               and canonical(r['normalized_result'].get('target', '')) == canonical(executable)]
    if not matched:
        raise ValueError('대상 실행의 실제 관측이 없습니다.')
    identities = {(r['normalized_result']['session_id'], r['normalized_result']['pid']) for r in matched}
    if len(identities) != 1:
        raise ValueError('여러 프로세스가 같은 검수 경로를 사용했습니다.')
    terminal = [r for r in matched if r['normalized_result']['state'] == 'detached']
    if not terminal:
        raise ValueError('종료 뒤 전체 로그가 없습니다.')
    # 번들은 증거 ID순으로 정렬되므로 마지막 행은 시간순 마지막 관측이 아닙니다.
    final = max(terminal, key=lambda r: len(r['normalized_result']['messages']))
    observed = final['normalized_result']
    if observed['messages_truncated']:
        raise ValueError('종료 관측 메시지가 잘렸습니다.')
    key = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    final_messages = {key(m) for m in observed['messages']}
    for record in matched:
        if not {key(m) for m in record['normalized_result']['messages']} <= final_messages:
            raise ValueError('종료 관측이 이전 메시지 전체를 포함하지 않습니다.')
    ready = [m['payload'] for m in observed['messages']
             if m.get('payload', {}).get('kind') == 'guard_ready']
    if len(ready) != 1 or ready[0]['pid'] != observed['pid']:
        raise ValueError('격리 가드의 프로세스 연결이 없습니다.')
    if not any(canonical(m['path']) == canonical(executable) for m in ready[0]['modules']):
        raise ValueError('실제 프로세스 경로가 대상과 다릅니다.')
    return final
