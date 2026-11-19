"""확정 ZIP·최종 설치 시험·실제 설치를 연결하고 공유 가능한 요약만 기록합니다."""
import collections
import json
from pathlib import Path
from release_package import ROOT, WORK, sha, write_json, verify_release_gate


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def ref(path):
    path = Path(path).resolve()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path))


def main():
    pack_path = WORK / 'package_1.0.0_r1/package.json'
    tests_path = WORK / 'package_1.0.0_r1/installer_tests.json'
    install_path = WORK / 'actual_install_1.0.0_r1/verification.json'
    gate_path = WORK / 'release_freeze_1.0.0_r1/release_gate.json'
    package, tests, installed = map(load, (pack_path, tests_path, install_path))
    assert tests['status'] == installed['status'] == 'PASS'
    assert package['zip_sha256'] == tests['zip_sha256'] == installed['zip_sha256'] == sha(package['archive'])
    assert verify_release_gate(gate_path, ROOT / 'build_candidate/COBALT_MINER/ko_candidate_03') == package['gates']
    assert sha(tests['final_test_report']['path']) == tests['final_test_report']['sha256']
    assert len(installed['actual_files']) == 15 and installed['changed_files'] == 6 and installed['preserved_user_files'] == 2
    counts = dict(collections.Counter(r['status'] for r in tests['tests']))
    assert counts == {'PASS': 44, 'NOT_APPLICABLE': 1}
    summary = dict(game_id='COBALT_MINER', steam_build='24347666', version='1.0.0', candidate='ko_candidate_03',
                   result='INSTALLED_WITH_USER_REQUESTED_REVIEW_LIMITS', installed_directory='D:/steam/steamapps/common/Cobalt Miner',
                   zip_name=Path(package['archive']).name, zip_sha256=package['zip_sha256'], zip_size=Path(package['archive']).stat().st_size,
                   package_file_count=len(package['allowed_files']), modified_game_files=6, verified_installed_files=15,
                   originals_backed_up=6, preserved_user_files=2, known_translation_omissions=0,
                   general_translation_positions=517, native_translation_fields=192, changed_images=12,
                   unknown_native_strings=1237, installer_checks=counts,
                   gates=dict(G0='PASS', G1='PASS', G2='FAIL', G3='PASS', G4='PASS', G5='FAIL', G6='PASS', G7='PASS', G8='NOT_RUN'),
                   gate_scope='G3/G4는 확인된 번역 대상과 고정 후보 범위. G2/G5 미완료를 생략한 개인용이며 공통 완성판 G8은 미통과.',
                   game_launch_after_install='NOT_RUN', public_upload='NOT_RUN',
                   limitations=['전체 시설·도움말·예비 화면·분기·회차 미검증', '엔진 문자열1237개 실제 표시 여부 미확정',
                                '빠른 A엔딩 전환 종료 오류는 원본과 후보 모두 재현. B검수 종료 오류 원인 미확정'])
    output = ROOT / 'validation/COBALT_MINER/ko_1.0.0'
    assert not output.exists()
    write_json(output / 'RELEASE_SUMMARY.json', summary)
    report = f'''# Cobalt Miner 개인용 한국어 패치 1.0.0 결과

2026-11-02 Steam 빌드24347666의 패치를 요청한 `D:\\steam\\steamapps\\common\\Cobalt Miner`에 적용했습니다. 설치된15파일이 고정 후보와 일치하고, 변경한6파일의 원본 백업과 기존 사용자 저장·설정2파일 및 Steam 명세 보존을 확인했습니다. 게임은 추가 실행하지 않았습니다.

[패치 ZIP](../../../release_output/{summary['zip_name']}) · [설치·제거 안내](../../../tasks/COBALT_MINER/README.md) · [요약 기록](RELEASE_SUMMARY.json)

## 적용 내용

- 메뉴·대사·설명397종517위치와 실행 모듈192필드를 번역했습니다. 확인된 대상의 빈 번역·원문 잔존·위치 불일치0건입니다.
- 광고판11장과 발전소 간판1장을 교체하고 필요한616문자 지원과 기존 문자 보존을 검사했습니다.
- 영어 언어 슬롯이 한국어로 바뀝니다. 게임 제목·제작사/제작진 이름·로고·모델 코드·수치와 다른 언어 슬롯 일부는 원래 표기를 유지합니다.
- 전체1550이미지의 변경 경계,895객체·17장면의 구조와 저장 키 보존을 검사했습니다. 원본 게임 수치·진행 규칙·저장 형식은 바꾸지 않았습니다.

## 실제 확인 범위

주요 대사107개·설명20개·주변 대사30개와 기재한 메뉴·설정·도입·엔딩·강화·표지를 판독했습니다. 현재 후보의 저장·A엔딩·이어하기 후 충분히 대기하고 종료한 경로는 오류0건이었습니다. 검수마다 확인한 설치본·사용자17파일이 보존됐으며 실제 패치 적용 후에는 의도한 게임6파일 변경과 사용자2파일 무변경을 구분해 확인했습니다.

사용자의 최신 요청 “특별히 번역이 안된 부분이 없다면 검수는 여기까지하고 마무리하시죠.”에 따라 추가 조사·화면 검수를 종료한 개인용입니다. 엔진 문자열1237개는 내부용인지 실제 표시용인지 확정하지 못했고, 전체 시설·도움말·예비 화면·전체 분기·전체 회차와 최종 후보의 새 프로세스 불러오기는 미완료입니다. 확인된 번역 누락0건을 모든 영문 문구가 없다는 주장으로 확대하지 않습니다.

빠른 A엔딩→이어하기→종료에서는 원본과 후보 모두 같은 접근 오류가 재현됐습니다. 충분히 대기한 후보 경로의 무오류만으로 전체 발생 조건이 해결됐다고 판단하지 않습니다. 이전 B엔딩 검수 종료의 그래픽 모듈 오류는 원인 미확정입니다. 예전 메뉴·설정 기록 중 종료 로그가 없는 실행과 오류가 확인된 B엔딩 PASS는 전체 G5 근거에서 제외했습니다.

| 단계 | 결과 | 범위 |
|---|---|---|
| G0·G1 | PASS | 원본·도구 고정, 소규모 재저장·한글·격리 저장/불러오기 위험 시험 |
| G2 | FAIL | 엔진 문구1237개 표시 여부 미확정 |
| G3·G4 | PASS | 확인된 번역·글꼴·이미지와 현재 후보의 정적 재검사 |
| G5 | FAIL | 대표 화면만 확인. 잔여 분기·종료 오류 조사는 사용자 요청으로 종료 |
| G6 | PASS | 수정6파일 정·역 복원과 ZIP23파일 허용 목록 |
| G7 | PASS | 최종 ZIP 설치·복구 및 실제 설치 지문·저장 보존 |
| G8 | NOT_RUN | 공통 완성판 조건 미충족. 개인용 적용·인수인계만 완료 |

## 설치·복구 검증

최종 ZIP에서 꺼낸 설치기로 정상 설치·중복 설치·제거·재설치, 백업 없이 역방향 복원, 부분 설치 재개·제거, 미지원 이전 후보·변조·누락·손상 파일 거부, 파일 잠금·두 번째 교체 실패·기록 쓰기 실패 되돌림, 강제 중단 뒤 복구, 실행 중 게임 거부, 한글·공백·추가 Steam 라이브러리 경로를 시험했습니다.

43개 시험 기록과 부분 설치 종합 판정1개가 PASS입니다. 이전 공개 패치 갱신1개는 최초 버전이므로 해당 없음입니다. 실행 중 거부 시험의 모형 EXE 기대값 오류를 수정한 뒤 같은 ZIP·원본·후보에서 기존41통과를 재사용하고 남은2시험을 수행했습니다. 실패 원문과 교정 도구 지문을 보존했습니다. 실제 게임을 시험용 모형 대신 실행한 것은 아닙니다.

ZIP에는 설치·제거기,차이 파일12개,도구·문서·라이선스만 포함합니다. 원본 게임 파일·검수 코드·저장 원문은 없습니다. 외부 공개 업로드는 하지 않았습니다.

## 제거와 원본 백업

ZIP을 완전히 풀어 `Remove.cmd`를 실행하고 같은 게임 폴더를 선택하면 원본으로 복원됩니다. 중단된 설치는 같은 ZIP의 설치·제거기를 다시 실행해 복구합니다. 게임 업데이트 또는 지원하지 않는 파일에는 강제 적용하지 않습니다.

설치기가 안내한 백업 위치는 `%LOCALAPPDATA%\\CobaltMinerKoreanPatch\\working_private\\560DFF75287DFEF1\\build_24347666`입니다. 이번 실행에서 실제 내용까지 확인한 경로는 아래와 같습니다.

`{installed['backup_directory']}`

## 파일 지문

- ZIP 크기: {summary['zip_size']:,}바이트
- ZIP SHA-256: `{summary['zip_sha256']}`
- 최종 DAT SHA-256: `{installed['actual_files']['COBALT MINER.dat']}`
- 최종 EXE SHA-256: `{installed['actual_files']['COBALT MINER.exe']}`

공유 요약에는 원본 자산·저장 내용을 넣지 않았습니다. 재현용 번역·도구는 `tasks/COBALT_MINER`, 비공개 원본·후보·실행 및 설치 증거는 각각의 전용 영역에 보존했습니다.
'''
    (output / 'RESULT_REPORT.md').write_text(report, encoding='utf-8')
    dependencies = [pack_path, tests_path, install_path, gate_path, Path(__file__), Path(__file__).with_name('verify_installation.py'),
                    Path(__file__).with_name('test_installer_resume_stub.py'), output / 'RESULT_REPORT.md', output / 'RELEASE_SUMMARY.json']
    write_json(WORK / 'release_freeze_1.0.0_r1/final_handoff.json', dict(status='PASS', scope='개인용 설치와 인수인계. 전체 G0~G8 PASS 아님.',
               zip_sha256=summary['zip_sha256'], dependencies=[ref(p) for p in dependencies]))
    print(json.dumps(dict(status='PASS', report=str(output / 'RESULT_REPORT.md'), zip_sha256=summary['zip_sha256']), ensure_ascii=False))


if __name__ == '__main__':
    main()
