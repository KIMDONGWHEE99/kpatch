"""고정된 최종 ZIP의 설치기를 비공개 사본에서 정상·거부·복구 시험합니다."""
import argparse
import ctypes
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from package_release import BASELINE, BUILD_ANCHORS, WORK, PACK, sha, write_json, utc_now

SHELL = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
EXE = 'AgromaticDemo.exe'


class InstallerTests:
    def __init__(self, report, source, resume_after_message_wrap=False, unsupported_pack=None):
        self.report_path = Path(report).resolve()
        self.report_path.relative_to(WORK.resolve())
        self.report = json.loads(self.report_path.read_text(encoding='utf-8'))
        self.scratch = self.report_path.parent
        self.package = self.scratch / 'from_final_zip'
        self.manifest = json.loads((self.package / 'manifest.json').read_text(encoding='utf-8'))
        self.source = Path(source).resolve()
        self.source.relative_to((WORK.parents[1] / 'source_original').resolve()) if self.source == BASELINE else self.source.relative_to(WORK.resolve())
        self.tests = self.scratch / 'tests'
        self.resuming = resume_after_message_wrap
        prior = None
        if self.resuming:
            prior_path = self.scratch / 'installer_tests.json'
            prior = json.loads(prior_path.read_text(encoding='utf-8'))
            assert prior['status'] == 'FAIL' and prior['failure'] == "AssertionError('reject_running_target_path_stub')"
            assert prior['zip_sha256'] == self.report['zip_sha256'] and self.tests.is_dir()
            preserved = self.scratch / 'installer_tests_failed_message_wrap.json'
            assert not preserved.exists(), '이전 실패 기록을 덮어쓰지 않습니다.'
            shutil.copy2(prior_path, preserved)
            self.resume_evidence = {'prior_report_sha256': sha(preserved), 'unaffected_tests_reused': len(prior['tests']),
                                    'reason': '설치기·ZIP·원본은 동일하며 공백 정규화 메시지 검사를 고쳐 남은 시험을 다시 수행'}
        else:
            assert not self.tests.exists(), '기존 최종 ZIP 시험을 덮어쓰지 않습니다.'
            self.tests.mkdir()
        self.env = dict(os.environ)
        self.env['LOCALAPPDATA'] = str(self.tests / 'state')
        self.env['PSModulePath'] = str(SHELL.parent / 'Modules') + r';C:\Program Files\WindowsPowerShell\Modules'
        self.records = prior['tests'] if prior else []
        self.started = prior['started_utc'] if prior else utc_now()
        assert sha(self.report['archive']) == self.report['zip_sha256']
        assert sha(self.package / 'manifest.json') == self.report['manifest_sha256']
        for file in self.manifest['payload']:
            assert sha(self.package / file['path']) == file['sha256'], file['path']
        for file in self.manifest['baseline']:
            assert sha(self.source / file['path']) == file['sha256'], file['path']
        self.change = self.manifest['changes'][0]
        self.unsupported_pack = Path(unsupported_pack).resolve() if unsupported_pack else None
        if self.unsupported_pack:
            self.unsupported_pack.relative_to((WORK.parents[1] / 'build_candidate/AGROMATIC_DEMO').resolve())
            assert self.unsupported_pack.name == PACK
            assert sha(self.unsupported_pack) not in (self.change['original_sha256'], self.change['patched_sha256'])

    def folder(self, name):
        folder = self.tests / name / 'game'
        assert not folder.exists(), folder
        shutil.copytree(self.source, folder)
        # 설치기가 게임 파일 이외 자료를 바꾸지 않는지 독립적으로 확인합니다.
        (folder / '사용자 저장 보존 확인.dat').write_bytes(b'isolated synthetic user-save sentinel')
        return folder

    def state_for(self, folder, env=None):
        import hashlib
        key = hashlib.sha256(str(folder).lower().encode('utf-8')).hexdigest().upper()[:16]
        return Path((env or self.env)['LOCALAPPDATA']) / 'AgromaticKoreanPatch/working_private' / key / 'build_25850896'

    def command(self, folder, mode='Install', package=None):
        return [str(SHELL), '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                str((package or self.package) / 'Patch.ps1'), '-Mode', mode, '-GameDirectory', str(folder)]

    def unchanged_snapshot(self, folder):
        changed = {record['path'] for record in self.manifest['changes']}
        return {path.relative_to(folder).as_posix(): sha(path)
                for path in folder.rglob('*') if path.is_file() and path.relative_to(folder).as_posix() not in changed}

    def run(self, name, mode, folder, *, success=True, hashes=None, package=None, env=None, message=None):
        before = self.unchanged_snapshot(folder)
        started = utc_now()
        command = self.command(folder, mode, package)
        result = subprocess.run(command, env=env or self.env, capture_output=True, timeout=90)
        (self.tests / (name + '.stdout')).write_bytes(result.stdout)
        (self.tests / (name + '.stderr')).write_bytes(result.stderr)
        assert (result.returncode == 0) == success, (name, result.returncode, result.stderr.decode('utf-8', errors='replace'))
        if message:
            # 긴 경로에서 오류 표시가 단어 중간에 자동 줄바꿈되어도 원래 문장을 판별합니다.
            displayed = result.stdout.decode('utf-8', errors='replace') + result.stderr.decode('utf-8', errors='replace')
            assert ''.join(message.split()) in ''.join(displayed.split()), name
        if hashes is None:
            key = 'patched_sha256' if mode == 'Install' else 'original_sha256'
            hashes = {record['path']: record[key] for record in self.manifest['changes']}
        observed = {name: sha(folder / name) if (folder / name).is_file() else None for name in hashes}
        assert observed == hashes, (name, observed, hashes)
        assert self.unchanged_snapshot(folder) == before, '무변경 게임 파일 또는 저장 표본이 바뀌었습니다.'
        self.records.append({'id': name, 'status': 'PASS', 'started_utc': started, 'completed_utc': utc_now(),
                             'command': command, 'exit_code': result.returncode, 'files': observed,
                             'unchanged_file_count': len(before), 'save_sentinel': 'PASS'})
        print(name, 'PASS', flush=True)

    def expected(self, kind='original'):
        return {record['path']: record[kind + '_sha256'] for record in self.manifest['changes']}

    def baseline_hashes(self, folder):
        return {record['path']: sha(folder / record['path']) if (folder / record['path']).is_file() else None
                for record in self.manifest['changes']}

    def failed_package(self, name):
        package = self.tests / name
        shutil.copytree(self.package, package)
        return package

    def lock_file(self, path, share=3):
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                   ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        api.CreateFileW.restype = ctypes.c_void_p
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = api.CreateFileW(str(path), 0x80000000, share, None, 3, 0x80, None)
        assert handle not in (None, ctypes.c_void_p(-1).value), ctypes.get_last_error()
        return api, handle

    def test_normal(self):
        folder = self.folder('한글 공백 & 직접 지정 경로')
        self.run('install_original', 'Install', folder)
        for index, record in enumerate(self.manifest['changes']):
            assert sha(self.state_for(folder) / f'cache/{index}/original') == record['original_sha256']
        self.run('duplicate_install', 'Install', folder)
        self.run('installed_status', 'Status', folder, hashes=self.expected('patched'))
        if len(self.manifest['changes']) > 1:
            partial = self.folder('mixed_partial_install')
            first = self.manifest['changes'][0]['path']
            shutil.copy2(folder / first, partial / first)
            self.run('mixed_partial_install_resume', 'Install', partial)
            self.run('mixed_partial_install_remove', 'Uninstall', partial)
        self.run('remove', 'Uninstall', folder)
        self.run('duplicate_remove', 'Uninstall', folder)
        self.run('reinstall', 'Install', folder)
        fresh = dict(self.env)
        fresh['LOCALAPPDATA'] = str(self.tests / 'fresh_state')
        self.run('remove_without_backup_reverse_patch', 'Uninstall', folder, env=fresh)

    def test_refusal(self):
        if self.unsupported_pack:
            # 이전 비공개 검수 후보도 지원 목록에 없으면 덮어쓰지 않고 거부합니다.
            folder = self.folder('unsupported_private_prior_candidate')
            shutil.copy2(self.unsupported_pack, folder / PACK)
            self.run('reject_unsupported_private_prior_candidate', 'Install', folder, success=False,
                     hashes=self.baseline_hashes(folder), message='게임 버전이 다르거나 파일이 변경됐습니다')
        for label, filename in (('altered_pack', self.change['path']), ('unsupported_dependency', 'data_Agromatic_windows_x86_64/Agromatic.dll')):
            folder = self.folder(label)
            path = folder / filename
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
            self.run(label, 'Install', folder, success=False, hashes=self.baseline_hashes(folder))
        anchor_names = set(BUILD_ANCHORS) | set(self.expected())
        other_dependencies = [record['path'] for record in self.manifest['baseline']
                              if record['path'] not in anchor_names]
        if other_dependencies:
            folder = self.folder('unsupported_non_anchor_dependency')
            path = folder / other_dependencies[0]
            data = bytearray(path.read_bytes())
            assert data, '시험할 의존 파일이 비어 있습니다.'
            data[-1] ^= 1
            path.write_bytes(data)
            self.run('unsupported_non_anchor_dependency', 'Install', folder, success=False,
                     hashes=self.baseline_hashes(folder),
                     message='게임 버전이 다르거나 파일이 변경됐습니다')
        folder = self.folder('truncated_game_file')
        (folder / self.change['path']).write_bytes(b'truncated')
        self.run('truncated_game_file', 'Install', folder, success=False, hashes=self.baseline_hashes(folder))
        folder = self.folder('missing_game_file')
        (folder / 'steam_api64.dll').unlink()
        self.run('missing_game_file', 'Install', folder, success=False, hashes=self.expected())
        folder = self.folder('missing_changed_file')
        (folder / self.change['path']).unlink()
        self.run('missing_changed_file', 'Install', folder, success=False, hashes=self.baseline_hashes(folder))
        for label, filename in (('damaged_forward', self.change['forward']),
                                ('damaged_reverse', self.change['reverse']),
                                ('damaged_decoder', 'tools/xdelta3.exe')):
            package = self.failed_package(label + '_package')
            (package / filename).write_bytes(b'broken payload')
            folder = self.folder(label)
            self.run(label, 'Install', folder, success=False, hashes=self.expected(), package=package)
        folder = self.tests / 'invalid_game_path'
        folder.mkdir()
        self.run('invalid_game_path', 'Install', folder, success=False, hashes={})
        folder = self.folder('unsafe_manifest_path')
        package = self.failed_package('unsafe_manifest_package')
        manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
        manifest['baseline'][0]['path'] = '../escape.dat'
        write_json(package / 'manifest.json', manifest)
        self.run('unsafe_manifest_path', 'Install', folder, success=False, hashes=self.expected(), package=package)

    def test_failures(self):
        folder = self.folder('receipt_failure')
        blocked = self.state_for(folder) / 'receipt.json'
        blocked.mkdir(parents=True)
        self.run('rollback_after_receipt_write_failure', 'Install', folder, success=False, hashes=self.expected())
        assert json.loads((self.state_for(folder) / 'transaction.json').read_text(encoding='utf-8'))['phase'] == 'ROLLED_BACK'
        blocked.rmdir()
        self.run('retry_after_receipt_failure', 'Install', folder)
        self.run('remove_after_receipt_failure', 'Uninstall', folder)
        folder = self.folder('journal_write_failure')
        (self.state_for(folder) / 'transaction.json.new').mkdir(parents=True)
        self.run('journal_write_failure', 'Install', folder, success=False, hashes=self.expected())
        folder = self.folder('replacement_file_lock')
        # 읽기는 허용하지만 교체를 막습니다. 복원 검사도 같은 잠금 상태에서 가능합니다.
        record = self.manifest['changes'][-1]
        api, handle = self.lock_file(folder / record['path'])
        try:
            self.run('rollback_locked_replacement', 'Install', folder, success=False, hashes=self.expected())
        finally:
            api.CloseHandle(handle)
        assert json.loads((self.state_for(folder) / 'transaction.json').read_text(encoding='utf-8'))['phase'] == 'ROLLED_BACK'
        self.run('retry_after_file_unlock', 'Install', folder)
        self.run('remove_after_file_unlock', 'Uninstall', folder)
        if len(self.manifest['changes']) > 1:
            self.records.append({'id': 'second_replacement_rollback', 'status': 'PASS',
                                 'evidence': 'rollback_locked_replacement', 'changed_files': len(self.manifest['changes'])})
        else:
            self.records.append({'id': 'second_replacement_rollback', 'status': 'NOT_APPLICABLE',
                                 'reason': '배포본의 수정 파일이 1개이므로 두 번째 교체가 없습니다. 동일 설치기의 합성 2파일 시험은 별도 기록합니다.'})
        folder = self.folder('corrupt_backup')
        self.run('prepare_backup_corruption', 'Install', folder)
        (self.state_for(folder) / 'cache/0/original').write_bytes(b'corrupt backup')
        self.run('reject_corrupt_original_backup', 'Uninstall', folder, success=False, hashes=self.expected('patched'))
        folder = self.folder('interrupted_backup_preparation')
        pending = self.state_for(folder) / 'cache/0/original.new'
        pending.parent.mkdir(parents=True)
        pending.write_bytes(b'partial backup from interrupted preparation')
        self.run('retry_interrupted_backup_preparation', 'Install', folder)
        assert not pending.exists()
        self.run('remove_after_backup_preparation_recovery', 'Uninstall', folder)

    def test_interruption(self):
        folder = self.folder('강제 중단 후 복구')
        journal = self.state_for(folder) / 'transaction.json'
        temporary = folder / (self.change['path'] + '.agromatic-korean-new')
        output = (self.tests / 'forced_stop.stdout').open('wb')
        process = subprocess.Popen(self.command(folder), env=self.env, stdout=output, stderr=subprocess.STDOUT)
        observed = None
        deadline = time.monotonic() + 60
        try:
            while process.poll() is None and time.monotonic() < deadline:
                if temporary.exists():
                    observed = 'temporary_file_copy_or_replace'
                    process.kill()
                    break
                if journal.exists():
                    try:
                        phase = json.loads(journal.read_text(encoding='utf-8-sig'))['phase']
                    except (OSError, ValueError):
                        continue
                    if phase == 'APPLYING':
                        observed = 'APPLYING'
                        process.kill()
                        break
                time.sleep(0.001)
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            output.close()
        assert observed, '강제 중단 시점을 포착하지 못했습니다.'
        assert json.loads(journal.read_text(encoding='utf-8-sig'))['phase'] == 'APPLYING'
        self.records.append({'id': 'forced_process_stop', 'status': 'PASS', 'observed_phase': observed,
                             'exit_code': process.returncode, 'journal_sha256': sha(journal)})
        self.run('resume_after_forced_stop', 'Install', folder)
        assert not temporary.exists()
        self.run('remove_after_forced_stop_recovery', 'Uninstall', folder)
        self.run('prepare_after_replace_interruption', 'Install', folder)
        data = json.loads(journal.read_text(encoding='utf-8-sig'))
        data['phase'] = 'APPLYING'
        for entry, record in zip(data['entries'], self.manifest['changes']):
            entry['before'] = record['original_sha256']
        write_json(journal, data)
        self.run('recover_after_atomic_replace', 'Uninstall', folder)
        # 복구 대상이 지원하지 않는 내용이면 덮어쓰지 않습니다.
        self.run('prepare_stale_journal', 'Install', folder)
        data = json.loads(journal.read_text(encoding='utf-8'))
        data['phase'] = 'APPLYING'
        data['manifest_sha256'] = '0' * 64
        write_json(journal, data)
        self.run('reject_mismatched_recovery_journal', 'Uninstall', folder, success=False, hashes=self.expected('patched'))

    def test_running_guard(self):
        folder = self.folder('running_game_guard_stub_resume' if self.resuming else 'running_game_guard_stub')
        # 게임은 실행하지 않습니다. Windows 명령 처리기의 이름만 바꾼 대기용 모형입니다.
        shutil.copy2(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', folder / EXE)
        process = subprocess.Popen([str(folder / EXE), '/d', '/c', 'set /p wait_input='],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            assert process.poll() is None
            self.run('reject_running_target_path_stub', 'Install', folder, success=False, hashes=self.baseline_hashes(folder),
                     message='적용 대상 게임이 실행 중입니다')
        finally:
            process.kill()
            process.communicate(timeout=10)

    def test_discovery(self):
        folder = self.folder('steam_library_discovery')
        steam = self.tests / 'fake_steam'
        library = self.tests / '추가 Steam 라이브러리'
        game = library / 'steamapps/common/바뀐 설치 폴더 이름'
        game.parent.mkdir(parents=True)
        shutil.copytree(self.source, game)
        (steam / 'steamapps').mkdir(parents=True)
        escaped = str(library).replace('\\', '\\\\')
        (steam / 'steamapps/libraryfolders.vdf').write_text(f'"libraryfolders"\n{{\n "1"\n {{\n "path" "{escaped}"\n }}\n}}', encoding='utf-8')
        (library / 'steamapps/appmanifest_4252500.acf').write_text('"AppState"\n{\n "installdir" "바뀐 설치 폴더 이름"\n}', encoding='utf-8')
        receipt_root = self.tests / 'nested_receipts'
        nested = receipt_root / 'path_key/build_25850896'
        nested.mkdir(parents=True)
        write_json(nested / 'receipt.json', {'game_directory': str(folder)})
        def quote(path):
            return "'" + str(path).replace("'", "''") + "'"
        script = self.tests / 'test_discovery.ps1'
        script.write_text(f"$ErrorActionPreference='Stop'\n[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n. {quote(self.package / 'ChooseGame.ps1')}\n"
                          f"$locations=@(Get-GameLocations -SteamRoots @({quote(steam)}) -NearbyPaths @() -ReceiptRoot {quote(receipt_root)})\n"
                          f"$direct=Resolve-GameLocation {quote(folder / EXE)}\n"
                          "$form=New-GameLocationForm 'Install' $locations\n"
                          "try { [ordered]@{locations=$locations;direct=$direct;title=$form.Text;button=$form.AcceptButton.Text;size=$form.ClientSize.ToString()} | ConvertTo-Json -Compress } finally { $form.Dispose() }\n",
                          encoding='utf-8-sig')
        result = subprocess.run([str(SHELL), '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                                env=self.env, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        observed = json.loads(result.stdout.decode('utf-8-sig'))
        assert set(observed['locations']) == {str(folder), str(game)}, observed
        assert observed['direct'] == str(folder) and observed['button'] == '설치', observed
        self.records.append({'id': 'steam_additional_library_and_nested_receipt_discovery', 'status': 'PASS',
                             'exit_code': result.returncode, 'locations': observed['locations'],
                             'direct_executable_path': 'PASS', 'dialog_construction': 'PASS'})

    def finish(self):
        assert sha(self.report['archive']) == self.report['zip_sha256']
        assert sha(self.package / 'manifest.json') == self.report['manifest_sha256']
        records = [{'id': 'previous_public_release_update', 'status': 'NOT_APPLICABLE',
                    'reason': '최초 공개판이므로 지원할 이전 공개 패치가 없습니다.'},
                   {'id': 'mixed_partial_file_install', 'status': 'NOT_APPLICABLE' if len(self.manifest['changes']) == 1 else 'PASS',
                    'reason': '수정 파일 1개인 배포본에서는 파일 간 부분 적용 조합이 없습니다. 거래 강제 중단 복구는 별도로 시험합니다.'}]
        result = {'game_id': self.manifest['game_id'], 'steam_build': self.manifest['steam_build'],
                  'candidate': self.manifest['candidate'], 'zip_sha256': self.report['zip_sha256'],
                  'manifest_sha256': self.report['manifest_sha256'], 'status': 'PASS',
                  'started_utc': self.started, 'completed_utc': utc_now(), 'exit_code': 0,
                  'test_tool_sha256': sha(Path(__file__)), 'tests': self.records + records,
                  'game_execution': 'NOT_RUN', 'actual_steam_installation': 'NOT_RUN'}
        if self.resuming:
            result['resumed_verification'] = self.resume_evidence
        if self.unsupported_pack:
            result['unsupported_private_prior_pack'] = {'path': str(self.unsupported_pack), 'sha256': sha(self.unsupported_pack)}
        write_json(self.scratch / 'installer_tests.json', result)
        print('PASS:', len(self.records), '시험 기록', flush=True)
        return result

    def run_all(self):
        try:
            if not self.resuming:
                self.test_normal()
                self.test_refusal()
                self.test_failures()
                self.test_interruption()
            self.test_running_guard()
            self.test_discovery()
            return self.finish()
        except Exception as failure:
            write_json(self.scratch / 'installer_tests.json', {
                'game_id': self.manifest['game_id'], 'steam_build': self.manifest['steam_build'],
                'candidate': self.manifest['candidate'], 'zip_sha256': self.report['zip_sha256'],
                'status': 'FAIL', 'started_utc': self.started, 'completed_utc': utc_now(),
                'exit_code': 1, 'tests': self.records, 'failure': repr(failure),
                'game_execution': 'NOT_RUN', 'actual_steam_installation': 'NOT_RUN'})
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-report', required=True, type=Path)
    parser.add_argument('--source', default=BASELINE, type=Path)
    parser.add_argument('--resume-after-message-wrap', action='store_true')
    parser.add_argument('--unsupported-pack', type=Path)
    args = parser.parse_args()
    InstallerTests(args.package_report, args.source, args.resume_after_message_wrap, args.unsupported_pack).run_all()


if __name__ == '__main__':
    main()
