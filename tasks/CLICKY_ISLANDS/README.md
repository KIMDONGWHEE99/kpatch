# Clicky Islands 한국어 패치 1.0.0 r1

2026-11-19에 Steam 빌드 26701014용 패치를 `D:\steam\steamapps\common\Clicky Islands`에 **설치했습니다**(G0~G8 통과 뒤 사용자 지시로 적용). 설치된 4개 파일은 검증한 후보 `ko_c03`과 해시가 같고, 사용자 저장은 설치 전후 동일합니다. 설치 뒤 Steam으로 실행해 보는 확인은 하지 않았습니다.

- [최종 설치 묶음](../../release_output/CLICKY_ISLANDS_KOREAN_PATCH_1.0.0_r1.zip) (약 8MB, SHA-256 `baf36898ebc314a6a1ab7cfc84bd6eb995f46a6697c11cdbe4ba6064f4962907`)
- 설치: [Install.cmd](../../release_output/CLICKY_ISLANDS_KOREAN_PATCH_1.0.0_r1/Install.cmd) · 제거: [Remove.cmd](../../release_output/CLICKY_ISLANDS_KOREAN_PATCH_1.0.0_r1/Remove.cmd)
- [결과 보고](../../validation/CLICKY_ISLANDS/ko_1.0.0/RESULT_REPORT.md)

- 대상: Steam 빌드 26701014 (Godot 4.5.2)
- 방식: 게임에 원래 있던 빈 한국어 칸(`kr`)을 채웁니다. 다른 언어는 그대로 남습니다.
- 번역: 언어표 1,078칸(고유 문구 977개), 언어표 밖 직접 문구 46개, 무작위 섬 이름 50개
- 한글 글꼴: Noto Sans KR 보통·굵게 (SIL OFL 1.1)
- 언어 선택 화면과 설정의 언어 탭에 "한국어" 버튼이 생기고, Windows가 한국어이면 처음부터 한국어로 시작합니다.

## 번역 원본의 위치

- 공식 번역 원본: `working_private/CLICKY_ISLANDS/translation/canonical.json`
- 작업 파일(고칠 때는 여기서): 같은 폴더의 `ko_001.txt`~`ko_005.txt`, `ko_fix.txt`(교정이 마지막에 덮어씀), `direct_ko.json`, `island_names_ko.json`
- 이 폴더는 정리할 때 지우지 않습니다.

## 설치 상태와 되돌리기

- 바뀐 파일은 `Clicky Islands.pck` 하나입니다. 원본 백업은 `%LOCALAPPDATA%\ClickyIslandsKoreanPatch\working_private\CD5061E25375181F\build_26701014`에 있으며 지우지 않습니다.
- 되돌리려면 게임을 끄고 `Remove.cmd`를 실행합니다. Steam의 파일 무결성 검사로도 원본으로 돌아갑니다.
- 게임이 업데이트되면 패치가 사라질 수 있고, 이 설치기는 새 빌드에 적용되지 않습니다.

## 남은 일

1. 화면 검수에서 가 보지 못한 화면(시장·가마솥·화산, 후반 단계 건물 등)은 미검증입니다. 목록은 `working_private/CLICKY_ISLANDS/qa/c03_a/qa_ledger.json`에 있습니다.
2. 남아 있는 사본: 원본 사본(248MB), 추출 자료(481MB), 최신 후보 `ko_c03`(256MB). 게임이 업데이트된 뒤에는 이 빌드의 원본을 다시 구할 수 없으므로, 지울지는 따로 정합니다.

## 유지한 것과 한계

- 게임 제목, 제작진 이름, 로고, 각 언어 이름 표기, 개발자 명령창은 영어 그대로입니다.
- 튜토리얼 시연 영상 12종은 영어 화면을 녹화한 것이라 영상 속 건물 이름·버튼 글자가 영어입니다(원작도 독일어·폴란드어 등에서 같은 영상을 씁니다). 영상 옆 설명문과 목표는 한국어입니다.
- 원작 언어표에 항목이 없는 키 14종은 원작처럼 키 이름이 그대로 보일 수 있습니다.
- 게임이 업데이트되면 이 패치는 적용되지 않습니다. 원작에 한국어 칸이 비어 있는 채로 들어 있어 공식 한국어가 나올 수 있습니다.

자세한 근거와 게이트 상태는 [작업 명세](TASK_SPEC.md)에 있습니다.
