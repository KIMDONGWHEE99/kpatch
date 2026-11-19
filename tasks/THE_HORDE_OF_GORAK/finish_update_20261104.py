"""업데이트 패치의 검수 기록, 최종 ZIP 및 설치기 시험을 같은 후보에 연결합니다."""
import argparse
import collections
import json
import shutil
from pathlib import Path

import release_package as release
from test_installer import InstallerTests
from update_20261104 import ROOT, WORK, SOURCE, GAME, sha, save

CANDIDATE = ROOT / 'build_candidate/THE_HORDE_OF_GORAK/ko_1_0_1_c01/game'
SCRATCH = WORK.parent / 'package_1.0.1_r1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def monitored_files(roots):
    result = {}
    for root in map(Path, roots):
        if root.name == 'userdata':
            files = [p for account in root.iterdir() if account.is_dir() for p in (account / '4911050').rglob('*') if p.is_file()]
        elif root.is_dir():
            files = [p for p in root.rglob('*') if p.is_file()]
        else:
            files = [root] if root.is_file() else []
        for path in files:
            result[str(path)] = {'path': str(path), 'size': path.stat().st_size, 'sha256': sha(path)}
    return result


def integrity():
    installed = read(WORK / 'installed_before.json')
    assert all(sha(GAME / r['path']) == r['sha256'] for r in installed), '검수 중 설치본 변경'
    results = []
    for name in ('qa_update1104', 'qa_update_original1104', 'qa_update_exact1104', 'qa_update_shop1104', 'qa_update_shop_direct1104'):
        evidence = WORK.parent / name / 'evidence'
        before = read(evidence / 'prelaunch.json')
        expected = {r['path']: r for r in before['user_files_before']}
        current = monitored_files(before['monitored_roots'])
        changes = [p for p in expected.keys() | current.keys() if expected.get(p) != current.get(p)]
        result = {'status': 'PASS' if not changes else 'FAIL', 'installed_files_unchanged': len(installed),
                  'user_files': len(expected), 'changed_user_files': changes,
                  'steam_manifest_unchanged': sha(WORK / 'steam_manifest.acf') == sha(Path('D:/steam/steamapps/appmanifest_4911050.acf')),
                  'scope': '명시한 저장·설정·Steam 앱 사용자 파일 영역과 설치 게임 32파일의 내용 비교'}
        save(evidence / 'post_integrity.json', result)
        assert not changes, changes
        results.append({'run': name, **result})
    rows = [json.loads(line) for line in (WORK / 'classification/inventory.jsonl').read_text(encoding='utf-8').splitlines()]
    summary_path = WORK / 'classification/summary.json'
    summary = read(summary_path)
    if not (WORK / 'classification/summary_before_resolution.json').exists():
        shutil.copy2(summary_path, WORK / 'classification/summary_before_resolution.json')
    summary['classification'] = dict(collections.Counter(r['classification'] for r in rows))
    summary['resolved_by'] = 'translations()의 확장 자료 숫자 필드 판독과 동일 네이티브 코드 근거'
    summary['inventory_sha256'] = sha(WORK / 'classification/inventory.jsonl')
    assert summary['classification'].get('UNKNOWN', 0) == 0
    save(summary_path, summary)
    save(WORK / 'unknown_resolution_final.json', {'status': 'PASS', 'remaining': 0, 'resolved': [r for r in rows if r['kind'] == 'utf16_candidate']})
    runtime = read(WORK.parent / 'qa_update_exact1104/evidence/rea_runtime.json')
    messages = runtime['normalized_result']['messages']
    exceptions = [m for m in messages if m.get('type') == 'error' or m.get('payload', {}).get('kind') == 'native_exception']
    assert not exceptions and not runtime['normalized_result']['messages_truncated']
    assert runtime['normalized_result']['state'] == 'detached'
    save(WORK / 'validation/runtime_summary.json', {
        'status': 'NOT_RUN', 'scope': '대표 흐름은 확인했으나 사용자의 현재 화면 검수 중단 요청으로 전체 G5는 미완료',
        'user_instruction': '화면 검수는 여기까지 하고 마무리해주세요',
        'checked': ['한국어 메뉴와 설정', '도입부', '지도', '전투 HUD와 안내', '저장 후 메뉴', '이어하기와 전투 복원', '정상 종료'],
        'not_checked': ['신규 상점의 실제 화면과 구매', '엔딩', '전체 분기', '모든 문구의 화면 표시', '최종 설치본 추가 실행'],
        'exact_run': 'qa_update_exact1104', 'pid': runtime['normalized_result']['pid'],
        'process_path': runtime['normalized_result']['target'],
        'candidate_dat_sha256': sha(CANDIDATE / 'THOG.dat'), 'qa_dat_sha256': sha(WORK.parent / 'qa_update_exact1104/game/THOG.dat'),
        'native_exceptions': 0, 'rea_script_errors': 0,
        'modules': [m['payload'] for m in messages if m.get('payload', {}).get('kind') == 'loaded_module' and any(k in m['payload'].get('name', '').lower() for k in ('d3d', 'dxgi', 'nvidia', 'nvwg'))],
        'isolation': 'REA 실행 전 저장 경로 전환·외부 쓰기·Steam 초기화 차단. 사용자 파일 전후 일치.',
        'qa_window_flags_issue': '변경한 창 플래그에서 원본과 후보가 동일 mmfs2.dll+0x1f759 오류. 원래 플래그의 후보는 정상 실행. Ghidra 함수 분석을 보존했으며 원인 전체 확정이나 엔진 코드 수정은 하지 않음.',
        'shop_fixture': '별도 검수 저장 및 새 게임 장면 이동 인수 2바이트 변경 사본은 제작했으나 상점 화면 미확인. 배포에는 포함하지 않음.',
        'integrity': results})
    save(WORK / 'validation/g4_method_clarification.json', {
        'status': 'PASS', 'summary_sha256': sha(WORK / 'validation/g4_summary.json'),
        'clarification': '이미지 원시 레코드와 독립 Nebula 픽셀 지문을 비교하고 수정한 4개는 승인 PNG를 BGRA로 변환해 비교했습니다. metadata-only 추출이므로 전 이미지 PNG 파일을 생성했다는 뜻이 아닙니다. g4_summary의 PNG RGBA 전수 대조라는 공통 안내를 이 설명으로 한정합니다.'})
    print(json.dumps({'integrity': 'PASS', 'runs': len(results), 'classification': summary['classification'], 'runtime': 'PARTIAL'}, ensure_ascii=False))


def package():
    release.BUILD = '26365992'
    release.BASELINE = SOURCE
    source = read(WORK / 'baseline_manifest.json')
    frozen = read(WORK / 'candidate_manifest.json')
    g4 = read(WORK / 'validation/g4_summary.json')
    runtime = read(WORK / 'validation/runtime_summary.json')
    assert g4['status'] == 'PASS' and g4['candidate_sha256'] == sha(CANDIDATE / 'THOG.dat')
    assert runtime['candidate_dat_sha256'] == g4['candidate_sha256'] == runtime['qa_dat_sha256']
    assert all(r['status'] == 'PASS' for r in runtime['integrity'])
    assert set(release.file_map(SOURCE)) == {r['path'] for r in source['files']}
    assert set(release.file_map(CANDIDATE)) == {r['path'] for r in frozen['files']}
    for folder, records in ((SOURCE, source['files']), (CANDIDATE, frozen['files'])):
        for r in records:
            assert sha(folder / r['path']) == r['sha256'] and (folder / r['path']).stat().st_size == r['size']
    originals = {r['path']: r for r in source['files']}
    changes = sorted(r['path'] for r in frozen['files'] if r['sha256'] != originals[r['path']]['sha256'])
    assert len(changes) == 12 and 'THOG.dat' in changes and frozen['qa_overrides_included'] is False
    dependencies = [WORK / x for x in ('baseline_manifest.json', 'candidate_manifest.json', 'translations.json', 'classification/inventory.jsonl', 'media_review.json', 'validation/g4_summary.json', 'validation/g4_method_clarification.json', 'validation/runtime_summary.json')]
    dependencies.extend(sorted((ROOT / 'tasks/THE_HORDE_OF_GORAK').glob('*.py')))
    dependencies.extend(sorted((ROOT / 'tasks/THE_HORDE_OF_GORAK/release_template').glob('*')))
    dependencies = [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p)} for p in dependencies if p.is_file()]
    public = {'game_id': release.GAME, 'steam_build': release.BUILD, 'candidate_id': frozen['candidate_id'],
              'status': 'RELEASED_WITH_USER_REQUESTED_REVIEW_OMISSIONS',
              'user_instruction': '화면 검수는 여기까지 하고 마무리해주세요',
              'inherited_omissions': '기존 공개판에서 사용자 중단 요청으로 남긴 네이티브 진단 문구 전수 분류와 전체 분기 검수는 완료로 바꾸지 않습니다.',
              'checks': {'G3': {'status': 'PASS', 'scope': '604종 875위치 번역·글꼴·이미지 준비'},
                         'G4': {'status': 'PASS', 'scope': '12,080개 독립 위치·글꼴·픽셀·게임 구조 검사. 예상 밖 변경 0건'},
                         'G2': {'status': 'NOT_RUN', 'scope': '새 DAT 2,818항목과 새 이미지 71개 분류 완료. 바뀌지 않은 엔진의 일부 영문 진단 문구 전수 분류는 기존 미완료 상태 유지'},
                         'G5': {'status': 'NOT_RUN', 'scope': '메뉴·설정·도입부·지도·전투·저장/이어하기·종료 확인. 신규 상점 실화면·엔딩·전체 분기·최종 설치본 추가 실행 미확인'},
                         'G7': {'status': 'NOT_RUN', 'scope': '이 기록은 ZIP 생성 시점. 최종 ZIP의 설치·복구 시험 결과는 공개 저장소 releases/v1.0.1.md 및 검증 요약에서 확인'}},
              'candidate_manifest_sha256': sha(WORK / 'candidate_manifest.json')}
    gate = {'status': 'USER_WAIVER', 'candidate_id': frozen['candidate_id'], 'allowed_changes': changes,
            'candidate_manifest_sha256': public['candidate_manifest_sha256'], 'dependencies': dependencies,
            'public_review_status': public}
    save(WORK / 'release_gate.json', gate)
    readme = '''The Horde of Gorak 한국어 패치 1.0.1

지원: Windows Steam 앱 4911050 / 빌드 26365992 / 게임 v1.1.04
게임이 v1.1.04로 업데이트되면서 막힌 1.0.0 패치를 새 자료 구조에 맞춰 갱신했습니다.
메뉴·본문 604종 875위치, 실행 모듈 표시 문구 176필드, 이미지 문구 4곳과 한글 글꼴을 반영합니다.
오우거 상점·금화 등 신규 문구 15종을 추가했습니다. 게임 규칙과 저장 형식은 바꾸지 않습니다.

설치
1. 게임을 종료하고 이 ZIP 전체를 새 폴더에 풉니다.
2. Install.cmd를 실행하여 THOG.exe가 있는 게임 폴더를 선택합니다.
3. 설치가 끝나면 Steam에서 평소처럼 실행합니다.
현재 v1.1.04 원본과 이전 패치의 실행 모듈이 함께 남은 업데이트 상태를 지원합니다.
v1.1.03에 그대로 적용하지 마세요. 먼저 Steam에서 게임을 업데이트합니다.

업데이트와 호환성
설치기는 Steam 빌드 번호만으로 막지 않고 실제 파일 내용 지문으로 판정합니다.
번호만 바뀌고 검증하는 파일이 같으면 적용할 수 있습니다. 파일 내용이 바뀌면 별도 대응이 필요합니다.
지원하지 않는 파일에 강제 적용하지 않습니다. 모든 미래 업데이트의 호환성을 보장하지 않습니다.

제거·복구
같은 패키지의 Remove.cmd에서 같은 게임 폴더를 선택합니다.
백업: %LOCALAPPDATA%\\TheHordeOfGorakKoreanPatch\\working_private\\<설치경로 지문>\\build_26365992
중단 후에는 같은 버전의 Install.cmd를 다시 실행해 복구합니다. 원본 백업을 임의로 삭제하지 마세요.
기존 build_26336311 백업은 별도로 보존합니다. 설치·제거기는 사용자 저장 파일을 바꾸지 않습니다.

확인 범위
새 후보의 번역 위치·글꼴·이미지·게임 구조 12,080개 검사를 통과했습니다.
새 버전 메뉴·설정·도입부·지도·전투·저장 후 이어하기·정상 종료를 확인했습니다.
사용자의 화면 검수 종료 요청에 따라 신규 상점 실화면·엔딩·전체 분기·최종 설치본 재실행은 미확인입니다.
기존 엔진의 일부 JSON 오류 등 영문 진단 문구가 남습니다. 전체 검수 통과판은 아닙니다.
최종 ZIP의 설치·복구 시험 결과는 저장소의 releases/v1.0.1.md에 별도로 기록합니다.
REVIEW_STATUS.json은 패키지 생성 시점의 확인 범위입니다.

게임 원본·개인 저장·검수용 변경을 포함하지 않는 차이 패치입니다.
게임 제목·브랜드 로고·제작진은 원문을 유지합니다. 도구·글꼴 라이선스는 licenses 폴더에 있습니다.
공개 저장소: https://github.com/KIMDONGWHEE99/the-horde-of-gorak-korean-patch
'''
    report = release.make_package(SOURCE, CANDIDATE, list(originals), changes,
                                  ROOT / 'release_output/THE_HORDE_OF_GORAK_KOREAN_PATCH_1.0.1_r1', SCRATCH,
                                  '1.0.1', frozen['candidate_id'], readme, gate)
    assert all(sha(ROOT / d['path']) == d['sha256'] for d in dependencies), '패키징 도중 입력 변경'
    print(json.dumps({'archive': report['archive'], 'zip_sha256': report['zip_sha256'], 'changes': len(changes)}, ensure_ascii=False))


class UpdateTests(InstallerTests):
    def test_normal(self):
        super().test_normal()
        # 실제 Steam 갱신 상태를 재현: 새 DAT와 이전 공개 패치의 동일 네이티브 모듈.
        mixed = self.folder('previous_public_patch_after_steam_update')
        for r in read(WORK / 'installed_before.json'):
            if r['state'] == 'old_patch':
                assert sha(CANDIDATE / r['path']) == r['sha256']
                shutil.copy2(CANDIDATE / r['path'], mixed / r['path'])
        self.run('previous_public_release_update', 'Install', mixed)
        self.run('updated_public_release_remove', 'Uninstall', mixed)
        # 빌드 번호가 달라도 내용이 동일한 경우의 직접 지정 설치.
        same = self.folder('same_files_new_build_number')
        acf = same.parent / 'appmanifest_4911050.acf'
        acf.write_text('"AppState" { "appid" "4911050" "buildid" "99999999" }', encoding='utf-8')
        self.run('same_files_different_build_number', 'Install', same)
        self.run('same_files_different_build_remove', 'Uninstall', same)
        # 예전 DAT를 새 패치로 강제 덮어쓰지 않는지 확인.
        old = self.folder('previous_game_build_rejected')
        shutil.copy2(WORK / 'previous_original/THOG.dat', old / 'THOG.dat')
        self.run('previous_game_build_rejected', 'Install', old, success=False, hashes=self.baseline_hashes(old))


def tests():
    result = UpdateTests(SCRATCH / 'package.json', SOURCE).run_all()
    assert result['status'] == 'PASS'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('step', choices=['integrity', 'package', 'tests'])
    args = parser.parse_args()
    globals()[args.step]()
