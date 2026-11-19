"""후보와 완료 근거를 확인하는 공통 단언입니다."""
import re

def check_entry(source,actual,expected):
    assert actual==expected and actual!='','번역 위치·빈 값 불일치'
    token=lambda s:re.findall(r'\{[^{}]+\}|</?[^>]+>',s)
    assert token(source)==token(actual),'인수 또는 태그 순서·속성 불일치'
    assert source.count('\n')==actual.count('\n'),'제어 줄바꿈 불일치'

def check_positions(expected,actual):
    assert expected.keys()==actual.keys(),'표시 위치 삭제·추가'
    for key,value in expected.items():assert actual[key]==value,('위치별 번역 불일치',key)

def check_coverage(strings,media,errors,resolutions):
    assert all(r['classification'] in ['VISIBLE_TRANSLATE','VISIBLE_KEEP','INTERNAL'] for r in strings),'미분류 문자열'
    assert all(r['disposition'] in ['TRANSLATE','KEEP','NO_TEXT'] and r['reason'] for r in media),'미검토 미디어'
    solved={(r['file'],r['path_id']) for r in resolutions if r['status']=='PASS'}
    assert all((r['file'],r['path_id']) in solved for r in errors),'미해결 추출 실패'

def check_binding(expected,actual):
    assert expected==actual,'입력 변경으로 만료된 검증 근거'

def check_characters(required,available):
    assert set(required)<=set(available),'글꼴 문자 누락'
