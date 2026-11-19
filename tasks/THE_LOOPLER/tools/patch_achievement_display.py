"""Steam의 업적 표시 조회 두 곳을 기존 한국어 표 조회로 연결합니다.

업적 달성·저장·통계 전송 메서드는 수정하지 않습니다. 원래 Steam 결과는
해당 키가 없는 경우의 대체 문구로 보존하며 Windows 예외 복원 정보도 추가합니다.
"""
from native_support import *
from build_candidate import CANDIDATE,REPORT

schema=json.loads((EXTRACT/'steam_achievement_schema.json').read_text('utf-8'))['4150860']['stats']
achievements=[]
for group in schema.values():
    for entry in group.get('bits',{}).values():
        achievements.append({'id':entry['name'],'name_key':entry['display']['name']['token'].rstrip('\n'),'desc_key':entry['display']['desc']['token'].rstrip('\n')})
assert len({r['id'] for r in achievements})==len(achievements)
path=CANDIDATE/'GameAssembly.dll';source=SOURCE/'GameAssembly.dll'
assert sha(path)==sha(source)
pe=PeImage(path.read_bytes());base,raw=pe.next_section();payload=bytearray();functions=[];evidence=[]
original_call=method_address('Steamworks.SteamUserStats','GetAchievementDisplayAttribute')['RVA']
localize=method_address('RunSummaryMenu','Localize')['RVA'];string_new=pe.exports()['il2cpp_string_new']
for kind in ('name','desc'):
    payload.extend(b'\0'*((-len(payload))%16));begin=base+len(payload)
    a=Assembler(begin)
    a.emit('4883ec48 48894c2420');a.relative('e8',original_call)
    a.emit('4889442430 488b442420 4885c0');a.relative('0f84','fallback')
    a.emit('488d5014 4889542428');a.relative('4c8d15','table')
    a.emit('41bb');a.code.extend(struct.pack('<I',len(achievements)))
    a.label('entry');a.emit('418b0a 3b4810');a.relative('0f85','next')
    a.emit('4c8b442428 4d8d4a04')
    a.label('character');a.emit('410fb710 66413911');a.relative('0f85','next')
    a.emit('4983c002 4983c102 ffc9');a.relative('0f85','character')
    a.emit('498d8a84000000');a.relative('e8',string_new)
    a.emit('4889c1 488b542430 4531c0');a.relative('e8',localize);a.relative('e9','exit')
    a.label('next');a.emit('4981c200010000 41ffcb');a.relative('0f85','entry')
    a.label('fallback');a.emit('488b442430')
    a.label('exit');a.emit('4883c448 c3')
    end=base+len(payload)+len(a.code)
    a.labels['table']=PeImage.align(end,16)
    code=a.finish();decoded=disassemble(code,begin)
    assert len(code)==sum(i['size'] for i in decoded)
    payload.extend(code);payload.extend(b'\0'*((-len(payload))%16))
    for row in achievements:
        identity=row['id'].encode('utf-16-le');key=row[kind+'_key'].encode('utf-8')+b'\0'
        assert 0<len(identity)<=128 and len(key)<=124
        record=bytearray(256);struct.pack_into('<I',record,0,len(identity)//2);record[4:4+len(identity)]=identity;record[132:132+len(key)]=key;payload.extend(record)
    payload.extend(b'\0'*((-len(payload))%4));unwind=base+len(payload)
    # 버전 1, 첫 4바이트에서 72바이트 스택 예약, 비휘발성 레지스터 변경 없음.
    payload.extend(bytes.fromhex('01040100 04820000'))
    functions.append((begin,end,unwind))
    evidence.append({'kind':kind,'begin_rva':begin,'end_rva':end,'unwind_rva':unwind,'instructions':decoded})

method=method_address('SteamStatsAndAchievements','GetAchievementSnapshots')
instructions=disassemble(bytes(pe.data[method['Offset']:method['Offset']+method['Length']]),method['RVA'])
calls=[i for i in instructions if i['mnemonic']=='call' and i['operands']==hex(original_call)]
assert len(calls)==2,calls
changes=[]
for call,function,kind in zip(calls,functions,('name','desc')):
    offset=pe.offset(call['rva']);old=bytes(pe.data[offset:offset+5]);new=b'\xe8'+struct.pack('<i',function[0]-call['rva']-5)
    assert old[0]==0xe8
    pe.data[offset:offset+5]=new
    changes.append({'method':'SteamStatsAndAchievements.GetAchievementSnapshots','kind':kind,'rva':call['rva'],'offset':offset,'before':old.hex(),'after':new.hex()})

directory=pe.optional+112+3*8;old_pdata,old_size=struct.unpack_from('<II',pe.data,directory)
exception_data=bytes(pe.data[pe.offset(old_pdata):pe.offset(old_pdata)+old_size]);assert old_size%12==0
assert struct.unpack_from('<I',exception_data,len(exception_data)-12)[0]<functions[0][0]
payload.extend(b'\0'*((-len(payload))%4));new_pdata=base+len(payload)
payload.extend(exception_data)
for function in functions:payload.extend(struct.pack('<III',*function))
struct.pack_into('<II',pe.data,directory,new_pdata,old_size+len(functions)*12)
pe.append_section(payload);path.write_bytes(pe.data)
check=PeImage(path.read_bytes());assert check.sections[-1][0].rstrip(b'\0')==b'.korean'
for row,function in zip(changes,functions):
    insn=disassemble(bytes(check.data[row['offset']:row['offset']+5]),row['rva'])[0]
    assert insn['operands']==hex(function[0])
write_json(REPORT/'achievement_display_patch.json',{'source_sha256':sha(source),'candidate_sha256':sha(path),'schema_sha256':sha(EXTRACT/'steam_achievement_schema.json'),'mapping':achievements,'call_changes':changes,'helpers':evidence,'new_section_rva':base,'new_section_size':len(payload),'exception_entries_added':len(functions),'status':'STATIC_PASS_RUNTIME_NOT_RUN'})
print('achievement mappings',len(achievements),'call changes',len(changes),'payload bytes',len(payload))
