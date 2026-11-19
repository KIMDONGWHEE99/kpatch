"""전용 공개 저장소를 만들고, 준비한 문서·설치기 소스를 올리고, 검증된 ZIP을 릴리스에 첨부합니다.

HOW_EMPIRES_WORK의 publish_github.py를 이 게임에 맞게 고쳤습니다. 먼저 prepare_github.py를 실행해 둡니다.
저장된 GitHub 로그인(자격 증명 관리자)을 쓰며 토큰 값은 화면이나 파일에 남기지 않습니다.
올린 뒤에는 릴리스의 ZIP을 다시 내려받아 해시가 같은지 확인합니다.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from github_account import token, api
from prepare_github import PUBLIC, STAGE, REMOTE, TAG, NAME, OWNER, REPOSITORY, sha, read, write

FULL = OWNER + '/' + REPOSITORY
ENV = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')


def git(args, cwd=None):
    result = subprocess.run(['git', *args], cwd=cwd, env=ENV, capture_output=True, text=True, encoding='utf8', errors='replace', timeout=300)
    assert result.returncode == 0, (args[0], result.stderr[-1500:])
    return result.stdout.strip()


def save_state(state):
    write(PUBLIC / 'publish_state.json', json.dumps(state, ensure_ascii=False, indent=2))


def main():
    manifest = read(PUBLIC / 'publication_manifest.json')
    for row in manifest['files']:
        assert sha(STAGE / row['path']) == row['sha256'], row['path']
    archive = Path(manifest['zip']['path'])
    assert sha(archive) == manifest['zip']['sha256']
    assert not (PUBLIC / 'publish_state.json').exists(), '이미 공개 기록이 있습니다. 다시 올리지 않습니다.'
    secret = token()
    user = api(secret, 'GET', '/user')
    assert user['login'] == OWNER, '로그인된 계정이 기대와 다릅니다.'
    try:
        api(secret, 'GET', '/repos/' + FULL)
    except urllib.error.HTTPError as error:
        assert error.code == 404, error.code
    else:
        raise RuntimeError('같은 이름의 저장소가 이미 있으므로 덮어쓰지 않습니다.')
    repository = api(secret, 'POST', '/user/repos', {
        'name': REPOSITORY, 'description': 'Clicky Islands 비공식 한국어 패치 — Windows Steam 빌드 26701014',
        'private': False, 'auto_init': False, 'has_wiki': False, 'has_projects': False})
    assert repository['full_name'] == FULL and not repository['private']
    state = {'repository_id': repository['id'], 'repository': repository['html_url'], 'phase': 'REPOSITORY_CREATED'}
    save_state(state)
    print('저장소 생성 완료', repository['html_url'], flush=True)
    local = PUBLIC / 'repository'
    assert not local.exists()
    local.mkdir()
    git(['init', '-q', '-b', 'main'], local)
    git(['config', 'user.name', OWNER], local)
    git(['config', 'user.email', str(user['id']) + '+' + OWNER + '@users.noreply.github.com'], local)
    git(['config', 'core.autocrlf', 'false'], local)
    git(['remote', 'add', 'origin', REMOTE + '.git'], local)
    for row in manifest['files']:
        dest = local / row['path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(STAGE / row['path'], dest)
    git(['add', '-A'], local)
    changed = git(['diff', '--cached', '--name-only'], local).splitlines()
    assert set(changed) == {r['path'] for r in manifest['files']}
    git(['commit', '-q', '-m', '한국어 패치 1.0.0 r1과 설치·검증 안내 공개'], local)
    commit = git(['rev-parse', 'HEAD'], local)
    git(['push', '-q', '-u', 'origin', 'main'], local)
    state.update(commit=commit, phase='COMMITTED')
    save_state(state)
    print('커밋 업로드 완료', commit, flush=True)
    remote = api(secret, 'GET', '/repos/' + FULL + '/commits/main')
    assert remote['sha'] == commit
    release = api(secret, 'POST', '/repos/' + FULL + '/releases', {
        'tag_name': TAG, 'target_commitish': commit, 'name': '한국어 패치 1.0.0 r1',
        'body': (PUBLIC / 'release_notes.md').read_text(encoding='utf8'), 'draft': True, 'prerelease': False})
    state.update(release_id=release['id'], phase='DRAFT_RELEASE')
    save_state(state)
    assets = []
    for path, media in [(archive, 'application/zip'), (STAGE / 'SHA256SUMS.txt', 'text/plain')]:
        url = release['upload_url'].split('{', 1)[0] + '?' + urllib.parse.urlencode({'name': path.name})
        print('파일 첨부 중', path.name, path.stat().st_size, flush=True)
        asset = api(secret, 'POST', url, raw=path.read_bytes(), content_type=media)
        assert asset['state'] == 'uploaded' and asset['size'] == path.stat().st_size and asset['name'] == path.name
        if asset.get('digest'):
            assert asset['digest'] == 'sha256:' + sha(path)
        assets.append({'id': asset['id'], 'name': asset['name'], 'size': asset['size'], 'url': asset['browser_download_url'], 'sha256': sha(path)})
        state['assets'] = assets
        save_state(state)
    release = api(secret, 'PATCH', '/repos/' + FULL + '/releases/' + str(release['id']), {'draft': False, 'make_latest': 'true'})
    assert not release['draft'] and release['tag_name'] == TAG
    state.update(release=release['html_url'], phase='PUBLISHED')
    save_state(state)
    # 공개된 주소에서 ZIP을 로그인 없이 다시 내려받아 해시를 확인합니다.
    # 초안 상태에서 받은 첨부 주소는 공개 뒤 바뀌므로(2026-11-19 404 발생), 공개된 릴리스의 주소를 다시 읽습니다.
    for asset in assets:
        asset['url'] = next(a['browser_download_url'] for a in release['assets'] if a['name'] == asset['name'])
    state['assets'] = assets
    download = next(a['url'] for a in assets if a['name'] == NAME)
    fetched = None
    for _ in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(download, headers={'User-Agent': 'kpatch-publisher'}), timeout=300) as response:
                fetched = response.read()
            break
        except urllib.error.HTTPError:
            time.sleep(3)
    import hashlib
    verified = fetched is not None and hashlib.sha256(fetched).hexdigest() == manifest['zip']['sha256']
    state.update(public_download_verified=verified, phase='VERIFIED' if verified else 'PUBLISHED_UNVERIFIED')
    save_state(state)
    assert not git(['status', '--porcelain'], local)
    print(json.dumps({'repository': repository['html_url'], 'commit': commit, 'release': release['html_url'],
                      'assets': len(assets), 'public_download_verified': verified}, ensure_ascii=False), flush=True)
    assert verified, '공개된 ZIP의 해시를 확인하지 못했습니다.'


if __name__ == '__main__':
    main()
