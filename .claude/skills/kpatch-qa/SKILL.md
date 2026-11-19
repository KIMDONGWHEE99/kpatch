---
name: kpatch-qa
description: 한글패치 후보의 화면 검수(G5)를 할 때 쓴다. 컴퓨터 유즈나 마우스·키보드 입력 없이, 게임 안에 넣은 검수 코드와 내부 캡처로 화면을 확인하고 저장 격리와 실행 경로를 검증한다.
argument-hint: "[게임 ID] [후보 ID]"
---

# 화면 검수 (G5)

대상: $ARGUMENTS

통과 기준은 `docs/KOREAN_PATCH_PLAYBOOK.md` 7절과 `docs/KOREAN_PATCH_RUNTIME_QA_REFERENCE.md` 4~6절이다. 이 스킬은 조작 방법을 정한다.

## 지킬 것

- 컴퓨터 유즈, 입력 주입(`SendInput`, `mouse_event`, `keybd_event`, `SendKeys`), 창을 앞으로 가져오기(`SetForegroundWindow`)를 쓰지 않는다. `send_game_key.ps1`, `click_game_window.ps1`, `send_game_input.ps1`은 실행이 차단돼 있다.
- 사용자의 저장 파일, 설정, Steam 클라우드, 업적을 건드리지 않는다.
- 접근하지 못한 화면은 미검증으로 남긴다. 사용자에게 대신 플레이해 달라고 하지 않는다.

## 순서

1. 검수 사본 준비: 여유 공간을 확인한 뒤 후보를 검수 폴더로 복사한다. 후보와의 차이(검수 코드, 제품명, 로그 위치)를 파일·객체 수준으로 기록한다.
2. 저장 격리: 실제 쓰기 위치(저장, 설정, 레지스트리, 로그, Steam 사용자 데이터)를 조사하고 검수 전용 위치로 돌린다. 실행 전에 사용자 저장의 목록·크기·해시를 기록한다.
3. 검수 코드 삽입: 게임 안에서 요청 파일을 읽어 화면 이동과 메서드 호출을 하고, 게임 화면을 PNG로 직접 저장하게 한다.
   - Godot: `tasks/HOW_EMPIRES_WORK/tools/`의 `qa_driver.gd`, `prepare_qa.py`, `launch_qa.py`, `qa_control.py`. 화면은 `get_viewport().get_texture().get_image().save_png()`으로 저장한다.
   - Unity: `tasks/KINGDOM_INC_DEMO/tools/KoreanQA/Driver.cs`. 화면은 `ScreenCapture.CaptureScreenshot()`으로 저장한다.
4. 실행: 창 모드, 고정 해상도, 소리 끔, 포커스를 가져가지 않는 창으로 띄운다. `launch_qa.py`처럼 `STARTUPINFO.wShowWindow = 4`를 쓴다. 최소화하지 않는다. 화면 갱신이 멈출 수 있다.
5. 실행 확인: 프로세스의 실제 경로가 검수 사본인지 확인한다. Steam이 설치본을 띄웠으면 즉시 종료하고 저장 영향을 확인한다.
6. 화면 수집: 지침서 7절의 필수 화면군 표를 따라 요청 파일로 화면을 옮기며 캡처한다.
7. 판독: 캡처 PNG를 Read 도구로 직접 열어 네모 글자, 깨진 자모, 잘림, 겹침, 태그 노출을 본다. 파일이 있다는 사실만으로 통과시키지 않는다. 로그의 글리프 누락 경고와 패치 고유 로딩 오류가 각각 0건인지 확인한다.
8. 마무리: 게임을 종료하고 사용자 저장의 전후 해시를 비교한다. 검수용 게임 사본은 삭제 목록에 올린다. 캡처, 로그, 요청·응답 기록, 보고서는 남긴다.

## 내부 검수 코드를 넣을 수 없는 게임

멈추고 이유를 사용자에게 설명한다. 사용자와 시간을 정한 뒤 AGENTS.md의 "화면 검수 진행 방식"으로 진행한다. 사용자가 화면을 옮기고, 제작자는 창 캡처와 판독만 한다. 이 프로젝트에서는 컴퓨터 유즈가 설정으로 차단돼 있다. 사용자가 자리를 비운 동안의 화면 조작을 원하면 사용자가 직접 설정을 바꿔야 한다고 알린다.

## 기록

화면군별 접근 방법, 관찰 결과, 캡처 해시, 미도달 화면을 `templates/QA_LEDGER_TEMPLATE.yaml` 형식으로 남긴다. 관찰 범위는 분모와 함께 쓰고, 첫 화면·대표 흐름·전체 분기를 구분한다.
