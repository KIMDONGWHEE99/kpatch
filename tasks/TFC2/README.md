# TFC2 한국어 패치

Steam 빌드 `25097525`, Unity `6000.2.9f1`, IL2CPP, Addressables `2.7.4` 대상이다. 원본은 `source_original/TFC2_BUILD_25097525`에 보존한다.

1.0.0의 정적 검사·글꼴 참조·메타데이터 재분석·설치 시험·대표 흐름 그래픽 실행 기록이 있다. 전체 캠페인과 분기를 끝까지 플레이한 검증은 아니다. 현재 공통 기준은 [핵심 지침서](../../docs/KOREAN_PATCH_PLAYBOOK.md), 통합 상태는 [PROJECT_STATUS](../../PROJECT_STATUS.md)이며 새 기준 통합 재검증은 수행하지 않았다.

- [작업 명세](TASK_SPEC.md)
- [정적 검사](../../validation/TFC2/candidate_static_validation.json)
- [실행 검수와 저장 격리](../../validation/TFC2/runtime_qa_report.json)
- [당시 최종 결과](../../validation/TFC2/final_release_validation.json)
- [설치기 시험](../../validation/TFC2/installer_qa_report.json)
- 배포 파일: `release_output/TFC2_The_Fertile_Crescent_2_Korean_Patch_v1.0.0.zip`

미디어 기본 분류·설치 실패 복구 등 공통 개선은 [작업 목록](../../docs/PROCESS_IMPROVEMENT_BACKLOG.md)에서 추적한다. 기존 보고서의 PASS를 새 게이트 통과로 자동 승격하지 않는다.
