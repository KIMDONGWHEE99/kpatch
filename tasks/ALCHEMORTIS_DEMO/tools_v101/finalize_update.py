"""업데이트 대응의 입력·후보·최종 설치 결과를 같은 빌드로 고정합니다."""
from pck_tools import ROOT, WORK
from pathlib import Path
from datetime import datetime
import json, hashlib, re, subprocess, zipfile

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

static = read(WORK/'static_validation.json')
runtime = read(WORK/'runtime_final_audit.json')
install = read(WORK/'installation_final.json')
package = read(WORK/'package_v3/package.json')
cases = read(WORK/'package_v3/installer_tests.json')['cases'] + read(WORK/'package_v3/installer_edge_tests.json')['cases']
archive = ROOT/'release_output/ALCHEMORTIS_DEMO_KOREAN_PATCH_1.0.1.zip'
folder = ROOT/'release_output/ALCHEMORTIS_DEMO_KOREAN_PATCH_1.0.1'
assert sha(archive) == package['zip_sha256'] == install['zip_sha256']
assert len(cases) == 27 and all(c['status'] == 'PASS' for c in cases)
assert install['status'] == 'PASS' and install['installed_hashes'] == static['files']
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist()) == set(package['allowed_files'])
    assert all(z.read(n) == (folder/n).read_bytes() for n in z.namelist())
assert {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()} == set(package['allowed_files'])

qa = WORK/'qa_02'
observations = {
    'main_v0222': '0.22.2 표시·한국어 첫 화면',
    'settings_v0222': '음량·화면·글꼴 설정',
    'languages_v0222': '기존 7개 언어와 한국어',
    'credits_v0222': '원래 제작진 장면의 한국어 제목',
    'character_v0222': '캐릭터·추가 규칙 미선택 안내',
    'update_ability_inspector': '새 지급·비용·복사 출처 설명과 아이콘, 픽셀 글꼴',
    'update_ability_readable': '새 설명의 읽기 편한 글꼴',
}
visual = [{'id': k, 'scope': v, 'status': 'PASS', 'capture_sha256': sha(qa/(k+'.png')), 'nodes_sha256': sha(qa/(k+'.json'))} for k,v in observations.items()]
save(WORK/'visual_review_ledger.json', {'candidate': static['candidate'], 'cases': visual, 'full_playthrough': 'NOT_RUN'})
process = subprocess.run(['powershell','-NoProfile','-Command',"@(Get-Process -Name 'Alchemortis Demo' -ErrorAction SilentlyContinue) | Select-Object Id,Path | ConvertTo-Json -Compress"], capture_output=True, text=True)
assert not process.stdout.strip(), process.stdout
save(qa/'normal_exit.json', {'status': 'PASS', 'method': '검수 사본의 SceneTree.Quit 정상 종료', 'processes_after': [], 'checked_at': datetime.now().astimezone().isoformat()})

public = ROOT/'validation/ALCHEMORTIS_DEMO/ko_1.0.1'
summary = {
    'game': 'ALCHEMORTIS_DEMO', 'steam_app': 4974580, 'old_build': 25423154, 'new_build': 25443537,
    'game_version': '0.22.2-demo', 'patch_version': '1.0.1', 'candidate': static['candidate'],
    'cause': 'Steam 업데이트가 실행 파일·PCK·게임 DLL을 새 원본으로 교체',
    'installation': {k:install[k] for k in ['status','files_verified','modified_files','additional_files','user_files_preserved','user_data_equal','legacy_backup_files_preserved']},
    'translation': {'entries': 2033, 'translated': 1598, 'hidden_original_entries': 435, 'new_translations': 3},
    'census': {k:v for k,v in read(WORK/'discovery/census_report.json').items() if not k.startswith('source_')},
    'runtime': {'actual_graphics_cases': visual, 'cards': 276, 'card_tiers': 1380, 'artifacts': 62, 'required_characters': 828,
                'missing_glyphs': 0, 'unexpected_errors': 0, 'original_fixture_diagnostic_lines': len(runtime['log']['original_fixture_diagnostics']),
                'full_playthrough': 'NOT_RUN', 'all_unlock_states': 'NOT_RUN'},
    'installer_cases': cases, 'package_files': package['allowed_files'], 'zip_sha256': sha(archive), 'zip_bytes': archive.stat().st_size,
    'changed_file_hashes': {k:static['files'][k] for k in static['changed_files']},
    'all_gates_passed': False, 'public_upload': 'NOT_RUN'
}
save(public/'release_evidence.json', summary)
save(public/'gates.json', {'candidate':static['candidate'], 'all_gates_passed':False, 'static_validation':'PASS',
     'updated_source_census':'PASS', 'specified_graphics_cases':'PASS', 'full_runtime_qa':'NOT_RUN',
     'final_zip_installer_tests':'PASS', 'actual_installation':'PASS', 'user_data_and_old_backups_preserved':'PASS',
     'note':'7건의 화면과 이번 업데이트 변경 범위만 확인. 이전 빌드의 전체 실행 QA를 새 빌드 완료로 옮기지 않음.'})

paths = set()
for directory in ['discovery','translation','fonts','media','qa_02']:
    for p in (WORK/directory).rglob('*'):
        if p.is_file() and 'game' not in p.relative_to(WORK/directory).parts and p.suffix.lower() in {'.json','.po','.tsv','.png','.jpg','.log','.ttf'}:
            paths.add(p)
for p in WORK.glob('*.json'):
    if p.name != 'final_input_lock.json': paths.add(p)
for name in ['package.json','installer_tests.json','installer_edge_tests.json']:
    paths.add(WORK/'package_v3'/name)
for base in [ROOT/'tasks/ALCHEMORTIS_DEMO/tools_v101',WORK/'toolchain/AssemblyTool',WORK/'toolchain/QaRunner',public,folder]:
    for p in base.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts: paths.add(p)
paths.add(archive)
save(WORK/'final_input_lock.json', {'candidate':static['candidate'], 'steam_build':25443537, 'created_at':datetime.now().astimezone().isoformat(),
     'candidate_files':static['files'], 'artifacts':{p.relative_to(ROOT).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(paths)},
     'invalidation':'입력이나 후보가 달라지면 관련 결과를 STALE로 바꾸고 새 검사 필요'})
for p in [public/'RESULT_REPORT.md', ROOT/'tasks/ALCHEMORTIS_DEMO/README.md',ROOT/'tasks/ALCHEMORTIS_DEMO/TASK_SPEC.md']:
    for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if '://' not in target: assert (p.parent/target).resolve().exists(),target
print(json.dumps({'installation':'PASS','screens':len(visual),'installer_cases':len(cases),'user_files':install['user_files_preserved'],'old_backup_files':install['legacy_backup_files_preserved'],'zip_sha256':sha(archive),'locked_artifacts':len(paths)},ensure_ascii=False))
