"""배포 후보와 저장이 격리된 화면 검수 사본을 별도로 만든다."""
import json,shutil,subprocess,sys
from pck_tools import ROOT,BASELINE,EXTRACTED,WORK,patch_pack,patch_settings

revision=sys.argv[1] if len(sys.argv)>1 else '01'
assert revision.isdigit() and len(revision)==2
candidate=ROOT/('build_candidate/ALCHEMORTIS_DEMO/ko_1.0.1_c'+revision)
if candidate.exists():raise SystemExit('기존 후보는 덮어쓰지 않습니다.')
shutil.copytree(BASELINE,candidate)
tool=WORK/'toolchain/AssemblyTool/AssemblyTool.dll'
dll='data_Alchemortis_windows_x86_64/Alchemortis.dll'
subprocess.run(['dotnet',str(tool),'patch',str(BASELINE/dll),str(candidate/dll),str(WORK/'translation/code_changes.json')],check=True)
for path,label in [(BASELINE/dll,'original'),(candidate/dll,'candidate')]:
    subprocess.run(['dotnet',str(tool),'dump',str(path),str(WORK/f'discovery/{label}_code.json')],check=True)
settings={'internationalization/locale/translations':['res://resources/translations/'+x+'.po' for x in ['en','ru','de','fr','pt_br','zh_cn','ja','ko']]}
changes={'project.binary':patch_settings((EXTRACTED/'raw/project.binary').read_bytes(),settings),'resources/translations/ko.po':(WORK/'translation/ko_full.po').read_bytes()}
for extension in ['gd','tscn']:changes['korean_patch/inventory_labels.'+extension]=(ROOT/('tasks/ALCHEMORTIS_DEMO/tools_v101/inventory_labels.'+extension)).read_bytes()
for r in json.loads((WORK/'fonts/config.json').read_text(encoding='utf-8'))['fonts']:changes[r['path']]=__import__('pathlib').Path(r['output']).read_bytes()
patch_pack(BASELINE/'Alchemortis Demo.pck',candidate/'Alchemortis Demo.pck',changes)
(WORK/'candidate_changes.json').write_text(json.dumps({'candidate':str(candidate),'settings':settings,'pck_entries':list(changes),'dll':dll},ensure_ascii=False,indent=2),encoding='utf-8')
if '--no-qa' in sys.argv:
    print(candidate)
    raise SystemExit(0)
trial=WORK/('qa_'+revision);game=trial/'game'
shutil.copytree(candidate,game)
(trial/'user').mkdir()
subprocess.run(['dotnet',str(tool),'qa',str(candidate/dll),str(game/dll)],check=True)
qa={
 'application/config/name':'Alchemortis Korean QA', 'application/config/name.demo':'Alchemortis Korean QA',
 'application/config/custom_user_dir_name':'Alchemortis Korean QA','application/config/custom_user_dir_name.demo':'Alchemortis Korean QA',
 'game/settings/save_file_path':str(trial/'user/alchemortis.sav').replace('\\','/'),
 'game/settings/options_file_path':str(trial/'user/options.sav').replace('\\','/'),
 'debug/file_logging/log_path':str(trial/'game.log').replace('\\','/'),
 'steam/initialization/initialize_on_startup':False,'sentry/options/dsn':'','sentry/options/auto_init':False,
 'autoload/KoreanQaObserver':'*res://korean_qa_observer.gd','korean_qa/output':str(trial).replace('\\','/'),
}
patch_pack(candidate/'Alchemortis Demo.pck',game/'Alchemortis Demo.pck',{'project.binary':patch_settings(changes['project.binary'],qa),'korean_qa_observer.gd':(ROOT/'tasks/ALCHEMORTIS_DEMO/tools_v101/qa_observer.gd').read_bytes()})
(trial/'qa_settings.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
print(candidate)
