"""코드 영역 문자 후보를 도달 가능한 x86 명령 바이트와 대조합니다."""
import bisect
import collections
import ctypes
import json
import re
import struct
from pathlib import Path
import pefile
from native_inspect import Instruction, CAPSTONE
from dat_container import sha

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "source_original/THE_HORDE_OF_GORAK/steam_26336311"
OUT = ROOT / "working_private/THE_HORDE_OF_GORAK/investigation_20261031"


def main():
    cap = ctypes.CDLL(str(CAPSTONE))
    cap.cs_open.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    cap.cs_option.argtypes = [ctypes.c_size_t, ctypes.c_int, ctypes.c_size_t]
    cap.cs_disasm.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_size_t, ctypes.POINTER(ctypes.POINTER(Instruction))]
    cap.cs_disasm.restype = ctypes.c_size_t
    cap.cs_free.argtypes = [ctypes.POINTER(Instruction), ctypes.c_size_t]
    cap.cs_close.argtypes = [ctypes.POINTER(ctypes.c_size_t)]
    handle = ctypes.c_size_t()
    assert cap.cs_open(3, 4, ctypes.byref(handle)) == 0
    assert cap.cs_option(handle, 5, 3) == 0  # Capstone CS_OPT_SKIPDATA/CS_OPT_ON
    path = OUT / "native_code_byte_candidates.jsonl"
    rows = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]
    files, summaries = sorted({row["file"] for row in rows}), []
    for name in files:
        data = (BASE / name).read_bytes()
        image = pefile.PE(data=data)
        base = image.OPTIONAL_HEADER.ImageBase
        instructions, address_to_offset, relocated, executable_ranges = {}, {}, set(), []
        for section in image.sections:
            if not section.Characteristics & 0x20000000:
                continue
            raw = section.get_data()
            executable_ranges.append((base + section.VirtualAddress, base + section.VirtualAddress + len(raw), section.PointerToRawData))
            buffer = ctypes.create_string_buffer(raw)
            pointer = ctypes.POINTER(Instruction)()
            count = cap.cs_disasm(handle.value, buffer, len(raw), base + section.VirtualAddress, 0, ctypes.byref(pointer))
            for index in range(count):
                value = pointer[index]
                if not value.id:
                    continue
                offset = section.PointerToRawData + value.address - base - section.VirtualAddress
                instruction = {"address": value.address, "offset": offset, "bytes": bytes(value.bytes[:value.size]).hex(),
                               "length": value.size, "mnemonic": value.mnemonic.decode(), "operands": value.op_str.decode()}
                instructions[value.address] = instruction
                address_to_offset[value.address] = offset
            cap.cs_free(pointer, count)
        def is_code(address):
            return any(left <= address < right for left, right, _ in executable_ranges)

        seeds = {base + image.OPTIONAL_HEADER.AddressOfEntryPoint: "PE entry point"}
        if hasattr(image, "DIRECTORY_ENTRY_EXPORT"):
            for entry in image.DIRECTORY_ENTRY_EXPORT.symbols:
                if is_code(base + entry.address):
                    seeds[base + entry.address] = "PE export"
        if hasattr(image, "DIRECTORY_ENTRY_LOAD_CONFIG"):
            config = image.DIRECTORY_ENTRY_LOAD_CONFIG.struct
            table, count = getattr(config, "SEHandlerTable", 0), getattr(config, "SEHandlerCount", 0)
            if table and count:
                offset = image.get_offset_from_rva(table - base)
                for index in range(count):
                    target = base + struct.unpack_from("<I", data, offset + index * 4)[0]
                    if is_code(target):
                        seeds[target] = "PE SafeSEH handler RVA table"
        for block in getattr(image, "DIRECTORY_ENTRY_BASERELOC", []):
            for entry in block.entries:
                if entry.type != 3:
                    continue
                try:
                    offset = image.get_offset_from_rva(entry.rva)
                    target = struct.unpack_from("<I", data, offset)[0]
                except (pefile.PEFormatError, struct.error):
                    continue
                relocated.update(range(offset, offset + 4))
                if is_code(target):
                    seeds.setdefault(target, "relocated function/address reference")
        seen, work = set(), list(seeds)
        while work:
            address = work.pop()
            if address in seen or not is_code(address):
                continue
            left, right, raw_start = next(item for item in executable_ranges if item[0] <= address < item[1])
            start = raw_start + address - left
            raw = data[start:start + min(512, right - address)]
            buffer = ctypes.create_string_buffer(raw)
            pointer = ctypes.POINTER(Instruction)()
            count = cap.cs_disasm(handle.value, buffer, len(raw), address, 64, ctypes.byref(pointer))
            for index in range(count):
                value = pointer[index]
                address = value.address
                if address in seen or not value.id:
                    break
                item = {"address": address, "offset": raw_start + address - left, "bytes": bytes(value.bytes[:value.size]).hex(),
                        "length": value.size, "mnemonic": value.mnemonic.decode(), "operands": value.op_str.decode()}
                instructions[address] = item
                seen.add(address)
                mnemonic, operands = item["mnemonic"], item["operands"]
                if mnemonic.startswith("j") or mnemonic in ("call", "loop", "loope", "loopne"):
                    if re.fullmatch(r"0x[0-9a-f]+", operands):
                        target = int(operands, 16)
                        if target not in seen:
                            work.append(target)
                if mnemonic in ("ret", "retf", "iret", "iretd", "jmp", "int3", "ud2"):
                    break
            else:
                if count:
                    work.append(address + item["length"])
            cap.cs_free(pointer, count)
        ordered = sorted((instructions[address]["offset"], address) for address in seen)
        offsets = [item[0] for item in ordered]
        file_rows = [row for row in rows if row["file"] == name]
        for row in file_rows:
            start, end = row["offset"], row["offset"] + row["bytes"]
            index = max(0, bisect.bisect_right(offsets, start) - 1)
            covered, proof, immediate = set(), [], False
            while index < len(ordered) and ordered[index][0] < end:
                item = instructions[ordered[index][1]]
                left, right = item["offset"], item["offset"] + item["length"]
                if right > start:
                    covered.update(range(max(start, left), min(end, right)))
                    proof.append(item)
                    # 네 글자 이상 즉시값은 스택에서 문구를 조립할 수 있으므로 명령 영역이라는 이유만으로 제외하지 않습니다.
                    if item["mnemonic"] in ("mov", "push") and item["length"] >= 5:
                        tail = data[right - 4:right]
                        if all(32 <= byte < 127 for byte in tail) and not all(pos in relocated for pos in range(right - 4, right)):
                            immediate = True
                index += 1
            row["instruction_evidence"] = proof
            if len(covered) == end - start and not immediate:
                row.update(type="REACHABLE_X86_INSTRUCTION_BYTES", classification="INTERNAL",
                           reason="PE진입점/내보내기/재배치주소참조에서 직접분기와연속명령으로따라간x86명령이 후보바이트전부를덮음. 4바이트이상문자즉시값조립후보는별도유지")
            elif len(covered) == end - start:
                row.update(type="INSTRUCTION_TEXT_IMMEDIATE_CANDIDATE", classification="UNKNOWN",
                           reason="코드명령의4바이트즉시값에문자가있음. 스택문구조합/숫자상수여부를소비함수로확인필요")
            else:
                row.update(type="UNPROVEN_EXECUTABLE_BYTE_RUN", classification="UNKNOWN",
                           reason="현재진입점/분기추적으로후보전부의명령경계가확정되지않음. 내장상수/코드/패딩여부추가근거필요")
        summaries.append({"file": name, "sha256": sha(data), "decoded_instructions": len(instructions), "reachable_instructions": len(seen),
                          "seeds": dict(collections.Counter(seeds.values())), "candidate_types": dict(collections.Counter(row["type"] for row in file_rows))})
    cap.cs_close(ctypes.byref(handle))
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    result = {"status": "PARTIAL", "method": "Capstone4 x86-32 선형명령판독 후 PE entry/export 및 relocation code-address seed에서 직접분기/연속명령추적",
              "capstone_sha256": sha(CAPSTONE.read_bytes()), "files": summaries,
              "types": dict(collections.Counter(row["type"] for row in rows)),
              "limits": ["간접호출·가상함수대상의완전한흐름복원아님", "도달한기계명령내문자즉시값은별도UNKNOWN으로보존", "실제게임프로세스에접근하지않음"]}
    (OUT / "native_code_typing_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["types"]))


if __name__ == "__main__":
    main()
