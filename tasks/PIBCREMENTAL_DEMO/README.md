# Pibcremental Demo 한국어 패치

당시 상태: 1.0.0 제작·검증·실제 설치 완료 기록 (2026-09-02)

현재 공통 기준은 [핵심 지침서](../../docs/KOREAN_PATCH_PLAYBOOK.md), 통합 상태는 [PROJECT_STATUS](../../PROJECT_STATUS.md)입니다. 아래 수치는 당시 보고서 기록입니다. [2026-09-05 평가](../../docs/PROJECT_REVIEW_2026-09-05.md)에서 확인한 분류·위치 비교·증거 연결·설치 복구 문제의 코드 수정과 새 기준 통합 재검증은 아직 완료하지 않았습니다.

## 대상과 번역 방향

- Steam 앱 4780080, 빌드 25008003, 게임 표시 버전 27.08.01
- Unity 6000.4.0f1, Mono, Addressables 2.9.1
- 실제 설치 경로: `D:\steam\steamapps\common\Pibcremental Demo`
- 인간이 사라진 뒤 피블들이 커다란 나무에서 문명을 키우는 점진 성장 게임이다. 공식 소개의 아기자기하고 장난스러운 분위기에 맞춰 짧고 친근한 문장을 사용했다.
- 공식 소개: https://store.steampowered.com/app/4780080/Pibcremental_Demo/

용어는 피블, 파파 피블, 메가피블, 수액, 고철, 실크, 풍선, 열매, 탐험, 환생, 유물, 주스로 통일했다. 플레이 규칙·자원 수치·조건은 정식 후보에서 변경하지 않았다.

## 필수 게이트와 최종 결과

작업 계획과 검증에는 `docs/KOREAN_PATCH_RUNTIME_QA_REFERENCE.md`의 글꼴·그래픽 실행·저장 경로 분리 절차를 적용했다.

1. 원본 212개 파일의 크기·SHA-256을 기록하고 게임 폴더 밖에서 작업했다.
2. Localization, TMP/Text 직접 문구, 직렬화 표시 필드, 코드 문자열·참조, enum 사용, 이미지·영상 계층을 조사했다.
3. 설정값·도전 과제·툴팁의 직접 저장 문구가 일반 Localization 테이블 밖에 있음을 확인하고 추가 번역했다. 표시 가능한 필드의 미번역 값은 자동으로 `UNKNOWN` 처리하도록 감사 규칙도 보완했다.
4. 42,105개 감사 기록에서 번역 대상 위치 4,455건, 미분류 0건으로 정리했다.
5. 영어·독일어 테이블 각각 2,093개 값을 한국어로 채웠다. 고유 Localization 원문은 1,183종이다.
6. 직접 표시 181종/557위치, 코드 36종/39위치, 추가 직렬화 문구를 반영했다. 대상 원문 잔존과 태그·토큰·자리표시자·줄바꿈 차이는 0건이다.
7. TMP 글꼴 자산 12개는 보존하고 Noto Sans KR 동적 폴백을 초기화한다. 전체 말뭉치에 필요한 648자의 글리프 누락은 0건이다. 다중 아틀라스를 사용한다.
8. 실제 그래픽 장치에서 첫 화면·설정·인트로·HUD·대화·건물·종료 메뉴·데모 감사 표시를 확인했다. 최종 추가 번역은 설정값과 최종 HUD에서 재확인했다.
9. 후보와 검수 복사본의 차이는 검수 제품명 및 완료 조건·Steam 전송 제어뿐이며, 해당 검수 변경은 배포본에 들어 있지 않다.
10. 설치/복원 차이 패치 14회 왕복 해시 검증과 설치기 12종 시험을 통과했다.
11. 실제 설치본 212개 파일의 최종 크기·SHA-256이 후보와 전부 일치했다.

## 실행 검증의 범위와 주의점

- 모든 회차·분기를 끝까지 플레이한 검증은 아니다. 데모 끝 화면은 검수용 저장 레벨과 완료 조건을 조정해 접근했다.
- 최종 화면 검수에서는 Steam 초기화를 끄고 통계 전송을 차단했다.
- 기존 진행·설정·자동 저장 메타데이터는 바뀌지 않았다. 초기 검수 실행에서 기본 `Player.log`가 갱신되고 `Player-prev.log`가 생겼다. 이후에는 로그도 작업 폴더로 분리했다.
- 한글 글리프 누락, 폰트 아틀라스 오류, 예외, 현지화 카탈로그 로딩 오류는 0건이었다. 일부 비치명적인 엔진·장면 설정 경고는 보고서에 구분해 기록했다.
- 독일어 테이블도 전수 한국어 변환과 정적 검증을 마쳤지만 실제 설정의 슬롯 전환은 확인하지 못했다.
- 게임명·개발사 로고, 인명·닉네임·곡명·URL, 의도한 약칭은 유지했다. Steam 자체 화면의 문구는 게임 파일 패치 범위 밖이다.

## 산출물

- 배포 폴더: `release_output/PIBCREMENTAL_DEMO_KOREAN_PATCH_1.0.0`
- 배포 ZIP: `release_output/Pibcremental_Demo_Korean_Patch_v1.0.0.zip`
- ZIP SHA-256: `FA83D3D94150AAB3E59C239BED5101423B3BAFCDEF7161D562ECF4320D1FE97A`
- 정적 검증: `validation/PIBCREMENTAL_DEMO/candidate_static_validation.json`
- 전수 분류: `validation/PIBCREMENTAL_DEMO/full_content_classification.csv`
- 실행 검증: `validation/PIBCREMENTAL_DEMO/graphical_qa_report.json`
- 설치기 시험: `validation/PIBCREMENTAL_DEMO/installer_test_report.json`
- 실제 설치본 확인: `validation/PIBCREMENTAL_DEMO/installed_verification.json`
- 대표 화면: `viewer_output/PIBCREMENTAL_DEMO/graphical_qa`

## 빌드 도구

`translations`에 번역 원문과 한국어 대응을 보관한다. 작업용 Python 패키지는 루트의 `tools/python_deps`를 `PYTHONPATH`로 지정해 사용한다.

- `build_korean_assets.py`: 자산과 현지화 테이블 생성
- `AssemblyPatcher`: 코드 문구 번역 및 한글 폴백 초기화 삽입
- `update_addressables_catalog.py`: 변경 묶음의 크기·CRC 정책 갱신
- `validate_candidate.py`, `build_final_audit.py`: 정적·전수 분류 검사
- `prepare_runtime_qa.py`, `FinalScreenQAPatcher`: 배포하지 않는 격리 실행 검수 도구
- `finalize_runtime_report.py`: 로그·화면·저장 영역 검사 기록
- `build_release.py`, `test_installer.ps1`, `finalize_release.py`: 차이 패치·설치기·ZIP 검증
- `verify_installed.py`: 실제 설치 폴더 전체 해시 대조

원본·추출·작업·후보 게임 파일과 검수용 DLL은 공개 배포하지 않는다. 게임 업데이트나 알 수 없는 해시는 설치기에서 거부한다. 최초 공개판이므로 이전 공개 패치 갱신 시험은 해당하지 않는다.
