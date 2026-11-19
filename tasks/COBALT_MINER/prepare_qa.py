"""게임 검수 사본의 저장·창·전체화면 변경을 한정해 기록합니다."""
import argparse
import json
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tasks/THE_HORDE_OF_GORAK'))
from dat_container import DatFile, sha
from inventory import event_operations

BASE = ROOT / 'source_original/COBALT_MINER/steam_24347666'
WORK = ROOT / 'working_private/COBALT_MINER'

def snapshot():
    roots = [Path('D:/steam/steamapps/common/Cobalt Miner'),
             Path('C:/Users/PC/AppData/Roaming/MMFApplications'), Path('C:/Windows/saveprofile.ini')]
    roots += [p / '4601880' for p in Path('D:/steam/userdata').iterdir() if p.is_dir()]
    rows = []
    for root in roots:
        files = root.rglob('*') if root.is_dir() else [root] if root.is_file() else []
        for path in sorted(files):
            if path.is_file():
                rows.append({'path': str(path), 'size': path.stat().st_size, 'sha256': sha(path.read_bytes())})
    return {'roots': [str(p) for p in roots], 'files': rows}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run')
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--candidate-game', type=Path)
    parser.add_argument('--automatic', action='store_true')
    parser.add_argument('--frame', type=int)
    parser.add_argument('--exact', action='store_true')
    parser.add_argument('--client-width', type=int, default=1920)
    parser.add_argument('--client-height', type=int, default=1080)
    args = parser.parse_args()
    if not args.run.startswith('qa_') or not args.run.replace('_', '').isalnum():
        raise ValueError('잘못된 검수 ID')
    out = WORK / args.run
    if out.exists():
        raise ValueError('기존 검수 사본 덮어쓰기 금지')
    game_source = (args.candidate_game or BASE).resolve()
    allowed_games = [BASE.resolve(), (ROOT / 'build_candidate/COBALT_MINER').resolve()]
    if not any(game_source == p or game_source.is_relative_to(p) for p in allowed_games):
        raise ValueError('검수 게임은 고정 원본 또는 이 게임의 후보 폴더여야 함')
    expected_names = {p.relative_to(BASE) for p in BASE.rglob('*') if p.is_file()}
    source_files = {p.relative_to(game_source): p for p in game_source.rglob('*') if p.is_file()}
    if set(source_files) != expected_names or any(p.is_symlink() for p in source_files.values()):
        raise ValueError('검수 입력 게임 파일 목록이 고정 원본과 다름')
    source_hashes = {str(name): sha(path.read_bytes()) for name, path in source_files.items()}
    shutil.copytree(game_source, out / 'game')
    for name, digest in source_hashes.items():
        if sha((out / 'game' / name).read_bytes()) != digest:
            raise ValueError('검수 게임 복사 지문 불일치')
    for name in ('profile', 'temp', 'evidence'):
        (out / name).mkdir()
    source = args.candidate or game_source / 'COBALT MINER.dat'
    dat = DatFile.load(source)
    overrides = []
    header = dat.one(0x2223)
    b = bytearray(header.decoded)
    flags = struct.unpack_from('<H', b, 4)[0]
    new_flags = (flags & ~((1 << 8) | (1 << 10) | (1 << 1) | (1 << 11))) | (1 << 4)
    struct.pack_into('<H', b, 4, new_flags)
    header.replacement = bytes(b)
    overrides.append({'target': header.location, 'offset': 4, 'before': flags, 'after': new_flags, 'reason': '전체화면·최대화 방지, 작은 창 배율'})
    frames = [c for c in dat.chunks if c.chunk_id == 0x3333]
    for fi, frame in enumerate(frames):
        chunk = next(c for c in frame.children if c.chunk_id == 0x333d)
        for ev in event_operations(chunk.decoded):
            for op in ev['Actions']:
                if op['type'] == -3 and op['num'] == 14:
                    dat.patch(chunk.location, op['offset'] + 4, struct.pack('<h', 14), struct.pack('<h', 15))
                    overrides.append({'target': chunk.location, 'offset': op['offset'] + 4, 'frame': fi, 'event': ev['index'], 'action': op['index'], 'before': 14, 'after': 15, 'reason': '검수 사본 전체화면 행동을 창 모드로 변경'})
    if args.frame is not None:
        if not 0 <= args.frame < len(frames):
            raise ValueError('장면 범위 오류')
        handles = struct.unpack('<' + 'h' * (len(dat.one(0x222b).decoded) // 2), dat.one(0x222b).decoded)
        entry_handle = handles.index(args.frame)
        first = next(c for c in frames[0].children if c.chunk_id == 0x333d)
        patched = False
        for ev in event_operations(first.decoded):
            for op in ev['Actions']:
                if op['type'] == -3 and op['num'] == 1:
                    p = op['parameters'][0]
                    dat.patch(first.location, p['offset'] + 4, struct.pack('<h', handles.index(1)), struct.pack('<h', entry_handle))
                    overrides.append({'target': first.location, 'offset': p['offset'] + 4, 'before': 1, 'after_frame': args.frame, 'reason': '첫 로고 뒤 검수 화면 이동'})
                    patched = True
        if not patched:
            raise ValueError('검수 진입용 장면 이동이 확인되지 않음')
    if args.exact:
        dat = DatFile.load(source)
        overrides = []
    (out / 'game/COBALT MINER.dat').write_bytes(dat.serialize())
    config = {name: str(out / name) for name in ('game', 'profile', 'temp')}
    config['root'] = str(out)
    config['automatic'] = args.automatic
    if not (640 <= args.client_width <= 2560 and 360 <= args.client_height <= 1440):
        raise ValueError('검수 창 크기 범위 오류')
    config['clientWidth'], config['clientHeight'] = args.client_width, args.client_height
    template = (ROOT / 'tasks/COBALT_MINER/qa_guard.js').read_text(encoding='utf-8')
    (out / 'qa_guard.js').write_text(template.replace('/*@@CONFIG@@*/ null', json.dumps(config, ensure_ascii=False)), encoding='utf-8')
    record = {'source': str(source), 'source_sha256': sha(source.read_bytes()), 'qa_dat_sha256': sha((out / 'game/COBALT MINER.dat').read_bytes()),
              'game_source': str(game_source), 'game_source_hashes': source_hashes,
              'qa_only_changes': overrides, 'before': snapshot(), 'guard_sha256': sha((out / 'qa_guard.js').read_bytes()),
              'files': [{'path': str(p.relative_to(out / 'game')), 'sha256': sha(p.read_bytes())} for p in sorted((out / 'game').rglob('*')) if p.is_file()]}
    (out / 'evidence/prelaunch.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'run': args.run, 'overrides': len(overrides), 'sha256': record['qa_dat_sha256']}))

if __name__ == '__main__':
    main()
