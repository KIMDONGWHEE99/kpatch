"""검토한 요약만 공유 영역에 기록하고 비공개 증거는 해시로 연결합니다."""
from common import *
import platform

report_dir=ROOT/'validation/BOREWORKS_DEMO/ko_1.0.0';report_dir.mkdir(parents=True,exist_ok=True)
package=json.loads((WORK/'package_v1/package.json').read_text(encoding='utf-8'))
runtime=json.loads((WORK/'runtime_final/runtime_checks.json').read_text(encoding='utf-8'))
static=json.loads((WORK/'ko_v002/static_report.json').read_text(encoding='utf-8'))
assert runtime['visual_review']==runtime['status']==static['status']=='PASS'
for p in ['coverage_progress.json','asset_coverage_report.json','font_graph.json','ko_v002/metadata_boundary.json','ko_v002/validator_negative_tests.json','package_v1/installer_tests.json','package_v1/installer_edge_tests.json']:
    assert json.loads((WORK/p).read_text(encoding='utf-8'))['status']=='PASS',p
installed=(WORK/'installed_verification.json').exists()
if installed:assert json.loads((WORK/'installed_verification.json').read_text(encoding='utf-8'))['status']=='PASS'
status='지정 Steam 설치본 적용까지 완료' if installed else '검증 완료, 지정 Steam 설치본 적용 대기'
gates={f'G{i}':'PASS' for i in range(8)};gates['G8']='PASS' if installed else 'NOT_RUN'
evidence_paths=['baseline.json','pck_inventory.json','source_ledger.json','constant_ledger.json','asset_ledger.json','recipe_coverage.json','enum_coverage.json','font_graph.json','ko_v002/build_manifest.json','ko_v002/static_report.json','ko_v002/metadata_boundary.json','ko_v002/validator_negative_tests.json','runtime_final/runtime_checks.json','runtime_final/screenshots.json','runtime_final/user_saves_after.json','package_v1/package.json','package_v1/installer_tests.json','package_v1/installer_edge_tests.json']
if installed:evidence_paths.append('installed_verification.json')
evidence=[dict(path='working_private/BOREWORKS_DEMO/'+p,sha256=sha((WORK/p).read_bytes())) for p in evidence_paths]
save_json(report_dir/'EVIDENCE_INDEX.json',dict(game_build='23942533',candidate='ko_v002',gates=gates,evidence=evidence,zip_sha256=package['zip_sha256']))
tool_paths=[ROOT/'tools/gdre_2.6.4/bin/gdre_tools.exe',ROOT/'tools/gdre_2.6.4/bin/gdre_tools.pck',WORK/'toolchain/AssemblyPatch/AssemblyPatch.dll',WORK/'toolchain/AssemblyTool/AssemblyTool.dll',WORK/'toolchain/AssemblyTool/Mono.Cecil.dll',Path('C:/Users/PC/.dotnet/tools/ilspycmd.exe'),ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf',ROOT/'release_output/BOREWORKS_DEMO_KOREAN_PATCH_1.0.0/tools/xdelta3.exe',BASE/'Boreworks.exe']
tools=[dict(path=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),sha256=sha(p.read_bytes()),size=p.stat().st_size) for p in tool_paths if p.exists()]
sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p.read_bytes())) for p in sorted((ROOT/'tasks/BOREWORKS_DEMO/tools').rglob('*')) if p.suffix in ('.py','.cs','.csproj') and 'obj' not in p.parts and 'bin' not in p.parts]
save_json(ROOT/'tasks/BOREWORKS_DEMO/TOOLCHAIN_LOCK.json',dict(python=platform.python_version(),godot_native='4.6.3.stable.mono.official.7d41c59c4',gdre='2.6.4 / Godot 4.8.dev.gh.8a459f517',ilspy='9.1.0.7988',dotnet_sdk='8.0.418',tools=tools,sources=sources))
text=f'''# BOREWORKS Demo 한국어 패치 1.0.0 결과

2026-09-12 · {status}. 지원 버전은 Steam 앱 4829140, 빌드 23942533, 게임 v1.0.5입니다. 최종 후보는 `ko_v002`입니다.

## 적용 내용

영어 번역표 505개 위치(번역 488개, 식별자·기호 등 유지 17개)와 코드의 직접 문구 56곳을 처리했습니다. 메뉴, 설정, 조작 안내, 연구·제작, 툴팁, 시작 안내, 데모 종료·결과·예비 화면을 포함합니다. Noto Sans KR 400/700을 글꼴 리소스 4개와 크기 조절 모드, 적재함 안내에 연결했습니다. 변경 파일은 `Boreworks.pck`와 `data_Boreworks_windows_x86_64/Boreworks.dll` 두 개입니다.

게임 규칙·수치·저장 형식·Steam 연결은 원본 그대로입니다. 검수용 Steam 차단·메뉴 자동 순회·캡처 코드는 배포 파일에 포함하지 않았습니다. 원본 글꼴 선택 옵션도 한글을 표시하며, 글자 크기를 조절하려면 원본 설정 방식대로 픽셀 글꼴 옵션을 끄면 됩니다.

## 검증 범위와 결과

| 단계 | 결과 | 근거 요약 |
|---|---|---|
| G0 원본 고정 | PASS | 192개 파일, 509,809,608바이트, SHA-256 기준선; Godot 4.6.3/.NET 8/PCK 3 확인 |
| G1 위험 시험 | PASS | 무변경 PCK 재구성 원본 일치; 실제 GPU에서 소규모 한국어 메뉴 확인 |
| G2 출처 조사 | PASS | PCK 1,014개, 코드 문자열 9,371곳, 컴파일 시 문자열 상수 501개, 제작 항목 55개 및 표시용 열거값 조사; UNKNOWN 0 |
| G3 번역·글꼴 | PASS | 505개 표·56개 코드 위치; 번역 필요 문자 469개와 유지 기호 포함 479개를 실제 글꼴/대체 글꼴에 대조 |
| G4 후보 재검사 | PASS | 재추출 505개 위치 일치, 객체·메서드·필드 변경 경계 비교, ILSpy 재분석, 잘못된 번역 입력 거부 7건 |
| G5 기재된 화면·흐름 | PASS | 실제 RTX 4060 Ti, 1280×800, 메뉴 21개·진행 4단계·글꼴/크기 5설정의 282개 배치 검사, 58개 화면 관찰; 시작 안내와 저장·불러오기 별도 실행 |
| G6 차이 복원 | PASS | 변경 파일 2개의 정방향·역방향 복원 후 후보·원본 해시 일치 |
| G7 최종 ZIP | PASS | ZIP에서 꺼낸 설치기로 25건: 설치·중복·제거·부분 설치/제거·버전/변조/누락/도구 손상 거부·잠금·중간 실패·강제 중단 복구·경로/추가 라이브러리 |
| G8 실제 적용 | {gates['G8']} | {'지정 폴더 파일 전체를 최종 후보와 대조하고 원본 백업·사용자 저장 보존 확인' if installed else '최종 ZIP 설치기로 지정 폴더에 적용할 예정'} |

실행 검수의 실제 프로세스 경로는 Windows QueryFullProcessImageNameW로 확인하고 해당 PCK·DLL·EXE 해시를 기록했습니다. APPDATA/LOCALAPPDATA와 Steam 연결을 검수 사본에 한정해 격리했습니다. 사용자 저장 위치의 실행 전후 상태는 동일합니다. 글리프 누락 및 패치 관련 로딩 오류는 0건입니다. 원본의 작은 실행 아이콘 경고 1종은 유지됩니다.

처음 자동 검사에서 최소화된 창의 검은 캡처가 생겨 해당 캡처는 그래픽 통과 근거에서 제외했습니다. 실제 창으로 다시 검사했습니다. 원본의 의사 번역(문자열을 일부러 늘리는 개발용 언어)에서는 150% 힌트 배치 2건이 실패했으며, 최종 한국어 282개 검사에서는 잘림이 없었습니다. 최종 후보는 의사 번역 설정을 바꾸지 않습니다.

## 유지 표기와 미검증 범위

190개 고유 이미지를 육안으로 조사했습니다. BOREWORKS 로고·게임 아이콘·착륙장 H 기호를 유지하며 별도 픽셀 번역은 없습니다. 제작진 실명·활동명, Steam, GIF, 우주선/소행성 식별 코드, 키 이름·숫자 단위 k/M, 저장 경로를 유지합니다. 원본 음악·환경음·효과음 241개는 유지하며 더빙하지 않았습니다.

정식판 전용 분기와 무작위 소행성의 모든 회차를 끝까지 플레이한 것은 아닙니다. 개발용 메뉴 전환/진행 상태로 도달한 화면은 화면 관찰로 기록했고 전체 게임 규칙 검증으로 확대하지 않았습니다. 이전 공개 패치 갱신은 첫 버전이므로 해당 없으며 미배포 ko_v001 파일의 강제 적용 거부는 시험했습니다.

## 사용과 복구

패치 ZIP을 모두 풀고 `Install.cmd`를 실행하여 게임 폴더를 선택합니다. 제거는 `Remove.cmd`입니다. 원본 백업과 중단 복구 기록은 `%LOCALAPPDATA%\\BoreworksKoreanPatch\\working_private`에 저장됩니다. 설치 중 중단되면 같은 설치기를 다시 실행하세요. 미지원 게임 업데이트에는 강제로 적용하지 않습니다.

ZIP: [BOREWORKS_DEMO_KOREAN_PATCH_1.0.0.zip](../../../release_output/BOREWORKS_DEMO_KOREAN_PATCH_1.0.0.zip) · 852,831바이트

SHA-256: `{package['zip_sha256']}`

세부 증거 해시는 [EVIDENCE_INDEX.json](EVIDENCE_INDEX.json), 사용 도구는 [TOOLCHAIN_LOCK.json](../../../tasks/BOREWORKS_DEMO/TOOLCHAIN_LOCK.json)에 있습니다. 원본·파생 자산·화면·저장은 비공개 영역에만 보관했습니다. ZIP에는 명시적으로 허용한 설치기·도구·라이선스·차이 파일 13개만 포함합니다. 외부 공개는 수행하지 않았습니다.
'''
(report_dir/'RESULT_REPORT.md').write_text(text,encoding='utf-8')
(ROOT/'tasks/BOREWORKS_DEMO/README.md').write_text(f'''# BOREWORKS Demo 한국어 패치

Steam 빌드 23942533용 한국어 패치 1.0.0: {status}.

[결과 보고서](../../validation/BOREWORKS_DEMO/ko_1.0.0/RESULT_REPORT.md) · [패치 ZIP](../../release_output/BOREWORKS_DEMO_KOREAN_PATCH_1.0.0.zip) · [작업 명세](TASK_SPEC.md)

번역 원본은 `working_private/BOREWORKS_DEMO/translation/ko.json`, 직접 코드 번역 위치는 `working_private/BOREWORKS_DEMO/ko_v002/code_changes.json`입니다. 전체 기준선과 출처 증거도 같은 비공개 작업 영역에 보관합니다.

후보 생성은 `tools/prepare_candidate.py <새 후보 ID>`, 위치별 검사는 `tools/verify_candidate.py <후보 ID>`를 사용합니다. 도구/패키지 생성과 검수 순서는 [작업 이력](WORK_LOG.md)에 기록합니다. 원본 변경 시 과거 통과 결과를 재사용하지 않습니다.
''',encoding='utf-8')
spec=ROOT/'tasks/BOREWORKS_DEMO/TASK_SPEC.md';s=spec.read_text(encoding='utf-8');s=s[:s.index('| 단계 |')]
s+='| 단계 | 상태 | 근거 |\n|---|---|---|\n'
for gate,value in gates.items():s+=f'| {gate} | {value} | 결과 보고서 및 EVIDENCE_INDEX.json |\n'
spec.write_text(s,encoding='utf-8')
save_json(WORK/'release_readiness.json',dict(status='PASS',gates=gates,candidate='ko_v002',zip_sha256=package['zip_sha256'],external_publication=False))
print('REPORTS_READY',status)
