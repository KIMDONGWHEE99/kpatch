"""게임·Steam을 실행하지 않고 업적 표시 도우미의 실제 x64 코드를 검증합니다."""
from native_support import *
from build_candidate import CANDIDATE,REPORT
import ctypes,json,struct

report=json.loads((REPORT/'achievement_display_patch.json').read_text('utf-8'))
pe=PeImage((CANDIDATE/'GameAssembly.dll').read_bytes());sec=pe.sections[-1];payload=bytearray(pe.data[sec[4]:sec[4]+sec[1]])
canonical=json.loads((WORK/'translation_canonical.json').read_text('utf-8'));source_map={r['source']:r['translation'] for r in canonical}
en_path=next((DATA/'StreamingAssets/aa/StandaloneWindows64').glob('localization-string-tables-english*'))
en=next(o for o in UnityPy.load(str(en_path)).objects if o.type.name=='MonoBehaviour').read_typetree();en_by_id={r['m_Id']:r['m_Localized'] for r in en['m_TableData']}
shared_path=DATA/'StreamingAssets/aa/StandaloneWindows64/localization-assets-shared_assets_all.bundle'
shared=next(o for o in UnityPy.load(str(shared_path)).objects if o.path_id==3335046104275354130).read_typetree()
translations={r['m_Key'].rstrip('\n'):source_map[en_by_id[r['m_Id']]] for r in shared['m_Entries'] if r['m_Id'] in en_by_id}
keep=[]
def managed(value):
    text=value.encode('utf-16-le');buffer=ctypes.create_string_buffer(b'\0'*16+struct.pack('<I',len(text)//2)+text+b'\0\0');keep.append(buffer);return ctypes.addressof(buffer)
def value(pointer):
    if not pointer:return None
    length=ctypes.c_uint32.from_address(pointer+16).value;assert length<10000
    return ctypes.string_at(pointer+20,length*2).decode('utf-16-le')
CALL3=ctypes.WINFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)
CALL1=ctypes.WINFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p)
@CALL3
def original(identity,attribute,method):return managed('원본 대체 문구')
@CALL1
def string_new(pointer):return managed(ctypes.string_at(pointer).decode('utf-8'))
@CALL3
def localize(key,fallback,method):return managed(translations.get(value(key),value(fallback)))
callbacks={method_address('Steamworks.SteamUserStats','GetAchievementDisplayAttribute')['RVA']:original,pe.exports()['il2cpp_string_new']:string_new,method_address('RunSummaryMenu','Localize')['RVA']:localize}
stubs={}
for rva,callback in callbacks.items():
    stubs[rva]=sec[2]+len(payload);payload.extend(b'\x48\xb8'+struct.pack('<Q',ctypes.cast(callback,ctypes.c_void_p).value)+b'\xff\xe0')
for helper in report['helpers']:
    for insn in helper['instructions']:
        if insn['mnemonic']=='call':
            target=int(insn['operands'],16);assert target in stubs
            offset=insn['rva']-sec[2];payload[offset:offset+5]=b'\xe8'+struct.pack('<i',stubs[target]-insn['rva']-5)
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.VirtualAlloc.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.c_uint32];kernel.VirtualAlloc.restype=ctypes.c_void_p
kernel.VirtualFree.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32]
memory=kernel.VirtualAlloc(None,len(payload),0x3000,0x40);assert memory
ctypes.memmove(memory,bytes(payload),len(payload));checks=[]
try:
    for helper in report['helpers']:
        call=CALL3(memory+helper['begin_rva']-sec[2]);kind=helper['kind']
        for row in report['mapping']:
            result=value(call(managed(row['id']),managed(kind),None));expected=translations[row[kind+'_key']]
            assert result==expected,(row,expected,result)
            checks.append({'achievement':row['id'],'kind':kind,'status':'PASS'})
        for identity in ('UNKNOWN_TEST_KEY','',None):
            result=value(call(None if identity is None else managed(identity),managed(kind),None))
            assert result=='원본 대체 문구',(identity,result)
            checks.append({'achievement':identity,'kind':kind,'status':'PASS_FALLBACK'})
finally:kernel.VirtualFree(memory,0,0x8000)
write_json(REPORT/'native_mapping_test.json',{'candidate_sha256':sha(CANDIDATE/'GameAssembly.dll'),'scope':'실제 도우미 x64 코드의 Windows 호출 규약·47개 업적 이름/설명 분기·미등록/빈 값/null 입력. 외부 Steam 함수와 게임 할당/조회 함수만 시험용으로 대체. 실제 Steam 접속 검수 아님.','checks':checks,'status':'PASS'})
print('native mapping checks',len(checks),'PASS')
