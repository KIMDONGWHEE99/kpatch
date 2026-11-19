"""REA의 PE 주소와 원본 파일을 대조하는 소규모 x86 보조 판독기."""
import ctypes
import json
import sys
from pathlib import Path
import pefile

ROOT = Path(__file__).resolve().parents[2]
CAPSTONE = ROOT / "tools/python_deps/TypeTreeGeneratorAPI/capstone.dll"

class Instruction(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint), ("address", ctypes.c_uint64), ("size", ctypes.c_uint16),
                ("bytes", ctypes.c_ubyte * 16), ("mnemonic", ctypes.c_char * 32),
                ("op_str", ctypes.c_char * 160), ("detail", ctypes.c_void_p)]

def disassemble(path, address, length):
    image = pefile.PE(str(path), fast_load=False)
    imports = {}
    for table_name in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
        for entry in getattr(image, table_name, []):
            for item in entry.imports:
                imports[item.address] = entry.dll.decode() + ":" + (item.name.decode() if item.name else str(item.ordinal))
    cap = ctypes.CDLL(str(CAPSTONE))
    cap.cs_open.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    cap.cs_disasm.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_size_t, ctypes.POINTER(ctypes.POINTER(Instruction))]
    cap.cs_disasm.restype = ctypes.c_size_t
    cap.cs_free.argtypes = [ctypes.POINTER(Instruction), ctypes.c_size_t]
    cap.cs_close.argtypes = [ctypes.POINTER(ctypes.c_size_t)]
    handle = ctypes.c_size_t()
    assert cap.cs_open(3, 4, ctypes.byref(handle)) == 0
    raw = image.get_data(address - image.OPTIONAL_HEADER.ImageBase, length)
    buff = ctypes.create_string_buffer(raw)
    pointer = ctypes.POINTER(Instruction)()
    count = cap.cs_disasm(handle.value, buff, len(raw), address, 0, ctypes.byref(pointer))
    result = []
    for i in range(count):
        value = pointer[i]
        args = value.op_str.decode()
        names = [name for target, name in imports.items() if hex(target) in args]
        result.append({"address":hex(value.address), "bytes":bytes(value.bytes[:value.size]).hex(),
                       "instruction":value.mnemonic.decode()+" "+args, "imports":names})
    cap.cs_free(pointer, count)
    cap.cs_close(ctypes.byref(handle))
    return result

if __name__ == "__main__":
    rows = disassemble(Path(sys.argv[1]), int(sys.argv[2],0), int(sys.argv[3],0))
    if len(sys.argv)>4:
        Path(sys.argv[4]).write_text(json.dumps(rows,indent=2),encoding="utf-8")
    for row in rows:
        print(row["address"],row["instruction"]," ".join(row["imports"]))
