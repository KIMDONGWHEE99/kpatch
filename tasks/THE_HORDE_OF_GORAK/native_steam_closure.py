"""Steam 두 모듈의 독립 분류 근거와 반영용 목록만 만듭니다. 주색인은 수정하지 않습니다."""
import ast
import collections
import hashlib
import json
import re
import struct
from pathlib import Path
import pefile
from native_inspect import disassemble

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'source_original/THE_HORDE_OF_GORAK/steam_26336311'
OUT = ROOT / 'working_private/THE_HORDE_OF_GORAK/native_steam_closure_01'
UCRT = Path('C:/Program Files (x86)/Windows Kits/10/Source/10.0.22621.0/ucrt')
VC = Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.43.34808')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def build_evidence():
    inputs = json.loads((OUT / 'input_rows.json').read_text(encoding='utf-8'))
    files = {}
    arrays = []
    p = UCRT / 'convert/atoldbl.cpp'
    txt = p.read_text(encoding='utf-8-sig')
    for name in ['ld12_pow10_positive', 'ld12_pow10_negative']:
        body = re.search(re.escape(name) + r'\[\]\s*=\s*\{(.*?)\n\};', txt, re.S).group(1)
        raw = bytes(int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{2})', body))
        arrays.append((name, raw, str(p), sha(p.read_bytes())))
    # 완전한 상수 배열만 위치와 용도를 확정합니다.
    literal_sources = {}
    source_paths = [VC / 'include' / x for x in ['vector','list','xtree','functional','regex','exception','vcruntime_exception.h','xiosbase','system_error']]
    source_paths += list((VC / 'crt/src/stl').glob('*.cpp')) + list((UCRT / 'stdio').glob('*.cpp')) + [VC / 'crt/src/vcruntime/undname.cxx']
    for p in source_paths:
        if not p.exists():
            continue
        txt = p.read_text(encoding='utf-8-sig', errors='replace')
        for m in re.finditer(r'"(?:[^"\\]|\\.)*"', txt):
            try:
                value = ast.literal_eval(m.group())
            except (ValueError, SyntaxError):
                continue
            if len(value) >= 4:
                literal_sources.setdefault(value, []).append({'path':str(p), 'sha256':sha(p.read_bytes()), 'line':txt.count('\n',0,m.start())+1})
    for name in ['Steamworks.mfx','steam_api.dll']:
        p = BASE / name
        data = p.read_bytes()
        pe = pefile.PE(str(p))
        ib = pe.OPTIONAL_HEADER.ImageBase
        relocs = {pe.get_offset_from_rva(e.rva) for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type == 3}
        ranges = []
        for e in getattr(pe, 'DIRECTORY_ENTRY_DEBUG', []):
            ranges.append({'type':'PE_CODEVIEW_DEBUG', 'start':e.struct.PointerToRawData, 'end':e.struct.PointerToRawData+e.struct.SizeOfData, 'directory_type':e.struct.Type})
        exp = pe.DIRECTORY_ENTRY_EXPORT.struct
        for key, count, width in [('AddressOfFunctions',exp.NumberOfFunctions,4),('AddressOfNames',exp.NumberOfNames,4),('AddressOfNameOrdinals',exp.NumberOfNames,2)]:
            start = pe.get_offset_from_rva(getattr(exp,key))
            ranges.append({'type':'PE_EXPORT_'+key, 'start':start, 'end':start+count*width,'elements':count,'element_bytes':width})
        for aname, raw, sp, sh in arrays:
            start = data.find(raw)
            if start >= 0:
                ranges.append({'type':'CRT_LDBL12_POW10_ARRAY','start':start,'end':start+len(raw),'array':aname,'sha256':sha(raw),'source_path':sp,'source_sha256':sh,'consumer_source_lines':[417,438]})
        files[name] = {'sha256':sha(data),'ranges':ranges,'reloc_offsets':sorted(relocs),'rows':[]}
        for row in [x for x in inputs['rows'] if x['file']==name]:
            o = row['file_offset']; end = o+row['bytes']
            assert sha(data[o:end]) == row['source_bytes_sha256']
            refs = []
            for ref in row['static_references']:
                target = ref['target_offset']; va = ib + pe.get_rva_from_offset(target)
                for loc in ref['pointer_offsets']:
                    assert struct.unpack_from('<I',data,loc)[0] == va
                    sec = pe.get_section_by_rva(pe.get_rva_from_offset(loc))
                    r = {'pointer_offset':loc,'target_offset':target,'pointer_va':hex(ib+pe.get_rva_from_offset(loc)), 'relocated':loc in relocs,'executable':bool(sec.Characteristics&0x20000000)}
                    if r['executable']:
                        # 명령어의 주소 피연산자 직전부터 보존하며, 시작이 명확한 push/mov를 구분합니다.
                        back = 1 if data[loc-1] in [0x68,*range(0xb8,0xc0)] else 2 if data[loc-2] in [0x8b,0xff] else 1
                        r['start_alignment'] = 'opcode_verified' if data[loc-1] in [0x68,*range(0xb8,0xc0)] else 'operand_window'
                        r['instructions'] = disassemble(p,ib+pe.get_rva_from_offset(loc-back),110)
                    refs.append(r)
            matched = [r for r in ranges if r['start']<=o and end<=r['end']]
            literal = row['source']
            # 주소값 뒷바이트가 문자열 앞에 붙은 경우 실제 참조 시작 위치를 따로 기록합니다.
            actual_literals = []
            for ref in row['static_references']:
                start = ref['target_offset']
                if row['encoding']=='ascii' and o<=start<end:
                    v = data[start:data.index(0,start)].decode('ascii',errors='replace')
                    if v not in actual_literals:actual_literals.append(v)
            source_matches = []
            for value in [literal,*actual_literals]:
                if value in literal_sources:source_matches.append({'literal':value,'sources':literal_sources[value]})
            files[name]['rows'].append({'offset':o,'source':literal,'bytes':row['bytes'],'source_bytes_sha256':row['source_bytes_sha256'],'actual_referenced_literals':actual_literals,'typed_ranges':matched,'source_matches':source_matches,'references':refs})
    write('structural_and_consumers.json',{'inventory_snapshot_sha256':inputs['inventory_sha256'],'files':files})
    print(json.dumps({f:{'rows':len(d['rows']),'typed':sum(bool(r['typed_ranges']) for r in d['rows']),'source_matches':sum(bool(r['source_matches']) for r in d['rows'])} for f,d in files.items()}))

if __name__ == '__main__':
    build_evidence()
