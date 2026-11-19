"""실행 모형 EXE를 원본 EXE로 잘못 비교한 시험만 교정하고 남은 검사를 수행합니다."""
import ast
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from test_installer import InstallerTests
from release_package import WORK, BASELINE, EXE, sha, write_json


class CorrectedTests(InstallerTests):
    def test_running_guard(self):
        folder = self.folder('running_game_guard_corrected')
        shutil.copy2(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', folder / EXE)
        # 검사 대상은 시험 시작 시점의 모형 파일입니다. 설치기가 바꾸지 않았는지 대조합니다.
        expected = self.baseline_hashes(folder)
        process = subprocess.Popen([str(folder / EXE), '/d', '/c', 'set /p wait_input='],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            assert process.poll() is None
            self.run('reject_running_target_path_stub', 'Install', folder, success=False, hashes=expected,
                     message='적용 대상 게임이 실행 중입니다')
        finally:
            process.kill()
            process.communicate(timeout=10)


def main():
    original = WORK / 'package_1.0.0_r1'
    prior_path = original / 'installer_tests.json'
    prior = json.loads(prior_path.read_text(encoding='utf-8'))
    package = json.loads((original / 'package.json').read_text(encoding='utf-8'))
    assert prior['status'] == 'FAIL' and prior['zip_sha256'] == package['zip_sha256']
    assert prior['failure'].startswith('AssertionError(') and prior['failure'].endswith(')')
    failure = ast.literal_eval(prior['failure'][len('AssertionError('):-1])
    assert failure[0] == 'reject_running_target_path_stub'
    observed, expected = failure[1:]
    assert set(observed) == set(expected)
    assert [n for n in observed if observed[n] != expected[n]] == [EXE]
    assert observed[EXE] == sha(Path(os.environ['SystemRoot']) / 'System32/cmd.exe')
    assert all(r['status'] == 'PASS' for r in prior['tests'])
    gate = json.loads((WORK / 'release_freeze_1.0.0_r1/release_gate.json').read_text(encoding='utf-8'))
    test_ref = next(r for r in gate['dependencies'] if r['path'] == 'tasks/COBALT_MINER/test_installer.py')
    assert sha(Path(__file__).with_name('test_installer.py')) == test_ref['sha256']
    scratch = WORK / 'package_1.0.0_r1_final_tests'
    assert not scratch.exists()
    scratch.mkdir()
    assert sha(package['archive']) == package['zip_sha256']
    with zipfile.ZipFile(package['archive']) as archive:
        assert set(archive.namelist()) == set(package['allowed_files']) and archive.testzip() is None
        archive.extractall(scratch / 'from_final_zip')
    package['scratch'] = str(scratch)
    write_json(scratch / 'package.json', package)
    tests = CorrectedTests(scratch / 'package.json', BASELINE)
    tests.records = prior['tests'].copy()
    tests.started = prior['started_utc']
    tests.test_running_guard()
    tests.clean_completed_group()
    tests.test_discovery()
    tests.clean_completed_group()
    result = tests.finish()
    result['test_tool_sha256'] = sha(Path(__file__))
    result['base_test_tool_sha256'] = test_ref['sha256']
    result['corrected_fixture_expectation'] = dict(prior_report_sha256=sha(prior_path), reused_passed_cases=len(prior['tests']),
        reason='원본 EXE 지문 대신 시험 모형의 실행 직전 지문을 기대값으로 사용. 설치기·ZIP·원본·후보·이전 시험 도구는 동일.',
        rerun_cases=['reject_running_target_path_stub', 'steam_additional_library_and_nested_receipt_discovery'])
    write_json(scratch / 'installer_tests.json', result)
    # 실패 원문을 별도 보존하고 원래 패키지 경로에는 최종 검사의 연결을 포함합니다.
    preserved = original / 'installer_tests_failed_stub_expectation.json'
    assert not preserved.exists()
    shutil.copy2(prior_path, preserved)
    result['final_test_report'] = dict(path=str(scratch / 'installer_tests.json'), sha256=sha(scratch / 'installer_tests.json'))
    write_json(prior_path, result)


if __name__ == '__main__':
    main()
