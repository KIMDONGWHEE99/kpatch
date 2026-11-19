"""원본 설치본을 변경하지 않고 소규모 한국어 후보와 격리 검수 사본을 만든다."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, re
from pck_tools import ROOT, BASELINE, EXTRACTED, WORK, patch_pack, patch_settings

trial = WORK/'risk_01'
game = trial/'game'
game.mkdir(parents=True, exist_ok=True)
shutil.copytree(BASELINE, game, dirs_exist_ok=True)
tool = WORK/'toolchain/AssemblyTool/AssemblyTool.dll'
rows = json.loads((WORK/'discovery/code_strings.json').read_text(encoding='utf-8'))
changes = [dict(r, target='ko-KR') for r in rows if r['source']=='en-US' and any('OptionsUtils::'+m in r['method'] for m in ['InitializeDefaultLocale','ApplyOptions','ToModel'])]
(trial/'code_changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
dll = Path('data_Alchemortis_windows_x86_64/Alchemortis.dll')
localized = game/dll.parent/'Alchemortis.localized.dll'
subprocess.run(['dotnet',str(tool),'patch',str(BASELINE/dll),str(localized),str(trial/'code_changes.json')],check=True)
subprocess.run(['dotnet',str(tool),'qa',str(localized),str(game/dll)],check=True)
raw = EXTRACTED/'raw'
po = (raw/'resources/translations/en.po').read_text(encoding='utf-8')
translations = {'UI_START':'시작','UI_QUIT':'종료','UI_SETTINGS':'설정','UI_CONTROLS':'조작법','UI_DISCORD':'디스코드','UI_WISHLIST':'찜하기','UI_UNLOCKS':'해금 목록','UI_TUTORIAL':'튜토리얼','UI_CREDITS':'제작진','UI_BACK':'뒤로','UI_LANGUAGE':'언어','UI_DONE':'완료','UI_CANCEL':'취소','UI_MASTER_VOLUME':'전체 음량','UI_MUSIC_VOLUME':'음악 음량','UI_FULLSCREEN':'전체 화면'}
for k,v in translations.items():
    pattern = r'(msgid '+re.escape(json.dumps(k))+r'\s+msgstr )"[^"\n]*"'
    po,n = re.subn(pattern,lambda m:m[1]+json.dumps(v,ensure_ascii=False),po)
    assert n==1,(k,n)
po=po.replace('Language: en\\n','Language: ko\\n')
settings={
 'internationalization/locale/translations':['res://resources/translations/'+x+'.po' for x in ['en','ru','de','fr','pt_br','zh_cn','ja','ko']],
 'application/config/name':'Alchemortis Korean QA',
 'application/config/name.demo':'Alchemortis Korean QA',
 'application/config/custom_user_dir_name':'Alchemortis Korean QA',
 'application/config/custom_user_dir_name.demo':'Alchemortis Korean QA',
 'game/settings/save_file_path':str(trial/'user/alchemortis.sav').replace('\\','/'),
 'game/settings/options_file_path':str(trial/'user/options.sav').replace('\\','/'),
 'debug/file_logging/log_path':str(trial/'game.log').replace('\\','/'),
 'steam/initialization/initialize_on_startup':False,
 'sentry/options/dsn':'',
 'sentry/options/auto_init':False,
}
(trial/'user').mkdir(exist_ok=True)
patch_pack(BASELINE/'Alchemortis Demo.pck',trial/'roundtrip.pck',{})
assert (trial/'roundtrip.pck').read_bytes()==(BASELINE/'Alchemortis Demo.pck').read_bytes()
patch_pack(BASELINE/'Alchemortis Demo.pck',game/'Alchemortis Demo.pck',{'project.binary':patch_settings((raw/'project.binary').read_bytes(),settings),'resources/translations/ko.po':po.encode('utf-8')})
(trial/'qa_settings.json').write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
print('시험 사본 준비 완료:',game)

