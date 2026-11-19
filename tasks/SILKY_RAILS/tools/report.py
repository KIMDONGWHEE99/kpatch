"""실제 완료 범위와 생략한 검수를 명확히 기록합니다."""
from baseline import *
import datetime
install=json.loads((WORK/'installation.json').read_text());package=json.loads((WORK/'package/package.json').read_text());candidate=json.loads((WORK/'ko_v003.json').read_text());independent=json.loads((WORK/'ko_v003_independent.json').read_text());log=(WORK/'qa_002/Player.log').read_text(encoding='utf-8',errors='replace')
assert install['status']=='PASS';missing=[x for x in log.splitlines() if any(s in x for s in ["Missing 'ko'",'Unknown key','Bad format','The character with Unicode value'])];assert not missing
snapshot=WORK/'qa_002/video_settings.png';tool_paths=[Path(sys.executable),WORK/'assembly_tool/AssemblyTool.dll',ROOT/'tools/python_deps/UnityPy/__init__.py',WORK/'NotoSansKR-Regular.ttf',WORK/'package/from_final_zip/tools/xdelta3.exe']
save(WORK/'toolchain.json',[dict(path=str(p),sha256=sha(p.read_bytes())) for p in tool_paths])
report=f'''# Silky Rails 한국어 패치 1.0.0 결과

작성일: 2026-09-24 · 지원 Steam 빌드: 25487146 · 앱: 3870990

지정 설치 폴더에 적용 완료. 후보 `ko_v003`과 설치본 239개 파일이 일치하며 원본 백업 4개를 생성했습니다. 적용 전후 사용자 저장·설정은 같습니다.

## 번역 범위

- 14개 번역표, 985개 키. 원문과 나머지 언어 열을 보존하고 기존 포르투갈어 열을 한국어로 교체.
- 장면·공용 자산의 직접 표시 문구 283곳, 코드 문자열 65곳(한국어 언어명·기본값 포함).
- Noto Sans KR 굵기 400, 전체 필요 문자 703자 지원. 동적 대체 글꼴과 다중 문자 이미지 생성 연결.
- 새 설정은 한국어로 시작합니다. 이전 설정이 있다면 언어에서 한국어를 선택합니다.
- 제목·로고·제작자 이름·Discord·키 이름·식별자·일부 개발용 임시 문구와 이미지 속 문구는 유지합니다. 한국어 음성 패치는 아닙니다.

## 수행한 최소 검사

| 검사 | 상태 | 실제 범위 |
|---|---|---|
| 원본 보존 | PASS | 239파일 원본 사본·크기·SHA-256 기록 |
| 후보 재열기 | PASS | 변경 312객체 전 필드 일치, 그 외 객체 원시 내용 동일 |
| 번역표 독립 재추출 | PASS | 985키 위치·번역 일치, 영어 및 나머지 열 동일 |
| 서식 | PASS | 태그 순서, 자리표시자, 레벨별 선택 수, 제어 줄바꿈 대조 |
| 코드 경계 | PASS | 6,292메서드 비교, 지정 문자열 65곳 외 명령 동일 |
| 글꼴 | PASS | 필요 문자 지원·동적 대체 글꼴·다중 아틀라스 설정 |
| 실제 그래픽 확인 | PASS | NVIDIA RTX 4060 Ti에서 소리 설정·화면 설정의 한글을 관찰. 관찰한 두 화면의 한글 깨짐·잘림 없음 |
| 실행 위치·저장 | PASS | 검수 사본 PID 34288의 실제 경로 확인. 별도 회사·제품명과 Steam/분석 초기화 격리. 사용자 저장·설정 동일 |
| 실행 로그 | PASS | 관찰 구간 한글 누락·한국어 키 누락·서식 오류 0. 원본에 포함된 누락 스크립트와 DontDestroyOnLoad 경고는 유지 |
| 차이 파일 복원 | PASS | 4파일 정방향·역방향 해시 일치 |
| 최종 ZIP 설치기 | PASS | 별도 한글·공백 경로에서 설치·중복 설치·제거·중복 제거·재설치 5회 |
| 실제 설치 | PASS | 최종 ZIP에서 꺼낸 설치기로 적용, 239파일 후보 일치 |

## 생략·미검증 범위

사용자의 **최대한 빠르게, 검수 최소화** 지시를 우선했습니다. 전체 분기·회차·전투 흐름·미디어 전수·개발 화면 전수 검수와 실패 주입 확장 시험은 NOT_RUN입니다. 소리·화면 설정 관찰을 첫 화면 전체 또는 전체 플레이 검증으로 확대하지 않습니다.

원본 조사 중 추출 오류 12건(설정 구조·참조 없는 스크립트·빈 이미지 등)을 기록했으며 전체 출처 판정을 마무리하지 않았습니다. 수정한 대상은 모두 다시 열어 대조했습니다. 공통 G2·G5·G7·G8 전체 통과 또는 완벽 한글화로 표시하지 않습니다.

첫 시험 `ko_v002`에서 BOM(파일 앞의 보이지 않는 표시) 처리 오류로 번역표 교체가 생략된 문제를 발견했습니다. 최종 `ko_v003`은 14개 표와 985개 키의 독립 재추출 및 실행 로그로 재확인했습니다. 초기 시험의 오류 기록은 최종 검증과 분리합니다.

## 배포·복구

- ZIP: `release_output/SILKY_RAILS_KOREAN_PATCH_1.0.0.zip`
- ZIP SHA-256: `{package['zip_sha256']}`
- 패키지 크기: {(ROOT/'release_output/SILKY_RAILS_KOREAN_PATCH_1.0.0.zip').stat().st_size:,}바이트
- 설치: 압축 전체를 풀고 `Install.cmd`. 제거: `Remove.cmd`에서 같은 게임 폴더 선택.
- 원본 백업: `%LOCALAPPDATA%\\SilkyRailsKoreanPatch\\working_private` 아래 설치 경로별 폴더.
- 미지원 원본 해시 거부·트랜잭션 기록·실패 복원 기능을 포함하며 이번 버전의 중단/변조 상황 확장 시험은 생략했습니다.
- 설치기·차이 파일·도구·라이선스·문서 17개만 포함. 게임 원본 및 검수 사본은 제외.

비공개 근거: `working_private/SILKY_RAILS`의 baseline, ko_v003, 독립 검사, package/package.json, installation.json, qa_002 기록.
'''
out=ROOT/'validation/SILKY_RAILS/ko_1.0.0';out.mkdir(parents=True,exist_ok=True);(out/'RESULT_REPORT.md').write_text(report,encoding='utf-8')
summary=dict(version='1.0.0',steam_build='25487146',candidate='ko_v003',translated_keys=985,direct_occurrences=283,code_occurrences=65,installed_files=239,modified_files=4,zip_sha256=package['zip_sha256'],user_save_unchanged=True,observed_screens=['소리 설정','화면 설정'],full_playthrough='NOT_RUN',all_gates_passed=False)
save(out/'summary.json',summary)
if snapshot.exists():save(WORK/'qa_002/observations.json',dict(screens=['소리 설정: 한글 정상','화면 설정: 한글 정상'],capture_sha256=sha(snapshot.read_bytes()),log_sha256=sha((WORK/'qa_002/Player.log').read_bytes()),missing_glyphs=0,full_playthrough='NOT_RUN'))
(ROOT/'tasks/SILKY_RAILS/README.md').write_text('''# Silky Rails 한국어 패치 1.0.0

Steam 빌드 25487146 대상 제작·지정 폴더 적용 완료.

- 번역표 985키, 직접 문구 283곳, 코드 65곳 및 한글 대체 글꼴.
- 실제 소리·화면 설정 표시, 파일 대조, 최종 ZIP 설치·제거 5회 확인.
- 요청에 따라 전체 플레이·전수 분류·실패 상황 확장 검수 생략.
- [결과 보고](../../validation/SILKY_RAILS/ko_1.0.0/RESULT_REPORT.md)
- [패치 ZIP](../../release_output/SILKY_RAILS_KOREAN_PATCH_1.0.0.zip)
- [작업 명세](TASK_SPEC.md)
''',encoding='utf-8')
f=ROOT/'PROJECT_STATUS.md';s=f.read_text(encoding='utf-8-sig');s=s.replace('갱신일: 2026-09-22 · 현재 작업: Alchemortis Demo 업데이트 대응 한국어 패치 1.0.1 적용 완료','갱신일: 2026-09-24 · 현재 작업: Silky Rails 한국어 패치 1.0.0 적용 완료');intro='**Silky Rails 한국어 패치 1.0.0을 지정 Steam 폴더에 적용했습니다.** 번역표 985키·직접 문구 283곳·코드 문구 65곳과 한글 글꼴을 적용했습니다. 요청에 따라 검수를 최소화하여 소리·화면 설정의 실제 한글 표시, 독립 재추출, 최종 ZIP 설치·제거 5회 및 설치본 239파일·저장 보존을 확인했습니다. 전체 플레이·전수 분류·확장 실패 시험은 미수행이며 G0~G8 전체 통과로 표시하지 않습니다. [패치 ZIP](release_output/SILKY_RAILS_KOREAN_PATCH_1.0.0.zip), [결과와 한계](validation/SILKY_RAILS/ko_1.0.0/RESULT_REPORT.md).\n\n';s=s.replace('\n\n**Alchemortis', '\n\n'+intro+'**Alchemortis',1);f.write_text(s,encoding='utf-8')
with (ROOT/'WORK_LOG.md').open('a',encoding='utf-8') as f:f.write('\n\n## 2026-09-24 Silky Rails\n\nSteam 25487146 한국어 1.0.0 제작 및 지정 폴더 적용. 사용자 요청에 따라 검수 최소화. 985키·283직접 문구·65코드 문구, 239파일 설치 대조 및 사용자 저장 보존. 실제 소리/화면 설정 관찰과 최종 ZIP 설치·제거 5회. 전체 G0~G8 통과 아님. validation/SILKY_RAILS/ko_1.0.0/RESULT_REPORT.md 참고.\n')
with (ROOT/'tasks/SILKY_RAILS/TASK_SPEC.md').open('a',encoding='utf-8') as f:f.write('\n## 완료 기록\n\n2026-09-24: 후보 ko_v003, 1.0.0 지정 설치 완료. 기존 포르투갈어 슬롯의 코드·표시명을 한국어로 대체하고 영어 원문은 유지. 실제 소리·화면 설정만 관찰. 전체 검수 미실행. 최종 보고서는 ../../validation/SILKY_RAILS/ko_1.0.0/RESULT_REPORT.md.\n')
print('보고서 작성 완료')
