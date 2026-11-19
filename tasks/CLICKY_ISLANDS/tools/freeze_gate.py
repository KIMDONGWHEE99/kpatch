"""후보를 고정하고 G2~G5 증거를 같은 후보 목록 지문에 묶어 배포 관문 기록을 만듭니다(G6 준비).

사용: python freeze_gate.py <build_id> <검수 실행 ID,...>
각 단계의 판정은 여기서 새로 정하지 않고, 이미 남긴 증거 파일을 다시 읽어 조건이 맞을 때만 PASS로 적습니다.
조건이 하나라도 어긋나면 멈춥니다. 출력은 working_private/CLICKY_ISLANDS/release_gate/<build_id> 아래에 둡니다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, WORK, CANDIDATE, PCK_NAME, save, load, sha

GAME, BUILD = 'CLICKY_ISLANDS', '26701014'


def rel(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def ref(path):
    return {'path': rel(path), 'sha256': sha(path)}


def main():
    build_id, runs = sys.argv[1], sys.argv[2].split(',')
    candidate = CANDIDATE / build_id
    out = WORK / 'release_gate' / build_id
    if out.exists():
        raise SystemExit('같은 후보의 관문 기록이 이미 있습니다. 덮어쓰지 않습니다.')
    out.mkdir(parents=True)
    files = [{'path': p.name, 'size': p.stat().st_size, 'sha256': sha(p)} for p in sorted(candidate.iterdir()) if p.is_file()]
    freeze = out / 'candidate_manifest.json'
    save(freeze, {'game_id': GAME, 'steam_build': BUILD, 'candidate_id': build_id, 'files': files})
    freeze_sha = sha(freeze)
    pck_sha = next(f['sha256'] for f in files if f['path'] == PCK_NAME)
    checks = {}

    def evidence(stage, condition, scope, sources, detail):
        if not condition:
            raise SystemExit(f'{stage} 조건 불충족: {detail}')
        path = out / (stage + '.json')
        save(path, {'status': 'PASS', 'candidate_manifest_sha256': freeze_sha, 'scope': scope,
                    'sources': [ref(s) for s in sources], 'detail': detail})
        checks[stage] = {'path': rel(path), 'status': 'PASS', 'sha256': sha(path)}

    classify = load(WORK / 'census/classify_summary.json')
    media = load(WORK / 'media/summary.json')
    errors = load(WORK / 'census/extraction_errors.json')
    evidence('G2', classify['unknown_unique'] == 0 and 'UNKNOWN' not in classify['classifications'] and 'UNKNOWN' not in media['handling'] and not errors,
             '문자열 전수 분류와 미디어 판정. 영어 화면을 녹화한 튜토리얼 영상 12종은 유지(KEEP)',
             [WORK / 'census/classify_summary.json', WORK / 'census/strings.json', WORK / 'census/manual_decisions.json',
              WORK / 'census/extraction_errors.json', WORK / 'media/media_review.json'],
             {'classifications': classify['classifications'], 'media_handling': media['handling'], 'extraction_errors': len(errors)})

    build = load(WORK / build_id / 'build.json')
    problems = load(WORK / 'translation/problems.json')
    canonical = load(WORK / 'translation/canonical.json')
    evidence('G3', not problems and build['translation_sha256'] == sha(WORK / 'translation/build_input.json') and build['slots_translated'] == len(canonical['slots']),
             '번역 원본의 형식 검사(자리표시자·태그·줄바꿈)와 후보 입력 일치',
             [WORK / 'translation/canonical.json', WORK / 'translation/build_input.json', WORK / 'translation/problems.json'],
             {'slots': len(canonical['slots']), 'direct': len(canonical['direct']), 'island_names': len(canonical['island_names']), 'problems': len(problems)})

    report = load(WORK / build_id / 'verify/validation_report.json')
    evidence('G4', report['status'] == 'PASS' and report['inputs']['candidate_pck_sha256'] == pck_sha
             and report['inputs']['canonical_sha256'] == sha(WORK / 'translation/canonical.json'),
             '후보 재추출 대조(파일 경계·언어표 칸·직접 문구·스크립트·장면·글꼴)',
             [WORK / build_id / 'verify/validation_report.json', WORK / 'validator_selftest.json'],
             {name: check['status'] for name, check in report['checks'].items()})

    ledger_path = WORK / 'qa' / runs[0] / 'qa_ledger.json'
    ledger = load(ledger_path)
    run_ok = all(ledger['runs'][r]['boundary']['source_pck_sha256'] == pck_sha and ledger['runs'][r]['exit']['user_saves_unchanged']
                 and ledger['runs'][r]['exit']['exit_code'] == 0 for r in runs)
    evidence('G5', run_ok and all(c['status'] == 'PASS' for c in ledger['checks']),
             '필수 화면군 7종의 대표 화면 육안 검수와 저장 격리·실행 경로·로그 비교. 전체 회차·모든 건물 화면은 미검증(검수 기록의 unreached_screens)',
             [ledger_path] + [WORK / 'qa' / r / 'exit.json' for r in runs] + [WORK / 'qa' / r / 'qa_boundary.json' for r in runs],
             {'runs': runs, 'observed': ledger['observed_strings']['matched_unique_translations'],
              'countable': ledger['observed_strings']['countable_unique_translations'], 'unreached': ledger['unreached_screens']})

    tools = Path(__file__).parent
    dependencies = [ref(p) for p in (WORK / 'baseline.json', WORK / 'translation/canonical.json', WORK / 'translation/build_input.json',
                                     WORK / 'fonts/fonts_report.json', tools / 'build.py', tools / 'build_resources.gd', tools / 'pck_tools.py',
                                     tools / 'optimized_translation.py', tools / 'validate_candidate.py')]
    gate = {'game_id': GAME, 'steam_build': BUILD, 'status': 'PASS', 'candidate_id': build_id, 'allowed_changes': [PCK_NAME],
            'dependencies': dependencies, 'candidate_manifest': {'path': rel(freeze), 'sha256': freeze_sha}, 'checks': checks}
    save(out / 'gate.json', gate)
    print(json.dumps({'gate': rel(out / 'gate.json'), 'candidate_manifest_sha256': freeze_sha, 'pck_sha256': pck_sha,
                      'checks': {k: v['status'] for k, v in checks.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
