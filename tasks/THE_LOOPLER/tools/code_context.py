"""여러 줄에 걸친 코드 리터럴을 포함해 명령 경계로 추출합니다."""
from common import *
import json,re
rows=[]
for path in sorted((EXTRACT/'cpp2il/IsilDump/Assembly-CSharp').glob('*.txt')):
    for section in path.read_text('utf-8').split('Method: ')[1:]:
        method=section.splitlines()[0]
        if 'ISIL:' not in section:continue
        body=section.split('ISIL:')[-1]
        instructions=re.findall(r'(?ms)^\t\d+ .*?(?=^\t\d+ |\Z)',body)
        for i,inst in enumerate(instructions):
            m=re.match(r'\s*\d+ (?:Move|LoadAddress) [^,]+, "(.*)"\s*$',inst,re.S)
            if not m:continue
            calls=[s.strip() for s in instructions[i+1:i+65] if re.search(r'\bCall ',s) and '0x' not in s and 'il2cpp' not in s]
            rows.append({'file':str(path.relative_to(EXTRACT)),'file_sha256':sha(path),'method':method,'line':inst.strip(),'source':m[1],'calls':calls[:8],'classification':'UNKNOWN'})
write_json(WORK/'review/code_context.json',rows)
print('코드 위치',len(rows),'여러 줄',sum('\n' in r['source'] for r in rows))
