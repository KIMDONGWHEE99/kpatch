"""번역에 필요한 글자를 계산하고 보조 글꼴을 모든 원본 글꼴에 연결한다."""
import json,os,subprocess,sys
from pck_tools import ROOT,WORK,BASELINE,EXTRACTED
sys.path.insert(0,str(ROOT/'tools/python_deps'))
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

runtime=WORK/'resource_probe'
runtime.mkdir(exist_ok=True)
(runtime/'project.godot').write_text('config_version=5\n[application]\nconfig/name="Alchemortis Resource Verification"\n',encoding='utf-8')
output=WORK/'fonts';output.mkdir(exist_ok=True)
texts=list(json.loads((WORK/'translation/ko_full.json').read_text(encoding='utf-8')).values())
texts += [r['target'] for r in json.loads((WORK/'translation/code_changes.json').read_text(encoding='utf-8'))]
chars=''.join(sorted(set(''.join(texts)+'한국어')))
chars=''.join(c for c in chars if not c.isspace())
for weight in [400,700]:
    font=TTFont(ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf')
    font=instantiateVariableFont(font,{'wght':weight},inplace=True)
    options=subset.Options();options.name_IDs=['*'];options.name_legacy=True;options.name_languages=['*']
    subsetter=subset.Subsetter(options=options);subsetter.populate(text=chars);subsetter.subset(font)
    font.save(output/f'AlchemortisKoreanFallback{weight}.ttf')
fontpaths=sorted((EXTRACTED/'raw/.godot/imported').glob('*.fontdata'))
config={'characters':list(chars),'fonts':[{'path':p.relative_to(EXTRACTED/'raw').as_posix(),'output':str(output/p.name).replace('\\','/'),'korean_font':str(output/('AlchemortisKoreanFallback700.ttf' if 'Black' in p.name or 'Grandeur' in p.name else 'AlchemortisKoreanFallback400.ttf')).replace('\\','/')} for p in fontpaths], 'report':str(output/'engine_report.json').replace('\\','/')}
(output/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
env=os.environ.copy();env['APPDATA']=str(runtime/'roaming');env['LOCALAPPDATA']=str(runtime/'local')
command=[str(ROOT/'tools/gdre_2.6.4/bin/gdre_tools.exe'),'--headless','--path',str(runtime),'--log-file',str(runtime/'font.log'),'--script',str(ROOT/'tasks/ALCHEMORTIS_DEMO/tools/font_fallbacks.gd'),'--',str(BASELINE/'Alchemortis Demo.pck'),str(output/'config.json')]
p=subprocess.run(command,env=env,capture_output=True,timeout=90)
(runtime/'font.stdout.log').write_bytes(p.stdout);(runtime/'font.stderr.log').write_bytes(p.stderr)
print(p.stdout.decode('utf-8',errors='replace'));print(p.stderr.decode('utf-8',errors='replace'));assert p.returncode==0
report=json.loads((output/'engine_report.json').read_text(encoding='utf-8'))
print('글꼴',len(report),'필요 문자',len(chars),'누락',sum(len(r['missing']) for r in report))
assert not any(r['missing'] for r in report)
