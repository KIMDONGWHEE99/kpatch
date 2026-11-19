"""모든 관리 코드의 표시 후보·참조·자동 초기화 위치를 해시와 함께 추출합니다."""
from common import *
import subprocess

out = EXTRACT/'code_scope'
out.mkdir(exist_ok=True)
tool = WORK/'assembly_tool/AssemblyTool.dll'
records = []
for dll in sorted((DATA/'Managed').glob('*.dll')):
    target = out/(dll.stem+'.json')
    subprocess.run(['dotnet',str(tool),'surface',str(dll),str(target)],check=True,capture_output=True)
    data = json.loads(target.read_text(encoding='utf8'))
    methods = [m for t in data['types'] for m in t['methods']]
    records.append(dict(file=dll.name,sha256=sha(dll),report_sha256=sha(target),types=len(data['types']),methods=len(methods),literals=sum(len(m['literals']) for m in methods),initializers=[m['method'] for m in methods if any('RuntimeInitializeOnLoadMethod' in a for a in m['attributes'])]))
save_json(out/'manifest.json',dict(tool_sha256=sha(tool),assemblies=records,status='NOT_RUN',reason='추출 완료; 표시 후보·진입점의 검토는 별도 판정'))
print('추출',len(records),'개 라이브러리',sum(r['literals'] for r in records),'개 코드 문자열')
