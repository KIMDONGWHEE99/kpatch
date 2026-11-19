# 현재 대화의 REA·Ghidra 연결 복구 결과

2026-10-31. 사용자 요청에 따라 연결 설정을 수정하고 **현재 대화에서 REA를 직접 호출하여 Ghidra 실제 분석을 확인했습니다. 결과는 PASS입니다.** 별도 PowerShell REA 실행기의 성공을 대화 연결 성공으로 대신하지 않았습니다.

## 변경 사항

- `C:\Users\PC\.codex\config.toml`의 REA 환경에 Ghidra·Java와 TEMP/TMP 경로를 추가했습니다.
- 기존 영문 경로 Ghidra 사본을 `C:\Users\PC\AppData\Local\REA\toolchains\ghidra_12.1.4_PUBLIC`로 이동했습니다. 같은 드라이브에서 이동했고 핵심 도구 4개의 내용 지문이 일치합니다. 새 설치나 추가 대용량 복사는 하지 않았습니다.
- 기존 Java 21.0.12.1을 재사용하며, 분석 임시 폴더는 `C:\Users\PC\AppData\Local\REA\runtime`입니다. Windows 전체 환경값을 바꾸지 않았습니다.
- 앱의 MCP 설정에서 연결을 다시 시작했습니다. 실제 REA 서버 시작 시각은 2026-10-31 16:51:39 한국 시간으로 바뀌었고 Ghidra 12.1.4가 사용 가능 상태를 반환했습니다.
- 기존 실행 명령·REA 6.8.0·호출 제한과 다른 설정은 유지했습니다. 재시작을 위한 사용 상태 전환 후 REA는 활성화 상태입니다.

원본 설정 백업: `C:\Users\PC\.codex\config.toml.before-rea-ghidra-20261031.bak`. SHA-256: `7084c12f038cf35face1e9b91d638e8e4ff393a5fa454721d97aee82dbae25b4`.

## 실제 분석 확인

MSVC로 직접 작성한 작은 C 예제를 64비트와 32비트 DLL로 만들었습니다. 게임 파일을 복사하거나 게임을 실행하지 않았습니다.

| 확인 항목 | 결과 |
|---|---|
| Ghidra·Java·분석 실행 파일 인식 | PASS — Ghidra 12.1.4, JDK 21.0.12.1 |
| 64비트 `calculate_total` 함수 복원 | PASS — `apply_discount` 호출 후 배송비를 더하는 동작과 호출 대상 확인 |
| 64비트 `apply_discount` 함수 복원 | PASS — 할인 사용 여부·양수 가격 조건 및 80/100 계산, 호출자 확인 |
| 32비트 두 함수 복원 | PASS — 같은 조건·계산·호출 관계 확인 |
| 분석 전후 대상 파일 | PASS — 파일 지문 동일 |
| REA 외 설정 | PASS — 백업과 대조하여 내용 무변경 확인 |
| 분석 종료 | PASS — 증거와 재사용용 기록 저장, 열린 대상·정리 대기 없음 |

최초 함수 분석은 64비트 약 62.65초, 32비트 약 55.44초였습니다. 같은 64비트 분석을 재사용한 다음 함수 조회는 약 0.065초였습니다. 이번 작은 예제에서 측정한 호출 시간이며 다른 게임의 처리 속도를 보장하는 수치는 아닙니다.

Ghidra가 복원한 32비트 코드에서는 `calculate_total`이 `apply_discount`를 호출해 반환값에 세 번째 인수를 더하고, `apply_discount`는 두 번째 인수가 참이며 가격이 양수일 때 가격의 80%를 반환했습니다. 원래 예제 코드와 일치합니다. 이 검사는 실제 역분석 결과 확인이며 모든 게임·파일 형식의 지원 또는 게임 실행 QA 완료를 뜻하지 않습니다.

예제 지문:

- x86-64, 2,560바이트: `31d0091bf2a9b656effb70da68078107b726f2532ceafca68c4f1970f3210789`
- x86, 1,536바이트: `5966ff607c6230eea09a0f2f2671cea87da823b19db3a6253ede27879f693b1b`

비공개 근거는 `working_private/REA_GHIDRA_20261031/`의 `configuration_change.json`, `connection_validation.json`, `final_integrity.json`, `probe_x64_evidence.json`, `probe_x86_evidence.json` 및 두 분석 스냅샷에 있습니다. 원시 근거에는 제공자 이름·버전·대상 지문·복원 코드·호출 관계가 포함됩니다.

설정 방식은 [OpenAI 공식 MCP 문서](https://learn.chatgpt.com/docs/extend/mcp)를, Windows 분석 조건은 [REA 공식 안내](https://github.com/morluto/rea/blob/main/docs/windows-ghidra-p0.md)를 참고했습니다. 실제 성공 판정은 문서상의 지원 여부가 아니라 위 직접 호출 결과를 근거로 했습니다. [프로젝트 사용 지침](../../docs/REA_IN_CHAT_WORKFLOW.md).
