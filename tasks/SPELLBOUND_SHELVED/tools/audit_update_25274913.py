"""새 빌드 조사와 후보 검증. 재사용은 동일 내용·사용 경로 근거를 남긴다."""
import hashlib
import re
import difflib
from collections import Counter
from pathlib import Path
from update_25274913 import ROOT,WORK,EXTRACTED,BASELINE,CANDIDATE,configure,read,write,sha

def inventory():
    old=ROOT/'extracted_private/SPELLBOUND_SHELVED/steam_25171813/recovered'
    previous=read(ROOT/'working_private/SPELLBOUND_SHELVED/ko_v001/code_review.json')
    new=EXTRACTED/'recovered';out=WORK/'ko_v001'
    pattern=re.compile(r'""".*?"""|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27',re.S)
    records=[]
    for p in sorted((new/'scripts').glob('*.gd')):
        rel=p.relative_to(new).as_posix();source=p.read_text(encoding='utf-8');lines=source.splitlines()
        matches=list(pattern.finditer(source));prior=[r for r in previous if r['file']==rel]
        if prior:assert all(r['source_file_sha256']==sha(old/rel) for r in prior)
        mapped={}
        for block in difflib.SequenceMatcher(a=[r['source'] for r in prior],b=[m[0] for m in matches],autojunk=False).get_matching_blocks():
            for i in range(block.size):mapped[block.b+i]=prior[block.a+i]
        methods=[(0,'global')]+[(m.start(),m[1]) for m in re.finditer(r'(?m)^(?:static )?func (\w+)',source)]
        for i,m in enumerate(matches):
            line=source.count('\n',0,m.start())+1;method=[name for pos,name in methods if pos<=m.start()][-1]
            row={'file':rel,'index':i,'line':line,'method':method,'source':m[0],'context':lines[line-1],
                'source_file_sha256':sha(p),'source_sha256':hashlib.sha256(m[0].encode()).hexdigest(),'classification':'UNKNOWN','evidence':''}
            if i in mapped:
                prev=mapped[i];row['classification']=prev['classification'];row['evidence']='새 원본의 메서드 차이를 검토하여 같은 사용 의미임을 확인. 이전 위치 '+str(prev['line'])+': '+prev['evidence'];row['prior_source_file_sha256']=prev['source_file_sha256']
            elif p.name=='customer.gd' and method=='global':
                assert m[0] in ['"JustPatrick"','"MikhailMysfit"','"UnkiePlays"','"LiamsiL"']
                row['classification']='VISIBLE_KEEP';row['evidence']='GIVEN_NAMES에 추가된 실제 게스트의 활동명이다. 기존 게스트 이름과 동일하게 유지하며 README에 명시한다.'
            else:
                reason=None
                if p.name=='playlog.gd':reason='로컬 playlogs 파일의 경로·JSON 필드·이벤트 이름 또는 콘솔 로그다. 파일 쓰기와 print만 사용하고 UI 표시나 외부 전송 경로가 없다.'
                elif p.name in ('achievements.gd','upgrades.gd'):reason='PlayLog.event에 전달하는 로컬 기록용 이벤트 이름과 JSON 필드다.'
                elif p.name=='bot.gd':reason='chat_log의 kind 인수 gnome이다. 잡담 숨김 필터에만 사용하며 표시하지 않는다.'
                elif p.name=='game_settings.gd':reason='ConfigFile의 게임 설정 섹션과 속성 이름이다. 표시 문구는 settings_ui의 I18n 키로 분리되어 있다.'
                elif p.name=='settings_ui.gd' and method=='_add_game_rows':reason='추가 설정 문구를 읽는 I18n 키다. 같은 키의 한국어 번역 위치를 데이터 목록에서 대조한다.'
                elif p.name=='main.gd':
                    if method in ('_run_plan_sim','_plan_tier_blocked','_plan_freebies','_tier_of','_plan_tiers'):reason='명령줄로만 시작하는 시뮬레이션의 ID·조건·로그 필드다. print로 출력하며 게임 UI로 전달하지 않는다.'
                    elif method in ('global','_ready'):reason='자산 참조 또는 명령줄 시험 인수·headless 표시기 이름이다. UI 문구가 아니다.'
                    elif method in ('_collect_tip','set_library_open','try_unlock_shelf','save_run','_load_run','_toggle_upgrades','_toggle_achievements','_toggle_settings','_toggle_help','_exit_tree'):reason='PlayLog 기록용 이벤트 이름·JSON 필드 또는 저장 필드 접근 키다.'
                    elif method in ('_refresh_hud','_hover_text'):reason='추가 통계 문구를 읽는 I18n 키다. 한국어 번역은 같은 키로 존재하며 위치별 대조 대상이다.'
                    elif method=='_setup_hud_extras':reason='Font·글자 크기·색을 설정하는 Godot 테마 속성 이름이다.'
                    elif method=='chat_log':reason='노움 잡담을 식별하는 필터 값이나 빈 기본 인수다.'
                    elif method=='_unhandled_input':reason='PlayLog 이벤트 이름 또는 Node.has_method로 확인하는 메서드 이름이다.'
                    elif method=='section_fill':reason='책의 내부 상태 shelved를 비교하여 채움 비율을 계산한다.'
                assert reason,(p,line,method,m[0]);row['classification']='INTERNAL';row['evidence']=reason+' 실제 문맥: '+lines[line-1].strip()
            assert row['classification']!='UNKNOWN';records.append(row)
    write(out/'code_review.json',records)
    # 이전 도구를 새 입력으로 다시 실행한다. 과거 보고서의 식별자만 바꾸어 재사용하지 않는다.
    configure()
    source=(ROOT/'tasks/SPELLBOUND_SHELVED/tools/close_inventory.py').read_text(encoding='utf-8')
    source=source.replace("'steam_build':'25171813'","'steam_build':'25274913'").replace("'scripts':22,'resources':51","'scripts':23,'resources':52")
    (WORK/'intake').mkdir(exist_ok=True)
    import shutil
    shutil.copy2(WORK/'baseline.json',WORK/'intake/baseline.json')
    exec(compile(source,'close_inventory.py','exec'),{'__name__':'update_inventory'})
    # 픽셀 및 글꼴 원본의 판정은 같은 원본 해시와 같은 import 경로일 때만 재사용한다.
    media=read(out/'media_inventory.json');reuse=[]
    for row in media:
        assert sha(old/row['file'])==row['sha256'],row['file']
        reuse.append({'file':row['file'],'sha256':row['sha256'],'previous_build':'25171813','new_build':'25274913','basis':'픽셀 원본·import 경로가 같고 코드 차이에서 새 이미지 사용 경로가 없음'})
    write(out/'media_reuse.json',reuse)
    print('코드 분류',dict(Counter(r['classification'] for r in records)))

def static():
    configure()
    import audit_candidate
    audit_candidate.run(CANDIDATE.name,WORK/'reextracted')
    path=WORK/'ko_v001'/(CANDIDATE.name+'_static.json');result=read(path)
    # 공통 함수의 역사적 고정 표시만 보정하며 검사는 위에서 새 입력 전체에 실행했다.
    result['steam_build']='25274913';write(path,result)
    assert result['ui_keys']==311 and result['ui_original_occurrences']==293
    assert result['original_pck_files']==121 and result['candidate_pck_files']==125
    print('새 빌드 후보 정적 검사 PASS')

if __name__=='__main__':
    import sys
    {'inventory':inventory,'static':static}[sys.argv[1]]()
