# PROFITS2167 작업 데이터

현재 공통 기준은 [핵심 지침서](../../docs/KOREAN_PATCH_PLAYBOOK.md), 통합 상태는 [PROJECT_STATUS](../../PROJECT_STATUS.md)입니다. 아래는 0.5.1 보유 자료 안내이며 새 기준 통합 재검증은 수행하지 않았습니다. [최종 보고서](../../docs/PROFITS2167_최종_보고서.md)와 [검증 요약](../../validation/PROFITS2167/VALIDATION_SUMMARY.md)의 실행 QA는 `NOT_RUN`입니다.

이 폴더에는 재현 가능한 도구와 공개 가능한 작업 안내만 둡니다.

- `tools/`: 추출, 번역 병합, 메타데이터 수정, 감사, 릴리스, 설치기 QA 도구
- `release_metadata/`: 최종 설치기 설명, 해시, 매니페스트
- `HANDOFF_MANIFEST.json`: 전달 파일과 원본 위치를 기록한 기계 판독용 목록

원문 파생 데이터와 후보 게임 자산은 각각 `working_private`, `extracted_private`, `build_candidate` 아래에서 관리하며 Git에 커밋하지 않습니다.

현재 배포 기준은 v0.5.1입니다. `정적 텍스트 전수 검사 통과`와 `실제 전 구간 플레이 검수 완료`는 서로 다른 상태이므로, 후속 문서에서도 둘을 구분해 표현해야 합니다.
