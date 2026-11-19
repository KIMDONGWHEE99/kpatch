"""사용자의 추가 검수 중단·마무리 요청을 기존 동결 후보에 연결한다."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/THE_HORDE_OF_GORAK'
OUT = WORK / 'personal_release_01'
CANDIDATE = ROOT / 'build_candidate/THE_HORDE_OF_GORAK/ko_candidate_03'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, data):
    path = OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}


def main():
    assert not OUT.exists(), '기존 마무리 기록은 덮어쓰지 않습니다.'
    assembly_path = CANDIDATE / 'assembly_manifest.json'
    assembly_hash = sha(assembly_path)
    assert assembly_hash == '16606e91d2f92afcec7e9b966e8d2d63ccab21bf9a6e514b7fd48996c0801754'
    assembly = json.loads(assembly_path.read_text(encoding='utf-8'))
    assert assembly['qa_overrides_included'] is False
    dependencies = {}

    def dependency(path, expected):
        path = Path(path).resolve()
        relative = path.relative_to(ROOT).as_posix()
        assert sha(path) == expected, '입력 변경: ' + relative
        if relative in dependencies:
            assert dependencies[relative] == expected
        dependencies[relative] = expected

    dependency(assembly_path, assembly_hash)
    for path, expected in assembly['inputs'].items():
        dependency(path, expected)
    files = []
    for row in assembly['files']:
        path = CANDIDATE / 'game' / row['path']
        assert path.stat().st_size == row['size'] and sha(path) == row['candidate_sha256']
        files.append({'path': row['path'], 'size': row['size'], 'sha256': row['candidate_sha256']})
    assert len(files) == 32
    assert {p.relative_to(CANDIDATE / 'game').as_posix() for p in (CANDIDATE / 'game').rglob('*') if p.is_file()} == {r['path'] for r in files}
    source_checks = {}
    for gate in ['G3', 'G4']:
        path = WORK / 'final_validation_03' / (gate.lower() + '_summary.json')
        data = json.loads(path.read_text(encoding='utf-8'))
        assert data['status'] == 'PASS' and data['assembly_manifest_sha256'] == assembly_hash
        dependency(path, sha(path))
        for item in data['source_evidence']:
            dependency(item['path'], item['sha256'])
        source_checks[gate] = (path, data)
    OUT.mkdir(parents=True)
    freeze = write('candidate_manifest.json', {
        'game_id': 'THE_HORDE_OF_GORAK', 'steam_build': '26336311',
        'candidate_id': 'ko_candidate_03', 'files': files,
        'source_assembly_manifest_sha256': assembly_hash,
        'qa_overrides_included': False,
        'scope': '기존 조립 목록을 설치기 형식으로 정규화. 게임 파일 변경 없음.'})
    checks = {}
    for gate in ['G3', 'G4']:
        path, data = source_checks[gate]
        ref = write(gate.lower() + '.json', {
            'status': 'PASS', 'candidate_manifest_sha256': freeze['sha256'],
            'assembly_manifest_sha256': assembly_hash,
            'source_report': {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)},
            'scope': data['scope'] + '. 동결 파일·입력 지문 일치로 기존 근거 재사용.'})
        checks[gate] = {'status': 'PASS', **ref}
    reviews = []
    for run in ['qa_full01', 'qa_full02', 'qa_late02', 'qa_research01', 'qa_research02', 'qa_research03', 'qa_dragon01']:
        path = WORK / run / 'evidence/visual_review_01.json'
        dependency(path, sha(path))
        reviews.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)})
    for gate, scope in {
        'G2': 'DAT와 이미지 분류 완료. 실행 모듈의 전체 코드 문자열 분류는 사용자 중단 요청으로 미완료. JSON 해석 오류 등 추가 영문 진단 문구가 남음.',
        'G5': '메뉴·설정·지도·명성 특전·전투·저장/재실행/불러오기·결과 정렬·19종 도감·8개 연구·주요 건물·용 모집을 확인. 엔딩·용 도감 본문·예비 장면·전 문구 실화면 전수 검수·최종 설치본 재실행은 생략.',
        'G7': '합성 자료 설치/복구 48건과 게이트 시험 15건은 기존 PASS. 최종 ZIP 확장 실패/중단 복구 시험은 사용자 요청으로 생략. 적용 시 백업·파일 지문 확인은 유지.'
    }.items():
        ref = write(gate.lower() + '.json', {'status': 'NOT_RUN',
            'candidate_manifest_sha256': freeze['sha256'], 'scope': scope,
            'visual_evidence': reviews if gate == 'G5' else []})
        checks[gate] = {'status': 'NOT_RUN', **ref}
    waiver = write('user_review_stop.json', {
        'authorization': 'EXPLICIT_USER_REQUEST',
        'user_instruction': '검수 그만합시다 / 한글패치 마무리하세요.',
        'interpretation': '검수 중단 지시를 유지하면서 기존 검증 후보를 개인용으로 마무리·설치. 추가 전수 조사와 장시간 화면·확장 복구 시험을 재개하지 않음. 미수행을 PASS로 바꾸지 않음.',
        'candidate_manifest_sha256': freeze['sha256'],
        'waived_checks': ['G2', 'G4_FINAL_RECHECK', 'G5', 'G7_EXTENDED_INSTALLER_QA'],
        'excluded_unfinished_work': 'native04의 JSON 오류창 중계 코드 및 모든 QA 전용 변경은 포함하지 않음.'})
    gate = write('release_gate.json', {'game_id': 'THE_HORDE_OF_GORAK',
        'steam_build': '26336311', 'status': 'USER_WAIVER', 'candidate_id': 'ko_candidate_03',
        'candidate_manifest': freeze, 'waiver': waiver,
        'allowed_changes': [r['path'] for r in assembly['files'] if r['changed']],
        'dependencies': [{'path': p, 'sha256': h} for p, h in sorted(dependencies.items())],
        'checks': checks})
    readme = '''The Horde of Gorak 한국어 패치 1.0.0 (개인용)

지원: Windows / Steam 앱 4911050 / 빌드 26336311 / 게임 v1.1.03

적용 내용
본문·메뉴 855위치, 실행 모듈 176필드, 이미지 문구 4곳과 한글 글꼴을 반영했습니다.
진행 상황 및 결과 화면의 줄 정렬을 수정했습니다. 게임 규칙과 저장 형식은 유지합니다.
게임 제목·제작진·브랜드 로고는 원문을 유지합니다. 일부 JSON 오류 안내 등 영문 진단 문구는 남아 있습니다.

설치
1. 게임을 종료합니다.
2. ZIP을 새 폴더에 모두 풉니다. 게임 폴더 안에 풀 필요는 없습니다.
3. Install.cmd를 실행하고 THOG.exe가 있는 게임 폴더를 선택합니다.
4. Steam에서 평소처럼 게임을 실행하면 한국어로 표시됩니다.
지원하는 원본 또는 이 패치가 적용된 파일만 처리합니다. 게임 업데이트 후에는 강제로 덮어쓰지 않습니다.

제거·복구
Remove.cmd를 실행하고 같은 게임 폴더를 선택합니다.
원본 백업은 설치 완료 메시지의 백업 경로에 보존됩니다.
기본 위치: %LOCALAPPDATA%\\TheHordeOfGorakKoreanPatch\\working_private\\<설치경로 지문>\\build_26336311
설치가 중단되면 같은 버전의 Install.cmd를 다시 실행해 복구합니다. 백업 폴더는 임의로 삭제하지 마세요.
설치기와 제거기는 사용자 저장 파일을 변경하지 않습니다.

확인 범위
메뉴·설정·지도·특전·전투·저장 후 재실행/이어하기·주요 건물·연구·결과·용 모집을 확인했습니다.
사용자의 검수 중단 후 마무리 요청에 따라 엔딩·전체 분기·일부 예비 화면·추가 코드 전수 분류·최종 ZIP의 확장 실패 복구 시험은 생략했습니다.
전체 검수 통과판으로 표시하지 않습니다. 자세한 상태는 REVIEW_STATUS.json에 있습니다.
검수용 저장 파일·개발 도구 활성화·실행 차단 코드는 포함하지 않습니다.

구성·라이선스
게임 원본 파일을 포함하지 않는 차이 패치입니다. xdelta3 및 Noto Sans KR의 라이선스는 licenses 폴더를 참고하세요.
'''
    (OUT / 'README.txt').write_text(readme, encoding='utf-8')
    print(json.dumps({'gate': gate, 'files': len(files), 'changed': assembly['changed_files'], 'dependencies': len(dependencies)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
