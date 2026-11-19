# 프로젝트 현재 상태

갱신: 2026-11-20

이 문서는 지금 상태만 담습니다. 날짜별 경과는 [WORK_LOG.md](WORK_LOG.md)에, 2026-11-16까지의 상태 문서 전문은 [docs/history/PROJECT_STATUS_until_2026-11-16.md](docs/history/PROJECT_STATUS_until_2026-11-16.md)에 있습니다.

아래 판정과 확인 범위는 과거 결과 보고서와 이전 상태 문서의 기록을 옮긴 것이며, 2026-11-17에 새로 검증한 것이 아닙니다. 과거의 PASS를 새 G0~G8 기준의 PASS로 바꿔 읽지 않습니다.

## 진행 중인 작업

- **제작 중인 게임:** 없습니다. Clicky Islands 1.0.0 r1을 2026-11-19에 설치본에 적용했고 시험 사본을 정리했습니다(2,437MB 확보). [안내](tasks/CLICKY_ISLANDS/README.md).
- **Claude Code 이전:** 2026-11-17에 작업 폴더를 `D:\kpatch`로 분리했고 자체 점검 6개 항목이 통과했습니다. 2026-11-19에 Git 저장소를 만들었습니다. 분석 도구(REA) 재연결이 남았습니다. [설정 안내](docs/CLAUDE_CODE_SETUP.md).
- **문구별 자동 재적용 시험(PROC-09):** OPEN입니다. How Empires Work에서 번역 재사용 후보 산출과 모의 시험 12개까지 했고, 실제 게임 업데이트에 자동 적용하는 동작은 구현·검증하지 않았습니다. [개선 작업 목록](docs/PROCESS_IMPROVEMENT_BACKLOG.md).

## 게임별 상태: 2026-09-05 이후 제작한 17개

| 게임 | 최신판 · 지원 빌드 | 설치·공개 | 판정과 확인 범위 | 미검증·제한 | 번역 원본 | 근거 |
|---|---|---|---|---|---|---|
| Clicky Islands | 1.0.0 r1 · Steam 26701014 | 설치본 적용, GitHub 공개 | G0~G8 PASS. 칸 1,078·직접 문구 46 독립 대조, 실제 실행 4회로 필수 화면군 7종의 대표 화면 확인, 최종 ZIP 설치·복구 41건(PASS 38, 해당 없음 3), 설치 후 파일 해시·저장 무변경 확인 | 설치 후 Steam 실행, 시장·가마솥·화산 등 미도달 화면, 전체 회차. 튜토리얼 시연 영상 12종은 영어 화면 그대로 | `working_private/CLICKY_ISLANDS/translation` | [GitHub](https://github.com/KIMDONGWHEE99/clicky-islands-korean-patch) · [결과 보고](validation/CLICKY_ISLANDS/ko_1.0.0/RESULT_REPORT.md) · [안내](tasks/CLICKY_ISLANDS/README.md) |
| How Empires Work | 1.0.1 r2 · Steam 26482667 | 설치본 적용, GitHub 공개 | 수정본 `full_06`이 위치·키·실행·설치·저장 복구 검사를 통과. 1.0.0의 G2~G5는 FAIL로 정정 | 전체 완주, 설치 후 Steam 추가 실행 | `working_private/HOW_EMPIRES_WORK/translation` | [결과 보고](validation/HOW_EMPIRES_WORK/ko_1.0.1/RESULT_REPORT.md) · [안내](tasks/HOW_EMPIRES_WORK/README.md) |
| The Horde of Gorak | 1.0.1 r1 · Steam 26365992 (게임 v1.1.04) | 설치본 적용, GitHub 공개 | 정적 12,080개 검사, 정역 복원 24개, 최종 ZIP 설치·복구 48개 판정 통과. 전체 검수 통과판 아님 | 신규 상점 실화면, 엔딩, 전체 분기, 설치 후 추가 실행. 일부 영문 진단 문구 남음 | 전용 파일 없음 | [결과 보고](validation/THE_HORDE_OF_GORAK/ko_1.0.1/RESULT_REPORT.md) · [안내](tasks/THE_HORDE_OF_GORAK/README.md) |
| Cobalt Miner | 1.0.0 r1 · Steam 24347666 | 설치본 적용(개인용), GitHub 공개 | G2·G5는 FAIL로 보존. G0~G8 전체 통과판 아님 | 엔진 문구 1,237개의 표시 여부, 전체 시설·분기. B검수 종료 오류 원인 미확정 | 일부 (`tasks/COBALT_MINER/translate_cobalt.py`) | [결과 보고](validation/COBALT_MINER/ko_1.0.0/RESULT_REPORT.md) · [안내](tasks/COBALT_MINER/README.md) |
| Soulash 2 | 1.0.0 (20261031) · Steam 25967323 (게임 0.10.4.0.1) | 개인용 ZIP 생성, GitHub 공개. 당시 기록상 설치본은 변경하지 않음 | 사용자 지시로 검수 생략. G0~G8 전체 통과 아님 | 마지막 수정본 재실행, 전체 미분류 조사, 사망·결과 화면, 최종 ZIP 확장 설치 시험 | `working_private/SOULASH_2/translations` | [결과 보고](validation/SOULASH_2/ko_1.0.0/RESULT_REPORT.md) · [안내](tasks/SOULASH_2/README.md) |
| Kingdom Inc. Demo | 1.0.0 r2 · Steam 25631786 | 설치본 적용 | G0~G8이 명시한 범위에서 PASS | 전체 회차, 무작위 분기, 정상 플레이를 통한 모든 해금, 전 문구의 실화면 관찰, 설치본 재실행 | 전용 파일 없음 | [결과 보고](validation/KINGDOM_INC_DEMO/ko_1.0.0/RESULT_REPORT.md) · [안내](tasks/KINGDOM_INC_DEMO/README.md) |
| Alaska Gold Fever | 개인용 교정 `ko_edit_c01` · Steam 25782395 | 설치본 적용. 공개 ZIP 없음 | 개인용 최소 검사. G0~G8 전체 통과 아님 | 추가 플레이, 전체 출처·미디어·분기 검사, 공개 ZIP과 확장 복구 시험 | `working_private/ALASKA_GOLD_FEVER/translation`, `dialogue_translation` | [결과 보고](validation/ALASKA_GOLD_FEVER/ko_edit_c01/RESULT_REPORT.md) · [안내와 복원](tasks/ALASKA_GOLD_FEVER/README.md) |
| Agromatic Demo | 1.0.0 r1 · Steam 25850896 | 설치본 적용 | 기대 번역 14,385위치 독립 대조, 대표 화면 22단계. 추가 검수 중단, G0~G8 전체 통과로 표시하지 않음 | 대화 선택 후 결과, 전체 회차·분기, 오디오 전수 청취, 최종 ZIP 확장 설치·복구 시험, 설치본 재실행 | 전용 파일 없음 | [결과 보고](validation/AGROMATIC_DEMO/ko_1.0.0/RESULT_REPORT.md) · [안내](tasks/AGROMATIC_DEMO/README.md) |
| MR MAGEBOY DEMO | 1.0.0 | 설치본 적용 | 번역·유지 1,172위치와 동적 문구 137곳 독립 대조, 설치·복구 38시험. 추가 검수 중단, G0~G8 전체 통과로 표시하지 않음 | G5 전체, 전체 회차, 일부 추가 화면, 원본 경고 대조 | 전용 파일 없음 | [안내](tasks/MR_MAGEBOY_DEMO/README.md). 결과 보고서 파일 없음 |
| Epic Idlenture Demo | 1.0.0 · Steam 23762546 | 설치본 적용 | G0~G8이 보고서에 기재한 범위에서 PASS | 전체 회차 완주 | 전용 파일 없음 | [안내](tasks/EPIC_IDLENTURE_DEMO/README.md). 결과 보고서 파일 없음 |
| Silky Rails | 1.0.0 | 설치본 적용 | 검수 최소화. G0~G8 전체 통과로 표시하지 않음 | 전체 플레이, 전수 분류, 확장 실패 시험 | 전용 파일 없음 | [안내](tasks/SILKY_RAILS/README.md). 결과 보고서 파일 없음 |
| Alchemortis Demo | 1.0.1 · Steam 25443537 (0.22.2-demo) | 설치본 적용 | 번역 1,598개·숨김 표기 435개 대조, 실제 GPU 변경 화면 7건, 설치·복구 27건 | 전체 회차, 모든 분기 | 전용 파일 없음 | [안내](tasks/ALCHEMORTIS_DEMO/README.md). 결과 보고서 파일 없음 |
| March and Conquer Demo | 1.0.0 · Steam 25323013 | 설치본 적용 | 표시 위치 1,099곳·코드 문구 85곳·글꼴 검증, 실제 GPU 주요 화면 16개, 설치·복구·경로 시험 24건 | 전체 60전 정상 완주, 무작위 회차 | 전용 파일 없음 | [안내](tasks/MARCH_AND_CONQUER_DEMO/README.md). 결과 보고서 파일 없음 |
| Spellbound & Shelved | 1.0.1 · Steam 25274913 | 설치본 적용 | 후보 재추출·위치 대조, 실제 GPU 대표 화면 16개, 설치·복구 24건 | 이 빌드의 전체 무작위 플레이, 일부 추가 화면 순회 | 전용 파일 없음 | [안내](tasks/SPELLBOUND_SHELVED/README.md). 결과 보고서 파일 없음 |
| The Loopler | 1.0.0 | 설치본 적용 | 후보 정적 검사, 설치·복구 22건, 경로 탐색 2건. 추가 검수 중단, G0~G8 전체 통과로 표시하지 않음 | 결과 화면, 마지막 설정 순회 | 전용 파일 없음 | [안내](tasks/THE_LOOPLER/README.md). 결과 보고서 파일 없음 |
| BOREWORKS Demo | 1.0.0 | 설치본 적용 | 실제 GPU 메뉴 21개·배치 검사 282개·화면 관찰 58개, 저장·불러오기, 최종 ZIP 설치·복구 | 전체 무작위 회차 완주 | 전용 파일 없음 | [안내](tasks/BOREWORKS_DEMO/README.md). 결과 보고서 파일 없음 |
| Combolands | 1.0.1 (설치기 개선, 번역은 1.0.0과 같음) | 1.0.0을 설치본에 적용 | 자산 문구 1,833곳·코드 문구 25곳 대조. 추가 테스트 중단, G0~G8 전체 통과로 표시하지 않음 | 전체 분기, 최종 후보 화면 재검수, 설치 실패 확장 시험 | 전용 파일 없음 | [안내](tasks/COMBOLANDS/README.md). 결과 보고서 파일 없음 |

## 게임별 상태: 초기에 제작한 5개

새 G0~G8 기준의 통합 판정은 하지 않았습니다.

| 게임 · 패치 | 보유 검증 범위 | 미검증·제한 | 번역 원본 | 근거 |
|---|---|---|---|---|
| 7 Days to Die / Vanilla Plus 1.6.0 · 한국어 0.1.0 (통합 ZIP) | 번역표 4,235개·참조 1,231곳 정적 검사, 최종 ZIP 설치·복구 19건 | 실제 플레이는 사용자가 직접 테스트하기로 함. 화면·로딩·글꼴 출력 미검증 | `release_output/SEVENDAYS_VANILLAPLUS/ko_0.1.0/korean.delta.json` | [안내](tasks/SEVENDAYS_VANILLAPLUS/README.md). 결과 보고서 파일 없음 |
| PROFITS2167 · 0.5.1 | 텍스트 정적 감사, IL2CPP 재분석, 설치·이전 패치 시험 | 실행 QA NOT_RUN. 사진·영상 속 일부 영문 유지 | 전용 파일 없음 | [안내](tasks/PROFITS2167/README.md) |
| SuperReap Demo · 1.0.1 | 정적·글꼴·목록·설치 시험, 첫 화면 그래픽 확인 | 필수 대표 흐름 전체의 그래픽 증거는 아님 | `tasks/SUPERREAP_DEMO/translations` | [안내](tasks/SUPERREAP_DEMO/README.md) |
| Pibcremental Demo · 1.0.0 | 정적·설치·대표 화면·저장 무결성 기록 | 이전 후보와 최종 후보의 화면이 섞임. 독일어 슬롯 전환과 전체 분기 미확인 | `tasks/PIBCREMENTAL_DEMO/translations` | [안내](tasks/PIBCREMENTAL_DEMO/README.md) |
| TFC2 · 1.0.0 | 정적·글꼴·IL2CPP·설치·대표 흐름 실행 기록 | 전체 캠페인과 분기를 끝까지 확인한 검증은 아님 | `tasks/TFC2/translations` | [안내](tasks/TFC2/README.md) |

## 자료 보유 현황

- **이 폴더에 있는 것:** 문서, 도구, 게임별 명세, 결과 보고서 일부, 배포 ZIP 전부, 번역 폴더 4개(How Empires Work, Soulash 2, Alaska Gold Fever, Clicky Islands), Alaska Gold Fever 설치 백업, Clicky Islands의 원본 사본·추출 자료·후보(제작 중).
- **예전 폴더에만 있는 것:** 예전 폴더는 `C:\Users\PC\Documents\ChatGPT\한글패치`이며 Codex가 계속 씁니다. 게임 원본 사본(How Empires Work, Kingdom Inc. Demo, Cobalt Miner), 추출 자료(7개 게임), 후보(How Empires Work `full_06`, Kingdom Inc. Demo `rc5`, Cobalt Miner, Soulash 2, Alaska Gold Fever, Agromatic Demo, The Horde of Gorak), 검수 원자료와 작업 기록이 거기 있습니다. 필요하면 게임 단위로 가져옵니다.
- **결과 보고서 파일이 없는 게임:** 위 표에 "결과 보고서 파일 없음"이라고 적은 게임은 `validation` 아래의 보고서가 2026-10-07에 삭제됐습니다. 표의 내용은 이전 상태 문서에 남아 있던 요약입니다.
- **전용 번역 파일이 없는 게임 14개:** 2026-11-17에 `tasks`와 `working_private`를 조사했을 때 표에 "전용 파일 없음" 또는 "일부"로 적은 게임은 번역 원문 파일을 찾지 못했습니다. 번역은 배포 ZIP의 차이 파일과 패치가 적용된 게임 파일에만 있을 수 있습니다. 복구는 [PROC-12](docs/PROCESS_IMPROVEMENT_BACKLOG.md)에서 다룹니다.
- **재작업 전 필요한 것:** 원본 사본과 지원 빌드 해시를 다시 확보해야 합니다. 과거 판정을 새 후보의 완료 근거로 재사용하지 않습니다.

## 문서와 구현을 구분한 상태

| 영역 | 현재 상태 | 근거·다음 작업 |
|---|---|---|
| 공통 지침·문서 역할 | 정비 완료. 2026-11-17에 검수 조작 규칙, 설치 시험 디스크 규칙, 사본 보관·정리 규칙 추가 | [핵심 지침서](docs/KOREAN_PATCH_PLAYBOOK.md), [문서 안내](docs/README.md) |
| 게임 설정·작업·검증·결과 양식 | 정비 완료 | [공통 설정의 양식 목록](PROJECT_CONFIG.yaml). 기존 게임 설정 이전은 미수행 |
| Claude Code 설정 | 자체 점검 6개 항목 PASS (2026-11-17) | [설정 안내](docs/CLAUDE_CODE_SETUP.md). 편집 차단 규칙 3개와 REA 연결은 미확인 |
| 코드 검토·격리 재현 | 수행 기록 있음 | [평가 보고서](docs/PROJECT_REVIEW_2026-09-05.md). 재현 결과 파일은 2026-10-07에 삭제됨 |
| 검증 허점·설치 복구·공통 실행기 | 미완료 | [PROC-01~08](docs/PROCESS_IMPROVEMENT_BACKLOG.md) |
| 설치 시험의 사본 삭제, 검수 코드 공통화, 번역 원문 복구 | 미완료. 규칙만 문서에 반영 | [PROC-10~12](docs/PROCESS_IMPROVEMENT_BACKLOG.md) |
| Git | 2026-11-19에 저장소 생성. 작업 저장소에는 원격이 없고 push하지 않음. 2026-11-19부터 걸러 낸 공개 사본을 [KIMDONGWHEE99/kpatch](https://github.com/KIMDONGWHEE99/kpatch)에 올림(번역 원본 폴더와 번역표가 든 도구 제외, 작성자는 GitHub 비공개 주소) | [설정 안내](docs/CLAUDE_CODE_SETUP.md) 8절의 "그 뒤의 규칙". 의미 있는 작업 단위마다 로컬에 커밋하고, 공개 사본은 `tools/publish_project.py --publish`로 갱신 |

## 다음 작업

1. PROC-10은 Clicky Islands의 `test_installer.py`에 반영했습니다(사례가 끝나는 대로 게임 사본 삭제). 라이브러리 탐색 시험의 사본 1개와 다른 게임의 도구에는 아직 반영하지 않았습니다.
2. 새 패치의 관련 단계에서 PROC-01~03·06의 잘못된 통과를 차단하는 검사를 구현하거나 동등한 독립 증거를 확보합니다.
3. 네이티브 코드 분석이 필요한 게임을 만나면 REA를 다시 연결합니다. Java 21을 프로젝트 밖 고정 위치에 다시 설치해야 합니다.
4. 전용 번역 파일이 없는 게임의 번역 원문 복구(PROC-12)는 그 게임을 다시 손볼 때 함께 합니다.
