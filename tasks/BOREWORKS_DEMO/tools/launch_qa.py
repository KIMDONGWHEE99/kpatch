"""저장·설정을 격리하고 실제 검수 프로세스의 경로와 입력 해시를 기록합니다."""
from common import *
from datetime import datetime, timezone
import sys
import ctypes

qa_name, run_id = sys.argv[1:3]
qa = WORK/qa_name
env = os.environ.copy()
env['APPDATA'] = str(WORK/('u_'+run_id))
env['LOCALAPPDATA'] = str(WORK/('l_'+run_id))
for name in ('APPDATA','LOCALAPPDATA'):
    Path(env[name]).mkdir(exist_ok=True)
out = (WORK/(run_id+'.stdout.log')).open('wb')
err = (WORK/(run_id+'.stderr.log')).open('wb')
args = [str(qa/'Boreworks.exe'), '--windowed', '--resolution', '1280x800', '--max-fps', '60', '--log-file', str(WORK/(run_id+'.log'))]
p = subprocess.Popen(args,cwd=qa,env=env,stdout=out,stderr=err)
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];kernel.OpenProcess.restype=ctypes.c_void_p
kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)]
kernel.CloseHandle.argtypes=[ctypes.c_void_p]
handle=kernel.OpenProcess(0x1000,False,p.pid);buffer=ctypes.create_unicode_buffer(32768);size=ctypes.c_uint32(len(buffer))
try:assert kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size))
finally:kernel.CloseHandle(handle)
actual_path=Path(buffer.value)
assert actual_path.resolve()==(qa/'Boreworks.exe').resolve()
row=dict(pid=p.pid,exe=args[0],actual_process_path=str(actual_path),process_query='Windows QueryFullProcessImageNameW',exe_sha256=sha(actual_path.read_bytes()),args=args,start_utc=datetime.now(timezone.utc).isoformat(),pck_sha256=sha((qa/'Boreworks.pck').read_bytes()),dll_sha256=sha((qa/'data_Boreworks_windows_x86_64/Boreworks.dll').read_bytes()),appdata=env['APPDATA'],localappdata=env['LOCALAPPDATA'])
save_json(WORK/(run_id+'_launch.json'),row)
print(json.dumps(row))
