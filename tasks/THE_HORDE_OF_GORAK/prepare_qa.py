"""소규모 후보에 검수 전용 창 설정을 적용하고 원본과 차이를 기록한다."""
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path
from dat_container import DatFile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'source_original/THE_HORDE_OF_GORAK/steam_26336311'
if '--base' in sys.argv:
    BASE = Path(sys.argv[sys.argv.index('--base') + 1]).resolve()
    BASE.relative_to(ROOT)
RUN = sys.argv[1] if len(sys.argv) > 1 else 'qa_s01'
if not RUN.startswith('qa_') or not RUN.replace('_', '').isalnum():
    raise SystemExit('잘못된 실행 ID입니다.')
QA = ROOT / 'working_private/THE_HORDE_OF_GORAK' / RUN
SMOKE = ROOT / 'working_private/THE_HORDE_OF_GORAK/container_tests/korean_smoke/THOG.dat'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if QA.exists():
        raise SystemExit('기존 검수 폴더를 덮어쓰지 않습니다.')
    shutil.copytree(BASE, QA / 'game')
    native_inputs = []
    if '--native' in sys.argv:
        native = Path(sys.argv[sys.argv.index('--native') + 1]).resolve()
        if not native.is_relative_to(ROOT / 'working_private/THE_HORDE_OF_GORAK'):
            raise SystemExit('네이티브 후보는 지정된 비공개 작업 폴더 안에 있어야 합니다.')
        audit = json.loads((native / 'native_patch_audit.json').read_text(encoding='utf-8'))
        for item in audit['files']:
            for relative in item['paths']:
                source_file = native / relative
                target_file = QA / 'game' / relative
                if not source_file.resolve().is_relative_to(native) or not target_file.resolve().is_relative_to(QA / 'game'):
                    raise SystemExit('잘못된 네이티브 후보 경로입니다.')
                if sha(target_file) != item['original_sha256'] or sha(source_file) != item['candidate_sha256']:
                    raise SystemExit('네이티브 후보 또는 기준선 지문이 맞지 않습니다.')
                shutil.copyfile(source_file, target_file)
                native_inputs.append({'path': relative, 'sha256': sha(source_file)})
    for folder in ['profile', 'temp', 'evidence']:
        (QA / folder).mkdir()
    baseline = '--baseline' in sys.argv
    text_only = '--text-only' in sys.argv
    custom = Path(sys.argv[sys.argv.index('--candidate') + 1]).resolve() if '--candidate' in sys.argv else None
    if custom and not custom.is_relative_to(ROOT):
        raise SystemExit('후보는 작업 폴더 안에 있어야 합니다.')
    source = custom or (BASE / 'THOG.dat' if baseline or text_only else SMOKE)
    dat = DatFile(source.read_bytes())
    if not baseline and not custom:
        dat.patch_utf16('object:28', 348, 'NEW GAME', '새 게임')
        if not text_only:
            dat.patch_utf16('object:28', 200, 'Tahoma', 'Malgun Gothic', slot_bytes=64)
    candidate = QA / 'evidence/smoke_candidate.dat'
    candidate.write_bytes(dat.serialize())
    header = dat.one(0x2223)
    changed = bytearray(header.decoded)
    old_flags = struct.unpack_from('<H', changed, 4)[0]
    new_flags = old_flags if '--exact' in sys.argv else (old_flags & ~((1 << 8) | (1 << 10) | (1 << 1))) | (1 << 4)
    struct.pack_into('<H', changed, 4, new_flags)
    header.replacement = bytes(changed)
    overrides = []
    if old_flags != new_flags:
        overrides.append({'location': header.location, 'offset': 4, 'before': old_flags, 'after': new_flags, 'reason': '검수 창 설정'})
    if '--entry-frame' in sys.argv:
        entry = int(sys.argv[sys.argv.index('--entry-frame') + 1])
        table = struct.unpack('<' + 'h' * (len(dat.one(0x222B).decoded) // 2), dat.one(0x222B).decoded)
        matches = [index for index, frame in enumerate(table) if frame == entry]
        if len(matches) != 1 or not 0 <= entry < 20:
            raise SystemExit('검수 시작 장면의 핸들이 유일하지 않습니다.')
        location = 'top/029:3333/008:333d'
        # 빌드마다 초기화 행동 수가 달라지므로 원시 이벤트에서 마지막 장면 이동을 찾는다.
        from inventory import event_operations
        operations = event_operations(dat.get_target(location)[1])
        jump = operations[10]['Actions'][-1]
        assert (jump['type'], jump['num']) == (-3, 2) and len(jump['parameters']) == 1
        parameter = jump['parameters'][0]
        assert parameter['code'] == 26 and parameter['size'] == 6
        offset = parameter['offset'] + 4
        dat.patch(location, offset, struct.pack('<h', 6), struct.pack('<h', matches[0]))
        overrides.append({'location': location, 'offset': offset, 'before': 6, 'after': matches[0],
                          'frame_index': entry, 'reason': '새 게임 초기화 뒤 지정 장면에 접근하는 검수 전용 2바이트 변경'})
    (QA / 'game/THOG.dat').write_bytes(dat.serialize())
    config = {name: str(QA / name) for name in ['game', 'profile', 'temp']}
    config['root'] = str(QA)
    script = (Path(__file__).parent / 'qa_guard.js').read_text(encoding='utf-8')
    script = script.replace('/*@@CONFIG@@*/ null', json.dumps(config, ensure_ascii=False))
    (QA / 'qa_guard.js').write_text(script, encoding='utf-8')
    monitored = [Path('C:/Users/PC/AppData/Roaming/MMFApplications'), Path('C:/Windows/saveprofile.ini'), Path('D:/steam/userdata')]
    user_files = []
    for folder in monitored:
        if folder.name == 'userdata':
            files = [p for account in folder.iterdir() if account.is_dir() for p in (account / '4911050').rglob('*') if p.is_file()]
        elif folder.is_dir():
            files = [p for p in folder.rglob('*') if p.is_file()]
        else:
            files = [folder] if folder.is_file() else []
        user_files.extend({'path':str(p), 'size':p.stat().st_size, 'sha256':sha(p)} for p in files)
    manifest = {'source_path': str(source), 'source_sha256': sha(source),
                'candidate_sha256': sha(candidate), 'qa_dat_sha256': sha(QA / 'game/THOG.dat'),
                'native_candidate_files': native_inputs,
                'user_files_before':user_files, 'monitored_roots':[str(p) for p in monitored],
                'qa_only_changes': overrides,
                'game_files': [{'path': p.relative_to(QA / 'game').as_posix(), 'sha256': sha(p)} for p in sorted((QA / 'game').rglob('*')) if p.is_file()],
                'guard_sha256': sha(QA / 'qa_guard.js')}
    (QA / 'evidence/prelaunch.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'qa':str(QA), 'dat_sha256':manifest['qa_dat_sha256']}))

if __name__ == '__main__':
    main()
