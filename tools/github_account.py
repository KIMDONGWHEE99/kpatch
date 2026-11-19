"""이 PC의 Git 자격 증명 관리자에 저장된 GitHub 로그인으로 어떤 계정에 접근되는지 확인합니다(읽기 전용).

토큰 값은 화면이나 파일에 남기지 않고 api.github.com 요청의 인증 머리말에만 씁니다.
기존 게임 공개 도구(tasks/HOW_EMPIRES_WORK/publish_github.py)와 같은 방식입니다.
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request

ENV = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
AGENT = 'kpatch-publisher'


def token():
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n', text=True,
                            capture_output=True, env=ENV, timeout=30)
    if result.returncode != 0:
        raise SystemExit('저장된 GitHub 로그인 정보를 쓸 수 없습니다(다시 로그인 필요).')
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if not fields.get('password'):
        raise SystemExit('저장된 GitHub 로그인 정보가 없습니다.')
    return fields['password']


def api(secret, method, path, payload=None, raw=None, content_type='application/json'):
    url = path if path.startswith('https://') else 'https://api.github.com' + path
    if urllib.parse.urlsplit(url).hostname not in ('api.github.com', 'uploads.github.com'):
        raise ValueError('GitHub 이외의 주소로는 보내지 않습니다.')
    data = raw if raw is not None else (json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None)
    request = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': 'Bearer ' + secret, 'Accept': 'application/vnd.github+json', 'Content-Type': content_type, 'User-Agent': AGENT})
    with urllib.request.urlopen(request, timeout=600) as response:
        body = response.read()
        return json.loads(body) if body else {}


def main():
    secret = token()
    user = api(secret, 'GET', '/user')
    print(json.dumps({'login': user['login'], 'id': user['id'], 'public_repos': user.get('public_repos'),
                      'noreply_email': f"{user['id']}+{user['login']}@users.noreply.github.com"}, ensure_ascii=False))


if __name__ == '__main__':
    main()
