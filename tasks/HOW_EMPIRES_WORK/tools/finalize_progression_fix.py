"""실제 적용 결과를 확인한 뒤 공개 가능한 수정 요약만 기록합니다."""
from common import *
stage=WORK/'progression_fix'
application=read_json(stage/'application.json');assert application['status']=='PASS'
tests=read_json(WORK/'package_1.0.1_r2/installer_tests.json');assert tests['status']=='PASS'
static=read_json(WORK/'final_audit_1.0.1/static_summary.json');assert static['status']=='PASS'
runtime=read_json(stage/'runtime_summary.json');assert runtime['status']=='PASS'
candidate=read_json(WORK/'full_06/build.json')['sha256']
assert application['candidate_sha256']==static['candidate_sha256']==runtime['candidate_sha256']==candidate
count=sum(r['status']=='PASS' for r in tests['tests'])
out=ROOT/'validation/HOW_EMPIRES_WORK/ko_1.0.1';out.mkdir(parents=True,exist_ok=True)
summary={'game':'HOW_EMPIRES_WORK','build':'26482667','patch_version':'1.0.1_r2','candidate':'full_06','candidate_sha256':candidate,'zip_sha256':application['zip_sha256'],'gates':{f'G{i}':'PASS' for i in range(9)},'fixed_progression_identifiers':11,'fixed_format_keys':2,'reclassified_unchanged_format_keys':2,'locale_rows':2553,'direct_locations':2732,'unknown':0,'unresolved_extraction_errors':0,'unresolved_format_errors':0,'missing_glyph_warnings':0,'new_error_classes':0,'installer_tests_pass':count,'installer_tests_not_applicable':sum(r['status']=='NOT_APPLICABLE' for r in tests['tests']),'repaired_saves':4,'latest_money_preserved':71,'other_user_files_unchanged':True,'actual_installation':'PASS','post_install_steam_launch':'NOT_RUN','full_playthrough':'NOT_RUN','publication':'NOT_REQUESTED','prior_patch_1.0.0_status':'FAIL — 내부 식별자 오역으로 정상 진행 불가'}
write_json(out/'summary.json',summary)
report=f'''# How Empires Work 1.0.1 진행 오류 수정·적용 결과

2026-11-10, Steam 빌드 26482667. 사용자가 지정한 `D:\\steam\\steamapps\\common\\How Empires Work`에 수정본을 적용했고, 영향을 받은 저장 4개를 복구했습니다. 최신 저장의 **71원**, 플레이 시간, 세금 징수 횟수와 기존 진행 기록은 유지했습니다. 새로 시작할 필요가 없습니다.

## 원인과 수정

1.0.0에서 진행 이벤트를 구분하는 `ThresholdPoint.message` 11곳을 표시 문구로 잘못 분류해 번역했습니다. 조건 통과 횟수는 올라갔지만 실제 기능 해제 처리가 실행되지 않았습니다. 제작자의 패치 결함입니다. 종전 G2~G5 정상 판정을 FAIL로 정정했습니다. 당시 화면 검수의 기능 강제 해제가 이 문제를 가렸으며, 이를 자연 진행 검증으로 간주하지 않습니다.

진행 리소스 4개를 원본 내용으로 복구했습니다. 같은 유형을 다시 조사하면서 무역 확인 창의 `cost`, `commodity` 서식 키 오역 2곳도 복구했습니다. 값은 원래와 같았던 `resource`, `amount` 키 2곳도 내부 항목으로 재분류했습니다. 번역된 코드 103개의 사전·분기 키 256개와 표시 필드 16종의 소비 위치를 대조했습니다. 원래부터 처리 분기가 없던 `lower_road_threshold` 이벤트도 원형을 유지합니다.

## 검증 범위

| 항목 | 결과 |
|---|---|
| 전체 위치·서식·글꼴 | 언어표 2,553행, 직접 문구 2,732위치. 미분류·미해결 추출·서식 오류 0. 원문 닫기 태그 1건 보완은 근거 보존. 글꼴 30개 재검사 통과 |
| 후보 재분석 | 코드 103개 독립 재추출, 원본 18,564개 항목 보존. 이전 후보 대비 변경은 리소스 4개와 코드 1개뿐 |
| 실제 새 게임 | 세금 징수 버튼으로 3원 첫 조건, 5원 전사 소집, 10원 도적 대응. 최초 모집 후 과세 기능 해제 확인. 자원 지급·강제 해제 사용 없음 |
| 기존 저장 복구 | 저장 4개 실제 불러오기, 71원 보존 화면 확인, 모집 후 다음 단계 및 저장·재불러오기 통과 |
| 무역 표시 | 실제 확인 창에서 `1 상인 귀족`, `소에만 적용` 표시 확인. 이 화면 접근에만 별도 검수용 기능 해제 사용 |
| 실행 격리 | 실제 검수 창 경로와 후보 지문 일치. Steam 차단·별도 저장/설정/로그 사용. 실행 전후 실제 사용자 파일 동일 |
| 설치·복구 | 최종 ZIP에서 꺼낸 설치기로 {count}개 PASS. 이전판 제거 후 교체, 중복 설치/제거, 변조 거부, 강제 중단·실패 복구 포함 |
| 실제 적용 | 설치 PCK와 후보 지문 일치. 나머지 게임 3파일과 원본 백업 보존. 저장 4개 외 사용자·클라우드 파일 지문 동일 |

저장 복구는 병력 기능의 활성 상태·해제 목록과 수도의 명령 목록만 변경했습니다. 원본 저장은 작업 폴더와 `%LOCALAPPDATA%\\HowEmpiresWorkKoreanPatch\\working_private\\7A2EF6E46A4A4B0C\\build_26482667\\save_repair_1.0.1`에 보존했습니다. 변경 중 실패 시 이전 저장으로 복원하며, 강제 종료 후에는 같은 복구 도구의 기록으로 복원할 수 있습니다. 일반 ZIP 설치기는 사용자 저장을 변경하지 않습니다.

설치 시험 중 공간 부족은 재생성 가능한 시험 사본 91.75GB를 정리한 뒤 다시 검사했습니다. 이후 기록 파일 교체가 한 번 거부됐을 때 설치기는 시작 전 상태로 되돌렸고, 파일 지문을 확인한 뒤 같은 ZIP으로 해당 제거와 후속 검사를 완료했습니다. 실패 기록을 삭제하거나 PASS로 덮어쓰지 않았습니다.

원본에서도 나타나는 편집기 확장·UID 경로 대체·빈 과제 분류·미니맵·종료 자원 정리 경고는 남습니다. 반복 불러오기로 종료 객체 수가 달라지므로 경고 수가 동일하다고 주장하지 않습니다. 새로운 오류 유형과 글리프 누락은 0건입니다. 전체 회차·모든 분기 완주 및 설치 후 Steam 설치본 추가 실행은 NOT_RUN입니다. 공개 업로드는 하지 않았습니다.

## 파일

- [수정본 ZIP](../../../release_output/HOW_EMPIRES_WORK_KOREAN_PATCH_1.0.1_r2.zip)
- [설치·제거 안내](../../../tasks/HOW_EMPIRES_WORK/README.md)
- [지문·상태 요약](summary.json)

후보 SHA-256: `{candidate}`

ZIP SHA-256: `{application['zip_sha256']}`
'''
(out/'RESULT_REPORT.md').write_text(report,encoding='utf8')
readme='''# How Empires Work 한국어 패치 1.0.1

2026-11-10, Steam 빌드 26482667의 수정본을 `D:\\steam\\steamapps\\common\\How Empires Work`에 적용했습니다. **세금을 모아도 다음 기능이 열리지 않던 1.0.0의 오류를 수정했습니다.** 이 환경의 기존 저장 4개도 원본 백업 후 복구했습니다. 최신 저장의 71원은 유지했으며 새로 시작할 필요가 없습니다.

- [최종 설치 묶음 1.0.1 r2](../../release_output/HOW_EMPIRES_WORK_KOREAN_PATCH_1.0.1_r2.zip)
- [제거기](../../release_output/HOW_EMPIRES_WORK_KOREAN_PATCH_1.0.1_r2/Remove.cmd)
- [검수·복구 결과](../../validation/HOW_EMPIRES_WORK/ko_1.0.1/RESULT_REPORT.md)

정상 새 게임은 세금 누적 5원에 전사 소집, 10원에 도적 대응이 열립니다. 복구한 최신 저장에서는 바로 전사 소집을 사용할 수 있습니다.

다른 위치에 설치할 경우 게임을 종료하고 Install.cmd를 실행합니다. 기존 1.0.0은 이전 묶음의 Remove.cmd로 원본을 복원한 뒤 설치합니다. 일반 설치기는 저장을 자동 복구하지 않으며, 이 사용자의 저장 복구는 별도로 검증·적용했습니다. 게임 업데이트나 다른 수정으로 지문이 달라진 파일에는 강제 적용하지 않습니다.

언어표 2,553행과 직접 문구 2,732위치를 번역 또는 근거를 갖춰 유지했습니다. 제목·로고·이름·원곡 제목·키보드 표기·명령어·원작 오디오는 유지합니다. 전체 회차·모든 분기 완주 검수는 아니며, 설치 후 Steam 설치본을 추가 실행하지 않았습니다. 공개 업로드도 하지 않았습니다. 과거 1.0.0과 1.0.1 r1은 최종본이 아닙니다.
'''
(ROOT/'tasks/HOW_EMPIRES_WORK/README.md').write_text(readme,encoding='utf8')
p=ROOT/'PROJECT_STATUS.md';text=p.read_text(encoding='utf8');tail=text[text.index('## 다음 신규 게임'):]
p.write_text('# 프로젝트 현재 상태\n\n## 2026-11-10 How Empires Work 1.0.1 진행 결함 수정·저장 복구 완료\n\n1.0.0 내부 식별자 오역으로 초기 진행이 막힌 결함을 확인하고 수정본을 실제 설치했습니다. 진행 이벤트 11곳과 무역 서식 키 2곳을 복구했습니다. 새 게임의 정상 세금→모집→과세 진행, 기존 저장 4개 복구 및 저장/불러오기, 최종 ZIP 설치·중단 복구를 검증했습니다. 최신 저장의 71원과 플레이 시간·기존 횟수는 유지했습니다. 전체 완주와 설치 후 Steam 추가 실행은 미검증입니다. 종전 정상 진행 판정은 무효로 정정했습니다.\n\n[결과 보고](validation/HOW_EMPIRES_WORK/ko_1.0.1/RESULT_REPORT.md), [게임 안내](tasks/HOW_EMPIRES_WORK/README.md), [최종 ZIP](release_output/HOW_EMPIRES_WORK_KOREAN_PATCH_1.0.1_r2.zip).\n\nPROC-09 자료 재사용 후보 시험은 현재 5,285행·모의 시험 12개 PASS이며 실제 미래 게임 업데이트 자동 적용은 여전히 미구현/미검증입니다.\n\n'+tail,encoding='utf8')
p=ROOT/'tasks/HOW_EMPIRES_WORK/TASK_SPEC.md';text=p.read_text(encoding='utf8');text=text[text.index('# '):];text=text[:text.index('## 현재 게이트')]+'''## 현재 게이트

1.0.0의 G2~G5는 진행 식별자 오역 때문에 FAIL로 정정했습니다. 수정본 full_06 / 1.0.1_r2는 최종 위치·키·실행·설치·저장 복구 검사를 통과해 적용했습니다. [수정 보고서](../../validation/HOW_EMPIRES_WORK/ko_1.0.1/RESULT_REPORT.md)에 근거와 제한을 기록했습니다.

초기 진행 검수에서는 기능 강제 해제나 자원 지급을 사용하지 않고, 실제 세금 징수 버튼으로 3·5·10원과 최초 모집 후 기능 해제를 확인합니다. 접근용 검수 명령을 사용한 무역 화면 확인은 이 진행 검증과 분리합니다. 전체 회차·모든 분기 완주 및 설치 후 Steam 추가 실행은 NOT_RUN입니다.
''';p.write_text(text,encoding='utf8')
p=ROOT/'tasks/HOW_EMPIRES_WORK/WORK_LOG.md'
with p.open('a',encoding='utf8') as f:f.write(f'\n\n## 2026-11-10 진행 결함 긴급 수정\n\nThresholdPoint.message 11곳과 format 사전 키 2곳을 내부 값으로 복구. 값이 원래와 같던 키 2곳도 재분류. 종전 강제 기능 해제 화면 검수가 자연 진행을 대체하지 못했음을 기록하고 관련 PASS를 무효화했다. full_06 / 1.0.1_r2 최종 검사 및 실제 적용, 저장 4개 최소 변경 복구 완료. 최종 설치 시험 {count}개 PASS. 원본·실패 기록·복구 백업 보존. [최종 결과](../../validation/HOW_EMPIRES_WORK/ko_1.0.1/RESULT_REPORT.md).\n')
print('수정 보고서와 현재 상태 갱신 완료')
