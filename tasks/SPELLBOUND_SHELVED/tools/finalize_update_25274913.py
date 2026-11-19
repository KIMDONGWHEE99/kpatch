"""업데이트 후보의 실제 검수 증거를 묶고 설치 전후 무결성을 확인한다."""
import hashlib
import os
import re
import struct
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from update_25274913 import ROOT, WORK, BASELINE, EXTRACTED, CANDIDATE, sha, read, write
from pck_tools import read_pack

package = WORK/'package_1.0.1'
output = WORK/'ko_v001'
archive = ROOT/'release_output/SPELLBOUND_SHELVED_KOREAN_PATCH_1.0.1.zip'
game = Path('D:/steam/steamapps/common/Spellbound & Shelved')
game_windows = game/'windows'
root_key = hashlib.sha256(str(game_windows.resolve()).lower().encode()).hexdigest().upper()[:16]
old_backup = Path(os.environ['LOCALAPPDATA'])/'SpellboundShelvedKoreanPatch/working_private'/root_key

def listing(folder):
    return [{'path':p.relative_to(folder).as_posix(),'size':p.stat().st_size,'sha256':sha(p)}
            for p in sorted(folder.rglob('*')) if p.is_file()]

def old_listing():
    return [r for r in listing(old_backup) if not r['path'].startswith('build_25274913/')]

def entries(path):
    return {e['name']:e['data'] for e in read_pack(path)[3]}

def settings(data):
    pos=8; result={}
    for _ in range(struct.unpack_from('<I',data,4)[0]):
        size=struct.unpack_from('<I',data,pos)[0];pos+=4
        key=data[pos:pos+size].decode();pos+=size
        size=struct.unpack_from('<I',data,pos)[0];pos+=4
        result[key]=data[pos:pos+size];pos+=size
    return result

def finalize():
    static=read(output/'ko_1.0.1_c01_static.json')
    inventory=read(output/'inventory_summary.json')
    tests=read(package/'installer_tests.json');pack=read(package/'package.json')
    assert all(r['status']=='PASS' for r in [static,inventory,tests])
    assert len(tests['tests'])==24 and all(r['status']=='PASS' for r in tests['tests'])
    assert sha(archive)==pack['zip_sha256']==tests['zip_sha256']
    assert sha(CANDIDATE/'windows/SpellboundShelved.pck')==static['pck_sha256']
    assert sha(WORK/'noop.pck')==sha(BASELINE/'windows/SpellboundShelved.pck')
    assert listing(BASELINE)==read(WORK/'baseline.json')
    assert read(WORK/'user_before.json')==read(WORK/'user_after.json')
    assert 'spellbound & shelved' in str(read(package/'discovery.json')).lower()
    with zipfile.ZipFile(archive) as z:
        assert sorted(z.namelist())==sorted(pack['allowed_files'])
        for name in z.namelist():
            assert z.read(name)==(package/'from_final_zip'/name).read_bytes()
    final=entries(CANDIDATE/'windows/SpellboundShelved.pck')
    qa=entries(WORK/'qa/SpellboundShelved.pck');allowed=read(WORK/'qa/allowed_changes.json')
    actual={n for n in final.keys()|qa.keys() if final.get(n)!=qa.get(n)}
    assert actual==set(allowed['resources'])
    assert sha(WORK/'qa/SpellboundShelved.pck')==allowed['qa_pck_sha256']
    assert allowed['source_pck_sha256']==static['pck_sha256']
    assert all(hashlib.sha256(qa[n]).hexdigest()==h for n,h in allowed['resources'].items())
    assert qa['qa_update_hook.gd']==(ROOT/'tasks/SPELLBOUND_SHELVED/tools/qa_update_hook.gd').read_bytes()
    a=settings(final['project.binary']);b=settings(qa['project.binary'])
    assert {k for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}==set(allowed['project_properties'])
    assert not any('KoreanQA' in k or 'qa_update_hook' in k for k in final)
    logs=[WORK/'qa/runtime_session1.log',WORK/'qa/runtime.log']
    text='\n'.join(p.read_text(encoding='utf-8') for p in logs)
    assert 'NVIDIA GeForce RTX 4060 Ti' in text and 'KOREAN_QA_STEAM=false' in text
    assert '/update_25274913/qa/' in text.lower() and 'SBS_KO_QA_25274913' in text
    assert not re.search(r'(?im)^(?:ERROR|SCRIPT ERROR):|missing glyph|missing character|could not load|failed loading',text)
    warnings=set(re.findall(r'(?m)^WARNING:.*',text))
    baseline=(WORK/'baseline_qa/runtime.log').read_text(encoding='utf-8')
    assert warnings<=set(re.findall(r'(?m)^WARNING:.*',baseline))
    assert 'KOREAN_QA_QUIET={"added":0,"enabled":true}' in text
    states=[__import__('json').loads(s) for s in re.findall(r'KOREAN_QA_STATE=(.*)',text)]
    saved=[s for s in states if not s['menu']]
    assert len(saved)==2 and all(s['credits']==78 and s['more_stats'] and s['hide_gnome_chat'] for s in saved)
    assert saved[0]['floor_text']==saved[1]['floor_text']
    process=read(WORK/'qa/process.json')
    assert Path(process['Path']).resolve()==(WORK/'qa/SpellboundShelved.exe').resolve()
    notes={
        'menu':'한국어 새 게임·설정 버튼과 원본 로고 확인.',
        'settings_new_options':'새 게임 설정 구분·잡담 숨기기·추가 통계 문구 표시 확인.',
        'settings_enabled':'새 옵션 두 개를 켠 상태 확인.',
        'settings_display':'화면 설정의 한국어 설명·해상도·전체 화면 표시 확인.',
        'floor_stats':'바닥에 놓인 책 수와 금화 HUD 확인.',
        'shelf_fill':'연금술과 물약 (0% 채움) 표시 확인.',
        'help':'도움말 본문과 제작 정보 배치 확인.',
        'upgrades':'업그레이드 안내·닫기·도서 목록 I 구매 상태 확인.',
        'dialogue':'일반 인명·실존 게스트 원문 이름·직업·책 제목·손님 대사 확인.',
        'achievements':'업적 제목·설명·달성 시간 표시 확인.',
        'finale':'검수 전용 메서드로 결과 화면의 시간·합계·버튼을 확인. 실제 완주 아님.',
        'saved':'진행 상황 저장 완료 알림과 금화 78 확인.',
        'exit_confirmation':'정말 종료할까요? 확인 후 정상 종료.',
        'reload_menu':'재실행 후 한국어와 이어하기 항목 유지.',
        'reload_game':'금화 78·저장한 서가·한국어 복귀 알림 확인.',
        'reload_settings':'재실행 후 잡담 숨기기와 추가 통계 옵션 유지 확인.'}
    screens=[{'screen':n,'path':(WORK/'screens'/(n+'.jpg')).relative_to(ROOT).as_posix(),
              'sha256':sha(WORK/'screens'/(n+'.jpg')),'status':'PASS','observation':note} for n,note in notes.items()]
    runtime={'steam_build':'25274913','candidate':'ko_1.0.1_c01','candidate_pck_sha256':static['pck_sha256'],
        'status':'PASS','scope':'대표 화면 16개 관찰 및 저장·재실행. 전체 분기 검증을 뜻하지 않는다.',
        'screens':screens,'process':process,'graphics_device':'NVIDIA RTX 4060 Ti / OpenGL 3.3 / Godot 4.7.1',
        'qa_allowed_changes':allowed,'quiet_probe':'PASS','save_reload':'PASS','credits':78,
        'new_settings_persistence':'PASS','user_data_integrity':'PASS','user_file_count':22,
        'glyph_warning_count':0,'patch_unique_loading_error_count':0,'baseline_warnings':sorted(warnings),
        'not_run':['전체 플레이 시간','모든 무작위 대사 조합','29개 업적 실제 달성','이번 빌드의 개발 HUD·재시작 확인·언어 왕복 추가 순회'],
        'not_applicable':{'unity_specific':'Godot PCK·GDScript·FontFile을 사용하므로 Mono/IL2CPP/TMP/Addressables는 없음.'}}
    write(output/'runtime_qa_report.json',runtime)
    fonts=read(output/'font_report.json')
    assert all(r['required_characters']==728 and r['font_characters']==726 for r in fonts)
    write(output/'font_graph.json',{'status':'PASS','required_characters':728,'korean_font_characters':726,
        'symbols':['✦','➔'],'body':'Nunito Regular → Korean400.ttf; NotoSansSymbols2 폴백 유지',
        'headings':'Nunito SemiBold/Bold/ExtraBold·Spectral Bold·Geist SemiBold → Korean700.ttf',
        'world':'ThemeDB fallback_font → Korean400.ttf','developer':'SystemFont.fallbacks → Korean400.ttf',
        'rendering':'Godot FontFile의 동적 TTF 그리기. 기존 재질·원본 글꼴을 유지하고 전체 필요 문자표를 검사했다.'})
    pack.update(final_zip_tests='PASS',installer_test_count=24,steam_discovery='PASS');write(package/'package.json',pack)
    write(output/'candidate_manifest.json',listing(CANDIDATE))
    bound=[WORK/'baseline.json',EXTRACTED/'pck_manifest.json',WORK/'entry_diff.json',WORK/'translation_changes.json',
        WORK/'user_before.json',WORK/'user_after.json',WORK/'baseline_qa/runtime.log',WORK/'qa/allowed_changes.json',
        WORK/'qa/process.json',package/'package.json',package/'installer_tests.json',package/'discovery.json',archive]
    bound+=list(output.glob('*.json'))+list((WORK/'translation').glob('*.json'))+logs
    bound+=list((WORK/'screens').glob('*.jpg'))+list((ROOT/'tasks/SPELLBOUND_SHELVED/tools').glob('*.*'))
    bound+=[ROOT/'tools/gdre_2.6.4/bin/gdre_tools.exe',ROOT/'tools/gdre_2.6.4/bin/gdre_tools.pck',package/'from_final_zip/tools/xdelta3.exe']
    bound=[p for p in bound if p.name!='release_lock.json']
    lock={'created_utc':datetime.now(timezone.utc).isoformat(),'steam_build':'25274913','candidate':'ko_1.0.1_c01',
        'zip_sha256':sha(archive),'dependencies':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in bound],
        'invalidation_rule':'입력·도구·후보·증거가 변경되면 해당 결과는 STALE이며 재검증한다.',
        'gates':{'G0':'PASS','G1':'PASS','G2':'PASS','G3':'PASS','G4':'PASS','G5':'NOT_RUN','G6':'PASS','G7':'PASS','G8':'NOT_RUN'},
        'gate_scope_note':'대표 화면 16개는 PASS. 기존 명세의 개발 HUD·재시작 확인·언어 왕복 추가 순회가 남아 전체 G5/G8 완료로 집계하지 않는다.',
        'installed':'NOT_RUN'}
    write(output/'release_lock.json',lock)
    print('후보·화면 16개·저장·최종 ZIP 시험 24건 증거 연결 완료')

def installation(stage):
    lock=read(output/'release_lock.json')
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in lock['dependencies'])
    expected=read(WORK/'baseline.json') if stage=='before' else read(output/'candidate_manifest.json')
    actual=listing(game);assert actual==expected
    if stage=='before':
        write(WORK/'old_backup_before.json',old_listing())
        assert old_listing(), '이전 백업 경로 확인 필요'
    else:
        assert old_listing()==read(WORK/'old_backup_before.json')
        assert sha(old_backup/'build_25274913/cache/0/original')==sha(BASELINE/'windows/SpellboundShelved.pck')
        receipt=read(old_backup/'build_25274913/receipt.json')
        assert receipt['status']=='COMPLETE' and receipt['mode']=='Install' and receipt['version']=='1.0.1'
        assert read(WORK/'user_before.json')==read(WORK/'user_after_install.json')
    write(WORK/('installed_'+stage+'.json'),{'status':'PASS','stage':stage,'files':actual,
        'backup_root':str(old_backup),'checked_utc':datetime.now(timezone.utc).isoformat()})
    print('설치 '+stage+' 파일 17개 및 관련 무결성 PASS')

if __name__=='__main__':
    if sys.argv[1]=='finalize':finalize()
    else:installation(sys.argv[1])
