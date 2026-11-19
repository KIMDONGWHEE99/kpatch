"""코드를 실행하지 않는 데이터 전용 로드로 Windows 문자열 소비를 확인합니다."""
import ctypes
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "working_private/THE_HORDE_OF_GORAK/native_candidate_01"


def main():
    report = json.loads((BASE / "native_patch_audit.json").read_text(encoding="utf-8"))
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
    kernel.LoadLibraryExW.restype = ctypes.c_void_p
    kernel.FreeLibrary.argtypes = [ctypes.c_void_p]
    user.LoadStringW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_int]
    user.LoadStringW.restype = ctypes.c_int
    results, handles = [], {}
    try:
        for row in report["translations"]:
            if row["kind"] != "RT_STRING":
                continue
            name = row["file"]
            if name not in handles:
                # AS_DATAFILE(2)|AS_IMAGE_RESOURCE(32): DllMain/초기화 코드를 실행하지 않습니다.
                handle = kernel.LoadLibraryExW(str(BASE / name), None, 0x22)
                assert handle, (name, ctypes.get_last_error())
                handles[name] = handle
            buffer = ctypes.create_unicode_buffer(1024)
            length = user.LoadStringW(handles[name], row["string_id"], buffer, len(buffer))
            assert length == len(row["target"]) and buffer.value == row["target"], (name, row["string_id"], buffer.value)
            results.append({"file": name, "id": row["string_id"], "expected": row["target"], "actual": buffer.value, "status": "PASS"})
    finally:
        for handle in handles.values():
            kernel.FreeLibrary(handle)
    result = {"status": "PASS", "method": "LoadLibraryExW flags0x22 data-only + LoadStringW", "game_executed": False,
              "graphics_qa": "NOT_RUN", "records": results}
    (BASE / "windows_resource_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "resource_strings": len(results), "game_executed": False}))


if __name__ == "__main__":
    main()
