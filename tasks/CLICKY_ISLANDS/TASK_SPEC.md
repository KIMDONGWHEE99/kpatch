# 작업 명세: CLICKY_ISLANDS 한국어 패치

작성일: 2026-11-19 · 게임: CLICKY_ISLANDS · 후보: `ko_c03` (PCK SHA-256 `1fc45c24e863624a84e3b00c4a99066d895505f438b32fbd87cdb9472f19460e`)

후보 이력: `ko_c01`은 설정 언어 탭의 버튼 배치 결함(QA-01)으로 대체됐습니다. `ko_c02`는 수정 스크립트가 중간에 멈춘 채 만들어져 `ko_c01`과 내용이 같은 폐기 대상입니다. 둘 다 삭제 목록에 있습니다.

공통 절차는 [핵심 지침서](../../docs/KOREAN_PATCH_PLAYBOOK.md)와 [글꼴·실행 검수 참조](../../docs/KOREAN_PATCH_RUNTIME_QA_REFERENCE.md)를 따릅니다. 이 문서에는 이 게임의 값과 예외만 적습니다.

## 1. 목표·현재 요청

- 요청: 2026-11-19 "`D:\steam\steamapps\common\Clicky Islands` 한글패치해줘". 신규 패치입니다.
- 완료할 결과: Steam 빌드 26701014용 한국어 패치. 검증을 통과한 뒤 위 설치본에 적용합니다.
- 방식: 게임에 이미 있는 **빈 한국어 칸(`kr`)** 을 채웁니다. 영어를 덮어쓰지 않으므로 다른 8개 언어는 그대로 고를 수 있습니다.
- 유지하는 것: 게임 제목(Clicky Islands), 제작진 인명·단체명·웹 주소, 각 언어의 자기 이름 표기(ENGLISH 등), 로고(Godot·Karrot Games·Pocketpair Publishing), 로마 숫자, 개발자 명령창(` 키)의 명령어와 진단 문구.
- 공개(GitHub 등) 요청은 없습니다. 개인용입니다.
- 참고: 원작이 `kr` 칸을 비워 둔 채 배포하고 있어, 나중에 공식 한국어가 추가될 수 있습니다. 그 경우 이 패치는 새 빌드에 적용되지 않으며(해시 불일치로 거부) 공식 번역을 쓰면 됩니다.

## 2. 기준선·재현 환경

- Steam 앱 4178790, 빌드 26701014, Windows x64. 엔진은 Godot 4.5.2 stable(실행 기록의 `Engine.get_version_info`), 스크립트는 GDScript 바이트코드 4.5.0(`ebc36a7`), C# 없음. GDExtension으로 GodotSteam을 씁니다.
- 자산 묶음: 별도 파일 `Clicky Islands.pck`, PCK 형식 v3, 항목 5,148개. Addressables에 대응하는 것은 PCK 목록과 `.remap`·`.import` 연결입니다.
- 원본 사본: `source_original/CLICKY_ISLANDS/steam_26701014` (4개 파일, 260,094,232바이트. Steam이 기록한 설치 크기와 같음).
- 기준선 목록: `working_private/CLICKY_ISLANDS/baseline.json`, SHA-256 `876714466e8ff32ca98f035b446e633f45b221eb9e6a67e6c954ff093fb27b5f`.

| 파일 | 크기 | SHA-256 |
|---|---|---|
| `Clicky Islands.exe` | 96,352,256 | `bdf87c9e9e0f9904419890fad8af90e124dc41edac75d73d338ce9a049fe0c65` |
| `Clicky Islands.pck` | 159,505,024 | `9325872cb1415fa2e8ac92821452dd86873357ba3175fd6edd0d68f3c656e19a` |
| `libgodotsteam.windows.template_release.x86_64.dll` | 3,919,872 | `e6ff4bedb9b4481fa0496f1146fe143d53c945c76107ec2fa95578349efce35c` |
| `steam_api64.dll` | 317,080 | `e3fe06e2d802c2f753aeb46869e2af898f34715ce85f08001456fd8a80ecd21e` |

- 도구: Python 3.10.11, fontTools 4.64.0·Pillow 12.3.0(`tools/python_deps`), GDRE Tools 2.6.4(`gdre_tools.exe` SHA-256 `88d6fbcc…78aa9eaf`, 내장 엔진 Godot 4.8-dev). 목록은 [외부 도구 목록](../../tools/THIRD_PARTY_TOOLS.md).
- 글꼴 원본: `tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf` (SIL OFL 1.1, SHA-256 `194018e6…7861e252`). 굵기 400·700 고정판 두 개를 만들어 씁니다.
- 도구는 `tasks/CLICKY_ISLANDS/tools`. PCK 도구는 `AGROMATIC_DEMO`(PCK v3), 기준선·조사·빌드·검수 도구는 `HOW_EMPIRES_WORK`, 문자열 추출기는 `MR_MAGEBOY_DEMO`의 것을 복사해 고쳤습니다. 가장 가까운 게임이 둘로 나뉜 이유는 PCK 형식(v3)과 스크립트 방식(순수 GDScript)이 서로 다른 기존 게임과 맞기 때문입니다.
- 실행 순서: `baseline.py` → `pck_tools.py extract` → `common.py`(GDRE 복원) → `locale_inventory.py` → `census.py` → `classify.py` → `media_census.py` → `fonts.py` → `assemble_translation.py` → `build.py <id> <번역>` → `validate_candidate.py <id>`. 검사기 시험은 `test_checks.py`, `test_validator.py`.
- REA(네이티브 코드 분석): 쓰지 않았습니다. 표시 문구와 저장 경로가 모두 GDScript·자원에서 확인돼 네이티브 질문이 남지 않았습니다.

## 3. 허용 변경·파일 경계

후보에서 원본과 달라도 되는 것은 PCK 안의 아래 8개 항목뿐입니다. exe와 dll 2개는 바꾸지 않습니다. 원본 항목은 PCK 안의 같은 위치에 그대로 두고, 바꾼 항목과 새 목록만 끝에 덧붙입니다.

| 항목 | 변경 |
|---|---|
| `locale/locale.kr.translation` | 빈 한국어 표를 번역으로 채움. 원본 영어 표와 같은 칸 구조(1,132칸)에 직접 문구 46개 추가 |
| `korean_patch/NotoSansKR-Regular.fontdata`, `…-Bold.fontdata` | 새 파일. 한글 글꼴 2개(각 약 6.2MB, 한글 11,172자 전부 포함) |
| `globals/font_locale_resolver/font_locale_resolver.gdc` | 언어가 `kr`일 때 주 글꼴 5종의 대체 글꼴로 한글 글꼴을 연결(일본어·중국어와 같은 방식, 사전에 항목 1개 추가) |
| `globals/game_settings/resolvers/locale_game_settings_resolver.gdc` | Windows 언어가 한국어(`ko`)이고 설정이 `auto`이면 `kr`을 고르는 조건 2줄 추가 |
| `ui/island_naming_ui/island_naming_ui.gdc` | 무작위 섬 이름의 한국어 목록 50개 추가(영어 목록은 그대로) |
| `language_modal.scn`, `settings_window_ui.scn` (`.godot/exported/1323966856/` 아래) | 언어 선택 화면 두 곳에 "한국어" 버튼 1개씩 추가 |

- 금지: 게임 규칙·수치·저장 형식·업적 조건·Steam 연동. 저장 파일에 쓰이는 식별자는 하나도 바꾸지 않았습니다(번역은 표시 단계의 언어표에서만 일어남).
- 검수 사본에만 넣는 변경: `godot_steam.gdc`의 Steam 초기화 건너뛰기, `korean_patch_qa/qa_driver.gdc`, `project.binary`의 앱 이름·저장 폴더 이름·자동 실행 1개. `prepare_qa.py`가 `qa_boundary.json`에 기록합니다.
- 경로: 원본 `source_original/CLICKY_ISLANDS`, 추출 `extracted_private/CLICKY_ISLANDS`, 작업·증거 `working_private/CLICKY_ISLANDS`, 후보 `build_candidate/CLICKY_ISLANDS/<id>`.

## 4. 조사·번역 계획과 결과

| 계층 | 조사 범위·도구 | 결과 |
|---|---|---|
| 언어표·언어 칸 | `locale.*.translation` 10개(압축 언어표). 이 형식은 키 이름을 저장하지 않으므로 **칸 위치**(해시 표 칸:원소)를 기준으로 삼음. `locale_inventory.py` | 영어 표 1,132칸 = 문구 있는 칸 1,078 + 빈 칸 54. 키 이름을 아는 칸 1,043, 모르는 칸 89(그중 문구 있는 칸 35). 모르는 칸도 위치로 번역함 |
| 장면·자원의 직접 문구 | 복원한 `.tscn` 553·`.tres` 799. `census.py`, `classify.py` | 아래 분류 표 |
| 스크립트 문자열 | 복원한 `.gd` 583 전부. 복원 실패 0 | 아래 분류 표. 키를 실행 중 조합하는 곳 1건 확인(`"GAME_TAG_NO_" + 태그`) |
| 표시 enum | 로마 숫자 변환표, 지형 종류 키 | 유지 또는 언어표 칸 |
| 런타임 조합·서식 | `{goal}` 같은 자리표시자, `%d:%02d` 서식, BBCode 조각 | 번역문에서 이름·개수 보존 검사 |
| 개발·예비 화면 | 개발자 명령창(`addons/console`, `game_console.gd`), 시험 장면(`levels/tests`), 편집기 플러그인 2개 | 명령창은 유지, 나머지는 게임에 나오지 않음 |
| 이미지·영상 | PNG 245·SVG 5·OGV 57. `media_census.py` | 이미지 250개 전부 확인. **영상 57개는 미확인** |

문자열 62,508개의 분류(2026-11-19): `INTERNAL` 62,017 · `VISIBLE_KEEP` 379 · `VISIBLE_TRANSLATE` 112 · `UNKNOWN` 0. 추출 오류 0건. 규칙으로 확정하지 못한 229종은 `working_private/CLICKY_ISLANDS/census/manual_decisions.json`에 값별 판정과 근거를 적었습니다.

- 공식 번역 원본: `working_private/CLICKY_ISLANDS/translation/canonical.json` (SHA-256 `4417be12…4fcf2549`). 작업 파일은 같은 폴더의 `ko_001~005.txt`, `ko_fix.txt`, `direct_ko.json`, `island_names_ko.json`이며, 고칠 때는 `ko_fix.txt`나 `direct_ko.json`을 고친 뒤 `assemble_translation.py`를 다시 돌립니다.
- 위치 ID: 언어표는 `locale/locale.en.translation::<표 칸>:<원소>`, 직접 문구는 `<복원 파일>::<문자열 순번>`.
- 번역량: 고유 원문 977개(칸 1,078개), 직접 문구 46개(그중 11개는 같은 영어 문구의 언어표 번역을 재사용), 섬 이름 50개.
- 직접 문구의 처리: 장면에 영어가 그대로 적힌 문구는 **그 영어 문구 자체를 키로** 한국어 표에 넣었습니다. Godot는 화면 글자를 표시할 때 언어표를 먼저 찾아보므로 장면을 고치지 않고도 번역됩니다. 표시 여부를 정적으로 확정하지 못한 자리 채움 글자도 낱말이 있으면 번역해 두었습니다.
- 용어: Reputation 명성, Gold 골드, Amber 호박, Fossil 화석, Artifact 유물, Blessing 축복, Perk 특성, Challenge 도전 과제, Task 임무, Unit 유닛, Comfort 안락도, Click strength 클릭 강도, Ruins 유적, Cauldron 가마솥, Run 회차, Spawn(유닛) 고용. 섬 단계는 야영지·정착지·마을·소도시·도시·수도·왕국. 설명문은 합쇼체, 버튼은 명사형.
- 원작에 없는 키: 언어표에 칸이 없는 키 24종이 장면·자원에 남아 있습니다. 뜻을 알 수 있는 10종(`UI_STATS_*` 등)은 직접 문구로 번역했고, 원문을 알 수 없는 14종(`UI_SLOP_MACHINE_*`, `ACHIEVEMENT_CELEBRITY_*` 등)은 원작과 같이 둡니다.

### 미디어

- 이미지 250개: 검수판 6장과 SVG 변환판을 제작자가 직접 확인. `NO_TEXT` 243, `KEEP` 7(로고 6, 참조가 없는 화면 예시 그림 1).
- 영상 57개: 프레임 추출 도구가 없어, 검수 실행(`c03_a`)에서 기본 영상 21개를 2배 크기 격자로 재생해 세 시점의 프레임을 직접 판독했습니다. 영상은 280×120 크기, 2~11초짜리 조작 시연입니다.
  - `KEEP` 12: **영어 화면을 녹화한 튜토리얼 시연 영상.** 9개에서 영어 글자(건물 이름, `Build`·`Close`, `TAKE CHALLENGE` 등)를 봤고, 3개(`reset`·`fossil`·`next`)는 표본에서는 못 봤지만 원작이 일본어·중국어용 변형을 따로 둔 영상입니다. 한국어 화면으로 다시 녹화하는 일은 이번 범위 밖입니다. 원작도 독일어·폴란드어·스페인어·포르투갈어에서 같은 영상을 씁니다. 영상 옆의 설명문과 목표는 한국어로 나옵니다.
  - `KEEP` 36: 일본어·중국어 전용 변형. `kr`에서는 재생되지 않습니다(`tutorial_resource.gd`가 언어 코드로 찾고 `kr` 항목이 없음). 직접 보지는 않았습니다.
  - `NO_TEXT` 9: 숫자·아이콘뿐인 영상 7개와 인트로 영상 2개(세 시점 표본).
  - 영상 처리 `UNKNOWN`은 0건입니다.
- 소리 173개: 픽셀 문구가 없어 `NOT_APPLICABLE`. 음성 대사 여부는 청취하지 않았습니다(폴더는 효과음·음악·동물 소리).

## 5. 글꼴·제작자 실행 계획

- 게임은 주 글꼴 5종(Cabin 보통·굵게, Merriweather 굵게, Thin Sans, Harmonic)에 언어별 대체 글꼴을 실행 중에 연결합니다. 원본은 일본어·중국어만 연결하고, Cabin·Merriweather는 시스템 글꼴 대체가 꺼져 있어 한국어가 그대로는 깨집니다. 그래서 `kr` 항목을 추가했습니다.
- 필요 문자: 후보 표에 실제로 든 문자 838종(한글 음절 포함). 주 글꼴 5종 각각에 대해 "주 글꼴 또는 한글 글꼴에 있음"을 fontTools로 확인, 누락 0.
- 주 글꼴 밖 사용처: `GillSansBold`가 2곳(떠오르는 숫자 `floating_text.tscn`, Steam 찜 버튼 `steam_button.tscn`)에 쓰입니다. 여기는 한글 글꼴을 직접 연결하지 않았고 이 글꼴은 시스템 글꼴 대체가 켜져 있습니다. 찜 버튼의 번역(`찜하기:`)이 시스템 글꼴로 나오는지 **G5에서 확인합니다.**
- 저장 위치: `%APPDATA%\Karrot Games\Clicky Islands` (설정 `settings_demo_1_3_6.ini`, 저장 `saves\<SteamID>_full_save_game_1_0_0.bin`, 키 설정, 로그). 검수 때는 `APPDATA`·`LOCALAPPDATA`를 검수 폴더로 바꾸고 저장 폴더 이름도 `ClickyIslands_KoreanQA/<실행 ID>`로 바꿉니다. Steam은 검수 사본에서 초기화하지 않습니다.
- 실행 전후 비교 대상: `%APPDATA%\Karrot Games`, `%APPDATA%\Godot\app_userdata\Clicky Islands`, `D:\steam\userdata\*\4178790`·`4401470`.
- 실행 경로 확인: 검수 코드가 `OS.get_executable_path()`와 저장 폴더를 상태 파일에 적고, `launch_qa.py`가 exe·PCK 해시를 기록합니다.
- 창: 1920×1080, 포커스 없이 띄우고(`SW_SHOWNOACTIVATE`) 화면 오른쪽 밖에 대부분을 둡니다. 소리 장치는 Dummy. 기본 설정이 전체 화면이므로 검수 폴더에 `fullscreen=false` 설정 파일을 미리 넣습니다.

| 필수 화면군 | 제작자 진입 방법 | 결과(2026-11-19, 실행 `c01_a`·`c03_a`) |
|---|---|---|
| 로고·첫 화면·언어 선택 | 첫 실행 흐름 | 확인. 한국어 자동 선택, 한국어 버튼 |
| 설정(5개 탭)·언어 전환·조작 설정·제작진 | 검수 코드로 설정 창과 탭 열기 | 확인. 일본어→영어→한국어 전환과 글꼴 재연결 포함 |
| 새 게임(섬 이름 짓기)·이어하기 | 첫 실행, 저장 파일을 넣고 재실행 | 확인. 누적 진행(튜토리얼 50/50)이 이어짐 |
| HUD·건설 패널·툴팁 | 개발자 명령으로 자원 지급, 창 안쪽 마우스 이동 이벤트 | HUD·도로 툴팁·건물 카드 확인. 자원 툴팁·큰 숫자 알림은 미도달 |
| 튜토리얼(영상 포함)·임무 편지 | 튜토리얼 패널, `open_task` | 1단계와 항해 화면 1단계, 사과 임무 편지 확인. 2단계 이후 진행은 미도달 |
| 항구·시장·가마솥·허수아비·화산 | 미니맵 내부 클릭, `Game.open_scarecrow_window` | 항구(창고·배 화물), 허수아비와 당첨 창, 섬 단계 상승 창 확인(`c03_b`). 시장·가마솥·화산은 **미도달** |
| 항해 화면(특성·화석·유물·도전 과제·통계) | `Game.load_transition` | 확인. 통계 탭은 상태 덤프만(육안 아님) |
| 결과·종료·축복 선택 | `show_finish_modal`, `add_blessing`, 출항 버튼 | 확인. 섬 떠나기 확인 창 포함 |

검수 기록: `working_private/CLICKY_ISLANDS/qa/c03_a/qa_ledger.json`. 화면에서 글자 그대로 확인한 번역문은 이 방식으로 셀 수 있는 고유 번역 702개 가운데 176개입니다(고유 문구 977개 중 자리표시자가 들어 실행 중 값이 채워지는 문구 등은 글자 그대로 대조할 수 없어 분모에서 뺌). 미도달 화면은 미검증으로 남깁니다. 목록은 검수 기록의 `unreached_screens`에 있습니다.

## 6. 게이트별 상태

| ID | 상태 | 실제 검사 | 증거 |
|---|---|---|---|
| G0 | PASS | 설치본 4개 파일 복사·3중 해시 일치, Steam 설치 크기와 합계 일치, PCK 항목 5,148개 MD5 전부 확인 | `baseline.json`, `extracted_private/CLICKY_ISLANDS/steam_26701014/pck_manifest.json` |
| G1 | PASS | 무변경 재저장이 원본과 바이트 동일. 번역 5칸·직접 문구 1개·섬 이름 3개·글꼴·스크립트 3개·장면 2개를 넣은 `risk_01`을 실제 게임(4.5.2, RTX 4060 Ti, Forward+)에서 실행. 한국어 자동 선택, "한국어" 버튼, 한글 표시, 빈 칸의 영어 대체, 한국어 섬 이름 확인. 저장 격리·실행 경로 일치·사용자 저장 무변경 | `working_private/CLICKY_ISLANDS/qa/risk_01_a` (상태 4건, 캡처 4장, `exit.json`) |
| G2 | PASS | 문자열 62,508개 분류 `UNKNOWN` 0, 추출 오류 0. 미디어 480개 처리 `UNKNOWN` 0(이미지 250개와 기본 영상 21개는 직접 확인, 다른 언어 전용 영상 36개는 코드 근거로 유지). 튜토리얼 영상 12종은 영어 화면 그대로 유지 | `census/strings.json`, `census/manual_decisions.json`, `media/media_review.json` |
| G3 | PASS | 칸 1,078·직접 46·섬 이름 50 번역. 자리표시자·태그 종류/속성/짝/중첩·줄바꿈·`%` 검사 0건. 검사기 결함 주입 10종 검출 | `translation/canonical.json`, `translation/problems.json`(빈 목록) |
| G4 | PASS (`ko_c03`) | 후보를 다시 풀어 대조. V1 파일 경계(변경 6·추가 2·무변경 5,142 동일), V2 칸 1,078 일치·빈 칸 54 유지, V3 직접 문구 46 일치, V4 스크립트 3개(추가 줄만), V5 장면 2개(버튼만 추가), V6 글꼴 누락 0. 결함 주입 후보(칸 교환·빈 번역·직접 문구 변경)는 FAIL로 검출. `ko_c01`의 같은 검사도 PASS였고 `ko_c03`은 장면 1개의 버튼 위치만 다름 | `working_private/CLICKY_ISLANDS/ko_c03/verify/validation_report.json`, `validator_selftest.json` |
| G5 | PASS (필수 화면군 7종의 대표 화면) | 실제 그래픽 실행 4회(원본 `base_a`, 후보 `c01_a`·`c03_a`·`c03_b`). 저장 격리·실행 경로·후보 해시 확인, 사용자 저장 전후 동일. 로그 오류는 원본과 같은 종류(종료 시)뿐, 글리프·로딩 오류 0. 상태 덤프의 글꼴 누락 글자 0. 결함 1건(QA-01) 수정 후 재확인. 화면에서 글자 그대로 확인한 번역문 176/702. 시장·가마솥·화산, 후반 단계 건물 화면, Steam 찜 버튼의 한글 표시(GillSans)는 미도달 | `working_private/CLICKY_ISLANDS/qa/c03_a/qa_ledger.json`, 각 실행의 `states`·`sheets` |
| G6 | PASS | 후보 목록을 고정하고 G2~G5 증거를 같은 지문에 연결(`freeze_gate.py`). 차이 파일 정방향 복원 = 후보 해시, 역방향 복원 = 원본 해시. ZIP 내용 11개가 허용 목록과 일치. 복원 검증 파일은 해시 기록 뒤 삭제 | `working_private/CLICKY_ISLANDS/release_gate/ko_c03/gate.json`, `package_1.0.0_r1/package.json` |
| G7 | PASS | 최종 ZIP(`baf36898…f4962907`)에서 꺼낸 설치기로 41건: PASS 38, 해당 없음 3. 정상 7, 거부 11, 중간 실패·복구 18, 실행 중 거부 1, 라이브러리 탐색 1. 합성 3파일 시험 49건 PASS. 사례가 끝나는 대로 게임 사본 19개 삭제(PROC-10 반영) | `package_1.0.0_r1/installer_tests.json`, `installer_synthetic_01/synthetic_summary.json` |
| G8 | PASS | ZIP 밖 결과 보고서 작성, 미해결 차단 항목 0. 사용자 지시("설치해 줘")로 2026-11-19에 실제 설치본에 적용: 설치기 종료 코드 0, 설치된 4개 파일이 후보 `ko_c03`과 해시 일치, 추가 파일 없음, 사용자 저장 전후 동일, 원본 백업이 기준선과 일치(`install_1.0.0_r1/install.json`). 설치 후 Steam 실행은 NOT_RUN | [결과 보고](../../validation/CLICKY_ISLANDS/ko_1.0.0/RESULT_REPORT.md) |

- G5는 대표 화면 검증이며 전체 회차·모든 건물·모든 분기를 본 것이 아닙니다. 미도달 화면을 "확인함"으로 쓰지 않습니다.
- 입력이 바뀌면: 번역 원본이 바뀌면 G3·G4와 그 뒤 전부, 원본 빌드가 바뀌면 G0부터 다시 합니다.
- 적용되는 PROC: PROC-10(설치 시험 사본 삭제)은 G7 도구에 반영 예정. PROC-09(문구별 자동 재적용)는 이 게임에서 시험하지 않았습니다. 다만 번역 원본이 칸 위치·키·원문 지문과 연결돼 있어 재사용 후보 산출은 가능합니다.
- 로그: 종료 시 `Parameter "data.tree" is null`과 자원 누수 경고가 나옵니다. 원본 검수 사본에서도 같은 종류가 나와(원본 7건, 후보 8건) 패치 고유 오류가 아닙니다. 글리프 누락 경고와 자원 로딩 오류는 0건입니다.
- 관찰: 한글은 줄바꿈이 낱말 중간에서 일어납니다(Godot의 기본 한글 줄바꿈). 읽는 데 지장은 없어 그대로 두었습니다.

## 7. 배포·중단·인수인계

- 지원 상태: 위 해시의 원본 4개 파일. 다른 해시(게임 업데이트 포함)에는 적용하지 않습니다.
- 배포 허용 파일(예정): 설치·제거기, 차이 파일, 안내문, 글꼴 라이선스(OFL). 원본 게임 자산·검수 코드는 넣지 않습니다.
- 차단 조건: 기대 번역 불일치, 글꼴·실행·저장 오류, 만료된 증거, 패키지 손상.
- 정리(2026-11-19, 사용자 승인 뒤 삭제, 2,437MB 확보): 이전 후보 `build_candidate/CLICKY_ISLANDS/risk_01`·`ko_c01`·`ko_c02`, 검수용 게임 사본 `working_private/CLICKY_ISLANDS/qa/{risk_01_a,base_a,c01_a,c03_a,c03_b}/game`, 무변경 재저장 시험본 `risk_probe/noop`, 설치 시험의 `package_1.0.0_r1/tests/추가 Steam 라이브러리`. 해시·build 기록, 캡처·로그·검수 기록, 시험 결과, `risk_probe/noop_report.json`은 남겼습니다. 남은 사본은 원본 `source_original/CLICKY_ISLANDS`(248MB), 추출 자료 `extracted_private/CLICKY_ISLANDS`(481MB), 최신 후보 `ko_c03`(256MB)입니다. 지운 후보와 검수 사본은 `build.py`·`prepare_qa.py`로 다시 만들 수 있습니다. 다만 자원 저장 결과가 실행마다 조금 달라 PCK 해시는 같지 않을 수 있습니다(같은 입력의 `ko_c01`과 `ko_c02`가 서로 다른 해시였음).
- 배포 산출물: `release_output/CLICKY_ISLANDS_KOREAN_PATCH_1.0.0_r1.zip`(7,998,169바이트, SHA-256 `baf36898ebc314a6a1ab7cfc84bd6eb995f46a6697c11cdbe4ba6064f4962907`)과 같은 내용의 폴더.
- 수행: Claude Code, 2026-11-19.
