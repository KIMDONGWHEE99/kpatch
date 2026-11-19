"""후보와 실행 검수 사본의 차이를 메서드·객체 단위로 독립 검사합니다."""
from common import *
import subprocess, copy

candidate = ROOT/'build_candidate/COMBOLANDS'/sys.argv[1]/'game'
folder = WORK/sys.argv[2]
game = folder/'game'
allowed_methods = {
    'System.Void SteamManager::Awake()',
    'System.String IO.StateSaver::get_PATH()',
    'System.Void Interaction.CheatsHandler::Start()',
    'System.Void Interaction.CheatsHandler::Update()',
}
records = {}
for label, root in [('candidate', candidate), ('qa', game)]:
    dll = root/'Combolands_Data/Managed/Assembly-CSharp.dll'
    for mode in ['dump', 'metadata']:
        output = folder/f'independent_{label}_{mode}.json'
        subprocess.run(['dotnet', str(WORK/'assembly_tool/AssemblyTool.dll'), mode, str(dll), str(output)], check=True)
        records[label, mode] = json.loads(output.read_text(encoding='utf8'))
assert records['candidate', 'metadata'] == records['qa', 'metadata']
left, right = records['candidate', 'dump'], records['qa', 'dump']
assert [m['method'] for m in left] == [m['method'] for m in right]
changed = []
for a, b in zip(left, right):
    if a == b:
        continue
    name = a['method']
    assert name in allowed_methods, name
    changed.append(name)
    instructions = [(i['op'], i['operand']) for i in b['instructions']]
    if name == 'System.Void SteamManager::Awake()':
        assert instructions == [('ret', None)] and not b['locals'] and not b['handlers']
    elif name == 'System.String IO.StateSaver::get_PATH()':
        assert instructions == [('ldstr', str((folder/'save').resolve())), ('ret', None)] and not b['locals'] and not b['handlers']
    elif name == 'System.Void Interaction.CheatsHandler::Start()':
        assert [(i['op'], i['operand']) for i in a['instructions']] == [('ret', None)]
        assert instructions == [('ldarg.0', None), ('ldc.i4.1', None), ('stfld', 'System.Boolean Interaction.CheatsHandler::_cheatsEnabled'), ('ret', None)]
        assert b['locals'] == a['locals'] and b['handlers'] == a['handlers']
    else:
        assert len(a['instructions']) == len(b['instructions'])
        expected = copy.deepcopy(a)
        count = 0
        for i, instruction in enumerate(expected['instructions'][:-1]):
            next_instruction = expected['instructions'][i+1]
            if instruction['op'] == 'ldc.i4' and instruction['operand'] == '303' and next_instruction['op'] == 'call' and next_instruction['operand'] == 'System.Boolean UnityEngine.Input::GetKey(UnityEngine.KeyCode)':
                instruction.update(op='ldc.i4.1', operand=None)
                next_instruction.update(op='nop', operand=None)
                count += 1
        assert count == 2
        actual = copy.deepcopy(b)
        remap = {y['offset']: x['offset'] for x, y in zip(a['instructions'], b['instructions'])}
        for instruction in actual['instructions']:
            instruction['offset'] = remap[instruction['offset']]
            operand = instruction['operand']
            if operand and operand.startswith('IL_'):
                instruction['operand'] = ','.join('IL_'+format(remap[int(v[3:], 16)], '04X') for v in operand.split(','))
        for handler in actual['handlers']:
            for key in ['start', 'end', 'handler', 'handlerEnd']:
                if handler[key] is not None:
                    handler[key] = remap[handler[key]]
        assert actual == expected, name
assert len(changed) in (2, 4)
if len(changed) == 4:
    assert set(changed) == allowed_methods
else:
    assert set(changed) == {m for m in allowed_methods if 'CheatsHandler' not in m}

special = {'Combolands_Data/globalgamemanagers', 'Combolands_Data/app.info', 'Combolands_Data/Managed/Assembly-CSharp.dll'}
candidate_files = {p.relative_to(candidate).as_posix(): p for p in candidate.rglob('*') if p.is_file()}
qa_files = {p.relative_to(game).as_posix(): p for p in game.rglob('*') if p.is_file()}
assert set(qa_files) == set(candidate_files) | {'Combolands_Data/Managed/Assembly-CSharp.dll.qa.json'}
for path, source in candidate_files.items():
    if path not in special:
        assert sha(source) == sha(qa_files[path]), path
assert qa_files['Combolands_Data/app.info'].read_bytes() == b'Crux QAaaa\r\nComboQA_06'
a = UnityPy.load(str(candidate_files['Combolands_Data/globalgamemanagers'])).file.objects
b = UnityPy.load(str(qa_files['Combolands_Data/globalgamemanagers'])).file.objects
assert list(a) == list(b)
changed_objects = []
for pid, obj in a.items():
    before, after = obj.get_raw_data(), b[pid].get_raw_data()
    if before != after:
        assert obj.type.name == 'PlayerSettings'
        assert before.count(b'Combolands') == before.count(b'Crux Games') == 1
        assert after == before.replace(b'Combolands', b'ComboQA_06').replace(b'Crux Games', b'Crux QAaaa')
        changed_objects.append(pid)
assert len(changed_objects) == 1
save_json(folder/'independent_qa_validation.json', dict(status='PASS', candidate=sys.argv[1], candidate_build_sha256=sha(candidate.parent/'build.json'), methods=changed, player_settings_objects=changed_objects, tool_sha256=sha(__file__), files=[dict(path=k, sha256=sha(v)) for k, v in sorted(qa_files.items())]))
print('PASS', len(changed), 'methods', len(candidate_files), 'files')
