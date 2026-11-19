# 한글패치 프로젝트

사용자에게 누락 탐색과 반복 플레이를 맡기지 않고, 제작자가 조사·번역·실행 검수·설치 복구까지 마치는 작업 공간입니다.

**처음에는 [핵심 지침서](docs/KOREAN_PATCH_PLAYBOOK.md)를 읽고, 재개할 때는 [현재 상태](PROJECT_STATUS.md)에서 다음 미완료 항목을 확인하세요.**

| 필요한 내용 | 문서 |
|---|---|
| 작업자가 항상 지킬 규칙 | [AGENTS.md](AGENTS.md) |
| Claude Code 전용 규칙과 설정 | [CLAUDE.md](CLAUDE.md), [설정 안내](docs/CLAUDE_CODE_SETUP.md) |
| 시작부터 배포까지 절차·통과 조건 | [핵심 지침서](docs/KOREAN_PATCH_PLAYBOOK.md) |
| 글꼴·그래픽 실행·저장 격리 상세 | [런타임 QA 참조](docs/KOREAN_PATCH_RUNTIME_QA_REFERENCE.md) |
| 문서 역할과 읽는 순서 | [문서 안내](docs/README.md) |
| 현재 게임별 상태·다음 작업 | [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| 아직 고치지 않은 검증 도구 문제 | [개선 작업 목록](docs/PROCESS_IMPROVEMENT_BACKLOG.md) |
| 파일 위치·원본 보호·배포 경계 | [ARCHITECTURE_SPEC.md](ARCHITECTURE_SPEC.md) |
| 신규 작업 작성 | [작업 명세 양식](tasks/TASK_SPEC_TEMPLATE.md), [게임 설정 양식](templates/GAME_CONFIG_TEMPLATE.yaml) |
| 검증·보고 작성 | [검증 기록 양식](templates/QA_LEDGER_TEMPLATE.yaml), [결과 보고 양식](templates/RESULT_REPORT_TEMPLATE.md) |

관리하는 게임은 21개입니다. 게임별 최신판과 확인 범위는 [현재 상태](PROJECT_STATUS.md)의 표에, 게임별 자료는 `tasks/<게임>/README.md`에 있습니다.

2026-09-05에 문서 체계를 정비했습니다. 검증 허점의 코드 수정과 기존 패치의 새 기준 재검증은 별도 미완료 작업입니다. 기존 배포 파일과 과거 보고서가 있다는 사실만으로 새 기준의 완성판 판정을 내리지 않습니다.

2026-11-17에 Claude Code용 작업 폴더를 `D:\kpatch`로 분리했습니다. 예전 폴더(`C:\Users\PC\Documents\ChatGPT\한글패치`)는 Codex용으로 남아 있습니다. 같은 날 검수 조작 규칙, 설치 시험 디스크 규칙, 사본 보관·정리 규칙을 지침서에 추가하고 현재 상태 문서를 게임별 표로 줄였습니다.
