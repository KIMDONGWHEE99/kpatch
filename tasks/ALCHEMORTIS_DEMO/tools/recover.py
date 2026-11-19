from pathlib import Path
import os,subprocess,json,re
r=Path.cwd(); w=r/'working_private/ALCHEMORTIS_DEMO/discovery'; e=os.environ.copy()
for k,n in [('APPDATA','roaming'),('LOCALAPPDATA','local')]:
 p=w/n;p.mkdir(parents=True,exist_ok=True);e[k]=str(p)
cmd=[str(r/'tools/gdre_2.6.4/bin/gdre_tools.exe'),'--headless','--recover='+str(r/'source_original/ALCHEMORTIS_DEMO/steam_25423154/Alchemortis Demo.pck'),'--output='+str(r/'extracted_private/ALCHEMORTIS_DEMO/steam_25423154/recovered')]
p=subprocess.Popen(cmd,env=e,stdout=(w/'gdre.stdout.log').open('wb'),stderr=(w/'gdre.stderr.log').open('wb'))
(w/'gdre_launch.json').write_text(json.dumps({'pid':p.pid,'command':cmd},ensure_ascii=False,indent=2),encoding='utf-8');print('gdre pid',p.pid)

