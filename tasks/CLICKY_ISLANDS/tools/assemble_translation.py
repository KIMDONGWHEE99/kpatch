"""번역 작업 파일을 하나의 공식 번역 원본(canonical.json)으로 합치고 형식을 검사합니다(G3).

입력(모두 working_private/CLICKY_ISLANDS/translation):
  todo.json            고유 원문 번호 ↔ 언어표 칸
  ko_*.txt, ko_fix.txt 번호<TAB>번역 (ko_fix가 마지막에 덮어씀). 그림 태그는 짧은 표식(<i:이름>)
  direct_ko.json       언어표 밖 직접 문구(영어 → 한국어)
  island_names_ko.json 무작위 섬 이름 한국어 목록
출력:
  canonical.json       공식 번역 원본(칸·키·원문·원문 지문·번역·판정)
  build_input.json     build.py 입력
수정은 ko_fix.txt나 direct_ko.json에서 하고 이 도구를 다시 실행합니다.
"""
import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import WORK, save, load, sha_text
import img_tokens

T = WORK / 'translation'
BS, NL = chr(92), chr(10)
PLACEHOLDER = re.compile(r'\{[a-z_0-9]+\}')
TAG = re.compile(r'\[(/?)([a-z_]+)((?:=[^\]]*)?(?: [^\]]*)?)\]')
PAIRED = {'b', 'i', 'color', 'wave', 'pulse', 'img', 'u', 'center'}


def unescape(text):
    """작업 파일의 \\n, \\\\ 표기를 실제 글자로 되돌립니다."""
    out, index = [], 0
    while index < len(text):
        if text[index] == BS and index + 1 < len(text):
            out.append(NL if text[index + 1] == 'n' else text[index + 1])
            index += 2
        else:
            out.append(text[index])
            index += 1
    return ''.join(out)


def tag_events(text):
    """BBCode 태그를 순서대로 뽑고 열고 닫는 짝·중첩이 맞는지 확인합니다."""
    events, stack = [], []
    for match in TAG.finditer(text):
        closing, name, argument = match[1] == '/', match[2], match[3]
        if name not in PAIRED:
            continue
        events.append(('/' if closing else '') + name + ('' if closing else argument))
        if closing:
            if not stack or stack[-1] != name:
                return events, False
            stack.pop()
        else:
            stack.append(name)
    return events, not stack


def check(source, target):
    """원문과 번역의 제어 정보가 같은지 검사해 문제 목록을 돌려줍니다."""
    problems = []
    if not target.strip() and source.strip():
        problems.append('빈 번역')
    if sorted(PLACEHOLDER.findall(source)) != sorted(PLACEHOLDER.findall(target)):
        problems.append('자리표시자 불일치')
    source_events, source_ok = tag_events(source)
    target_events, target_ok = tag_events(target)
    if sorted(source_events) != sorted(target_events):
        problems.append('태그 종류·개수·속성 불일치')
    # 원문 자체의 태그 짝이 어긋난 경우(원작의 오타)는 같은 순서로 보존했는지만 봅니다.
    if source_ok and not target_ok:
        problems.append('태그 짝·중첩 오류')
    if not source_ok and source_events != target_events and sorted(source_events) == sorted(target_events):
        problems.append('짝이 어긋난 원문 태그의 순서가 바뀜')
    if source.count(NL) != target.count(NL):
        problems.append('줄바꿈 수 불일치')
    if (source.endswith(NL)) != (target.endswith(NL)):
        problems.append('끝 줄바꿈 불일치')
    if re.search(r'<i[bct]?:', target):
        problems.append('그림 표식이 남음')
    if source.count('%') != target.count('%'):
        problems.append('% 개수 불일치')
    if unicodedata.normalize('NFC', target) != target:
        problems.append('NFC 정규화 아님')
    return problems


def main():
    todo = load(T / 'todo.json')
    tokens = load(T / 'img_tokens.json')
    inventory = {r['slot']: r for r in load(WORK / 'census/locale_inventory.json')}
    answers = {}
    files = sorted(p for p in T.glob('ko_[0-9]*.txt')) + [T / 'ko_fix.txt']
    for path in files:
        for line in path.read_text(encoding='utf-8').split(NL):
            if not line.strip():
                continue
            # 번호와 번역 사이는 탭입니다. 탭이 공백으로 바뀐 줄도 받아들입니다.
            match = re.match(r'^(\d+)\t(.*)$', line, re.S) or re.match(r'^(\d+) +(.*)$', line, re.S)
            if re.fullmatch(r'\d+', line.strip()):
                # 번호만 있는 줄은 "원문 그대로"(공백 한 칸짜리 원문 등)라는 뜻입니다.
                answers[int(line.strip())] = None
                continue
            if not match:
                raise SystemExit(f'형식이 잘못된 줄: {path.name}: {line[:40]!r}')
            answers[int(match[1])] = match[2]
    missing = [row['n'] for row in todo if row['n'] not in answers]
    extra = sorted(set(answers) - {row['n'] for row in todo})
    if missing or extra:
        raise SystemExit(f'번호 누락 {missing[:10]} / 없는 번호 {extra[:10]}')
    records, problems = [], []
    for row in todo:
        answer = answers[row['n']]
        target = row['source'] if answer is None else img_tokens.restore(unescape(answer), tokens)
        found = check(row['source'], target)
        if found:
            problems.append({'n': row['n'], 'keys': row['keys'][:2], 'problems': found})
        for slot in row['slots']:
            item = inventory[slot]
            same = target == row['source']
            records.append({'id': item['id'], 'slot': slot, 'key': item['key'], 'n': row['n'], 'file_sha256': item['file_sha256'],
                            'source': row['source'], 'source_sha256': sha_text(row['source']), 'target': target,
                            'classification': 'VISIBLE_KEEP' if same else 'VISIBLE_TRANSLATE',
                            'evidence': '인명·공백 등 원문 그대로 두는 값' if same else '언어표 칸의 표시 문구'})
    translated_slots = {r['slot'] for r in records}
    empty_slots = [s for s, item in inventory.items() if not item['source']]
    if translated_slots | set(empty_slots) != set(inventory):
        raise SystemExit('번역되지 않은 칸이 있습니다.')
    # 직접 문구: 언어표에 같은 영어 문구가 있으면 그 번역을 쓰고, 없으면 direct_ko.json에서 가져옵니다.
    plan = load(T / 'direct_todo.json')
    strings = load(WORK / 'census/strings.json')
    wanted = collections.OrderedDict()
    for record in strings:
        if record['classification'] == 'VISIBLE_TRANSLATE' and record.get('handling') == 'direct':
            wanted.setdefault(record['source'], []).append(record['id'])
    by_source = {}
    for record in records:
        by_source.setdefault(record['source'], set()).add(record['target'])
    manual = {img_tokens.restore(k, tokens): img_tokens.restore(v, tokens) for k, v in load(T / 'direct_ko.json').items()}
    direct = collections.OrderedDict()
    for source, ids in wanted.items():
        if source in by_source:
            if len(by_source[source]) != 1:
                raise SystemExit('같은 영어 문구의 번역이 여러 개라 직접 문구에 자동으로 쓸 수 없습니다: ' + source)
            target, origin = next(iter(by_source[source])), 'table'
        elif source in manual:
            target, origin = manual[source], 'manual'
        else:
            raise SystemExit('직접 문구 번역 없음: ' + repr(source))
        key_like = re.fullmatch(r'[A-Z0-9_]+\n?', source) is not None
        found = [] if key_like else check(source, target)
        if found:
            problems.append({'direct': source[:60], 'problems': found})
        direct[source] = {'target': target, 'origin': origin, 'locations': ids, 'source_sha256': sha_text(source)}
    unused = sorted(set(manual) - set(direct))
    names = load(T / 'island_names_ko.json')
    english_names = [r['source'] for r in strings if r.get('handling') == 'island_names']
    if len(names) != len(english_names) or len(set(names)) != len(names) or any(len(n) > 16 or not n.strip() for n in names):
        problems.append({'island_names': '개수·중복·길이(16자) 검사 실패', 'korean': len(names), 'english': len(english_names)})
    save(T / 'problems.json', problems)
    if problems:
        print(json.dumps(problems, ensure_ascii=False)[:6000])
        raise SystemExit(f'형식 문제 {len(problems)}건')
    canonical = {'game_id': 'CLICKY_ISLANDS', 'baseline': 'steam_26701014', 'locale_slot': 'kr',
                 'slots': records, 'direct': [dict(source=k, **v) for k, v in direct.items()],
                 'island_names': [{'source': e, 'target': k} for e, k in zip(english_names, names)],
                 'empty_slots': empty_slots, 'unused_manual_direct': unused}
    save(T / 'canonical.json', canonical)
    save(T / 'build_input.json', {'slots': {r['slot']: r['target'] for r in records},
                                  'direct': {k: v['target'] for k, v in direct.items()}, 'island_names': names})
    characters = sorted({c for r in records for c in r['target']} | {c for v in direct.values() for c in v['target']} | {c for n in names for c in n} | set('한국어'))
    save(T / 'required_characters.json', {'count': len(characters), 'hangul': sum(1 for c in characters if '가' <= c <= '힣'),
                                          'characters': ''.join(characters)})
    print(json.dumps({'unique_sources': len(todo), 'slots': len(records), 'kept_as_source': sum(1 for r in records if r['classification'] == 'VISIBLE_KEEP'),
                      'direct': len(direct), 'direct_from_table': sum(1 for v in direct.values() if v['origin'] == 'table'),
                      'island_names': len(names), 'required_characters': len(characters), 'unused_manual_direct': unused,
                      'canonical_sha256': sha_text((T / 'canonical.json').read_text(encoding='utf-8'))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
