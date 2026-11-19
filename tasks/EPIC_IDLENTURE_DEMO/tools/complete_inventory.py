"""내장 자산과 보조 라이브러리까지 빠짐없이 별도 추출합니다."""
from common import *
import subprocess
def walk(value,path=''):
    if isinstance(value,dict):
        for k,v in value.items():yield from walk(v,path+'/'+k)
    elif isinstance(value,list):
        for i,v in enumerate(value):yield from walk(v,path+'/'+str(i))
    elif isinstance(value,str) and value:yield path,value
g=generator();rows=[];objects=[];media=[];errors=[]
for name in ['Resources/unity default resources','Resources/unity_builtin_extra']:
    e=load(BASE/DATA/name,g)
    for obj in e.objects:
        loc=dict(file=name,path_id=obj.path_id,type=obj.type.name,source_sha256=sha(obj.get_raw_data()))
        try:
            t=obj.read_typetree();objects.append(dict(loc,name=t.get('m_Name')))
            rows.extend(dict(loc,field=k,source=v,classification='UNKNOWN') for k,v in walk(t))
            if obj.type.name=='Texture2D':
                row=dict(loc,name=t.get('m_Name'),classification='MEDIA',disposition='UNKNOWN')
                if t['m_Width'] and t['m_Height']:
                    dest=EXTRACT/'builtin_textures'/f'{obj.path_id}.png';dest.parent.mkdir(exist_ok=True);obj.read().image.save(dest);row['png']=str(dest)
                else:row['empty']=True
                media.append(row)
        except Exception as exc:errors.append(dict(loc,error=str(exc)))
save(EXTRACT/'builtin_strings.json',rows);save(EXTRACT/'builtin_objects.json',objects);save(EXTRACT/'builtin_media.json',media);save(EXTRACT/'builtin_errors.json',errors)
print('내장',len(objects),len(rows),'오류',errors,flush=True)
reports=[]
for p in sorted((BASE/DATA/'Managed').glob('*.dll')):
    out=EXTRACT/'managed_strings'/f'{p.stem}.json';out.parent.mkdir(exist_ok=True)
    if not out.exists():subprocess.run(['dotnet',str(WORK/'assembly_tool/AssemblyTool.dll'),'dumpall',str(p),str(out)],check=True,capture_output=True)
    values=json.loads(out.read_text(encoding='utf8'));reports.append(dict(file=p.name,sha256=sha(p.read_bytes()),string_count=len(values),extraction_sha256=sha(out.read_bytes())))
save(WORK/'managed_inventory.json',reports);print('관리 코드',len(reports),sum(r['string_count'] for r in reports))
