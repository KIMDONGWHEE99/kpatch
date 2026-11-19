"""후보를 다시 열어 위치별 번역과 수정 경계를 독립 비교합니다."""
import sys
import re
import collections
from common import *

candidate_id=sys.argv[1]
candidate=ROOT/'build_candidate/BOREWORKS_DEMO'/candidate_id
stage=WORK/candidate_id
original=read_pack(BASE/'Boreworks.pck')[3]
actual=read_pack(candidate/'Boreworks.pck')[3]
expected=json.loads((WORK/'translation/ko.json').read_text(encoding='utf-8'))
source=json.loads((WORK/'english.json').read_text(encoding='utf-8'))
assert set(original)==set(actual)
changed=[name for name in original if original[name]['data']!=actual[name]['data']]
assert set(changed)=={'localization/strings.en.translation'}|{k for k in original if k.endswith('.fontdata')}
reextracted=stage/'reextracted';reextracted.mkdir(exist_ok=True)
for k in changed:
    p=reextracted/k;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(actual[k]['data'])
script=WORK/'resource_probe/verify.gd'
script.write_text('''extends SceneTree
func _initialize():
 var args = OS.get_cmdline_user_args()
 var t = ResourceLoader.load(args[0])
 if t == null:
  quit(2)
  return
 var rows = {}
 for k in t.get_message_list():
  rows[str(k)] = str(t.get_message(k))
 var f = FileAccess.open(args[1], FileAccess.WRITE)
 f.store_string(JSON.stringify(rows, "  "))
 f.close()
 print("REEXTRACTED ", rows.size())
 quit()
''',encoding='utf-8')
godot(script,[reextracted/'localization/strings.en.translation',stage/'actual_ko.json'],'verify_'+candidate_id)
observed=json.loads((stage/'actual_ko.json').read_text(encoding='utf-8'))
unchanged=verify_translation(source,expected,observed)
before_methods=json.loads((EXTRACT/'code/Boreworks.il.json').read_text(encoding='utf-8'))
after_methods={m['method']:m for m in json.loads((stage/'Boreworks.il.json').read_text(encoding='utf-8'))}
text_changes={(r['method'],r['offset']):r for r in json.loads((stage/'code_changes.json').read_text(encoding='utf-8'))}
old_font='Godot.SystemFont Game.UI.Framework.BoreworksTheme::BuildSystemFont(System.Boolean)'
new_font='Godot.Font Game.UI.Framework.BoreworksTheme::BuildSystemFont(System.Boolean)'
counts=collections.Counter()
for method in before_methods:
    name=method['method']; newname=new_font if name==old_font else name
    other=after_methods.pop(newname)
    if name==old_font:
        body=other['instructions']
        assert [i['op'] for i in body]==['ldarg.0','brfalse','ldstr','br','ldstr','call','ret']
        assert [i['operand'] for i in body if i['op']=='ldstr']==['res://Art/Assets/UI/Fonts/PixelOperator-Bold.ttf','res://Art/Assets/UI/Fonts/PixelOperator.ttf']
        counts['font_loader']+=1
        continue
    assert method['locals']==other['locals'] and method['handlers']==other['handlers'],name
    assert len(method['instructions'])==len(other['instructions']),name
    for left,right in zip(method['instructions'],other['instructions']):
        if (name,left['offset']) in text_changes:
            row=text_changes[(name,left['offset'])]
            assert left['op']==right['op']=='ldstr' and left['operand']==row['source'] and right['operand']==row['target']
            counts['text_positions']+=1
        elif left['operand']==old_font:
            assert right==dict(left,operand=new_font);counts['font_calls']+=1
        elif name.startswith('System.Void Game.PlayerNode::') and left['operand']=='Godot.Font Godot.ThemeDB::get_FallbackFont()':
            assert right==dict(left,operand='Godot.Font Game.UI.Framework.BoreworksTheme::get_LabelFont()');counts['hud_font_calls']+=1
        else:
            assert left==right,(name,left,right)
assert not after_methods and counts['text_positions']==len(text_changes) and counts['font_loader']==1 and counts['font_calls']==2 and counts['hud_font_calls']==1
baseline=json.loads((WORK/'baseline.json').read_text(encoding='utf-8'))
changed_files=[]
for f in baseline:
    p=candidate/f['path'];assert p.exists()
    if sha(p.read_bytes())!=f['sha256']:changed_files.append(f['path'])
assert set(changed_files)=={'Boreworks.pck','data_Boreworks_windows_x86_64/Boreworks.dll'}
assert len([p for p in candidate.rglob('*') if p.is_file()])==len(baseline)
save_json(stage/'static_report.json',dict(status='PASS',candidate=candidate_id,translation_locations=len(observed),retained_keys=unchanged,pck_changed_entries=changed,code_counts=dict(counts),candidate_files=len(baseline),changed_files=changed_files,unknown_changes=0,empty_targets=0,token_errors=0,method_count=len(before_methods)))
print('STATIC_PASS',len(observed),dict(counts))
