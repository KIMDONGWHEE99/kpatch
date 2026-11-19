"""보존된 완료 묶음·교정·새 번역을 명시적으로 통합하고 독립 검사를 호출한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / 'working_private/SOULASH_2/translations'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--batch', type=Path, action='append', default=[])
    args = parser.parse_args()
    if not args.id.replace('_', '').isalnum():
        raise ValueError('잘못된 통합 이름')
    output = TRANSLATIONS / args.id
    output.mkdir(exist_ok=False)
    selection_path = TRANSLATIONS / 'finish_existing_selection.json'
    selection = json.loads(selection_path.read_text(encoding='utf-8'))
    inputs = {selection_path: sha(selection_path), Path(__file__): sha(Path(__file__))}
    rows, origin = {}, {}
    batches = [(ROOT / entry['path'], entry['sha256']) for entry in selection['selected_batches']]
    batches += [(p.resolve(), sha(p.resolve())) for p in args.batch]
    for path, expected_hash in batches:
        if not path.is_relative_to(TRANSLATIONS) or sha(path) != expected_hash:
            raise ValueError('번역 입력 경계·지문 불일치')
        inputs[path] = expected_hash
        for row in read_rows(path):
            identity = row['location_id']
            if identity in rows:
                raise ValueError('번역 중복: ' + identity)
            rows[identity] = row
            origin[identity] = path.relative_to(ROOT).as_posix()
    overrides = {}
    for name in ('overrides_001.jsonl', 'overrides_002.jsonl', 'overrides_003.jsonl', 'overrides_004.jsonl',
                 'overrides_entities_b_001.jsonl', 'dialogues_b_overrides_001.jsonl'):
        path = TRANSLATIONS / name
        inputs[path] = sha(path)
        for change in read_rows(path):
            previous = ROOT / change['previous_batch']
            if sha(previous) != change['previous_batch_sha256']:
                raise ValueError('교정 근거 원본 묶음 변경: ' + str(previous))
            inputs[previous] = sha(previous)
            identity = change['location_id']
            original = next(r for r in read_rows(previous) if r['location_id'] == identity)
            if original['target'] != change['previous_target']:
                raise ValueError('교정 전 번역 불일치: ' + identity)
            overrides.setdefault(identity, []).append((change, path))
    corrections = []
    for identity, chain in overrides.items():
        row = rows[identity]
        allowed = {change[k] for change, _ in chain for k in ('previous_target', 'target')}
        if row['target'] not in allowed:
            raise ValueError('선택된 묶음과 교정 계보 불일치: ' + identity)
        change, path = chain[-1]
        for key in ('file', 'field_path', 'source', 'source_file_sha256', 'source_value_sha256'):
            if row[key] != change[key]:
                raise ValueError('교정 원문 식별 불일치')
        if row['target'] != change['target']:
            corrections.append({'location_id': identity, 'before': row['target'], 'after': change['target']})
        row['target'] = change['target']
        row['review_override'] = {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path), 'reason': change['reason']}
    batch = output / 'combined.jsonl'
    with batch.open('x', encoding='utf-8') as stream:
        for identity, row in rows.items():
            stream.write(json.dumps({**row, 'integration_origin': origin[identity]}, ensure_ascii=False) + '\n')
    hold_source = TRANSLATIONS / 'dialogues_a_final_holds.json'
    inputs[hold_source] = sha(hold_source)
    holds = output / 'holds.jsonl'
    held_rows = json.loads(hold_source.read_text(encoding='utf-8'))['holds']
    with holds.open('x', encoding='utf-8') as stream:
        for hold in held_rows:
            row = rows[hold['location_id']]
            if row['target'] != hold['target']:
                raise ValueError('보류 결정과 번역 불일치')
            stream.write(json.dumps({**row, 'reason': hold['reason'], 'evidence_path': hold_source.relative_to(ROOT).as_posix(),
                                     'evidence_sha256': sha(hold_source)}, ensure_ascii=False) + '\n')
    if any(sha(p) != digest for p, digest in inputs.items()):
        raise ValueError('통합 도중 입력 변경')
    manifest = {'created': datetime.now(timezone.utc).isoformat(), 'status': 'PASS', 'rows': len(rows),
                'explicit_holds': len(held_rows), 'corrections': corrections, 'release_ready': False,
                'inputs': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': digest} for p, digest in inputs.items()],
                'combined_sha256': sha(batch), 'holds_sha256': sha(holds)}
    (output / 'integration_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    stage = ROOT / 'build_candidate/SOULASH_2' / args.id
    subprocess.run([sys.executable, str(ROOT / 'tools/soulash2_translation_stage.py'), '--batch', str(batch),
                    '--hold-batch', str(holds), '--output', str(stage)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / 'tools/soulash2_translation_stage_verify.py'), str(stage)], cwd=ROOT, check=True)
    print(json.dumps({'status': 'PASS', 'stage': str(stage), 'submitted': len(rows), 'new_corrections_applied': len(corrections)}))


if __name__ == '__main__':
    main()
