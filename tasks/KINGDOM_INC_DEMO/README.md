# Kingdom Inc. Demo

Steam 빌드 25631786용 한국어 패치 1.0.0을 `D:\steam\steamapps\common\Kingdom Inc. Demo`에 적용했습니다. 평소처럼 Steam에서 실행하면 한국어로 표시됩니다.

- [작업 명세](TASK_SPEC.md)
- [패치 ZIP — 최종 r2](../../release_output/KINGDOM_INC_DEMO_KOREAN_PATCH_1.0.0_r2.zip)
- [결과·검사 범위](../../validation/KINGDOM_INC_DEMO/ko_1.0.0/RESULT_REPORT.md)
- [실제 화면 검수](../../validation/KINGDOM_INC_DEMO/ko_1.0.0/RUNTIME_QA.md)
- [설치·복구 검사](../../validation/KINGDOM_INC_DEMO/ko_1.0.0/INSTALLER_QA.md)

## 다시 설치하거나 제거하기

1. 게임을 종료하고 최종 r2 ZIP 전체를 풉니다.
2. 설치는 `Install.cmd`, 제거는 `Remove.cmd`를 실행합니다.
3. `KingdomInc.exe`가 있는 게임 폴더를 선택합니다.

설치 중 중단됐으면 같은 설치기를 다시 실행합니다. 원본 백업과 복구 기록은 `%LOCALAPPDATA%\KingdomIncKoreanPatch\working_private`에 있습니다. 지원하지 않는 게임 업데이트에는 적용하지 않습니다.

## 확인한 범위

번역표 1,556행·누락 표시 키 6개·직접 문구 154곳·코드 문구 4곳, 한글 글꼴과 두 크기의 글상자 아이콘을 처리했습니다. 대표 화면·저장/불러오기·정상 종료와 설치/복구 43개 시험을 확인했습니다. 실제 설치본 191파일이 최종 후보와 일치하며 원본 백업 8개와 사용자 저장·설정 무변경을 확인했습니다.

생성 인명·로고·제작사명·물리 키 이름 등은 원형을 유지합니다. 전체 회차·모든 무작위 분기와 전 문구의 실제 표시 관찰은 미수행입니다. 검수는 화면 절반 이하 무음 창과 격리된 저장을 사용했으며, 사용자 설치본을 추가로 실행하지 않았습니다.

## 제작 자료

원본 사본은 `source_original/KINGDOM_INC_DEMO/steam_25631786/game`, 조사 자료는 `extracted_private/KINGDOM_INC_DEMO`, 번역 원본·원시 증거는 `working_private/KINGDOM_INC_DEMO`, 최종 후보는 `build_candidate/KINGDOM_INC_DEMO/1.0.0_rc5/game`에 보존합니다. 도구는 이 게임의 `tools` 아래에 있습니다. 원본·후보·검수 사본은 Git과 일반 배포에서 제외됩니다.

재제작은 고정 원본·번역·그림·글꼴 입력을 확인한 뒤 `build_candidate.py`로 새 이름의 후보를 만들고, `validate_candidate.py`로 재추출 대조합니다. `QA_USAGE.md`에 따라 별도 사본의 실제 화면을 검수한 뒤 `package_release.py`, `test_installer.py`, `package_final_audit.py` 순서로 최종 ZIP을 검사합니다. 입력이 달라지면 관련 과거 결과를 그대로 재사용하지 않습니다.

ZIP SHA-256: `a290b3952218061a67f49b80504638ec04fc6a7e99cdeb38035d75f76968f092`
