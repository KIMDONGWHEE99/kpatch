"""실제로 판독한 화면의 수동 판정과 실행·지문 증거를 연결합니다."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from qa_runtime_observation import final_observation

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/COBALT_MINER'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(run, screenshot, status, notes, extra_screenshots=(), width=1920, height=1080):
    folder = (WORK / run).resolve()
    folder.relative_to(WORK.resolve())
    evidence = folder / 'evidence'
    output = evidence / 'screen_review.json'
    if output.exists():
        raise ValueError('기존 육안 판정을 덮어쓰지 않습니다.')
    pre = json.loads((evidence / 'prelaunch.json').read_text(encoding='utf-8'))
    post = json.loads((evidence / 'post_integrity.json').read_text(encoding='utf-8'))
    bundle = json.loads((evidence / 'rea_runtime.json').read_text(encoding='utf-8'))
    executable = (folder / 'game/COBALT MINER.exe').resolve()
    final = final_observation(bundle, executable)
    assert post['status'] == 'PASS'
    observed = final['normalized_result']
    messages = observed['messages']
    errors = [m for m in messages if m.get('type') == 'error' or m.get('payload', {}).get('kind') in ('exception', 'native_exception')]
    # 오류가 있는 실행도 FAIL 증거로 남기되 PASS 승격은 금지합니다.
    assert (not errors or status == 'FAIL') and not observed['messages_truncated']
    assert observed['state'] == 'detached', '종료 이후의 전체 로그가 필요합니다.'
    windows = [m['payload'] for m in messages if m.get('payload', {}).get('kind') == 'qa_window_created']
    assert windows and all((w['x'], w['y'], w.get('client_width', w['width']), w.get('client_height', w['height'])) == (8, 8, width, height) for w in windows)
    picture = (evidence / screenshot).resolve()
    picture.relative_to(evidence)
    with Image.open(picture) as im:
        dimensions = list(im.size)
    assert dimensions == [width, height]
    for row in pre['files']:
        assert sha(folder / 'game' / row['path']) == row['sha256']
    deps = [evidence / 'prelaunch.json', evidence / 'post_integrity.json', evidence / 'rea_runtime.json', picture, folder / 'qa_guard.js']
    additional = []
    for name in extra_screenshots:
        extra = (evidence / name).resolve()
        extra.relative_to(evidence)
        with Image.open(extra) as im:
            size = list(im.size)
        if size != [width, height]:
            raise ValueError('추가 캡처 해상도 불일치')
        deps.append(extra)
        additional.append(dict(path=name, dimensions=size, sha256=sha(extra)))
    source = Path(pre['source'])
    source = source.resolve() if source.is_absolute() else (ROOT / source).resolve()
    for relative in ('fixture_report.json', 'probe_report.json', 'hold_report.json', 'world_report.json', 'entry/fixture_report.json'):
        fixture = source.parent / relative
        if fixture.exists():
            deps.append(fixture)
    for capture in ('cycle_manifest.json', 'cycle_config.json'):
        if (evidence / capture).exists():
            deps.append(evidence / capture)
    for capture in folder.glob('qa_capture*.js'):
        deps.append(capture)
    report = dict(game_id='COBALT_MINER', steam_build='24347666', run_id=run, status=status,
                  reviewer='제작자 실제 캡처 육안 검수', reviewed_utc=datetime.now(timezone.utc).isoformat(), notes=notes,
                  candidate_source=pre['game_source'], candidate_files=pre['game_source_hashes'], qa_dat_sha256=pre['qa_dat_sha256'],
                  runtime=dict(actual_path=str(executable), pid=observed['pid'], session_id=observed['session_id'],
                               evidence_id=final['evidence_id'], window=windows[-1], exceptions=errors),
                  screenshot=dict(path=screenshot, dimensions=dimensions, sha256=sha(picture)), user_integrity='PASS',
                  additional_screenshots=additional,
                  dependencies=[dict(path=p.resolve().relative_to(ROOT).as_posix(), sha256=sha(p)) for p in deps],
                  limits=['관찰한 화면만 판정. 전체 문구·분기·최종 후보 완료를 뜻하지 않음.',
                          '검수 전용 창·입력·저장 격리 가드 사용.'])
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(run=run, status=status, screenshot_sha256=sha(picture))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run')
    parser.add_argument('screenshot')
    parser.add_argument('--status', choices=['PASS', 'FAIL'], required=True)
    parser.add_argument('--notes', required=True)
    parser.add_argument('--additional-screenshot', action='append', default=[])
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    args = parser.parse_args()
    record(args.run, args.screenshot, args.status, args.notes, args.additional_screenshot, args.width, args.height)
