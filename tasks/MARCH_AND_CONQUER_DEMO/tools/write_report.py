"""비공개 원시 증거를 제외하고 공유 가능한 결과 요약을 작성합니다."""
from baseline import *
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
ready=read(WORK/'release_ready.json');installed=read(WORK/'actual_install.json');runtime=read(WORK/'qa_v006/runtime_validation.json')
assert read(WORK/'user_baseline_actual.json')==read(WORK/'user_after_install.json')
assert ready['zip_sha256']==installed['zip_sha256']
release=ROOT/'release_output'/f'{GAME}_KOREAN_PATCH_1.0.0.zip';assert sha(release.read_bytes())==ready['zip_sha256']
out=ROOT/'validation'/GAME/'ko_1.0.0';out.mkdir(parents=True,exist_ok=True)
summary=dict(game=GAME,version='1.0.0',steam_build='25323013',candidate='ko_v005',status='PASS',installed_files=191,original_backups=4,source_strings=33365,code_strings=367,media_objects=739,translation_positions=1099,translated_positions=1022,retained_positions=77,translated_code_positions=85,required_characters=385,unknown=0,unresolved_extraction_errors=0,installer_cases=24,checker_cases=13,runtime_frames=217,runtime_nodes=153,runtime_units=48,runtime_main_screens=16,runtime_exact_value_matches=805,runtime_unobserved_exact_positions=294,whole_random_campaign='NOT_RUN',missing_glyph_warnings=0,patch_loading_errors=0,user_save_preserved=True,zip_sha256=ready['zip_sha256'],candidate_manifest_sha256=ready['candidate_manifest_sha256'])
save(out/'verification_summary.json',summary)
report=f'''# March and Conquer Demo 한국어 패치 1.0.0 결과

작성일: 2026-09-16 · Steam 앱 5203110 · 빌드 25323013 · 게임 v1.1

## 결과

사용자가 지정한 Steam 게임 폴더에 적용을 완료했습니다. 설치된 191개 파일이 최종 후보 `ko_v005`와 일치하고, 변경 전 파일 4개를 해시가 일치하는 백업으로 보관했습니다. 검수 및 설치 전후 사용자 파일 1개·설정 26개가 동일합니다. 해당 파일은 로그이며 기존 플레이 저장 파일은 없었습니다.

- [패치 ZIP](../../../release_output/{GAME}_KOREAN_PATCH_1.0.0.zip)
- [설치 파일](../../../release_output/{GAME}_KOREAN_PATCH_1.0.0/Install.cmd) · [제거 파일](../../../release_output/{GAME}_KOREAN_PATCH_1.0.0/Remove.cmd)
- [기계 판독용 검증 요약](verification_summary.json)

게임은 평소처럼 Steam에서 실행하면 됩니다. 기존 English 항목을 한국어로 바꿨으며 기본 선택 상태도 한국어입니다. 독일어를 선택해 둔 경우 설정 → 언어에서 한국어를 고르면 됩니다.

## 번역과 보존 범위

- 언어표 391행(중복 키 1개 포함), 장면·프리팹·유닛·기술 설명을 포함한 1,099개 표시 위치를 원문과 대조했습니다. 실제 번역 1,022개 위치와 숫자·기호 등 유지 77개 위치로 구분합니다.
- 코드 문자열 85곳과 전투·생산 상태의 표시 변환 2곳을 적용했습니다. enum(저장 등에 사용하는 내부 식별 값)은 바꾸지 않았습니다.
- Noto Sans KR 400과 기존 라틴 글꼴을 연결했습니다. 필요한 문자 385자, TMP 글꼴 자산 3개, 글꼴 사용 참조 110곳을 검사했습니다. 한국어 단어 단위 줄바꿈과 능력치 숫자 표시 8곳의 한 줄 출력을 적용했습니다.
- 게임 규칙·수치·저장 형식은 유지합니다. 제목·Unity 로고, 버전·숫자·기호, 음원 이름과 기존 독일어 슬롯은 유지했습니다. 별도 한국어 이미지 교체는 없습니다.
- 문자열 33,365개, 게임 코드 문자열 367곳, 미디어 객체 739개를 분류했습니다. 이미지 170개 중 실제 픽셀 164개와 빈 글꼴 텍스처 6개를 구분했고, 스프라이트 569개를 검토한 텍스처에 연결했습니다. 미디어 유지 68개·문구 없음 671개이며 미분류는 0개입니다.

## 검증

| 단계 | 상태 | 확인한 내용 |
|---|---|---|
| G0 기준선 | PASS | Unity 6000.3.9f1·Mono, 원본 191파일·217,696,576바이트, SHA-256 고정 |
| G1 기술 시험 | PASS | 원본 메타데이터를 보존한 재저장·재해석, 분리 사본의 소규모 한글 출력 |
| G2 출처 조사 | PASS | 전체 문자열·코드·미디어 분류, 최초 추출 오류 8건의 해시별 대체 조사 완료 |
| G3 번역·글꼴 | PASS | 번역 위치·필요 문자·동적 글꼴·대체 글꼴·다중 문자 이미지 연결 검사 |
| G4 후보 검사 | PASS | 1,099위치 재추출, 446변경 객체 경계, 원본 메서드 1,277개와 비교 |
| G5 화면 검수 | PASS | 아래에 기재한 화면군·글꼴·저장 격리 검수 범위 |
| G6 차이 파일 | PASS | 4파일의 정방향·역방향 복원 8건, 허용 파일 17개만 포함 |
| G7 설치·복구 | PASS | 최종 ZIP에서 꺼낸 설치기로 22개 설치 시험 및 경로 탐색 2개 |
| G8 적용·전달 | PASS | 실제 설치본 191파일·원본 백업 4개·저장 보존·전달 ZIP 해시 확인 |

검사기에도 정상 입력과 빈 번역·위치 교환·객체 삭제·원문 잔존·깨진 태그·아이콘 속성·줄바꿈·미분류·추출 실패·글꼴 누락·만료된 근거 등 13개 사례를 넣어 통과와 차단을 확인했습니다. 공통 개선 목록 전체를 구현 완료로 표시하지는 않습니다.

설치 시험은 정상·중복 설치, 상태 확인, 제거·중복 제거, 부분 설치/제거, 백업 없이 역방향 복원, 변조 자산/다른 빌드/누락 파일/미지원 이전 후보/손상 차이 파일/손상 도구/잘못된 경로 차단, 설치·제거 중 파일 잠금과 복구, 실제 설치 프로세스 강제 중단 후 재개, 실행 중 대상 차단, 한글·공백 경로, 추가·실제 Steam 라이브러리 탐색을 포함합니다. 첫 공개판이므로 이전 공개판 갱신은 해당 없음입니다.

## 실제 화면 검수 범위

RTX 4060 Ti에서 1280×720 그래픽 모드로 최종 후보 사본을 실행했습니다. 실제 실행 경로·프로세스·후보 해시·화면·로그를 연결했습니다. 배치 모드나 편집기 미리보기가 아닙니다.

- 주요 화면 16개: 첫 메뉴, 설정, 독일어 전환, 한국어 복귀, 화면 설정 확인·시간 경과 복구, 새 게임 안내, HUD, 일시정지 설정, 승리 보상, 지역 정복, 데모 완료, 패배 통계, 저장 후 메뉴, 새 게임 확인, 불러오기.
- 데이터베이스에 들어 있는 기술/건물 설명 153/153개, 유닛명·체력 표시 48/48개를 순회했습니다. 합계 217개 프레임의 화면과 표시 문자열 기록을 확보했습니다.
- 수정 용 체력 `2000`의 줄 나뉨을 발견하여 같은 능력치 표시군 8곳을 수정하고 최종 후보에서 한 줄 출력을 확인했습니다.
- 글리프(글자 모양) 누락 경고 0개, 패치 고유 로딩 오류 0개, 격리 저장·불러오기 및 정상 종료를 확인했습니다.

표시 문자열 기록과 번역 값을 대조한 일치 위치는 805/1,099개입니다. 같은 문구가 여러 위치에 있는 경우 각 위치가 따로 집계되므로, 이는 모든 개별 객체가 직접 관찰됐다는 뜻은 아닙니다. 정확한 값이 기록되지 않은 294개 위치도 정적 재추출 비교는 통과했으며 별도 목록으로 보관합니다. 조합 문구와 예비 표기를 포함해 모든 값을 화면에서 보았다고 주장하지 않습니다.

기술·유닛 순회와 승리·지역·데모 완료·큰 통계값은 검수 전용 조건으로 진입했습니다. 이전 사본의 정상 새 게임에서는 훈련·전투·승리·패배 흐름도 확인했습니다. **60전 전체 정상 완주와 모든 무작위 회차는 NOT_RUN**입니다. 별도 대화·음성 대사·접근성 메뉴는 해당 게임 코드·장면에서 확인되지 않았고 시작 안내가 도움말을 담당합니다.

## 격리·오류 이력

최종 검수 사본은 별도 회사/제품명으로 저장과 설정을 분리하고 로그도 작업 영역에 기록했습니다. 게임 파일에서는 회사/제품명 두 값, `app.info`, `GameTextManager.Awake`의 검수 진입 호출 1개와 별도 검수 모듈만 달라짐을 확인했습니다. 실행 중 일시정지·화면 순회·시험 통계값과 유닛 팝업의 위치 조정은 검수 사본에만 적용했습니다. 배포본에 검수 모듈은 없습니다.

초기 창 실행 도구가 원본 설치본을 대신 실행한 시행착오가 있었습니다. 이 실행은 후보 검수에서 제외했고 이후 종료를 확인했습니다. 그때 원본 로그와 기본 설정이 생성됐으므로 작업 시작 전의 빈 상태와 동일하다고 쓰지 않습니다. 이후 실제 사용자 계정에서 기준을 다시 확보했고, 분리 검수 및 최종 설치 전후 해당 파일·설정이 동일함을 확인했습니다. 초기의 잘못된 길이 설정과 검수 도구 오류도 최종 후보 검수에서 제외했습니다.

## 설치·제거·복구

현재 지정 폴더에는 설치되어 있습니다. 재설치가 필요하면 ZIP을 모두 풀고 `Install.cmd`, 제거하려면 `Remove.cmd`를 실행해 같은 게임 폴더를 선택하세요. 게임 실행 중에는 먼저 게임을 종료해야 합니다.

원본 백업과 복구 기록은 `%LOCALAPPDATA%\\MarchConquerKoreanPatch\\working_private`에 있습니다. 설치 도중 실패하면 직전 상태로 복원하며, 강제로 중단됐다면 같은 설치기를 다시 실행하면 기록을 읽어 복구합니다. 게임 업데이트나 다른 파일 해시는 차단합니다.

ZIP SHA-256:

`{ready['zip_sha256']}`

외부 업로드나 공개 게시, Git 커밋은 수행하지 않았습니다.

## 재현 자료

게임별 도구는 `tasks/MARCH_AND_CONQUER_DEMO/tools`에 있습니다. 원본 사본·추출 자료·번역 원본·검수 게임·화면·저장 원시 증거는 비공개 영역에 보관합니다. 제작 순서는 `baseline.py` → `inventory.py`/`resolve_inventory.py` → `prepare_translation.py`/`prepare_code.py`/`audit_sources.py` → `build_candidate.py`/`verify_candidate.py` → 격리 그래픽 검수 → `package_release.py`/설치 시험 → `finalize_evidence.py` → `install_target.py`입니다. 생성 도구는 고유 출력 경로를 요구하므로 기존 확정 후보나 패키지를 덮어쓰지 않고 새 이름으로 실행해야 합니다.
'''
(out/'RESULT_REPORT.md').write_text(report,encoding='utf-8')
task=ROOT/'tasks'/GAME
(task/'README.md').write_text('''# March and Conquer Demo 한글패치

한국어 패치 1.0.0을 Steam 빌드 25323013용으로 제작하여 지정 설치본에 적용했습니다.

- 메뉴·유닛·기술 설명·상태·결과를 한국어로 표시합니다.
- 정적 비교 1,099개 표시 위치, 실제 그래픽 주요 화면 16개·기술 153개·유닛 48개를 검수했습니다.
- 최종 ZIP의 설치·복구·경로 시험 24건과 설치본 191파일·원본 백업 4개를 확인했습니다.
- 전체 60전 정상 완주와 무작위 회차는 미실행입니다. 로고·음원 이름·기존 독일어 표기는 유지합니다.

[패치 ZIP](../../release_output/MARCH_AND_CONQUER_DEMO_KOREAN_PATCH_1.0.0.zip) · [상세 결과와 제거 방법](../../validation/MARCH_AND_CONQUER_DEMO/ko_1.0.0/RESULT_REPORT.md) · [작업 명세](TASK_SPEC.md)
''',encoding='utf-8')
spec=task/'TASK_SPEC.md';s=spec.read_text(encoding='utf-8');start=s.index('| G0 |');end=s.index('\n\n공통 기준',start)
s=s[:start]+'''| G0 | PASS | 원본 191파일·빌드·환경·해시 고정 |
| G1 | PASS | 원본 메타데이터 보존 재저장, 소규모 실제 한글 출력 |
| G2 | PASS | 문자열 33,365개·코드 367곳·미디어 739개, 미분류·미해결 오류 0 |
| G3 | PASS | 번역 1,022위치·유지 77위치·코드 85곳, 필요 문자 385자 |
| G4 | PASS | ko_v005 독립 재추출·허용 변경 대조, 검사기 13사례 |
| G5 | PASS | 기재 화면군 217프레임·격리 저장·종료. 전체 60전 정상 완주는 NOT_RUN |
| G6 | PASS | 확정 후보 4파일의 양방향 복원 8건·허용 목록 17파일 |
| G7 | PASS | 최종 ZIP 설치·복구·경로 시험 24건 |
| G8 | PASS | 지정 설치본 적용·191파일·백업 4개·저장 보존·최종 보고 |
'''+s[end:];s+='\n\n2026-09-16 완료 근거: [결과 보고서](../../validation/MARCH_AND_CONQUER_DEMO/ko_1.0.0/RESULT_REPORT.md). 그래픽 관찰 범위와 미실행 항목은 보고서의 분모·한계를 따른다.\n';spec.write_text(s,encoding='utf-8')
config=task/'GAME_CONFIG.yaml';s=config.read_text(encoding='utf-8').replace('working_private/MARCH_AND_CONQUER_DEMO/media_review.json','working_private/MARCH_AND_CONQUER_DEMO/media_ledger.json').replace('isolation_preflight_status: NOT_RUN','isolation_preflight_status: PASS').replace('current_gate: G0','current_gate: G8').replace('validation/MARCH_AND_CONQUER_DEMO/RESULT_REPORT.md','validation/MARCH_AND_CONQUER_DEMO/ko_1.0.0/RESULT_REPORT.md');config.write_text(s,encoding='utf-8')
status=ROOT/'PROJECT_STATUS.md';s=status.read_text(encoding='utf-8');lines=s.splitlines();lines[2]='갱신일: 2026-09-16 · 현재 작업: March and Conquer Demo 한국어 패치 1.0.0 적용 완료';s='\n'.join(lines)+'\n';pos=s.index('\n\n',s.index('갱신일:'))
s=s[:pos]+'''\n\n**March and Conquer Demo 한국어 패치 1.0.0을 Steam 빌드 25323013의 지정 폴더에 적용했습니다.** 1,099개 표시 위치(번역 1,022·유지 77)와 코드 문구 85곳·한글 글꼴을 검증했습니다. 실제 GPU 주요 화면 16개·기술 153개·유닛 48개, 최종 ZIP 설치·복구·경로 시험 24건, 설치본 191파일·백업 4개·사용자 저장·설정 보존을 확인했습니다. 전체 60전 정상 완주와 무작위 회차는 NOT_RUN입니다. [패치 ZIP](release_output/MARCH_AND_CONQUER_DEMO_KOREAN_PATCH_1.0.0.zip), [결과 보고서](validation/MARCH_AND_CONQUER_DEMO/ko_1.0.0/RESULT_REPORT.md).'''+s[pos:];status.write_text(s,encoding='utf-8')
with (ROOT/'WORK_LOG.md').open('a',encoding='utf-8') as f:f.write('''\n\n## 2026-09-16 — March and Conquer Demo 한국어 패치 1.0.0

Steam 빌드 25323013의 한글패치를 제작하고 사용자가 지정한 폴더에 적용했다. Unity Mono 자산의 원본 메타데이터 보존 재저장, 생성 구조의 정렬·문자 배열·관리 참조 해석을 보완했다. 1,099개 표시 위치와 코드 85곳·상태 표시 2곳을 대조했으며, 실제 그래픽 검수에서 발견한 체력 숫자 줄바꿈을 관련 8개 필드에서 수정했다. 최종 ko_v005의 217프레임 검수·저장 격리·정상 종료, 최종 ZIP의 설치·복구 22건과 경로 2건, 검사기 오류 입력 13건을 확인했다. 실제 설치본 191파일과 원본 백업 4개, 사용자 저장·설정 보존 및 전달 ZIP 해시를 확인했다. 전체 무작위 플레이 완주와 실제 화면의 모든 번역 위치 관찰은 구분하여 보고했다. 초기 원본 오실행과 검수 도구 오류는 후보 통과 근거에서 제외하고 보고서에 기록했다. 상세: validation/MARCH_AND_CONQUER_DEMO/ko_1.0.0/RESULT_REPORT.md.
''')
print('REPORTS COMPLETE')
