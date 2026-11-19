"""게임 외 라이브러리의 문자열과 화면 출력 호출을 검색하여 범위를 기록합니다."""
from common import *
from pathlib import Path
import json,re,collections
rows=[];ui=[];assemblies=collections.Counter()
base=EXTRACT/'cpp2il/IsilDump'
for directory in sorted(base.iterdir()):
    if not directory.is_dir() or directory.name=='Assembly-CSharp':continue
    for path in sorted(directory.rglob('*.txt')):
        long_path=Path('\\\\?\\'+str(path))
        text=long_path.read_text('utf-8');digest=sha(long_path)
        for section in text.split('Method: ')[1:]:
            if 'ISIL:' not in section:continue
            method=section.splitlines()[0];body=section.split('ISIL:')[-1]
            literals=re.findall(r'(?ms)^\t\d+ (?:Move|LoadAddress) [^\n,]+, "(.*?)"\s*(?=^\t\d+ |\Z)',body)
            for value in literals:
                rows.append({'assembly':directory.name,'file':str(path.relative_to(EXTRACT)),'file_sha256':digest,'method':method,'source':value,'classification':'UNKNOWN'})
            assemblies[directory.name]+=len(literals)
            if literals and re.search(r'Call (?:TMP_Text\.set_text|Text\.set_text|GUI\.Label|GUI\.Button|GUILayout\.|GUIContent\.\.ctor|DebugUI\.Widget\.set_displayName)',body):
                ui.append({'assembly':directory.name,'file':str(path.relative_to(EXTRACT)),'file_sha256':digest,'method':method,'strings':literals,'calls':[x.strip() for x in body.splitlines() if 'Call ' in x and re.search(r'GUI|Text|DebugUI',x)]})
write_json(WORK/'review/framework_literals.json',rows)
write_json(WORK/'review/framework_ui_candidates.json',ui)
print('라이브러리 문구 위치',len(rows),'화면 호출 후보',len(ui));print(dict(assemblies))
for r in ui:print(r['assembly'],r['file'].split('\\')[-1],r['method'],r['strings'][:15])
