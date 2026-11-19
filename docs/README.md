# 문서 안내

## 현재 기준

| 문서 | 역할 | 읽는 시점 |
|---|---|---|
| [핵심 지침서](KOREAN_PATCH_PLAYBOOK.md) | 공통 절차·G0~G8·증거·완료 기준의 원본 | 최초 적용, 절차 변경 시 |
| [AGENTS.md](../AGENTS.md) | 작업자가 항상 지킬 요약 | 작업 시작 시 |
| [현재 상태](../PROJECT_STATUS.md) | 게임별 현재 요약·다음 작업 | 재개 시 |
| [런타임 QA 참조](KOREAN_PATCH_RUNTIME_QA_REFERENCE.md) | 글꼴·실제 화면·저장 격리의 상세 검사와 사고 사례 | 새 한글화 작업 전, 관련 결함 수정 시 |
| [파일 구조](../ARCHITECTURE_SPEC.md) | 원본·작업·증거·배포 경계 | 경로 설정·이전·공유 전 |
| [개선 작업 목록](PROCESS_IMPROVEMENT_BACKLOG.md) | 평가에서 발견한 코드 결함과 수정 완료 조건 | 해당 도구 사용·수정 전 |
| [현재 대화에서 REA 사용](REA_IN_CHAT_WORKFLOW.md) | 연결된 REA를 필요한 코드 질문에만 호출하는 방법·준비 상태·재평가 기준. Codex 기준으로 쓰였으며 Claude Code의 연결 절차는 설정 안내 4절 | REA가 필요한 단계, 연결·분석 엔진 문제 발생 시 |
| [Claude Code 설정 안내](CLAUDE_CODE_SETUP.md) | Claude Code 설정 파일, 첫 실행 점검, REA 재연결, 예전 폴더와의 관계 | Claude Code 설정을 바꾸거나 점검할 때 |
| [CLAUDE.md](../CLAUDE.md) | Claude Code가 세션마다 읽는 지침. AGENTS.md를 불러오고 Claude Code 전용 규칙을 더함 | 세션 시작 시 자동으로 읽힘 |

현재 요청 → 작업 지침과 핵심 지침서 → 게임별 명세의 순서로 적용 범위를 정합니다. 게임별 명세는 더 구체적인 입력과 검수 범위를 채우며, 근거 없이 필수 검사를 줄이지 않습니다. 서로 다른 지시가 있으면 현재 사용자 요청에 맞춰 정리하고 실제로 필요한 정보만 확인합니다.

## 양식과 기록

- [작업 명세](../tasks/TASK_SPEC_TEMPLATE.md): 작업 전 입력·허용 변경·단계·실행 계획.
- [게임 설정](../templates/GAME_CONFIG_TEMPLATE.yaml): 경로·기준선·번역·도구·증거의 값.
- [검증 기록](../templates/QA_LEDGER_TEMPLATE.yaml): 항목별 분류·추출 오류·화면·검사 증거의 형식.
- [결과 보고](../templates/RESULT_REPORT_TEMPLATE.md): 수행 범위와 게이트 결과, 복구·인수인계.
- [작업 이력](../WORK_LOG.md): 언제 무엇이 바뀌었는지 기록. 현재 상태의 대체 자료가 아님.

양식은 작성 계약입니다. 빈 양식과 선언된 정책만으로 자동 검사나 게임 검증이 구현됐다고 보지 않습니다.

## 과거 근거

- [2026-11-16까지의 상태 문서 전문](history/PROJECT_STATUS_until_2026-11-16.md): 날짜별 경과 요약. 현재 상태 문서를 게임별 표로 줄이면서 옮겼습니다.
- [2026-10-31 Soulash 2 REA 효과와 비용 평가](REA_VALUE_REVIEW_2026-10-31.md): 이전 패치와의 차이, 보존된 시간·토큰 기록, 실제 기여와 다음 작업의 사용 기준.
- [2026-09-05 프로젝트 평가](PROJECT_REVIEW_2026-09-05.md): 코드 검토와 격리 재현 결과. 당시 상태를 보존합니다.
- [PROFITS2167 최종 보고서](PROFITS2167_최종_보고서.md), [인수인계](PROFITS2167_인수인계.md): 초기 누락과 사용자 테스트 의존 문제의 경과.
- [구 V2 프레임워크](../templates/PROFITS2167/GAME_KOREAN_PATCH_V2_CODEX_DEVELOPER_PROMPT_KO.md): 설계 출처를 보존한 역사 자료. 신규 작업의 실행 지침으로 적용하지 않습니다.

규칙 변경은 핵심 지침서를 먼저 수정하고 AGENTS·양식과 충돌하는지만 확인합니다. 게임 결과는 해당 빌드 보고서에 쓰고 현재 상태에는 링크와 핵심 한계만 반영합니다. 중요한 새 설계 결정은 근거·되돌리는 방법을 WORK_LOG에 남기며, 별도 설명이 필요할 때만 ADR 문서를 추가합니다.
