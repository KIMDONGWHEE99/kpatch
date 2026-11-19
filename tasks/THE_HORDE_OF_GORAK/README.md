# The Horde of Gorak 한글패치

## 현재 버전: 1.0.1 / 게임 v1.1.04

2026-11-04 Steam 빌드26365992에 대응하는 업데이트 패치를 지정 D: 게임 폴더에 적용하고 GitHub에 게시했습니다. 신규 문구15종을 포함해 총604종875위치, 기존 네이티브176필드와 이미지4곳을 반영했습니다. 원본32파일 중12파일을 변경하며 이전 패치가 남은 Steam 업데이트 상태도 지원합니다.

[패치1.0.1 ZIP](../../release_output/THE_HORDE_OF_GORAK_KOREAN_PATCH_1.0.1_r1.zip) · [업데이트 결과·확인 범위](../../validation/THE_HORDE_OF_GORAK/ko_1.0.1/RESULT_REPORT.md) · [공개 다운로드·설명](https://github.com/KIMDONGWHEE99/the-horde-of-gorak-korean-patch)

메뉴·설정·도입부·지도·전투·저장/이어하기·종료를 확인했습니다. 사용자의 화면 검수 종료 요청으로 신규 상점 실화면·엔딩·전체 분기는 미확인입니다. 정적12,080개 검사와 최종 ZIP 설치·복구48개 판정은 통과했습니다. 실제 설치본32파일·새 백업12개·기존 백업27파일·사용자 저장2파일의 보존을 확인했습니다.

설치는 새 ZIP의 Install.cmd, 제거는 같은 ZIP의 Remove.cmd를 사용합니다. 새 백업은 build_26365992에 있으며 예전 build_26336311 백업은 보존합니다. 설치기는 실제 파일 내용으로 판정하므로 번호만 달라지고 파일이 같으면 적용되지만 모든 미래 업데이트의 호환성을 보장하지는 않습니다.

아래는 초기 제작과 1.0.0 배포 이력입니다. 이전 빌드·후보 경로는 현재 지원 버전을 뜻하지 않습니다.

---

[전용 공개 저장소](https://github.com/KIMDONGWHEE99/the-horde-of-gorak-korean-patch) · [공식 이미지 6장으로 보는 게임 소개·리뷰](https://github.com/KIMDONGWHEE99/the-horde-of-gorak-korean-patch/blob/main/INTRODUCTION.md) · [카페 복사용 글과 이미지](../../deliverables/THE_HORDE_OF_GORAK_INTRO_20261102.zip)

2026-11-02 사용자 요청으로 기존 패치와 소개글을 새 공개 저장소에 올렸습니다. [패치 ZIP 다운로드](https://github.com/KIMDONGWHEE99/the-horde-of-gorak-korean-patch/raw/refs/heads/main/downloads/THE_HORDE_OF_GORAK_KOREAN_PATCH_1.0.0_r1.zip)의 내용은 아래 개인용 제작본과 같습니다. 공개 업로드로 기존 검수 범위가 확대되는 것은 아닙니다. [게시 결과](../../validation/THE_HORDE_OF_GORAK/github_publish_20261102/RESULT_REPORT.md).

오크 무리를 이끌고 마을과 군대를 키우는 픽셀 그래픽 성장형 전략 게임입니다. 건설·병력 모집·기술 연구·마법으로 인간의 성을 무너뜨리고 붙잡힌 대족장을 구출하는 것이 목표입니다. [Steam 게임 소개](https://store.steampowered.com/app/4911050/The_Horde_of_Gorak/)

2026-10-31, 한국어 패치 1.0.0을 요청한 `D:\steam\steamapps\common\The Horde of Gorak`에 적용했습니다. Steam에서 평소처럼 실행하면 한국어로 표시됩니다. 지원 버전은 Steam 앱 **4911050 / 빌드 26336311 / 게임 v1.1.03**입니다.

본문·메뉴 590종/855위치, 실행 모듈 176필드, 이미지 문구 4곳과 한글 글꼴을 반영했습니다. 진행 상황과 결과 화면의 줄 정렬도 수정했습니다.

[개인용 패치 ZIP](../../release_output/THE_HORDE_OF_GORAK_KOREAN_PATCH_1.0.0_r1.zip) · [결과와 확인 범위](../../validation/THE_HORDE_OF_GORAK/ko_1.0.0/RESULT_REPORT.md)

## 설치와 제거

이미 설치되어 있으므로 다시 적용할 필요는 없습니다. 재설치할 때는 ZIP을 새 폴더에 모두 풀고 `Install.cmd`를 실행하여 `THOG.exe`가 있는 게임 폴더를 선택합니다. 제거는 같은 ZIP의 `Remove.cmd`로 진행합니다. 게임 업데이트 후 지원하지 않는 파일에는 강제로 적용하지 않습니다.

현재 설치의 원본 백업:

`C:\Users\PC\AppData\Local\TheHordeOfGorakKoreanPatch\working_private\35633642EDCA0C0A\build_26336311`

설치가 중단되면 같은 버전의 설치기를 다시 실행해 복구합니다. 설치·제거기는 사용자 저장 파일을 변경하지 않습니다.

## 확인 범위와 남은 부분

메뉴·설정·지도·명성 특전·전투·정상 저장 후 재실행/이어하기·주요 건물·연구 8개·결과 정렬·용 모집을 실제 화면에서 확인했습니다. 파일별 번역 위치, 글꼴, 변경 경계와 차이 파일의 정방향/역방향 복원도 확인했습니다. 최종 ZIP에서 꺼낸 설치기로 사본 설치·제거를 한 차례 수행했고, 실제 설치 후 32파일·원본 백업 12개와 확인된 사용자 파일의 보존을 확인했습니다.

사용자의 **“검수 그만합시다” → “한글패치 마무리하세요.”** 요청에 따라 추가 검수는 생략했습니다. 엔딩·전체 분기·일부 예비 화면·추가 코드 전수 분류·최종 ZIP의 확장 실패 복구 시험·설치본 재실행은 미완료입니다. 전체 G0~G8 통과판으로 표시하지 않습니다.

게임 제목·제작진·브랜드 로고는 원문을 유지합니다. JSON 해석 오류 등 일부 진단 문구는 영문으로 남아 있습니다. 미완성 오류창 중계 코드와 모든 검수용 변경은 배포본에서 제외했습니다.

ZIP SHA-256: `22b94d117534760284ae2d2d0f310d646465f0e21cd6058c3ff05f67a5981d2f`

[작업 명세](TASK_SPEC.md), [공통 지침](../../docs/KOREAN_PATCH_PLAYBOOK.md)

## 작업 사본 공간 정리

2026-10-31 사용자 요청으로 원본 작업 사본·후보·QA 게임 사본과 원시 추출 자산 10,616파일(약 7.01GB)을 삭제했습니다. 실제 설치 게임·원본 복구 백업·패치 ZIP·번역·제작 도구·화면 및 분석 기록은 보존했고, 보존 대상 2,810파일의 내용이 정리 전과 일치합니다. 현재 패치는 그대로 사용할 수 있습니다. 이후 수정 시 지원 빌드 원본과 후보를 다시 준비해야 합니다.

[공간 정리 결과](../../validation/THE_HORDE_OF_GORAK/storage_cleanup_20261031/RESULT_REPORT.md) · [이번 REA 사용 점검](../../validation/THE_HORDE_OF_GORAK/rea_review_20261031/RESULT_REPORT.md)
