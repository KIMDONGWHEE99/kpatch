# PROFITS2167 실무 인수인계

> 아래는 0.5.1 당시 인수인계 자료입니다. 새 작업에서는 [핵심 지침서](KOREAN_PATCH_PLAYBOOK.md)와 [현재 상태](../PROJECT_STATUS.md)를 먼저 확인합니다. 기존 경로와 해시는 재확인하며, 현재 요청에서 허용된 격리 검수를 다시 승인받을 필요는 없습니다.

## 당시 상태

- 최종 패치 버전: `0.5.1`
- 게임 빌드: `V0.23.8.12`
- Unity: `2022.3.62f3`
- IL2CPP 메타데이터: `31.1`
- 게임 빌드 GUID: `ef70fc61842a4a7e88293bd7daf7bd9f`
- 최종 ZIP SHA-256: `0326e80cf6eaf4d1bc96e0921392750e991dd2e7fe6d15169e9216cd3611e244`

## 중요 경로

- 새 프로젝트: `C:\Users\PC\Documents\ChatGPT\한글패치`
- 기존 작업 원본: `C:\Users\PC\Documents\Codex\2026-08-28\dl\work\profits2167_ko`
- 게임: `D:\steam\steamapps\common\PROFITS2167`
- 최종 패치: `release_output\PROFITS2167_Korean_Patch_v0.5.1.zip`
- 재현 도구: `tasks\PROFITS2167\tools`
- 번역 데이터: `working_private\PROFITS2167\translation_data`
- 전체 감사 자료: `extracted_private\PROFITS2167\audit`

## 저작권과 Git 경계

`source_original`, `build_candidate`, `extracted_private`, `working_private`, `backups`, `quarantine`는 Git에서 제외됩니다. 원본 게임 자산이나 재구성된 전체 자산을 `release_output` 또는 Git 추적 영역으로 옮기지 마십시오.

최종 배포 ZIP은 원본 파일을 포함하지 않고 xdelta 차이 패치만 포함합니다.

## 핵심 번역 데이터

- `translations_ko_by_key.json`: Localization 키 기준 번역
- `scene_translation_overrides.json`: 장면 직접 텍스트
- `resource_translation_overrides_*.json`: 표시 데이터·기술·업그레이드
- `serialized_translation_overrides_v050.json`: 직렬화 필드 최종 추가 번역
- `metadata_translation_overrides_v050.json`: IL2CPP 최종 문자열 260개
- `metadata_enum_names_v050.json`: 성장 트리 `UpgradeTag` 필드 이름
- `font_map_*.json`: Mulmaru 글꼴 교체 계획

## 검증 자료

- `audit_v050_initial.json`: 전수 감사 전 상태
- `audit_v050_coverage_latest.json`: 최종 정적 감사
- `prepare_v050_report.json`: 최종 번역 병합 수치
- `validation/PROFITS2167/VALIDATION_SUMMARY.md`: 사람이 읽는 검증 요약
- `extracted_private/PROFITS2167/validation`: 재추출 JSON. 원문 파생 데이터이므로 비공개 유지

## 최종 대상 파일 해시

| 대상 | 원본 SHA-256 | 패치 SHA-256 |
|---|---|---|
| `resources.assets` | `c6b11354b95414ddfdce6c5ce416d7b256908622fa371fcd58bfa9ef49a4ed33` | `54b4c31232e20bf8c994602974e3d3485d86a8d93b6d6ed96bc3006cc8ad7064` |
| `catalog.json` | `c52e0c7648e3d53be80d0b67ef4db3a78d29d04f65a6fc9f7d50f03641a3737d` | `6f36fb04418b966016b5a4c5982c6eec42beaa6a217d899cbc6315971ce9e8ec` |
| Localization bundle | `709dc25ac7abdb5227f9e8cf6409a16d31e6b503a31881d1587c84bde4f28e0b` | `5e745a71ca5298fc27d90829578ebdd136f871de32161adabf340be81b09e07b` |
| `sharedassets0.assets` | `e855a59079bc8448cc0d795760134ab2d5a3aa49f137cc7c42a822de503682da` | `46529647c828d4b74f732740c3142c74054fac9656408cd38cd282b8e8709bf0` |
| `level0` | `7f214ffa7da17139c4a09d098d95e0765b7dc248870f23ad6bbd1729145c774a` | `7af88e32f6b834af341c2a6d83ea5f88ca336f48ed0412dfd872966d0ec69daf` |
| `level1` | `95a1f7e8273401cc68705efdbb1aa5ec1347f7e89462e9c9dea06f08aa860137` | `e05e63ab4d12b358f5016de71a5d3d986c88096c91b3963fff9390d0f177e205` |
| `level2` | `1964d017c2f2e718a2c9ab19c07d0b5e68c69a1836742c96e1239c4619b1e499` | `6001d1d3a43604b519ce5dc7c3d36772b2df4f1ee2556ce3bb3d403b99f97d17` |
| `level3` | `e9c92e6e1f2ee839ceedb1237393959b994f409ca933039c6ceea9176877e280` | `c659cd6c2b930985eade7d842ff790070e4762cfb10aa1a4a7f1af3e2f73b21a` |
| `level4` | `19840680ed5de79668bc398450b6c7bd43c6c044bcc8a00156077e97fabdd3fc` | `4ee39d9269208e564a5ca6380abc66f161773921bba15fff2f3e25d80fd74af0` |
| `level5` | `4fb35f7922e41baedc5b7c8181ce95ff4fe22c1bf5a68174706f11862a1fd705` | `4642d415db54bbcfcfd22c5743ac7641e97e3e266e438a373e1ee7ba49620da1` |
| `level6` | `b119f935ac124b39aada6733c7ea537244e3de49a4bf3a917d6b027ba9bc766d` | `175112e5476c448db2a6bdb3990b1c780ecb3a98b3f1dd99325f5fc3d5c046ac` |
| `global-metadata.dat` | `9bd685aa8f35d05df2d26109ac6e32912d46daa0a2adfe9f420472c83abcf4bf` | `cb14bab5acbb31bf15064ea7257d7da4ce7c0f67264a9f94a7f02b4311d32aed` |

## 다음 작업자가 먼저 할 일

1. `docs/PROFITS2167_최종_보고서.md`의 남은 한계를 읽습니다.
2. 새 게임 빌드가 나왔다면 해시가 다르므로 기존 xdelta를 재사용하지 않습니다.
3. `audit_v050_coverage.py`를 기반으로 분류 체계를 `VISIBLE_TRANSLATE/KEEP/INTERNAL/MEDIA/UNKNOWN`으로 강화합니다.
4. 실제 실행 검수가 허용되면 격리 복사본에서 시작 화면, 설정, 튜토리얼, 성장 트리, 부스터, 결과 화면을 자동 캡처하는 스모크 테스트를 추가합니다.
5. 튜토리얼 이미지·영상의 픽셀 영문을 제거하려면 별도 미디어 재제작 단계와 품질 검수를 계획합니다.
6. 릴리스 전에 사용자 노출 미번역 0건, `UNKNOWN` 0건, 글리프 누락 0건을 증빙합니다.
