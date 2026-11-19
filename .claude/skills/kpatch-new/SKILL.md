---
name: kpatch-new
description: 새 게임의 한글패치를 시작하거나 중단한 게임을 재개할 때 쓴다. 게임 이름이나 설치 폴더를 받아 상태 확인, 여유 공간 확인, 엔진 판별, 기존 도구 재사용, 작업 명세 작성, 기준선 고정부터 정적 검증(G0~G4)까지 안내한다.
argument-hint: "[게임 이름 또는 설치 폴더]"
---

# 새 게임 시작·재개

대상: $ARGUMENTS

공통 규칙은 AGENTS.md와 `docs/KOREAN_PATCH_PLAYBOOK.md`가 기준이다. 이 스킬은 순서와 읽을 범위만 정한다.

## 1. 현재 상태 확인

1. `tasks/`에 해당 게임 폴더가 있는지 본다. 있으면 재개다. 그 폴더의 `README.md`와 `TASK_SPEC.md`를 읽고, `PROJECT_STATUS.md`는 게임 이름으로 검색해 해당 절만 읽는다.
2. 없으면 신규다. `tasks/TASK_SPEC_TEMPLATE.md`와 `templates/GAME_CONFIG_TEMPLATE.yaml`로 명세를 직접 작성한다. 사용자에게 양식 작성을 넘기지 않는다.
3. 이 폴더에 그 게임의 작업 자료가 없으면 예전 폴더 `C:\Users\PC\Documents\ChatGPT\한글패치`를 확인한다. `source_original/<게임>`, `extracted_private/<게임>`, `working_private/<게임>`, `build_candidate/<게임>` 가운데 이번 작업에 필요한 것만 같은 상대 경로로 복사한다. 복사 전에 여유 공간을 확인하고, 예전 폴더는 읽기만 한다. 복사한 내용은 `WORK_LOG.md`에 남긴다.
4. 지침서는 필요한 절만 읽는다. 시작과 단계 표는 1~3절, G0~G1은 4절, G2는 5절, G3~G4는 6절, 사본 보관은 11절이다. 글꼴을 건드리기 전에 `docs/KOREAN_PATCH_RUNTIME_QA_REFERENCE.md` 3~4절을 읽는다.

## 2. 여유 공간 확인

게임 설치 폴더 크기를 재고 프로젝트 드라이브의 여유 공간과 비교한다. 원본 사본, 후보, 검수 사본이 동시에 있을 수 있으므로 여유가 (게임 크기 × 3) + 20GB보다 적으면 사용자에게 알리고 `/kpatch-cleanup`을 먼저 한다.

## 3. 엔진 판별과 도구 재사용

실제 게임 폴더는 읽기만 한다. 엔진을 확인한 뒤 아래에서 가장 가까운 게임의 도구를 새 게임 폴더로 복사해 고쳐 쓴다. 설치기(`release_template/Patch.ps1`), 설치 시험, 패키징, 기준선 도구를 처음부터 다시 쓰지 않는다.

| 엔진 | 참고할 기존 게임 (`tasks/` 아래) | 메모 |
|---|---|---|
| Godot 4, GDScript | `HOW_EMPIRES_WORK`(가장 최근), `MR_MAGEBOY_DEMO`, `SPELLBOUND_SHELVED`, `AGROMATIC_DEMO`(C# 혼합) | PCK 도구 `pck_tools.py`, 검수 코드 `qa_driver.gd`, 재적용 시험 `reapply_translation.py` |
| Godot 4, C# | `ALCHEMORTIS_DEMO`, `BOREWORKS_DEMO` | 어셈블리 문자열 조사 포함 |
| Unity, Mono | `KINGDOM_INC_DEMO`(가장 최근), `EPIC_IDLENTURE_DEMO`, `MARCH_AND_CONQUER_DEMO`, `PIBCREMENTAL_DEMO`, `COMBOLANDS`, `SILKY_RAILS` | 검수 코드 `tools/KoreanQA/Driver.cs` |
| Unity, IL2CPP | `TFC2`, `ALASKA_GOLD_FEVER`, `THE_LOOPLER` | 메타데이터를 수정하면 Cpp2IL로 재분석 |
| Clickteam Fusion | `THE_HORDE_OF_GORAK`, `COBALT_MINER` | Nebula 추출 도구 사용. 설치기와 설치 시험이 가장 최신형 |
| SDL2 네이티브 + JSON 자료 | `SOULASH_2` (도구는 프로젝트 루트 `tools/soulash2_*.py`) | 네이티브 문구는 REA 필요 |

Unity TMP 글꼴 사고 사례는 `SUPERREAP_DEMO`와 런타임 QA 참조에 있다. 표에 없는 엔진이면 구조를 조사해 가장 비슷한 것을 고르고, 고른 이유를 TASK_SPEC에 적는다.

## 4. 진행

1. G0: 원본 사본과 해시 목록을 만든다. 실제 게임 폴더에서 추출·수정·임시 파일 생성을 하지 않는다.
2. G1: 대량 번역 전에 무변경 재저장, 짧은 한글 문구, 글꼴, 로딩을 작게 시험한다.
3. G2~G4: 지침서 5~6절대로 전수 조사, 번역, 후보 재추출 비교를 한다. 새 항목과 추출 실패의 기본값은 `UNKNOWN`이다.
4. 네이티브 코드 질문이 남을 때만 REA를 쓴다. 연결 상태는 `/mcp`로 확인하고 `docs/CLAUDE_CODE_SETUP.md` 4절을 따른다.
5. 새 후보가 G4를 통과하면 이전 후보 폴더를 삭제 목록에 올린다. 해시와 build 기록은 남긴다.

## 5. 이어지는 단계

- 화면 검수는 `/kpatch-qa`, 패키징과 설치 시험은 `/kpatch-release`를 쓴다.
- 단계가 끝날 때마다 게임의 `TASK_SPEC.md` 단계 표와 `PROJECT_STATUS.md`의 게임별 표에서 그 게임의 행을 갱신한다. 경과는 `WORK_LOG.md`에 적는다. 번역 원본의 위치는 게임 README에 적는다. 통과하지 않은 단계를 통과로 쓰지 않는다.
