"""실제 후보 검사에 쓰는 함수가 알려진 결함을 차단하는지 확인합니다."""
from baseline import *
from checks import *
cases=[]
def reject(name,fn):
    try:fn()
    except AssertionError:cases.append(dict(case=name,status='PASS'));return
    raise AssertionError('결함을 놓쳤습니다: '+name)
check_entry('<b>{0}</b>\nReady','<b>{0}</b>\n준비','<b>{0}</b>\n준비')
check_positions({'a':'확인','b':'취소'},{'a':'확인','b':'취소'})
check_coverage([{'classification':'INTERNAL'}],[{'disposition':'NO_TEXT','reason':'빈 픽셀'}],[],[])
check_binding({'build':'a'},{'build':'a'});check_characters('한글','한글ABC')
cases.append(dict(case='valid_inputs',status='PASS'))
reject('blank',lambda:check_entry('Ready','',''))
reject('source_left',lambda:check_entry('Ready','Ready','준비'))
reject('swapped_positions',lambda:check_positions({'a':'확인','b':'취소'},{'a':'취소','b':'확인'}))
reject('missing_object',lambda:check_positions({'a':'확인','b':'취소'},{'a':'확인'}))
reject('broken_tag_order',lambda:check_entry('<b><i>{0}</i></b>','<b><i>{0}</b></i>','<b><i>{0}</b></i>'))
reject('icon_attribute',lambda:check_entry('<sprite index=1>','<sprite index=2>','<sprite index=2>'))
reject('control_newline',lambda:check_entry('A\nB','가 나','가 나'))
reject('unknown_string',lambda:check_coverage([{'classification':'UNKNOWN'}],[],[],[]))
reject('unknown_media',lambda:check_coverage([],[{'disposition':'UNKNOWN','reason':'미분류'}],[],[]))
reject('extraction_failure',lambda:check_coverage([],[],[{'file':'x','path_id':1}],[]))
reject('missing_glyph',lambda:check_characters('한글','한'))
reject('stale_evidence',lambda:check_binding({'build':'a'},{'build':'b'}))
save(WORK/'checker_tests.json',dict(status='PASS',cases=cases));print('검사기 검증 PASS',len(cases))
