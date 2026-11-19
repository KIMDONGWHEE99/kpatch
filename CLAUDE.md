# 한글패치 프로젝트 (Claude Code)

@AGENTS.md

## Claude Code 전용 규칙

공통 규칙은 AGENTS.md와 `docs/KOREAN_PATCH_PLAYBOOK.md`에 있다. 이 절은 Claude Code에서만 필요한 내용이다.

### 스킬

| 상황 | 스킬 |
|---|---|
| 새 게임을 시작하거나 중단한 게임을 재개 | `/kpatch-new` |
| 화면 검수(G5) | `/kpatch-qa` |
| 차이 패치, 최종 ZIP, 설치 시험, 배포(G6~G8) | `/kpatch-release` |
| 작업 사본 정리, 용량 확보 | `/kpatch-cleanup` |

이 폴더에서 게임 이름을 받으면 한글패치 작업으로 해석한다. 방송 게임 추천 카드 스킬(`woojunging-game-card`)과 `claude-api` 스킬은 사용자가 그 작업을 명시했을 때만 쓴다.

### 설정으로 강제되는 것

- 컴퓨터 유즈 도구와 입력 주입 스크립트 3개(`send_game_key`, `click_game_window`, `send_game_input`)는 실행이 차단돼 있다. 화면 검수는 AGENTS.md의 "화면 검수 진행 방식"과 `/kpatch-qa`를 따른다. 캡처는 Read 도구로 열어 판독한다.
- 실제 게임 설치 폴더(`D:\steam`)와 예전 폴더는 편집 도구로 고칠 수 없다. `source_original`을 편집하려면 사용자 승인이 필요하다.
- 세션을 시작할 때 프로젝트 드라이브의 여유 공간이 전달된다. 50GB 미만이라는 경고가 있으면 게임 사본을 만들지 말고 사용자에게 알린 뒤 `/kpatch-cleanup`부터 한다.
- 사본의 보관과 삭제는 핵심 지침서 11절을 따른다. 시험 도구의 자동 삭제를 제외한 삭제는 목록을 사용자에게 보여 주고 승인받은 뒤에 한다.

### 실행 환경

- Windows이며 프로젝트 폴더는 `D:\kpatch`다. 게임 폴더와 예전 폴더의 경로에는 공백이나 한글이 있으므로 경로는 항상 따옴표로 감싸고, PowerShell에서는 `-LiteralPath`를 쓴다.
- Python 출력의 한글이 깨져 보이면 그 명령에만 `PYTHONIOENCODING=utf-8`을 붙인다. `PYTHONUTF8`을 전역으로 켜지 않는다. 기존 도구 일부가 하위 프로세스 출력과 파일을 시스템 기본 인코딩으로 읽는다.
- 새 도구는 파일을 열 때 `encoding='utf-8'`을 명시한다.
- 새 게임의 도구는 같은 엔진의 기존 게임 도구를 복사해 고쳐 쓴다. 설치기·설치 시험·패키징을 처음부터 다시 쓰지 않는다. 참고 구현 목록은 `/kpatch-new`에 있다.
- 보고서와 문서는 프로젝트 폴더 안의 Markdown 파일로 만든다. 외부 문서 서비스나 별도 문서 도구로 만들지 않는다.

### 예전 폴더

- 이 폴더는 2026-11-17에 `C:\Users\PC\Documents\ChatGPT\한글패치`에서 분리했다. 예전 폴더는 Codex가 계속 쓰므로 읽기만 하고, 고치거나 지우지 않는다.
- 예전에 작업한 게임의 원본 사본, 추출 자료, 후보, 작업 기록은 예전 폴더에 남아 있다. 필요한 게임의 자료만 같은 상대 경로로 복사해 온다. 절차는 `/kpatch-new` 1절에 있다.
- 과거 문서와 증거 파일에 적힌 예전 폴더 경로는 당시 기록이다. 새 작업의 경로는 이 폴더 기준으로 쓴다.

### 문서를 읽는 범위

- `PROJECT_STATUS.md`는 현재 상태만 담는다. 과거 경과는 `WORK_LOG.md`와 `docs/history/`에 있으며, 필요할 때 해당 게임 이름으로 검색해 그 부분만 읽는다.
- AGENTS.md와 docs에 나오는 Codex 전용 표현은 바꿔 읽는다. `.codex/config.toml`의 MCP 설정은 Claude Code의 MCP 설정으로, "앱 설정에서 MCP 다시 시작"은 `/mcp`의 Reconnect로 읽는다. "호출 제한 450초"는 Codex의 값이라 적용하지 않는다.
- REA·Ghidra 연결은 `docs/CLAUDE_CODE_SETUP.md` 4절을 따른다. 연결을 실제 호출로 확인하기 전에는 REA 분석을 했다고 쓰지 않는다.
