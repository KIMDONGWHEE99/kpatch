from pathlib import Path
import sys,json,hashlib,shutil,subprocess,os
ROOT=Path.cwd();W=ROOT/'working_private/ALCHEMORTIS_DEMO';E=ROOT/'extracted_private/ALCHEMORTIS_DEMO/steam_25423154';B=ROOT/'source_original/ALCHEMORTIS_DEMO/steam_25423154'
sys.path.insert(0,str(ROOT/'tools/python_deps'))
from fontTools.ttLib import TTFont
report=[]
for p in (E/'recovered/resources/fonts/source').glob('*.ttf'):
 f=TTFont(p);c=f.getBestCmap();report.append({'font':p.name,'glyphs':len(c),'hangul':sum(0xac00<=i<=0xd7a3 for i in c),'test':all(ord(i) in c for i in '한국어설정시작종료')})
print(json.dumps(report,ensure_ascii=False,indent=2));(W/'discovery/font_cmaps.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
