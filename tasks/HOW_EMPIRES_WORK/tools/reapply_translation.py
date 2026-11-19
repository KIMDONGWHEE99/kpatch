"""업데이트 입력에서 동일 위치·원문·문맥·서식만 번역 재사용 후보로 만듭니다."""
from common import *
import re,collections,tempfile,sys

def fingerprint(row):
    source=row['source']
    return {'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'context_sha256':hashlib.sha256(row.get('context',row.get('key','')).encode()).hexdigest(),
        'format':re.findall(r'\{[^}]*\}|\[/?[^\]]*\]|%(?:[-+0#]*\d*(?:\.\d+)?[sdifuxXoegGc]|%)|[\n\r\t]',source)}

def propose(previous,current):
    index=collections.defaultdict(list)
    for row in previous:index[row['id']].append(row)
    counts=collections.Counter(row['id'] for row in current)
    result=[]
    for row in current:
        matches=index[row['id']]
        good=len(matches)==1 and counts[row['id']]==1 and fingerprint(matches[0])==fingerprint(row)
        result.append({**row,'target':matches[0]['target'] if good else row['source'],
            'status':'REUSE_CANDIDATE' if good else 'UNKNOWN','review_required':not good,
            'reason':'위치·원문·문맥·서식 일치' if good else '신규·변경·이동·중복 항목은 영어 유지 후 재검토',
            'fingerprint':fingerprint(row)})
    return result

def atomic_write(path,value,interrupt=False):
    pending=path.with_suffix(path.suffix+'.new')
    with pending.open('w',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    if interrupt:raise RuntimeError('검수용 중단 주입')
    os.replace(pending,path)

def test():
    folder=WORK/('reapply_trial_1.0.1' if '--fix' in sys.argv else 'reapply_trial');folder.mkdir(exist_ok=True)
    source=[{'id':'a','source':'Cost: {0}','context':'tooltip/money','target':'비용: {0}'},
            {'id':'b','source':'Save','context':'button/save','target':'저장'},
            {'id':'c','source':'Close','context':'dialog/close','target':'닫기'}]
    cases=[]
    def check(name,current,expected):
        out=propose(source,current);assert [r['status'] for r in out]==expected,name
        assert all(r['target']==r['source'] for r in out if r['status']=='UNKNOWN')
        cases.append({'id':name,'status':'PASS'})
    check('unchanged',source,['REUSE_CANDIDATE']*3)
    check('new_entry',source+[{'id':'d','source':'New screen','context':'new'}],['REUSE_CANDIDATE']*3+['UNKNOWN'])
    check('changed_source',[{**source[0],'source':'Total cost: {0}'}],['UNKNOWN'])
    check('changed_placeholder',[{**source[0],'source':'Cost: {amount}'}],['UNKNOWN'])
    check('changed_context',[{**source[1],'context':'button/discount'}],['UNKNOWN'])
    check('moved_location',[{**source[1],'id':'new/b'}],['UNKNOWN'])
    check('duplicate_context_identity',[source[1],source[1]],['UNKNOWN','UNKNOWN'])
    check('deleted_entry',source[:2],['REUSE_CANDIDATE']*2)
    check('reordered_entries',source[::-1],['REUSE_CANDIDATE']*3)
    destination=folder/'translation.json';sentinel=folder/'사용자저장.dat'
    sentinel.write_bytes(b'save is unchanged');saved_hash=sha(sentinel)
    atomic_write(destination,propose(source,source));before=sha(destination)
    atomic_write(destination,propose(source,source));assert sha(destination)==before
    cases.append({'id':'idempotent_reapply','status':'PASS'})
    try:atomic_write(destination,propose(source,source[:1]),True)
    except RuntimeError:pass
    assert sha(destination)==before
    atomic_write(destination,propose(source,source));assert sha(destination)==before
    assert sha(sentinel)==saved_hash
    cases.extend([{'id':'interrupted_write_recovery','status':'PASS'},{'id':'save_preservation','status':'PASS'}])
    actual=read_json(WORK/'translation/canonical.json')+read_json(WORK/'translation/direct_canonical.json')
    reused=propose(actual,actual)
    assert all(r['status']=='REUSE_CANDIDATE' for r in reused)
    atomic_write(folder/'registry.json',reused)
    write_json(folder/'report.json',{'status':'PASS','cases':cases,'real_rows':len(reused),'registry_sha256':sha(folder/'registry.json'),'scope':'번역 자료의 재사용 후보 산출·모의 업데이트. 게임 파일 자동 변경 없음. 실제 새 빌드는 별도 전체 검사 필요.'})
    print('PROC-09',len(cases),'cases PASS;',len(reused),'rows')

if __name__=='__main__':test()
