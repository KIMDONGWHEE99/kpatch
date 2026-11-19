"""대화별 순서를 보존한 한국어 교정 작업본을 만듭니다."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'extracted_private/ALASKA_GOLD_FEVER/25782395/dialogue_scan/dialogue_entries.json'
OUT = ROOT / 'working_private/ALASKA_GOLD_FEVER/dialogue_translation'
NAMES = {'FullStoryQuests(MSQ)': 'main_story', 'FullSideQuests(SSQ)': 'side_quests',
         'FullGenericDialogues': 'generic', 'DLCQuests(DLC)': 'dlc', 'Playtest0226': 'playtest'}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main() -> None:
    canonical = OUT / 'dialogue_canonical.json'
    if canonical.exists():
        raise RuntimeError('이미 준비한 교정 작업본은 덮어쓰지 않습니다.')
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(SOURCE.read_text('utf-8'))
    rows, empty_menu, by_database = [], [], defaultdict(list)
    for item in source:
        if item['field_title'] == 'Menu Text ko' and not item['english'] and not item['original_korean']:
            empty_menu.append({**item, 'treatment': 'PRESERVE_EMPTY_FALLBACK',
                               'reason': '선택지 전용 글이 비어 있어 기본 대사를 재사용하는 필드. 빈 번역 오류로 집계하지 않음'})
            continue
        row = {**item, 'translation': item['original_korean'], 'review_status': 'NOT_RUN',
               'review_reason': '', 'translator_note': '', 'group': NAMES[item['database']]}
        rows.append(row)
        by_database[row['group']].append(row)
    write_json(canonical, rows)
    write_json(OUT / 'preserved_empty_menu_fields.json', empty_menu)
    for group, items in by_database.items():
        write_json(OUT / (group + '.json'), items)
        lines = [f'대화 한국어 교정 — {group}', f'총 {len(items)}개. 기존 번역을 그대로 담은 미검토 작업본입니다.',
                 '각 항목의 식별자와 위치는 변경하지 않습니다. 대화 순서·화자·분기 조건을 함께 읽습니다.', '']
        conversation = None
        for index, row in enumerate(items, 1):
            if row['conversation'] != conversation:
                conversation = row['conversation']
                lines += ['=' * 72, f'대화: {conversation} (번호 {row["conversation_id"]})', '=' * 72]
            lines += [f'[{index:04d}] {row["id"]}', f'화자: {row["actor_name"]} (번호 {row["actor_id"]}) · 노드 {row["entry_id"]}',
                      '영어: ' + row['english'].replace('\n', '\\n'),
                      '기존 한국어: ' + row['original_korean'].replace('\n', '\\n')]
            if row['conditions']:
                lines.append('표시 조건: ' + row['conditions'])
            lines += ['']
        (OUT / (group + '_review.txt')).write_text('\n'.join(lines), encoding='utf-8')
    summary = {'status': 'PASS', 'scope': '교정 작업본 준비; 번역 검토 NOT_RUN',
               'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
               'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'canonical_count': len(rows), 'preserved_empty_menu_fields': len(empty_menu),
               'groups': dict(Counter(row['group'] for row in rows))}
    write_json(OUT / 'preparation.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
