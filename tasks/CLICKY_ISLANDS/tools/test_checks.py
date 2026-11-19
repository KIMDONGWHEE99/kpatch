"""검사기가 알려진 결함을 실제로 잡는지 합성 자료로 확인합니다(정상 입력은 통과해야 함)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from assemble_translation import check
import optimized_translation as ot

NL = chr(10)
GOOD = ('Have ({current}/{goal}) [b][color=#FFBE0D]Gold[/color][/b] +5%' + NL, '[b][color=#FFBE0D]골드[/color][/b] ({current}/{goal}) 보유 +5%' + NL)
CASES = {
    '빈 번역': (GOOD[0], NL),
    '자리표시자 누락': (GOOD[0], '[b][color=#FFBE0D]골드[/color][/b] ({current}) 보유 +5%' + NL),
    '자리표시자 이름 바뀜': (GOOD[0], '[b][color=#FFBE0D]골드[/color][/b] ({current}/{goals}) 보유 +5%' + NL),
    '닫는 태그 누락': (GOOD[0], '[b][color=#FFBE0D]골드[/color] ({current}/{goal}) 보유 +5%' + NL),
    '태그 중첩 뒤바뀜': (GOOD[0], '[b][color=#FFBE0D]골드[/b][/color] ({current}/{goal}) 보유 +5%' + NL),
    '색상 값 바뀜': (GOOD[0], '[b][color=#FFBE0E]골드[/color][/b] ({current}/{goal}) 보유 +5%' + NL),
    '줄바꿈 누락': (GOOD[0], '[b][color=#FFBE0D]골드[/color][/b] ({current}/{goal}) 보유 +5%'),
    '퍼센트 누락': (GOOD[0], '[b][color=#FFBE0D]골드[/color][/b] ({current}/{goal}) 보유 +5' + NL),
    '그림 표식 남음': ('x [img]res://a.tres[/img]', 'x <i:a>'),
    '그림 태그 누락': ('x [img]res://a.tres[/img]', 'x'),
}


def main():
    failures = []
    if check(*GOOD):
        failures.append(('정상 입력이 통과하지 못함', check(*GOOD)))
    for name, (source, target) in CASES.items():
        if not check(source, target):
            failures.append((name, '검출 실패'))
    # 언어표: 위치 교환·빈 값이 재구성 결과에 그대로 드러나는지, 추가 키를 조회할 수 있는지 확인합니다.
    entries = [{'table_index': ot.godot_hash(0, key) % 11, 'seed': 1, 'key_hash': ot.godot_hash(1, key), 'text': text, 'key': key}
               for key, text in (('A', '가'), ('B', ''), ('C', '다'))]
    ot.add_key(entries, 11, 'Direct text', '직접')
    hash_table, bucket_table, strings = ot.build(11, entries)
    slots = ot.parse(hash_table, bucket_table, None)
    index = ot.index_slots(slots)
    for key, text in (('A', '가'), ('B', ''), ('C', '다'), ('Direct text', '직접')):
        slot = ot.find(index, 11, key)
        value = strings[slot['offset']:slot['offset'] + slot['uncomp_size']].rstrip(b'\0').decode('utf-8') if slot else None
        if value != text:
            failures.append(('언어표 재구성', key, value))
    if ot.find(index, 11, 'Missing') is not None:
        failures.append(('언어표 재구성', '없는 키가 조회됨'))
    print('checker self-test', 'FAIL' if failures else 'PASS', len(CASES), 'defect cases', failures)
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
