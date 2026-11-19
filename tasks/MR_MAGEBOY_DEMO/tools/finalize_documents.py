"""추가 검수 없이 이미 확보한 결과와 설치 기록을 공유용 안내에 반영합니다."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[3]
work = root / 'working_private/MR_MAGEBOY_DEMO'
draft = work / 'report_draft'
destination = root / 'validation/MR_MAGEBOY_DEMO/ko_1.0.0'
destination.mkdir(parents=True, exist_ok=True)
installation = json.loads((work / 'installation_1.0.0_c06/installation_report.json').read_text(encoding='utf-8'))
assert installation['status'] == 'PASS'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

gate = json.loads((draft / 'final_gate.json').read_text(encoding='utf-8'))
gate.update(is_draft=False, status='NOT_RUN', release_status='LOCAL_APPLIED_BY_USER_REQUEST',
            all_gates_passed=False, canonical_zip_copy_status='PASS',
            canonical_zip='release_output/MR_MAGEBOY_DEMO_KOREAN_PATCH_1.0.0.zip',
            user_instruction='검수 그만하고 마무리하세요', remaining=[])
gate['gates']['G1'].update(evidence=['early_actual_risk_evidence'], scope='원본과 같은 PCK 왕복·실제 GPU 소규모 한글 글꼴/장면 출력 및 저장 격리. early_evidence.json의 실제 관찰과 연결.')
gate['gates']['G5'].update(status='NOT_RUN', progress='사용자 지시로 추가 검수 중단',
                         evidence=['observed_menu_screens', 'observed_skill_screens', 'runtime_path', 'qa_save_after'],
                         scope='메뉴·대표 흐름의 기존 관찰과 기술 설명60개 PASS. 가방 알림·색상창·기본확인버튼·최종종료·원본경고 대조 및 전체 통합 판정 미완료.')
gate['gates']['G8'].update(status='PASS', progress='지정 폴더 적용 완료', evidence=['actual_installation'],
                         scope='최종 ZIP 동일 사본에서 추출한 설치기 적용·4파일 후보 일치·원본백업1파일·저장/설정 경로 보존·안내 전달. 전체 G5 PASS를 의미하지 않음.')
gate['graphics_scope'].update(planned_skill_descriptions=60, observed_skill_descriptions=60,
                              actual_save_integrity='PASS', current_candidate_observation_gate='NOT_RUN')
gate['not_run_by_user_request'] = ['원본 경고 실제 실행 대조', '색상창·기본 확인 버튼·가방 알림·최종 종료 표시', '필수화면 전체통합판정', '전체 회차·모든 무작위 분기']
gate['installation'] = {'status': 'PASS', 'game_directory': installation['game_directory'],
                        'verified_files': 4, 'changed_files': 1, 'original_backups': 1,
                        'user_save_integrity': 'PASS', 'backup_directory': installation['backup_directory']}
(destination / 'final_gate.json').write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding='utf-8')
index = json.loads((draft / 'evidence_index.json').read_text(encoding='utf-8'))
index['evidence'].pop('risk_existing_gate_statement', None)
extra = {'early_actual_risk_evidence': 'working_private/MR_MAGEBOY_DEMO/early_evidence.json',
         'observed_menu_screens': 'working_private/MR_MAGEBOY_DEMO/ko_1.0.0_c06/visual_review_menus.json',
         'observed_skill_screens': 'working_private/MR_MAGEBOY_DEMO/ko_1.0.0_c06/visual_review_skills.json',
         'runtime_path': 'working_private/MR_MAGEBOY_DEMO/ko_1.0.0_c06/process_path.json',
         'qa_save_after': 'working_private/MR_MAGEBOY_DEMO/ko_1.0.0_c06/user_save_after.json',
         'actual_installation': 'working_private/MR_MAGEBOY_DEMO/installation_1.0.0_c06/installation_report.json',
         'source_rule_notes': 'working_private/MR_MAGEBOY_DEMO/ko_1.0.0_c06/independent_reviews/source_runtime_notes.json'}
for name, path in extra.items():
    index['evidence'][name] = {'path': path, 'sha256': digest(root / path), 'private_evidence_only': True}
for item in index['evidence'].values():
    item['sha256'] = digest(root / item['path'])
index['scope'] = '공유용 검토를 마친 요약 근거의 위치와 지문. 원시 게임/저장 자료는 포함하지 않음.'
(destination / 'evidence_index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
report = (draft / 'RESULT_REPORT.md').read_text(encoding='utf-8')
report += '\n\n## 설치 완료 기록과 확인 범위\n\n'
report += '2026-10-07 사용자의 추가 검수 중단 지시에 따라 지정 폴더 `D:\\steam\\steamapps\\common\\MR MAGEBOY DEMO`에 적용을 완료했습니다. 최종 ZIP에서 꺼낸 설치기가 정상 종료했고 설치된 4파일이 후보와 일치했습니다. 수정 PCK 원본 백업 1개가 원본 지문과 일치하며 사용자 저장·설정 경로는 전후 동일했습니다. G8은 이 적용 범위에서 PASS이며 G5 전체는 NOT_RUN입니다.\n\n'
report += '최종 c06에서 이미 판독한 메뉴·대표 흐름과 기술 설명 60종의 기록을 보존했습니다. 기술 설명은 제목 가림·본문 잘림 없이 화면 여백 안에 표시됐습니다. 키·마우스 표시 153개는 기존 대조 PASS입니다. 가방 상태·색상 팝업·기본 확인 버튼·최종 종료 화면·원본 경고 실행 대조는 미완료로 남깁니다. 검수 사본 종료 후 사용자 저장 경로 보존도 확인했습니다. 추가 게임 실행은 하지 않았습니다.\n\n'
report += '예비 제작진 창 검사에서 로고 자원 로딩 오류 10건이 기록됐으나 원본 실행 대조를 중단했으므로 패치 고유 오류 0건으로 단정하지 않습니다. 기록된 글리프(글자 모양) 누락 경고는 0건이며 미관찰 화면 전체의 보증으로 확대하지 않습니다. 원본 기술 설명과 계산값의 차이 4종(기술092·093·199·216)은 원본 숫자와 규칙을 그대로 보존했습니다.\n\n'
report += f"원본 백업: `{installation['backup_directory']}`. 복구하려면 게임 종료 후 [Remove.cmd](../../../release_output/MR_MAGEBOY_DEMO_KOREAN_PATCH_1.0.0/Remove.cmd)를 실행합니다.\n"
(destination / 'RESULT_REPORT.md').write_text(report, encoding='utf-8')
readme = (draft / 'README.md').read_text(encoding='utf-8')
(root / 'tasks/MR_MAGEBOY_DEMO/README.md').write_text(readme, encoding='utf-8')
spec = root / 'tasks/MR_MAGEBOY_DEMO/TASK_SPEC.md'
text = spec.read_text(encoding='utf-8')
text = text[:text.index('## 완료 단계')] + (draft / 'TASK_SPEC_GATES.md').read_text(encoding='utf-8')
spec.write_text(text, encoding='utf-8')
status = root / 'PROJECT_STATUS.md'
text = status.read_text(encoding='utf-8')
start = text.index('**MR MAGEBOY DEMO')
end = text.index('**Epic Idlenture', start)
text = text[:start] + '**MR MAGEBOY DEMO 한국어 패치 1.0.0을 지정 Steam 폴더에 적용했습니다.** 부제를 ‘채집 마법사’와 도트 글꼴로 바꾸고 어색한 문구·조작 이름 잘림·기술 설명 제목 겹침을 수정했습니다. 번역·유지 1,172위치와 동적 문구137곳의 독립 대조, 최종 ZIP 설치·복구38시험을 완료했고 설치본4파일·원본백업1개·저장 경로 보존을 확인했습니다. 기술 설명60개와 대표 화면을 판독했으며 사용자 지시로 추가 검수를 중단했습니다. G5 전체·전체 회차·일부 추가 화면과 원본 경고 대조는 미완료이며 G0~G8 전체 통과로 표시하지 않습니다. [패치 ZIP](release_output/MR_MAGEBOY_DEMO_KOREAN_PATCH_1.0.0.zip), [결과와 확인 범위](validation/MR_MAGEBOY_DEMO/ko_1.0.0/RESULT_REPORT.md).\n\n' + text[end:]
status.write_text(text, encoding='utf-8')
log = root / 'WORK_LOG.md'
text = log.read_text(encoding='utf-8')
entry = '## 2026-10-07 — MR-MAGEBOY-DEMO-KO-1.0.0\n\n- Steam 빌드25734075·Godot4.7.2의 원본4파일과 전체 PCK를 고정하고 문구·미디어·글꼴을 조사했다. 최종c06의 가시1,172위치·동적137곳·번역876값을 독립 대조했다.\n- 사용자 의견에 따라 부제를 채집 마법사로 교정하고 Galmuri11 Bold 도트 글꼴을 적용했다. 조작 이름23개와 기술 도움말 배치를 수정했다.\n- 실제GPU 대표 화면과 기술 설명60개를 판독했다. 추가 검수 중단 지시 후 게임 실행/시험을 더 하지 않고 확인 범위와 미완료를 분리했다. G5전체/전체회차/원본경고 대조 미완료이며 전체 게이트 통과로 표시하지 않았다.\n- 같은 최종ZIP의 정·역 복원·설치/실패복구38시험·손상검출14시험 증거를 보존했다. ZIP에서 꺼낸 설치기로 지정D폴더 적용, 4파일후보일치·원본백업1개·사용자저장경로 보존을 확인했다.\n- [패치ZIP](release_output/MR_MAGEBOY_DEMO_KOREAN_PATCH_1.0.0.zip), [결과보고서](validation/MR_MAGEBOY_DEMO/ko_1.0.0/RESULT_REPORT.md). 공개 업로드는 하지 않았다.\n\n'
if entry.splitlines()[0] not in text:
    log.write_text(text.replace('# WORK_LOG\n\n', '# WORK_LOG\n\n' + entry, 1), encoding='utf-8')
print('FINAL_DOCUMENTS_WRITTEN')
