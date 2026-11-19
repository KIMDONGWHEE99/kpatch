"""kpatch 프로젝트의 공개용 사본을 걸러서 GitHub 공개 저장소에 올립니다.

이 작업 저장소(D:\\kpatch)를 그대로 push하지 않습니다. 추적 중인 파일 가운데 아래를 뺀 사본을 따로 만들어 올립니다.
  1. 게임 원문이 든 번역 원본 폴더(tasks/<게임>/translations)
  2. 영어 문구와 한글 번역이 한 줄에 짝지어 든 줄이 많은 파일(번역표가 박힌 도구)
공개 사본의 커밋 작성자는 GitHub가 주는 비공개 주소(noreply)로 적어 개인 이메일이 드러나지 않게 합니다.
올리기 전에 이메일·계정 식별자·토큰 형식이 없는지 다시 검사하고, 하나라도 있으면 멈춥니다.

사용: python tools/publish_project.py            (점검과 사본 준비만)
      python tools/publish_project.py --publish  (저장소 생성 또는 갱신까지)
"""
import datetime
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from github_account import token, api

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'working_private/_publication/kpatch_public'
REPOSITORY = 'kpatch'
DESCRIPTION = '게임 한글패치 제작 절차·검증 도구·작업 기록 (비공식, 걸러 낸 공개 사본)'
ENV = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
PAIR = re.compile(r'''["'][^"']*[A-Za-z]{3,}[^"']*["']\s*[:,=]\s*["'][^"']*[\uac00-\ud7a3]''')
PAIR_LIMIT = 25
QUOTED_KOREAN = re.compile(r'''["'][^"'\n]*[가-힣][^"'\n]*["']''')
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
SECRET = re.compile(r'7656119[0-9]{10}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|Bearer [A-Za-z0-9]{20,}')
BINARY = {'.ttf', '.otf', '.png', '.jpg', '.jpeg'}


def git(args, cwd=ROOT):
    result = subprocess.run(['git', *args], cwd=cwd, env=ENV, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f'git {args[0]} 실패: {result.stderr[-1500:]}')
    return result.stdout.strip()


def select():
    """공개할 파일과 뺄 파일을 나눕니다."""
    if git(['status', '--porcelain']):
        raise SystemExit('작업 폴더에 커밋하지 않은 변경이 있습니다. 먼저 로컬에 커밋해 주세요.')
    listed = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout.decode('utf-8')
    included, excluded, problems = [], [], []
    for name in [n for n in listed.split('\0') if n]:
        path = ROOT / name
        if '/translations/' in name or '/translation/' in name:
            excluded.append({'path': name, 'reason': '번역 원본 폴더(게임 원문 포함)'})
            continue
        if path.suffix.lower() not in BINARY:
            text = path.read_text(encoding='utf-8', errors='replace')
            pairs = sum(1 for line in text.splitlines() if PAIR.search(line))
            if pairs >= PAIR_LIMIT and path.suffix.lower() != '.md':
                excluded.append({'path': name, 'reason': f'영어 문구와 한글 번역이 짝지어진 줄 {pairs}개(번역표가 든 도구)'})
                continue
            lines = text.splitlines()
            korean = sum(1 for line in lines if QUOTED_KOREAN.search(line))
            if korean >= 100 and korean >= 0.6 * len(lines) and path.suffix.lower() not in ('.md', '.html', '.txt'):
                excluded.append({'path': name, 'reason': f'따옴표 안 한글 문구가 {korean}줄로 대부분인 파일(번역표가 든 도구)'})
                continue
            for address in set(EMAIL.findall(text)):
                if 'noreply' in address or address.endswith(('example.com', 'anthropic.com')) or '/third_party/' in name:
                    continue
                problems.append({'path': name, 'kind': 'email'})
            if SECRET.search(text):
                problems.append({'path': name, 'kind': 'account id or token'})
        included.append(name)
    return included, excluded, problems


def note(head, included, excluded):
    reasons = {}
    for row in excluded:
        key = '번역 원본 폴더' if row['reason'].startswith('번역 원본') else '번역표가 든 도구'
        reasons[key] = reasons.get(key, 0) + 1
    lines = ['# 공개 사본 안내', '',
             '이 저장소는 한글패치 작업 폴더를 **걸러서 만든 공개 사본**입니다. 작업 저장소를 그대로 올린 것이 아닙니다.', '',
             f'- 원본 커밋: `{head[:12]}` · 만든 날: {datetime.date.today().isoformat()}',
             f'- 포함한 파일: {len(included)}개 · 뺀 파일: {len(excluded)}개',
             '- 뺀 것: 게임 원문이 든 번역 원본 폴더(`tasks/<게임>/translations`), 영어 문구와 한글 번역이 표로 들어 있는 도구 파일',
             '  (' + ', '.join(f'{k} {v}개' for k, v in sorted(reasons.items())) + ')',
             '- 처음부터 들어 있지 않은 것: 게임 원본·추출 자료·후보·번역 작업 파일·배포 ZIP·외부 도구 실행 파일(`.gitignore` 참고)', '',
             '그래서 일부 게임의 도구는 여기 있는 파일만으로는 다시 실행되지 않습니다. 절차 문서와 검증 도구의 구조를 참고하는 용도입니다.',
             '게임의 권리는 각 권리자에게 있으며, 이 저장소는 게임 제작사와 무관한 비공식 자료입니다.',
             '포함된 글꼴은 각 폴더의 라이선스 파일(SIL Open Font License)을 따릅니다.', '']
    return '\n'.join(lines)


def remove_tree(path):
    def writable(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onerror=writable)


def main():
    publish = '--publish' in sys.argv
    head = git(['rev-parse', 'HEAD'])
    included, excluded, problems = select()
    PUBLIC.mkdir(parents=True, exist_ok=True)
    plan = {'source_commit': head, 'included': len(included), 'excluded': excluded, 'problems': problems}
    (PUBLIC / f'plan_{head[:12]}.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'source_commit': head[:12], 'included': len(included), 'excluded': len(excluded), 'problems': problems}, ensure_ascii=False))
    if problems:
        raise SystemExit('공개 대상에 이메일·계정 식별자·토큰 형식이 있습니다. 올리지 않습니다.')
    if not publish:
        return
    secret = token()
    user = api(secret, 'GET', '/user')
    owner = user['login']
    full = f'{owner}/{REPOSITORY}'
    remote = f'https://github.com/{full}.git'
    try:
        repository = api(secret, 'GET', '/repos/' + full)
        created = False
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        repository = api(secret, 'POST', '/user/repos', {'name': REPOSITORY, 'description': DESCRIPTION, 'private': False,
                                                         'auto_init': False, 'has_wiki': False, 'has_projects': False})
        created = True
    if repository['full_name'] != full or repository['private']:
        raise SystemExit('저장소 이름이나 공개 범위가 기대와 다릅니다.')
    local = PUBLIC / 'repository'
    if not (local / '.git').exists():
        if not created:
            raise SystemExit('같은 이름의 저장소가 이미 있는데 이 PC에 공개 사본 기록이 없습니다. 덮어쓰지 않습니다.')
        local.mkdir(parents=True)
        git(['init', '-q', '-b', 'main'], local)
        git(['remote', 'add', 'origin', remote], local)
    elif git(['remote', 'get-url', 'origin'], local) != remote:
        raise SystemExit('공개 사본 폴더의 원격 주소가 다릅니다.')
    git(['config', 'user.name', owner], local)
    git(['config', 'user.email', f"{user['id']}+{owner}@users.noreply.github.com"], local)
    git(['config', 'core.autocrlf', 'false'], local)
    # 사본 폴더를 비우고(.git 제외) 고른 파일만 다시 복사합니다.
    for child in local.iterdir():
        if child.name == '.git':
            continue
        remove_tree(child) if child.is_dir() else child.unlink()
    for name in included:
        target = local / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (local / 'PUBLIC_EXPORT.md').write_text(note(head, included, excluded), encoding='utf-8', newline='\n')
    git(['add', '-A'], local)
    staged = git(['diff', '--cached', '--name-only'], local)
    if staged:
        git(['commit', '-q', '-m', f'공개 사본 갱신: 원본 커밋 {head[:12]}'], local)
    commit = git(['rev-parse', 'HEAD'], local)
    authors = set(git(['log', '--format=%ae'], local).splitlines())
    if any(not address.endswith('@users.noreply.github.com') for address in authors):
        raise SystemExit('공개 사본의 커밋 작성자에 비공개 주소가 아닌 것이 있습니다. 올리지 않습니다.')
    git(['push', '-q', '-u', 'origin', 'main'], local)
    remote_head = api(secret, 'GET', f'/repos/{full}/commits/main')
    tree = api(secret, 'GET', f'/repos/{full}/git/trees/{commit}?recursive=1')
    remote_files = sorted(item['path'] for item in tree['tree'] if item['type'] == 'blob')
    expected = sorted(included + ['PUBLIC_EXPORT.md'])
    verified = remote_head['sha'] == commit and remote_files == expected and not tree.get('truncated')
    record = {'repository': repository['html_url'], 'full_name': full, 'private': repository['private'], 'created_now': created,
              'source_commit': head, 'public_commit': commit, 'files': len(expected), 'excluded': len(excluded),
              'verified_remote_matches': verified, 'published_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (PUBLIC / 'publication.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False))
    if not verified:
        raise SystemExit('올린 내용이 준비한 사본과 다릅니다.')


if __name__ == '__main__':
    main()
