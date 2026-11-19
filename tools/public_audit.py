"""공개 저장소로 올리기 전에 추적 중인 파일을 조사합니다(읽기 전용).

찾는 것: 이메일, Steam 계정 식별자, 접근 토큰 형식, 개인 사용자 폴더 경로,
그리고 게임 원문이 들어 있을 가능성이 큰 파일(긴 영어 따옴표 문구가 많은 파일, 번역 폴더).
결과는 사람이 판단할 재료이며, 이 도구가 "안전하다"고 판정하지는 않습니다.
사용: python tools/public_audit.py [결과 JSON 경로]
"""
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
STEAM_ID = re.compile(r'7656119[0-9]{10}')
TOKEN = re.compile(r'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}')
USER_PATH = re.compile(r'[Cc]:[/\\]+Users[/\\]+([^/\\"\' ]+)')
HANGUL = re.compile('[가-힣]')
LONG_ENGLISH = re.compile(r'["\'][A-Z][A-Za-z ,.!?\'-]{24,}["\']')
BINARY = {'.ttf', '.otf', '.png', '.jpg', '.jpeg'}


def main():
    listed = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout.decode('utf-8')
    files = [name for name in listed.split('\0') if name]
    found = collections.defaultdict(list)
    stats = []
    for name in files:
        path = ROOT / name
        if path.suffix.lower() in BINARY:
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for address in sorted(set(EMAIL.findall(text))):
            if 'noreply' in address or address.endswith(('example.com', 'anthropic.com')):
                continue
            # 주소 자체는 결과에 남기지 않고 도메인만 남깁니다.
            found['email'].append([name, '***@' + address.split('@', 1)[1]])
        if STEAM_ID.search(text):
            found['steam_id'].append(name)
        if TOKEN.search(text):
            found['token_like'].append(name)
        for user in sorted(set(USER_PATH.findall(text))):
            found['user_path:' + user].append(name)
        lines = text.splitlines()
        stats.append({'file': name, 'lines': len(lines), 'hangul_lines': sum(1 for line in lines if HANGUL.search(line)),
                      'long_english_lines': sum(1 for line in lines if LONG_ENGLISH.search(line))})
    translation_dirs = collections.Counter('/'.join(name.split('/')[:3]) for name in files if '/translations/' in name or '/translation/' in name)
    report = {'tracked_files': len(files), 'found': {key: value for key, value in found.items()},
              'translation_dirs': dict(translation_dirs),
              'top_long_english': sorted(stats, key=lambda row: -row['long_english_lines'])[:40],
              'binary': [name for name in files if Path(name).suffix.lower() in BINARY]}
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for key, value in found.items():
        print(key, len(value), value[:5])
    print('translation dirs', dict(translation_dirs))
    for row in report['top_long_english'][:26]:
        print(row['long_english_lines'], row['hangul_lines'], row['lines'], row['file'])
    print('binary', report['binary'])


if __name__ == '__main__':
    main()
