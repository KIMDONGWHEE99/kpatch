"""현재 후보의 확인된 번역·미완료 검수 범위를 고정합니다. 전체 통과로 바꾸지 않습니다."""
import collections
import json
from pathlib import Path
from release_package import ROOT, WORK, BASELINE, file_map, sha, write_json, utc_now

CANDIDATE = ROOT / 'build_candidate/COBALT_MINER/ko_candidate_03'
OUT = WORK / 'release_freeze_1.0.0_r1'
INSTRUCTION = '특별히 번역이 안된 부분이 없다면 검수는 여기까지하고 마무리하시죠.'


def ref(path):
    path = Path(path).resolve()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path))


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


def main():
    assert not OUT.exists(), '기존 고정 기록을 덮어쓰지 않습니다.'
    baseline_path = WORK / 'investigation_20261101/baseline_manifest.json'
    baseline = {r['path']: r for r in load(baseline_path)['files']}
    original, candidate = file_map(BASELINE), file_map(CANDIDATE)
    assert set(original) == set(candidate) == set(baseline)
    for name, path in original.items():
        assert path.stat().st_size == baseline[name]['size'] and sha(path) == baseline[name]['sha256']
    build_path = WORK / 'candidate_builds/ko_candidate_03/build_report.json'
    build = load(build_path)
    assert {name: sha(path) for name, path in candidate.items()} == build['candidate_files']
    for path, digest in build['inputs']['tracked_inputs'].items():
        assert sha(path) == digest, '입력 변경: ' + path
    static_path = WORK / 'final_static_01/validation.json'
    static = load(static_path)
    assert static['status'] == 'PASS' and static['files'] == build['candidate_files']
    assert static['dat']['translated_positions'] == 517 and static['native']['checked_fields'] == 192
    assert all(not font['missing'] for font in static['dat']['fonts'])
    translations_path = WORK / 'translation_02/translations.json'
    translations = load(translations_path)
    assert len(translations) == 397 and sum(len(r['occurrences']) for r in translations) == 517
    assert all(r['translation'].strip() and r['translation'] != r['source'] for r in translations)
    assert sha(translations_path) == static['translation_sha256']
    inventory_path = WORK / 'investigation_20261101/classification/inventory.jsonl'
    native_path = WORK / 'investigation_20261101/native/native_inventory_v19.jsonl'
    ordinary = collections.Counter(r['classification'] for r in lines(inventory_path))
    native = collections.Counter(r['classification'] for r in lines(native_path))
    assert ordinary['VISIBLE_TRANSLATE'] == 517 and ordinary['UNKNOWN'] == 0
    assert native['VISIBLE_TRANSLATE'] == 192 and native['UNKNOWN'] == 1237
    nebula_path = WORK / 'candidate_builds/ko_candidate_03/nebula_validation.json'
    nebula = load(nebula_path)
    assert nebula['status'] == 'PASS' and nebula['candidate_dat_sha256'] == static['candidate_dat_sha256']
    assert nebula['translation_sha256'] == sha(translations_path)
    OUT.mkdir(parents=True)
    freeze = dict(game_id='COBALT_MINER', steam_build='24347666', candidate_id=CANDIDATE.name,
                  frozen_utc=utc_now(), files=[dict(path=n, size=p.stat().st_size, sha256=sha(p)) for n, p in candidate.items()])
    freeze_path = OUT / 'candidate_manifest.json'
    write_json(freeze_path, freeze)
    common = dict(candidate_manifest_sha256=sha(freeze_path))
    checks = {
        'G2': dict(status='FAIL', scope='일반 분류 미확정0, 네이티브 표시 여부 미확정1237. 추가 조사 종료, 전체 분류 통과 아님.',
                   counts=dict(general=dict(ordinary), native=dict(native)), evidence=[ref(inventory_path), ref(native_path)]),
        'G3': dict(status='PASS', scope='확인된 번역 대상397종517위치·네이티브192필드·이미지12개와 필요 문자616종. 미분류 엔진 문구는 포함하지 않음.',
                   known_translation_omissions=0, font_missing_characters=0, evidence=[ref(translations_path), ref(static_path), ref(WORK / 'translation_02/change_report.json')]),
        'G4': dict(status='PASS', scope='현재 후보15파일의 위치별 재추출·기대 번역·변경 경계·전체 이미지·글꼴 정적 재검사. 화면 검수 통과를 뜻하지 않음.',
                   evidence=[ref(static_path), ref(nebula_path), ref(WORK / 'final_static_01/positions.json'), ref(WORK / 'final_static_01/native_positions.json')]),
        'G5': dict(status='FAIL', scope='대표 대사·설정·이미지·A엔딩 일부 확인. 전체 시설·분기·예비 화면 및 최종 재시작 불러오기 미완료. 기존 종료 오류 기록 보존.',
                   stopped_by_current_user_request=True,
                   findings=['빠른 A엔딩→이어하기→종료는 원본과 후보에서 동일 오류. 충분히 대기한 후보 경로는 오류0건.',
                             '이전 B엔딩 검수 종료의 D3D11 오류 원인은 미확정.',
                             '현재 후보 A엔딩 저장·이어하기·종료와 감시 파일17개 보존 확인. 전체 회차 완주 아님.',
                             'qa_ko03_restart01은 사용자 중단 뒤 종료만 확인, 새 프로세스 불러오기 성공으로 기록하지 않음.'],
                   evidence=[ref(WORK / 'runtime_planning_01/close_failure_matrix.json'), ref(WORK / 'runtime_planning_01/terminal_log_reaudit.json'),
                             ref(WORK / 'qa_ko03_terminal_a_settled/evidence/screen_review.json'), ref(WORK / 'qa_ko03_restart01/evidence/post_integrity.json')])
    }
    check_refs = {}
    for name, check in checks.items():
        path = OUT / (name + '.json')
        write_json(path, dict(**common, **check))
        check_refs[name] = dict(status=check['status'], **ref(path))
    waiver_path = OUT / 'user_review_scope.json'
    write_json(waiver_path, dict(authorization='EXPLICIT_USER_REQUEST', user_instruction=INSTRUCTION,
                                recorded_utc=utc_now(), candidate_manifest_sha256=sha(freeze_path), waived_checks=['G2', 'G5'],
                                interpretation='추가 조사·화면 검수를 종료하고, 확인된 번역 범위와 미확인 엔진 문구를 명시한 개인용으로 마무리. 기존 FAIL은 유지.',
                                retained_checks=['G4_FINAL_RECHECK', 'G6', 'G7_EXTENDED_INSTALLER_QA', 'ACTUAL_INSTALL_HASH_AND_SAVE_INTEGRITY']))
    dependencies = {p.resolve() for p in [baseline_path, build_path, translations_path, inventory_path, native_path, static_path, nebula_path,
                                        Path(__file__), Path(__file__).with_name('release_package.py'), Path(__file__).with_name('test_installer.py')]}
    for name in ('Patch.ps1', 'ChooseGame.ps1'):
        dependencies.add((Path(__file__).parent / 'release_template' / name).resolve())
    dependencies.update(Path(p).resolve() for p in build['inputs']['tracked_inputs'])
    dependencies.update((ROOT / p).resolve() for p in build['inputs']['tools'])
    for check in checks.values():
        dependencies.update((ROOT / item['path']).resolve() for item in check['evidence'])
    for run in ('qa_ko03_terminal_a_settled', 'qa_ko03_restart01'):
        dependencies.update((WORK / run / 'evidence' / n).resolve() for n in ('prelaunch.json', 'rea_runtime.json', 'post_integrity.json'))
    write_json(OUT / 'release_gate.json', dict(game_id='COBALT_MINER', steam_build='24347666', candidate_id=CANDIDATE.name,
                                            status='USER_WAIVER', candidate_manifest=ref(freeze_path), waiver=ref(waiver_path),
                                            allowed_changes=[n for n in candidate if sha(candidate[n]) != sha(original[n])],
                                            checks=check_refs, dependencies=[ref(p) for p in sorted(dependencies)]))
    print(json.dumps(dict(status='FROZEN_WITH_LIMITED_REVIEW', candidate=CANDIDATE.name, known_translation_omissions=0,
                          native_unknown=native['UNKNOWN'], changes=6, gates={k:v['status'] for k,v in checks.items()})))


if __name__ == '__main__':
    main()
