"""검수 전용 장면 진입/저장 DAT를 생성합니다. 게임을 실행하지 않습니다."""
from __future__ import annotations
import argparse
import json
import struct
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tasks/THE_HORDE_OF_GORAK'))
from dat_container import DatFile,sha,u32
from inventory import event_operations

PRIVATE=ROOT/'working_private/COBALT_MINER'
ORIGINAL=ROOT/'source_original/COBALT_MINER/steam_24347666/COBALT MINER.dat'

def chunk_for(dat,index):
    frames=[x for x in dat.chunks if x.chunk_id==0x3333]
    return next(x for x in frames[index].children if x.chunk_id==0x333D)

def frame_handle(dat,index):
    frames=[x for x in dat.chunks if x.chunk_id==0x3333]
    return u32(next(x for x in frames[index].children if x.chunk_id==0x334C).decoded)

def op_bytes(data,op):
    return data[op['offset']:op['offset']+op['size']]

def make_event(data,event,conditions=None,actions=None):
    header=bytearray(data[event['offset']:event['offset']+8])
    conditions=conditions if conditions is not None else [op_bytes(data,x)for x in event['Conditions']]
    actions=actions if actions is not None else [op_bytes(data,x)for x in event['Actions']]
    if not 0<len(conditions)<256 or not 0<len(actions)<256:raise ValueError('검수 이벤트 명령 수 범위 초과')
    body=b''.join(conditions+actions)
    size=8+len(body)
    if size>=32768:raise ValueError('검수 이벤트 길이 범위 초과')
    sign=-1 if struct.unpack_from('<h',header)[0]<0 else 1
    struct.pack_into('<h',header,0,sign*size)
    header[2]=len(conditions);header[3]=len(actions)
    return bytes(header)+body

def event_region(data):
    marker=data.index(b'ERev')
    start=marker+8
    length=u32(data,marker+4)
    end=start+length
    reserve=data.index(b'ERes')+4
    if data[end:]!=b'<<ER' or u32(data,reserve)!=length:raise ValueError('이 게임의 단일 ERev/ERes 구조와 다름')
    return start,end,reserve,marker+4

def rewrite_events(data,replacements,append=None):
    events=event_operations(data)
    start,end,reserve,length_field=event_region(data)
    if events[0]['offset']!=start or events[-1]['offset']+events[-1]['size']!=end:raise ValueError('이벤트 경계 대조 실패')
    pieces=[]
    for event in events:
        pieces.append(replacements.get(event['index'],data[event['offset']:event['offset']+event['size']]))
    pieces.extend(append or [])
    body=b''.join(pieces)
    header=bytearray(data[:start])
    struct.pack_into('<I',header,reserve,len(body));struct.pack_into('<I',header,length_field,len(body))
    result=bytes(header)+body+data[end:]
    parsed=event_operations(result)
    if len(parsed)!=len(events)+len(append or []):raise ValueError('재추출 이벤트 수 불일치')
    for i,event in enumerate(parsed):
        if result[event['offset']:event['offset']+event['size']]!=pieces[i]:raise ValueError('재추출 이벤트 위치 대조 실패')
    return result

def build(input_path,output,mode,entry_frame=None,autosave=False,settings_value=None):
    input_path=input_path.resolve();output=output.resolve()
    permitted=[ROOT/'source_original/COBALT_MINER',PRIVATE,ROOT/'build_candidate/COBALT_MINER']
    if not any(input_path.is_relative_to(p)for p in permitted) or not output.is_relative_to(PRIVATE):raise ValueError('입출력은 이 게임의 비공개 영역만 허용')
    if output.exists():raise ValueError('기존 검수 출력을 덮어쓰지 않음')
    if autosave and (mode!='newgame' or entry_frame not in (None,7)):raise ValueError('자동 저장은 새 게임 본편7 검사에만 허용')
    if settings_value is not None and (mode!='settings' or not 0<=settings_value<=100):raise ValueError('설정 시험 값은 settings 모드의 0..100만 허용')
    source=input_path.read_bytes();dat=DatFile(source)
    if dat.integrity_summary()['status']!='PASS':raise ValueError('입력 DAT 무결성 실패')
    frame0=chunk_for(dat,0);menu=chunk_for(dat,2)
    events0=event_operations(frame0.decoded);events2=event_operations(menu.decoded)
    condition_start=op_bytes(frame0.decoded,events0[0]['Conditions'][0])
    if (events0[0]['Conditions'][0]['type'],events0[0]['Conditions'][0]['num'],len(condition_start))!=(-3,-1,8):raise ValueError('시작 조건 기대값 불일치')
    jump_template=events2[9]['Actions'][1]
    if (jump_template['type'],jump_template['num'],jump_template['size'])!=(-3,2,16):raise ValueError('장면 이동 템플릿 불일치')
    jump=bytearray(op_bytes(menu.decoded,jump_template))
    struct.pack_into('<I',jump,12,frame_handle(dat,2))
    event2=events0[2]
    if (event2['Conditions'][0]['type'],event2['Conditions'][0]['num'],event2['Actions'][0]['type'],event2['Actions'][0]['num'])!=(-6,-1,-3,0):raise ValueError('원본 로고 Escape 이벤트 불일치')
    replacement=make_event(frame0.decoded,event2,[condition_start],[bytes(jump)])
    if len(replacement)!=event2['size']:raise ValueError('로고 진입 변경의 길이 보존 실패')
    frame0.replacement=rewrite_events(frame0.decoded,{2:replacement})
    changes=[dict(frame=0,event=2,reason='원본 Escape16+NextFrame8을 StartOfFrame8+JumpToFrame16으로 대체. fullscreen/header 보존',before=frame0.decoded[event2['offset']:event2['offset']+event2['size']].hex(),after=replacement.hex())]
    expected_events={0:{2:replacement}}
    if mode!='menu':
        index={'settings':9,'newgame':7,'continue':8,'frame':9}[mode]
        event=events2[index]
        conditions=[condition_start]+[op_bytes(menu.decoded,x)for x in event['Conditions'][1:]]
        actions=[op_bytes(menu.decoded,x)for x in event['Actions']]
        target=entry_frame if entry_frame is not None else {'settings':3,'newgame':7,'continue':7,'frame':7}[mode]
        if not 0<=target<17:raise ValueError('장면 번호는 0..16')
        jump_indexes=[i for i,x in enumerate(event['Actions'])if (x['type'],x['num'])==(-3,2)]
        if len(jump_indexes)!=1:raise ValueError('목표 장면 이동 명령이 유일하지 않음')
        ji=jump_indexes[0];modified=bytearray(actions[ji]);struct.pack_into('<I',modified,12,frame_handle(dat,target));actions[ji]=bytes(modified)
        if settings_value is not None:
            # 원본의 Global A 숫자 대입 명령을 복제해 기존 설정 UI의 저장 경로를 사용합니다.
            setter=bytearray(op_bytes(menu.decoded,events2[5]['Actions'][0]))
            if len(setter)!=16 or struct.unpack_from('<II',setter,8)!=(0,50):raise ValueError('Global A 기본 대입 명령 불일치')
            struct.pack_into('<i',setter,12,settings_value);actions.insert(ji,bytes(setter))
        replacement=make_event(menu.decoded,event,conditions,actions)
        menu.replacement=rewrite_events(menu.decoded,{index:replacement})
        expected_events[2]={index:replacement}
        changes.append(dict(frame=2,event=index,reason='기존 메뉴 버튼 조건을 StartOfFrame으로 교체. 원래 초기화/저장 읽기·삭제 행동과 순서를 보존하며 장면만 지정',target_frame=target,target_handle=frame_handle(dat,target),settings_value=settings_value,before=menu.decoded[event['offset']:event['offset']+event['size']].hex(),after=replacement.hex()))
    if autosave:
        game=chunk_for(dat,7);events=event_operations(game.decoded);save_event=events[217]
        if (save_event['Conditions'][0]['type'],save_event['Conditions'][0]['num'],save_event['Conditions'][0]['handle'])!=(33,-81,416):raise ValueError('SAVE GAME 조건 불일치')
        save_actions=[op_bytes(game.decoded,x)for x in save_event['Actions']]
        appended=make_event(game.decoded,save_event,[condition_start],save_actions)
        game.replacement=rewrite_events(game.decoded,{},[appended])
        expected_events[7]={len(events):appended}
        changes.append(dict(frame=7,event=len(events),reason='모든 원래 시작 이벤트 이후 SAVE GAME event217의 전체 행동을 복제 실행하는 마지막 StartOfFrame 이벤트. 검수용 자동 저장',source_event=217,source_actions_sha256=sha(b''.join(save_actions)),after=appended.hex()))
    result=dat.serialize();after=DatFile(result);before=DatFile(source)
    if after.integrity_summary()['status']!='PASS' or after.serialize()!=result:raise ValueError('출력 DAT 재열기/무결성 실패')
    allowed={chunk_for(before,i).location for i in expected_events}|{before.one(0x2242).location}
    changed=[]
    for key,old in before.by_location.items():
        new=after.by_location[key]
        if old.children:continue
        if old.decoded!=new.decoded:
            if key not in allowed:raise ValueError('허용하지 않은 청크 변경: '+key)
            changed.append(key)
    if before.header!=after.header or before.one(0x2223).decoded!=after.one(0x2223).decoded:raise ValueError('헤더 변경 감지')
    for fi,edits in expected_events.items():
        old=chunk_for(before,fi).decoded;new=chunk_for(after,fi).decoded
        old_events=event_operations(old);new_events=event_operations(new)
        for i,event in enumerate(new_events):
            expected=edits.get(i,old[old_events[i]['offset']:old_events[i]['offset']+old_events[i]['size']] if i<len(old_events) else None)
            if new[event['offset']:event['offset']+event['size']]!=expected:raise ValueError('이벤트 단위 변경 경계 실패')
        for event in old_events:
            for op in event['Actions']:
                if (op['type'],op['num'])==(-3,14):
                    actual=new_events[event['index']]['Actions'][op['index']]
                    if op_bytes(old,op)!=op_bytes(new,actual):raise ValueError('전체화면 명령 변경 감지')
    output.mkdir(parents=True)
    path=output/'COBALT MINER.qa-only.dat';path.write_bytes(result)
    report=dict(qa_only=True,status='PASS',runtime_status='NOT_RUN',mode=mode,input_path=str(input_path),input_sha256=sha(source),output_path=str(path),output_sha256=sha(result),tool_sha256=sha(Path(__file__).read_bytes()),changes=changes,changed_decoded_chunks=changed,header_unchanged=True,fullscreen_operations_unchanged=True,
        limits=['검수 전용 자동 장면 접근/저장. 일반 입력 흐름·전체 분기 통과 근거 아님','기존 저장 격리/Steam 차단은 실행자의 별도 guard가 필수','settings_value는 원래 Global A 소비를 사용하므로 원본의 두 음량 슬라이더 초기화도 같은 값을 사용할 수 있음'])
    (output/'fixture_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if input_path.read_bytes()!=source:raise ValueError('입력 DAT 변경')
    print(json.dumps({k:report[k]for k in ('status','runtime_status','mode','output_path','output_sha256')},ensure_ascii=False))
    return path

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,default=ORIGINAL);ap.add_argument('--output',required=True,type=Path);ap.add_argument('--mode',choices=['menu','settings','newgame','continue','frame'],required=True);ap.add_argument('--entry-frame',type=int);ap.add_argument('--autosave',action='store_true');ap.add_argument('--settings-value',type=int)
    args=ap.parse_args();build(args.input,args.output,args.mode,args.entry_frame,args.autosave,args.settings_value)
