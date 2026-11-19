"""게임의 표시 문구 호출만 바꾸기 위한 PE 읽기와 x64 명령 검사."""
from common import *
import struct,ctypes,json

class PeImage:
    def __init__(self,data):
        self.data=bytearray(data);self.pe=struct.unpack_from('<I',data,60)[0];assert data[self.pe:self.pe+4]==b'PE\0\0'
        self.coff=self.pe+4;self.optional=self.coff+20
        self.count=struct.unpack_from('<H',data,self.coff+2)[0]
        self.section_table=self.optional+struct.unpack_from('<H',data,self.coff+16)[0]
        self.sections=[struct.unpack_from('<8sIIIIIIHHI',data,self.section_table+i*40) for i in range(self.count)]
        self.section_alignment,self.file_alignment=struct.unpack_from('<II',data,self.optional+32)
    def offset(self,rva):
        for s in self.sections:
            if s[2]<=rva<s[2]+max(s[1],s[3]):return s[4]+rva-s[2]
        raise ValueError(hex(rva))
    def cstring(self,rva):
        p=self.offset(rva);return bytes(self.data[p:self.data.index(0,p)]).decode('ascii')
    def exports(self):
        rva,size=struct.unpack_from('<II',self.data,self.optional+112)
        p=self.offset(rva);_,_,_,_,_,base,nfunc,nnames,functions,names,ordinals=struct.unpack_from('<IIHHIIIIIII',self.data,p)
        result={}
        for i in range(nnames):
            name_rva=struct.unpack_from('<I',self.data,self.offset(names)+i*4)[0]
            ordinal=struct.unpack_from('<H',self.data,self.offset(ordinals)+i*2)[0]
            result[self.cstring(name_rva)]=struct.unpack_from('<I',self.data,self.offset(functions)+ordinal*4)[0]
        return result
    @staticmethod
    def align(value,alignment):return (value+alignment-1)//alignment*alignment
    def next_section(self):
        return self.align(max(s[2]+s[1] for s in self.sections),self.section_alignment),self.align(len(self.data),self.file_alignment)
    def append_section(self,payload):
        rva,raw=self.next_section();header=self.section_table+self.count*40
        assert header+40<=min(s[4] for s in self.sections if s[4])
        assert not any(self.data[header:header+40])
        rawsize=self.align(len(payload),self.file_alignment)
        self.data.extend(b'\0'*(raw-len(self.data)));self.data.extend(payload);self.data.extend(b'\0'*(rawsize-len(payload)))
        struct.pack_into('<8sIIIIIIHHI',self.data,header,b'.korean\0',len(payload),rva,rawsize,raw,0,0,0,0,0x60000020)
        struct.pack_into('<H',self.data,self.coff+2,self.count+1)
        struct.pack_into('<I',self.data,self.optional+56,self.align(rva+len(payload),self.section_alignment))
        struct.pack_into('<I',self.data,self.optional+64,0)
        return rva,raw

def method_address(cls,name,signature=None):
    code=json.loads((EXTRACT/'code_map.json').read_text('utf-8'))
    t=next(t for t in code if t['type']==cls)
    matches=[m for m in t['methods'] if m['name']==name and (signature is None or signature in m['fullName'])]
    assert len(matches)==1,(cls,name,matches)
    m=matches[0];a=next(a['fields'] for a in m['attributes'] if a['type'].endswith('AddressAttribute'))
    return {k:int(v,16) for k,v in a.items()}

def disassemble(data,rva):
    class Instruction(ctypes.Structure):
        _fields_=[('id',ctypes.c_uint),('address',ctypes.c_uint64),('size',ctypes.c_ushort),('bytes',ctypes.c_ubyte*16),('mnemonic',ctypes.c_char*32),('op_str',ctypes.c_char*160),('detail',ctypes.c_void_p)]
    lib=ctypes.CDLL(str(ROOT/'tools/python_deps/TypeTreeGeneratorAPI/capstone.dll'))
    lib.cs_open.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_size_t)];lib.cs_open.restype=ctypes.c_int
    lib.cs_disasm.argtypes=[ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint64,ctypes.c_size_t,ctypes.POINTER(ctypes.POINTER(Instruction))];lib.cs_disasm.restype=ctypes.c_size_t
    lib.cs_free.argtypes=[ctypes.POINTER(Instruction),ctypes.c_size_t];lib.cs_close.argtypes=[ctypes.POINTER(ctypes.c_size_t)]
    handle=ctypes.c_size_t();assert lib.cs_open(3,8,ctypes.byref(handle))==0
    buffer=ctypes.create_string_buffer(data);insns=ctypes.POINTER(Instruction)();count=lib.cs_disasm(handle,buffer,len(data),rva,0,ctypes.byref(insns))
    result=[{'rva':i.address,'size':i.size,'hex':bytes(i.bytes[:i.size]).hex(),'mnemonic':i.mnemonic.decode(),'operands':i.op_str.decode()} for i in insns[:count]]
    lib.cs_free(insns,count);lib.cs_close(ctypes.byref(handle))
    assert sum(i['size'] for i in result)==len(data),'명령 전체를 해석하지 못함'
    return result

class Assembler:
    def __init__(self,rva):self.rva=rva;self.code=bytearray();self.labels={};self.fixups=[]
    def emit(self,hexbytes):self.code.extend(bytes.fromhex(hexbytes))
    def label(self,name):self.labels[name]=self.rva+len(self.code)
    def relative(self,opcode,target):
        self.emit(opcode);p=len(self.code);self.code.extend(b'\0'*4);self.fixups.append((p,target))
    def finish(self):
        for p,t in self.fixups:struct.pack_into('<i',self.code,p,(self.labels[t] if isinstance(t,str) else t)-(self.rva+p+4))
        return bytes(self.code)
