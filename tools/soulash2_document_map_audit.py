"""동봉 기록·라이선스의 보존 범위와 지도 본문의 실제 문자열을 별도로 기록한다."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BUILD = '0.10.4.0.1_20261029'
BASE = ROOT / 'extracted_private/SOULASH_2' / BUILD
SOURCE = ROOT / 'source_original/SOULASH_2' / BUILD
OUTPUT = ROOT / 'working_private/SOULASH_2/document_map_review_003'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s]


def save(name, value):
    path = OUTPUT / name
    if name.endswith('.jsonl'):
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in value), encoding='utf-8')
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'artifact': path.relative_to(ROOT).as_posix(), 'artifact_sha256': sha(path.read_bytes())}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    manifest_path = BASE / 'baseline_manifest.json'
    baseline = {r['path']: r['sha256'] for r in json.loads(manifest_path.read_text(encoding='utf-8'))['files']}
    cache = {}

    def blob(relative):
        if relative not in cache:
            data = (SOURCE / relative).read_bytes()
            assert sha(data) == baseline[relative], relative
            cache[relative] = data
        return cache[relative]

    # 법적 문구·개발자 원문 기록은 번역 대상 누락이 아니라 명시적 원문 보존 범위다.
    policies = {
        'changelog.txt': ('VISIBLE_KEEP', '원본 변경 이력 보존', '개발자가 배포한 날짜별 버전 변경 기록. 문서 첫머리의 Changelog 선언과 날짜별 구성을 확인. 과거 업데이트·API 명칭·명령어의 원문 기록으로 보존하며 한국어 문서라고 주장하지 않음.'),
        'data/docs/dependencies.txt': ('VISIBLE_KEEP', '원본 빌드 의존성 안내 보존', 'SDL·Steam·curl 등의 실제 라이브러리 이름, 빌드 명령과 .lib 목록을 담은 개발자 안내. 실행 화면 번역이 아닌 원문 개발 문서로 보존.'),
        'data/docs/mutex_order.txt': ('VISIBLE_KEEP', '원본 잠금 순서 문서 보존', '게임 개발자가 정의한 Companies/Factions/ECS 등 잠금 획득·해제 순서. 원문 개발 문서로 보존.'),
        'data/mods/core_2/npc/filelist.txt': ('VISIBLE_KEEP', '원본 인명 파일 경로 목록', 'names/이름.txt 형식의 상대 파일 경로를 기록한 목록. 번역 문장이 아닌 경로 표기로 보존한다. 원본에서 참조 대상이 없는 항목도 별도로 기록하며 런타임 사용 여부를 추정하지 않음.'),
        'version.txt': ('VISIBLE_KEEP', '빌드 버전 식별자', '문구가 아닌 숫자와 점으로 구성된 게임 버전 0.10.4.0.1. 지원 빌드 식별을 위해 보존.'),
    }
    text_rows = [r for r in rows(BASE / 'text_lines.jsonl') if r['classification'] == 'UNKNOWN']
    documents = []
    for relative in sorted({r['file'] for r in text_rows}):
        data = blob(relative)
        lines = data.decode('utf-8-sig').splitlines()
        if relative.startswith('data/docs/licenses/'):
            assert 'copyright' in data.decode('utf-8-sig').lower() or 'license' in data.decode('utf-8-sig').lower()
            policy = ('VISIBLE_KEEP', '제삼자 라이선스 원문 보존', '동봉 제삼자 라이선스·저작권 고지의 실제 텍스트를 확인. 권리·배포 조건의 원본을 바꾸지 않고 그대로 보존하며 한국어 번역 문서라고 주장하지 않음.')
        else:
            policy = policies[relative]
        targets = []
        if relative.endswith('/filelist.txt'):
            for index, line in enumerate(lines, 1):
                assert line and not line.startswith('/') and '..' not in line.split('/')
                target = 'data/mods/core_2/npc/' + line
                targets.append({'line': index, 'file': target, 'exists_in_baseline': target in baseline,
                                'sha256': sha(blob(target)) if target in baseline else None})
        if relative == 'version.txt':
            assert data.decode('utf-8-sig').strip() == '0.10.4.0.1'
        if relative == 'changelog.txt':
            assert lines[0] == '# Changelog' and 'All notable changes' in '\n'.join(lines[:5])
        documents.append({'file': relative, 'source_file_sha256': sha(data), 'line_count': len(lines),
                          'classification': policy[0], 'policy': policy[1], 'reason': policy[2],
                          'header_sample': lines[:8], 'references': targets,
                          'runtime_nonvisibility_claimed': False, 'translation_scope': '원문 보존으로 사용자에게 공개'})
    document_evidence = save('document_evidence.json', {'documents': documents,
        'baseline_manifest_sha256': sha(manifest_path.read_bytes()), 'code_sha256': sha(Path(__file__).read_bytes())})
    document_index = {r['file']: r for r in documents}
    overlays = []
    for row in text_rows:
        lines = blob(row['file']).decode('utf-8-sig').splitlines()
        assert lines[row['line'] - 1] == row['source']
        assert row['source_file_sha256'] == sha(blob(row['file']))
        assert row['source_value_sha256'] == sha(row['source'].encode('utf-8'))
        decision = document_index[row['file']]
        overlays.append({**row, 'axis': 'text_line', 'previous_classification': 'UNKNOWN',
                         'classification': decision['classification'], 'reason': decision['reason'],
                         'evidence': document_evidence, 'runtime_observed': False})
    text_overlay = save('classification_text_overlay.jsonl', overlays)
    map_records, body_strings, missing, residuals = [], [], [], []
    for row in rows(BASE / 'map_names.jsonl'):
        data = blob(row['file'])
        parts = data.decode('utf-8-sig').split('|')
        assert parts[0] == row['map_id'] and parts[1] == row['source']
        assert sha(data) == row['sha256'] and sha(parts[1].encode('utf-8')) == row['source_value_sha256']
        body = '|'.join(parts[2:])
        found = []
        for index, match in enumerate(re.finditer(r'[A-Za-z_][A-Za-z0-9_-]*', body)):
            value = match.group()
            target = 'data/mods/core_2/entities/' + value.removeprefix('core_2_') + '.json'
            valid = value.startswith('core_2_') and target in baseline
            record = {'file': row['file'], 'source_file_sha256': sha(data),
                      'location_id': row['file'] + '#body/string/' + str(index),
                      'body_character_offset': match.start(), 'source': value,
                      'source_value_sha256': sha(value.encode('utf-8')), 'classification': 'UNKNOWN',
                      'matching_entity_file': target if valid else None,
                      'matching_entity_sha256': sha(blob(target)) if valid else None,
                      'reason': '실재 개체 정의와 ID가 대응함. 실제 지도 읽기 코드의 참조 소비 확인 전에는 확정 분류하지 않음.'}
            body_strings.append(record)
            found.append(value)
            if not valid:
                missing.append(record)
        residual = re.sub(r'[A-Za-z_][A-Za-z0-9_-]*', '', body)
        unexpected = ''.join(sorted(set(residual) - set('0123456789-+.,&*| \r\n\t')))
        if unexpected:
            residuals.append({'file': row['file'], 'characters': unexpected})
        map_records.append({**row, 'pipe_parts': len(parts), 'body_string_count': len(found),
                            'body_unique_strings': sorted(set(found)), 'body_nonidentifier_text': unexpected,
                            'remaining_payload_audit': 'PASS_LEXICAL_ONLY', 'header_classification': 'UNKNOWN'})
    map_evidence = save('map_payload_audit.jsonl', map_records)
    body_evidence = save('map_body_strings.jsonl', body_strings)
    save('summary.json', {'created': datetime.now(timezone.utc).isoformat(),
         'text_locations': len(overlays), 'text_classification_counts': dict(Counter(r['classification'] for r in overlays)),
         'text_overlay': text_overlay, 'map_count': len(map_records), 'map_header_unknown': len(map_records),
         'map_body_strings': len(body_strings), 'map_body_unique_strings': len({r['source'] for r in body_strings}),
         'map_body_unmatched_references': missing, 'map_body_unrecognized_characters': residuals,
         'map_payload_evidence': map_evidence, 'map_body_evidence': body_evidence,
         'g2_status': 'FAIL', 'release_ready': False})
    print(json.dumps({'text_locations': len(overlays), 'maps': len(map_records), 'body_strings': len(body_strings),
                      'body_unmatched': len(missing), 'body_unrecognized': len(residuals)}))


if __name__ == '__main__':
    main()
