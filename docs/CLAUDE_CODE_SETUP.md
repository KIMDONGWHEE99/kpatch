# Claude Code 이전 안내

작성: 2026-11-16 · 대상: 이 프로젝트를 Codex 대신 Claude Code에서 쓰기 위한 설정과 첫 실행 점검

**2026-11-17에 `D:\kpatch`에서 2절의 자체 점검 6개 항목이 모두 PASS였다.** 근거는 2절의 "점검 기록"에 있다. 그 점검이 다루지 않은 것은 아직 동작을 확인하지 않았다: 사용자가 직접 보는 Computer use 설정(2절 5번 단계), `Edit` 차단·승인 규칙 3개, 스킬 4개의 실제 실행, 4절의 REA 연결.

2026-11-16의 첫 점검은 예전 폴더(`C:\Users\PC\Documents\ChatGPT\한글패치`)에서 했고, 2026-11-17에 프로젝트를 `D:\kpatch`로 옮긴 뒤 다시 점검했다.

## 1. 추가한 파일

| 파일 | 역할 |
|---|---|
| `CLAUDE.md` | Claude Code가 세션마다 읽는 지침. `AGENTS.md`를 불러오고 Claude Code 전용 규칙을 더한다 |
| `.claude/settings.json` | 차단 규칙과 세션 시작 훅 |
| `.claude/hooks/disk_report.ps1` | 세션을 시작할 때 프로젝트 드라이브의 여유 공간을 Claude에게 전달 |
| `.claude/skills/kpatch-new/SKILL.md` | 새 게임 시작·재개 절차 |
| `.claude/skills/kpatch-qa/SKILL.md` | 화면 조작 없는 화면 검수 절차 |
| `.claude/skills/kpatch-release/SKILL.md` | 패키징·설치 시험·배포 절차와 디스크 규칙 |
| `.claude/skills/kpatch-cleanup/SKILL.md` | 작업 사본 정리 절차 |
| `docs/CLAUDE_CODE_SETUP.md` | 이 문서 |

기존 문서와 도구는 바꾸지 않았다. 되돌리려면 `CLAUDE.md`, `.claude` 폴더, 이 문서를 지운다.

### 예전 폴더와의 관계

`D:\kpatch`는 Claude Code용 작업 폴더이고, `C:\Users\PC\Documents\ChatGPT\한글패치`는 Codex용으로 그대로 둔다. 두 폴더는 따로 움직이며, 한쪽에서 한 작업은 다른 쪽에 반영되지 않는다.

| 새 폴더로 복사한 것 | 예전 폴더에만 있는 것 |
|---|---|
| 루트 문서, `docs`, `templates`, `tasks`, `tools`, `validation`, `deliverables` | 게임 원본 사본, 추출 자료, 후보 |
| `release_output`의 ZIP 전부, ZIP이 없는 폴더 4개, 문서가 가리키는 풀린 폴더 5개 | 그 밖의 풀린 폴더 |
| 번역 폴더(How Empires Work, Soulash 2, Alaska Gold Fever) | 검수 원자료와 작업 기록 |
| Alaska Gold Fever 설치 백업과 설치 기록, REA 시험 자료 | `viewer_output`, `backups`, `.git` |

- 복사한 2,964개 파일(약 2.1GB)은 원본과 SHA-256이 모두 일치했다. `__pycache__`와 `obj`는 빼고 복사했다.
- 예전 폴더는 Claude Code가 편집하지 못하게 설정으로 차단했다. 읽기는 가능하며 처음 읽을 때 승인 창이 뜰 수 있다.
- 끝낸 게임을 다시 손볼 때는 `/kpatch-new` 1절대로 그 게임의 자료만 가져온다.
- 예전 폴더를 지우기 전에, 새 폴더에 없는 게임 자료 가운데 남길 것이 있는지 먼저 확인한다.

## 2. 첫 실행 점검

Claude 데스크톱 앱의 Code 탭에서 한다. 터미널은 필요 없다.

1. 앱 사이드바 맨 위의 **Code** 탭을 연다.
2. 입력창 아래 줄에서 환경은 **Local**, 폴더는 **Open folder…**로 이 프로젝트 폴더를 고른다. 권한 모드는 **Manual**로 시작한다.
3. 폴더를 신뢰하느냐는 확인 창이 나오면 내용을 확인하고 수락한다.
4. 아래 문장을 그대로 보낸다.

   > docs/CLAUDE_CODE_SETUP.md 2절의 자체 점검을 수행하고 표로 보고해 줘.

5. 앱 설정의 This computer → System → Computer use가 꺼져 있는지 직접 확인한다.

### 자체 점검 (Claude Code가 수행)

각 항목을 실제로 확인하고 PASS 또는 FAIL과 근거를 표로 보고한다. 확인하지 못한 항목을 PASS로 쓰지 않는다.

| # | 확인할 것 | 방법 | 기대 결과 |
|---|---|---|---|
| 1 | 지침 로드 | 세션에 들어온 지침에 `CLAUDE.md`의 "Claude Code 전용 규칙"과 `AGENTS.md`의 "무조건 지킬 검증 규칙"이 모두 있는지 본다 | 둘 다 있다 |
| 2 | 여유 공간 보고 | 세션 시작 때 받은 "Disk report" 문장을 그대로 인용한다 | 드라이브와 GB 수치가 있다. 없으면 FAIL로 쓰고 5절의 명령으로 스크립트를 직접 실행해 결과를 덧붙인다 |
| 3 | 스킬 | 사용할 수 있는 스킬에서 `kpatch-new`, `kpatch-qa`, `kpatch-release`, `kpatch-cleanup`을 찾는다 | 4개 모두 있다 |
| 4 | 입력 주입 차단 | `Get-Item "tasks/TFC2/tools/send_game_input.ps1"`처럼 해롭지 않은 명령을 실행해 본다. 스크립트 자체는 실행하지 않는다 | 권한 규칙으로 거부된다 |
| 5 | 컴퓨터 유즈 차단 | 사용할 수 있는 도구 중 이름이 `mcp__computer-use__`로 시작하는 것이 있는지 본다 | 없다 |
| 6 | 다른 플러그인의 간섭 | 세션 시작 때 이 프로젝트 지침과 무관한 플러그인 안내(예: bkit)가 함께 들어왔는지 본다 | 없다. 있으면 플러그인 이름과 자동 실행 규칙을 보고한다 |

하나라도 FAIL이면 5절을 본다. `/permissions`처럼 터미널 전용 화면을 여는 명령은 데스크톱 앱에서 쓸 수 없어서 점검에 넣지 않았다.

### 점검 기록

| 날짜 | 환경 | 결과 |
|---|---|---|
| 2026-11-16 | Claude 데스크톱 앱 Code 탭, 예전 폴더 | 5개 항목 모두 PASS |
| 2026-11-17 | Claude 데스크톱 앱 Code 탭, `D:\kpatch` | 6개 항목 모두 PASS |

2026-11-16 점검의 근거:

| # | 판정 | 근거 |
|---|---|---|
| 1 | PASS | 세션 지침에 `CLAUDE.md`의 "Claude Code 전용 규칙"과 `AGENTS.md`의 "무조건 지킬 검증 규칙"이 모두 있었다 |
| 2 | PASS | `Disk report: project drive C:\ has 297.3 GB free of 881.8 GB. Before copying game files, confirm the copies fit with 20 GB to spare (see CLAUDE.md).` |
| 3 | PASS | 스킬 목록에 `kpatch-new`, `kpatch-qa`, `kpatch-release`, `kpatch-cleanup`이 모두 있었다. 실행은 하지 않았다 |
| 4 | PASS | PowerShell의 `Get-Item "tasks/TFC2/tools/send_game_input.ps1"`과 Bash의 `ls -l "tasks/TFC2/tools/send_game_input.ps1"`이 `Permission to use … has been denied.`로 거부됐다. 파일은 실제로 있고, 대조로 실행한 `Get-Item -LiteralPath "tasks/TFC2/tools"`는 통과했다. 스크립트는 실행하지 않았다 |
| 5 | PASS | 도구 목록과 도구 검색("computer-use")에 `mcp__computer-use__`로 시작하는 도구가 없었다. 컴퓨터 유즈 안내문과 `anthropic-skills:computer-use` 스킬 이름은 세션에 들어와 있었다 |

이 점검에 포함되지 않은 것:

- 사용자가 직접 하는 5번 단계(앱 설정의 Computer use 꺼짐)는 확인 결과를 받지 못했다.
- `send_game_key`, `click_game_window` 차단 규칙은 따로 시험하지 않았다. `send_game_input` 규칙과 같은 형식이다.
- `Edit(//d/steam/**)` 차단과 `Edit(/source_original/**)` 승인 요청은 시험하지 않았다.

점검 중 본 것: 같은 세션에 bkit 플러그인의 세션 시작 안내가 함께 들어왔다. "검증", "분석", "보고서", "개선" 같은 낱말에 bkit 전용 서브에이전트를 실행하라는 규칙이 있어 이 프로젝트의 일상 용어와 겹친다. 이 프로젝트 설정에서 나온 것이 아니며 조치하지 않았다.

2026-11-17 점검의 근거(`D:\kpatch`, Claude Code 세션의 보고를 옮겨 적음):

| # | 판정 | 근거 |
|---|---|---|
| 1 | PASS | 세션 지침에 `CLAUDE.md`의 "Claude Code 전용 규칙"과 `AGENTS.md`의 "무조건 지킬 검증 규칙"이 모두 있었다 |
| 2 | PASS | `Disk report: project drive D:\ has 301 GB free of 931.5 GB. Before copying game files, confirm the copies fit with 20 GB to spare (see CLAUDE.md).` |
| 3 | PASS | 스킬 목록에 4개가 모두 있었다. 실행은 하지 않았다 |
| 4 | PASS | PowerShell의 `Get-Item`과 Bash의 `ls -l`로 `tasks/TFC2/tools/send_game_input.ps1`을 조회하는 명령이 모두 거부됐고 대조 명령은 통과했다. `send_game_key`와 `click_game_window`도 같은 방식으로 시험해 둘 다 거부됐다(PowerShell만 시험). 스크립트는 실행하지 않았다 |
| 5 | PASS | 도구 목록과 도구 검색에 `mcp__computer-use__`로 시작하는 도구가 없었다 |
| 6 | PASS | bkit 안내가 들어오지 않았고 세션 시작 훅이 보낸 것은 Disk report뿐이었다. 연결 서비스 안내 4개(Claude Docs, Notion, Claude in Chrome, computer-use)에는 낱말에 반응하는 자동 실행 규칙이 없어 간섭으로 보지 않았다 |

이 점검에 포함되지 않은 것: 앱 설정의 Computer use 꺼짐(사용자 확인 항목), `Edit(//d/steam/**)`·`Edit(//c/Users/PC/Documents/ChatGPT/**)`·`Edit(/source_original/**)` 규칙, 스킬 4개의 실제 실행, REA 연결.

bkit 플러그인은 2026-11-17에 사용자가 제거했다.

## 3. 설정이 하는 일

`CLAUDE.md`의 규칙은 Claude가 따르려고 노력하는 지침이고, `.claude/settings.json`의 규칙은 Claude Code가 강제한다.

| 규칙 | 종류 | 이유 |
|---|---|---|
| `mcp__computer-use__*` | 차단 | 검수 중 화면 조작으로 사용자의 PC 사용을 방해한 문제 |
| `send_game_key`, `click_game_window`, `send_game_input`이 들어간 명령 | 차단 | 창을 앞으로 가져와 입력을 주입하는 기존 스크립트 3개 |
| `Edit(//c/Users/PC/Documents/ChatGPT/**)` | 차단 | Codex가 쓰는 예전 폴더를 Claude Code가 고치지 못하게 한다 |
| `Edit(//d/steam/**)` | 차단 | 실제 게임 설치 폴더를 편집 도구로 직접 고치지 못하게 한다. 설치기(`Patch.ps1`) 실행은 막지 않으며 평소처럼 승인 창을 거친다 |
| `Edit(/source_original/**)` | 승인 요청 | 원본 기준선은 처음 복사할 때 말고는 바꾸지 않는다. 처음 복사가 정당한 단계라서 차단이 아니라 승인 요청으로 두었다 |
| 세션 시작 훅 | 알림 | 여유 공간이 50GB 미만이면 게임 사본을 만들지 말라고 Claude에게 경고한다 |

알아 둘 한계:

- 차단 규칙은 Claude Code의 편집 도구와 명령 문자열에 적용된다. Python 스크립트가 내부에서 파일을 쓰는 것까지 막지는 않는다. 게임 폴더 보호는 기존처럼 설치기의 해시 검사와 승인 절차가 맡는다.
- Steam 라이브러리가 `D:\steam`이 아닌 곳에도 있으면 `Edit(//<드라이브 소문자>/<경로>/**)` 줄을 더한다.
- Python 인코딩 환경값(`PYTHONUTF8`, `PYTHONIOENCODING`)은 설정에 넣지 않았다. 기존 도구 가운데 18개 파일이 하위 프로세스 출력을 텍스트로 읽는데 대부분 인코딩을 지정하지 않는다. 전역으로 바꾸면 설치 시험 등이 깨질 수 있다. 한글 출력이 깨져 보일 때 그 명령에만 붙인다.

## 4. 분석 도구(REA) 다시 연결

현재 상태:

- REA는 Codex 설정(`C:\Users\PC\.codex\config.toml`)에만 등록돼 있다. Claude Code에는 등록돼 있지 않다.
- Ghidra는 2026-10-31 기록상 `C:\Users\PC\AppData\Local\REA\toolchains\ghidra_12.1.4_PUBLIC`에 있다. 지금도 있는지는 확인하지 못했다.
- Java는 기록상 `working_private/SOULASH_2/toolchain/jdk-21.0.12.1+1`이었지만 2026-11-16에 확인했을 때 그 폴더가 없었다. Codex 쪽 Ghidra 분석도 지금은 동작하지 않을 수 있다.

아래 절차의 `claude mcp` 명령은 터미널용 CLI를 따로 설치했을 때 쓸 수 있다. 데스크톱 앱만 쓰면 Code 탭 세션에서 "이 문서 4절대로 REA를 연결해 줘"라고 요청하고, 서버 설정은 `C:\Users\PC\.claude.json`이나 프로젝트 루트의 `.mcp.json`에 둔다. 데스크톱 앱도 이 두 파일을 읽는다.

절차:

1. JDK 21을 프로젝트 밖의 고정 위치에 둔다. 예: `C:\Users\PC\AppData\Local\REA\toolchains\jdk-21`. 작업 폴더 안에 두면 정리할 때 함께 지워진다.
2. Node.js 버전을 확인한다(`node --version`). REA 저장소 안내는 22.x, 24.x, 26.x의 최근 버전을 요구한다.
3. 터미널에서 `npx rea-agents@latest setup`을 실행하고 대상으로 Claude Code를 고른다. REA 저장소 안내에 따르면 이 명령이 MCP 서버 등록까지 한다.
4. `claude mcp list`로 등록된 이름을 확인하고 `claude mcp get <이름>`으로 실행 명령을 본다.
5. 그 서버의 환경값에 다음을 추가한다. `C:\Users\PC\.claude.json`의 해당 서버 항목 `env`에 넣거나, 같은 명령에 `env`를 더해 `claude mcp add-json`으로 다시 등록한다.

   | 이름 | 값 |
   |---|---|
   | `GHIDRA_INSTALL_DIR` | Ghidra 폴더 |
   | `JAVA_HOME` | 1번에서 정한 JDK 폴더 |
   | `TEMP`, `TMP` | `C:\Users\PC\AppData\Local\REA\runtime` (영문 경로) |

6. Claude Code에서 `/mcp`를 열어 해당 서버를 Reconnect 한다.
7. 실제 호출로 확인한다. `binary_session`으로 상태를 보고, 작은 시험 파일을 `open_binary`(`provider_id: "ghidra"`)로 열어 `analyze_function` 응답을 받는다. 상태 조회 성공만으로 연결 완료라고 하지 않는다. 시험 파일은 `working_private/REA_GHIDRA_20261031/probe.dll`을 쓸 수 있다.
8. 긴 분석이 중간에 끊기면 그 서버 항목에 `"timeout"`(밀리초)을 넣는다.

서버 이름이 `rea`로 등록되면 도구 이름은 문서에 적힌 `mcp__rea__binary_session` 형식 그대로다. 다른 이름이면 문서의 도구 이름을 그 이름으로 바꿔 읽는다. 3~5번의 세부는 REA 버전에 따라 다를 수 있으니 REA 저장소의 설치 안내를 기준으로 한다.

## 5. 문제가 생기면

| 증상 | 확인할 것 |
|---|---|
| 차단 규칙이 동작하지 않는다 | `.claude/settings.json` 문법 오류일 수 있다. Claude Code에게 이 파일을 JSON으로 검사해 달라고 한다. 터미널용 CLI가 있으면 `claude doctor`를 실행한다 |
| 여유 공간을 답하지 못한다 | 터미널에서 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .claude\hooks\disk_report.ps1`을 직접 실행한다. JSON 한 줄이 나오면 스크립트는 정상이고 훅 등록 쪽 문제다 |
| 세션 시작 때 훅 오류가 뜬다 | `settings.json`에서 `"hooks"` 블록만 지운다. 차단 규칙에는 영향이 없다 |
| 필요한 작업이 차단 규칙에 막힌다 | deny는 allow로 풀 수 없다. 해당 줄을 지우거나 고친다 |
| 스킬이 안 뜬다 | `.claude/skills/<이름>/SKILL.md` 위치와 첫 줄의 `---`를 확인한다 |
| Python 출력의 한글이 깨진다 | 그 명령에만 `PYTHONIOENCODING=utf-8`을 붙인다 |

## 6. Codex 문서 표현 대응

기존 문서는 Codex 기준으로 쓰여 있다. 문서를 고치기 전까지 이렇게 바꿔 읽는다.

| 기존 문서의 표현 | Claude Code에서 |
|---|---|
| `AGENTS.md` | `CLAUDE.md`가 불러온다. 내용은 그대로 유효하다 |
| `C:/Users/PC/.codex/config.toml`의 `[mcp_servers.rea]` | Claude Code의 MCP 설정 (`claude mcp` 명령, `C:\Users\PC\.claude.json`) |
| 앱 설정 → 플러그인 → MCP → 다시 시작 | `/mcp`에서 Reconnect |
| 호출 제한 450초 | Codex의 값이다. Claude Code는 서버별 `timeout`으로 정한다 |
| "현재 대화에서 시작" | Claude Code 세션에서 시작. `/kpatch-new`를 쓴다 |
| 병렬 작업자 | 서브에이전트. 아직 따로 정의하지 않았다 |

## 7. 아직 하지 않은 것

기존 문서 개정은 2026-11-17에 마쳤다. 내용은 `WORK_LOG.md`의 같은 날짜 기록에 있다.

Git 시작은 2026-11-19에 8절의 절차로 마쳤다(첫 커밋 `50dffc6`). 결과는 `WORK_LOG.md`의 "2026-11-19 Git 시작" 기록에 있다.

- 분석 도구(REA) 재연결: 4절
- 편집 차단·승인 규칙 3개와 스킬 4개의 실제 동작 확인
- 설치 시험 도구에 사례별 삭제 넣기: 규칙은 `/kpatch-release`에 적었지만 기존 `test_installer.py`들의 코드는 아직 고치지 않았다
- 공통 도구 만들기: 설치기, 설치 시험, 패키징이 게임마다 복제돼 있다 (개선 목록 PROC-08)

## 8. Git 시작 절차

Git은 파일의 변경 이력을 저장해 두고 필요하면 이전 상태로 되돌리는 도구다. 2026-11-19에 아래 절차로 이 폴더에 저장소를 만들었다(첫 커밋 `50dffc6`). 절차는 한 번만 수행하는 것이라 다시 수행하지 않으며, 앞으로는 아래 "그 뒤의 규칙"을 따른다. 저장소는 이 PC 안에만 두고 인터넷에 올리지 않는다.

준비된 것(2026-11-19):

- `.gitignore`: 게임 사본과 파생 자산, 배포 ZIP과 풀어 둔 폴더, 외부 도구 바이너리, 빌드 산출물, 실행 파일, 게임에서 나온 이미지를 제외한다.
- `.gitattributes`: 줄바꿈 자동 변환을 끈다. 도구 파일의 해시가 기록과 달라지지 않게 하기 위해서다.
- `tools/THIRD_PARTY_TOOLS.md`: Git에 넣지 않는 외부 도구의 이름·버전·해시.

절차:

1. `git --version`으로 Git이 설치돼 있는지 확인한다. 없으면 멈추고 사용자에게 Git for Windows 설치가 필요하다고 알린다.
2. `D:\kpatch\.git`이 이미 있으면 멈추고 상태를 보고한다. 예전 폴더의 `.git`은 건드리지 않는다.
3. `_to_delete` 폴더의 내용을 확인하고(복사 중 생긴 임시 파일 1개와 플러그인 상태 파일 2개) 사용자 승인을 받아 폴더를 지운다.
4. `git init`으로 저장소를 만든다. 기본 브랜치 이름은 `main`으로 한다.
5. `git config user.name`과 `git config user.email`을 확인한다. 비어 있으면 사용자에게 묻는다. 임의로 정하지 않는다.
6. 커밋하기 전에 대상을 확인한다. `git status --porcelain -uall`의 목록으로 아래를 검사하고 결과를 보고한다.
   - 파일 수가 약 1,000개인지. 2026-11-19에 같은 규칙으로 시험했을 때 `.claude`를 뺀 대상이 996개, 22.2MiB였다.
   - 5MB를 넘는 파일이 `tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf` 하나뿐인지.
   - 다음이 하나도 없는지: `source_original`·`extracted_private`·`working_private`·`build_candidate`·`_to_delete` 아래의 파일, `.dll`·`.exe`·`.pdb`·`.zip`·`.pck`·`.assets`·`.xdelta` 파일, `tools/python_deps`, `tools/gdre_2.6.4`, `release_output`의 ZIP과 폴더, `bin`·`obj`·`media`·`images` 폴더의 파일.
   - 기대와 다르면 커밋하지 않고 목록과 함께 보고한다. `.gitignore`를 고쳐야 하면 이유를 설명한 뒤 고친다.
7. `git add -A` 후 첫 커밋을 만든다. 커밋 메시지는 `기준선: D:\kpatch 분리와 문서 개정 1.3`으로 한다.
8. 원격 저장소를 연결하지 않고 push하지 않는다.
9. `git status`가 깨끗한지, `git log --oneline`에 커밋이 있는지 확인한다.
10. 문서를 갱신한다: `ARCHITECTURE_SPEC.md`의 Git 문장, `PROJECT_STATUS.md`의 Git 행과 "다음 작업" 1번, 이 문서의 7절, `WORK_LOG.md`. 갱신분은 두 번째 커밋으로 남긴다.
11. 결과를 표로 보고한다: 커밋 해시, 파일 수, 크기, 6번 검사 결과, 지운 것, 남은 미확인 항목.

그 뒤의 규칙:

- 게임의 단계 통과나 문서 개정처럼 의미 있는 작업 단위마다 커밋한다.
- 커밋하기 전에 `git status`로 게임에서 나온 파일이 섞이지 않았는지 본다. `.gitignore`만 믿지 않는다.
- 이 작업 저장소 자체는 push하지 않는다(원격을 연결하지 않는다). 커밋 작성자에 개인 이메일이 있고 번역 원본이 추적되고 있기 때문이다.
- 프로젝트의 공개 사본은 `python tools/publish_project.py --publish`로만 올린다(2026-11-19 사용자 요청으로 시작). 이 도구는 번역 원본 폴더와 번역표가 든 도구를 빼고, 이메일·계정 식별자·토큰 형식이 없는지 검사한 뒤, GitHub의 비공개 주소(noreply)를 작성자로 해서 `https://github.com/KIMDONGWHEE99/kpatch`에 올린다. 로컬에 커밋한 뒤 실행한다.
- 게임별 패치의 공개는 게임별 전용 절차(`tasks/<게임>/prepare_github.py`, `publish_github.py`)로 한다.
- `working_private`의 번역 폴더는 비공개 영역이라 Git에 들어가지 않는다. 번역은 "지우지 않는다"는 규칙으로 보호한다.

## 참고

- [Claude Code 지침 파일(CLAUDE.md)](https://code.claude.com/docs/en/memory)
- [스킬](https://code.claude.com/docs/en/skills)
- [권한 규칙](https://code.claude.com/docs/en/permissions)
- [훅](https://code.claude.com/docs/en/hooks)
- [MCP](https://code.claude.com/docs/en/mcp)
- [데스크톱 앱의 컴퓨터 유즈](https://code.claude.com/docs/en/desktop)
- [REA 저장소](https://github.com/morluto/rea)
