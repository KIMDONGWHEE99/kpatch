"""화면 명령 완료를 확인한 뒤 다음 명령을 보냅니다."""
import argparse
import json
import time
import ctypes
from ctypes import wintypes
from pathlib import Path
from common import WORK, write_json


def process_running(pid):
    # 개별 프로세스 접근 권한을 요구하지 않고 현재 PID 목록만 읽습니다.
    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        found = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while found:
            if entry.th32ProcessID == pid:
                return True
            found = kernel.Process32NextW(handle, ctypes.byref(entry))
        error = ctypes.get_last_error()
        if error != 18:  # ERROR_NO_MORE_FILES가 아닌 실패를 종료로 오인하지 않습니다.
            raise ctypes.WinError(error)
        return False
    finally:
        kernel.CloseHandle(handle)


def run_step(output, step):
    action, _, value = step.partition(":")
    ident = time.strftime("%H%M%S") + "_" + str(time.time_ns())[-7:] + "_" + action
    temporary = output / "command.tmp"
    write_json(temporary, {"id": ident, "action": action, "value": value,
                          "capture": action not in ("quit", "unlock", "unlock_all")})
    temporary.replace(output / "command.json")
    # 정상 종료는 게임의 다음 프레임을 기다리는 결과 파일을 남길 수 없습니다.
    if action == "quit":
        pid = json.loads((output / "runtime.json").read_text(encoding="utf-8"))["pid"]
        deadline = time.monotonic() + 30
        while process_running(pid):
            if time.monotonic() > deadline:
                raise TimeoutError("검수 게임 정상 종료 대기")
            time.sleep(.2)
        result = {"id": ident, "action": action, "status": "EXITED", "pid": pid,
                  "check_method": "CreateToolhelp32Snapshot/TH32CS_SNAPPROCESS"}
        write_json(output / (ident + ".exit.json"), result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return result
    result_path = output / (ident + ".result.json")
    deadline = time.monotonic() + 40
    while not result_path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError(ident)
        time.sleep(.2)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    image = output / (ident + ".png")
    result["image"] = str(image) if image.exists() else None
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if result["status"] == "FAIL":
        raise RuntimeError(result["error"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--step", action="append", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.relative_to(WORK.resolve())
    assert (output / "runtime.json").is_file(), "실제 실행 경로부터 확인해야 합니다."
    for step in args.step:
        run_step(output, step)
