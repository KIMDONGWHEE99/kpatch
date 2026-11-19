"""게임에 포함된 .NET 9 참조로 검수 도구만 독립 컴파일한다."""
from pck_tools import ROOT,WORK,BASELINE
import struct,subprocess
out=WORK/'toolchain/QaRunner';out.mkdir(exist_ok=True)
refs=[]
for path in (BASELINE/'data_Alchemortis_windows_x86_64').glob('*.dll'):
    data=path.read_bytes()
    if data[:2]!=b'MZ':continue
    pe=struct.unpack_from('<I',data,60)[0];optional=pe+24
    magic=struct.unpack_from('<H',data,optional)[0]
    if magic not in (0x10b,0x20b):continue
    directory=optional+(112 if magic==0x20b else 96)
    if struct.unpack_from('<I',data,directory+14*8)[0]:refs.append(path)
lines=['/noconfig','/nostdlib+','/target:library','/langversion:latest','/nullable:enable','/out:"'+str(out/'QaRunner.dll')+'"']
lines += ['/reference:"'+str(path)+'"' for path in refs]
lines += ['"'+str(ROOT/'tasks/ALCHEMORTIS_DEMO/tools_v101/QaRunner/Runner.cs')+'"']
rsp=out/'compile.rsp';rsp.write_text('\n'.join(lines),encoding='utf-8-sig')
p=subprocess.run(['dotnet','C:/Program Files/dotnet/sdk/8.0.418/Roslyn/bincore/csc.dll','@'+str(rsp)],capture_output=True)
(out/'build.stdout.log').write_bytes(p.stdout);(out/'build.stderr.log').write_bytes(p.stderr)
print(p.stdout.decode('utf-8',errors='replace'));print(p.stderr.decode('utf-8',errors='replace'));assert p.returncode==0
print('참조 DLL',len(refs),'검수 도구 컴파일 완료')
