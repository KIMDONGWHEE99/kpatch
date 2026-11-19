"""검토한 번역·고정 굵기 글꼴로 독립 후보를 생성합니다."""
import sys
import json
import shutil
import subprocess
import os
from common import *

sys.path.insert(0, str(ROOT/'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset

candidate_id = sys.argv[1]
candidate = ROOT/'build_candidate/BOREWORKS_DEMO'/candidate_id
if candidate.exists():
    raise RuntimeError('기존 후보는 덮어쓰지 않습니다.')
stage = WORK/candidate_id
stage.mkdir(parents=True, exist_ok=True)
ko = json.loads((WORK/'translation/ko.json').read_text(encoding='utf-8'))
synthetic = json.loads((WORK/'translation/synthetic_ko.json').read_text(encoding='utf-8'))
source_literals = json.loads((WORK/'Boreworks.literals.json').read_text(encoding='utf-8'))
code_changes = []
for row in source_literals:
    target = None
    if 'Game.UI.HoverTooltipNode::Synthetic' in row['method']:
        target = synthetic[row['text']]
    elif row['method'] == 'System.Void Game.Main::TickScreenshot()' and row['text'] == 'Screenshot: ':
        target = '스크린샷: '
    elif 'Game.Settings.Keybinds::MouseDisplayName(Godot.MouseButton,' in row['method'] and row['text'] == 'Mouse ':
        target = '마우스 '
    elif 'Game.UI.HoverTooltipContent::AddDistrict(' in row['method'] and row['text'] == ' (id ':
        target = ' (내부 번호 '
    if target is not None:
        code_changes.append(dict(method=row['method'], offset=row['offset'], source=row['text'], target=target))
save_json(stage/'code_changes.json', code_changes)
characters = set(''.join(ko.values()) + ''.join(synthetic.values()) + ''.join(r['target'] for r in code_changes))
characters.update(chr(i) for i in range(32, 127))
for row in source_literals:
    if 'Game.UI.CreditsScreenNode::' in row['method']:
        characters.update(row['text'])
characters -= set('\r\n\t')
font_source = ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf'
reports = []
for weight in (400, 700):
    font = TTFont(font_source)
    needed = {ord(c) for c in characters}
    missing = needed-set(font.getBestCmap())
    fallback = TTFont('C:/Windows/Fonts/segoeui.ttf')
    if not missing.issubset(fallback.getBestCmap()):
        raise RuntimeError('대체 글꼴까지 문자 누락: '+repr(missing-set(fallback.getBestCmap())))
    supported = needed - missing
    font = instantiateVariableFont(font, {'wght':weight}, inplace=True)
    options = subset.Options(); options.name_IDs=['*']; options.name_legacy=True; options.name_languages=['*']
    sub = subset.Subsetter(options=options); sub.populate(unicodes=supported); sub.subset(font)
    font.recalcTimestamp=False
    target = stage/f'Korean{weight}.ttf'; font.save(target)
    checked = TTFont(target)
    assert supported.issubset(checked.getBestCmap()) and checked['OS/2'].usWeightClass == weight
    reports.append(dict(weight=weight, sha256=sha(target.read_bytes()), characters=len(needed), primary_characters=len(supported), fallback_characters=sorted(missing), fallback_source_sha256=sha(Path('C:/Windows/Fonts/segoeui.ttf').read_bytes()), missing=[]))
    # 실제 게임과 동일한 Godot 4.6.3 실행 파일로 자산을 저장합니다.
    env=os.environ.copy(); env['APPDATA']=str(WORK/'native_env/roaming'); env['LOCALAPPDATA']=str(WORK/'native_env/local')
    command=[str(WORK/'native_export/Boreworks.exe'),'--headless','--log-file',str(stage/f'export{weight}.log'),'--',str(WORK/'translation/ko.json'),str(stage/'strings.en.translation'),str(target),str(stage/f'Korean{weight}.fontdata')]
    result=subprocess.run(command,env=env,capture_output=True,timeout=60)
    (stage/f'export{weight}.stdout.log').write_bytes(result.stdout)
    (stage/f'export{weight}.stderr.log').write_bytes(result.stderr)
    assert result.returncode==0 and b'SAVE_FONT 0' in result.stdout and b'SAVE_TRANSLATION 0' in result.stdout
    assert (stage/f'Korean{weight}.fontdata').exists() and (stage/'strings.en.translation').exists()
save_json(stage/'font_report.json',reports)
(stage/'required_characters.txt').write_text(''.join(sorted(characters)),encoding='utf-8')
shutil.copytree(BASE,candidate)
originals=read_pack(BASE/'Boreworks.pck')[3]
changes={'localization/strings.en.translation':(stage/'strings.en.translation').read_bytes()}
for name in originals:
    if name.endswith('.fontdata'):
        weight=700 if 'Bold' in name else 400
        changes[name]=(stage/f'Korean{weight}.fontdata').read_bytes()
patch_pack(BASE/'Boreworks.pck',candidate/'Boreworks.pck',changes)
command=['dotnet',str(WORK/'toolchain/AssemblyPatch/AssemblyPatch.dll'),'patch',str(BASE/'data_Boreworks_windows_x86_64/Boreworks.dll'),str(candidate/'data_Boreworks_windows_x86_64/Boreworks.dll'),str(stage/'code_changes.json')]
subprocess.run(command,check=True)
save_json(stage/'build_manifest.json',dict(candidate_id=candidate_id,translation_sha256=sha((WORK/'translation/ko.json').read_bytes()),code_changes_sha256=sha((stage/'code_changes.json').read_bytes()),pck_changes=[dict(path=k,sha256=sha(v)) for k,v in changes.items()],files=[dict(path=f.relative_to(candidate).as_posix(),size=f.stat().st_size,sha256=sha(f.read_bytes())) for f in sorted(candidate.rglob('*')) if f.is_file()]))
print(json.dumps(dict(candidate=candidate_id,keys=len(ko),code_texts=len(code_changes),fonts=reports),ensure_ascii=False))
