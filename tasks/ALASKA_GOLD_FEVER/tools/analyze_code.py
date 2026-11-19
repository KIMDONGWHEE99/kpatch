"""고정 원본 사본을 게임 실행 없이 분석하고 입력·도구·출력 지문을 남깁니다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'source_original/ALASKA_GOLD_FEVER/25782395/game'
OUTPUT = ROOT / 'extracted_private/ALASKA_GOLD_FEVER/25782395/code'
TOOL = ROOT / 'tasks/TFC2/tools/third_party/Cpp2IL-2022.1.0-pre-release.21/Cpp2IL.exe'


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['dummy', 'isil'], default='dummy')
    args = parser.parse_args()
    output = OUTPUT / args.mode
    report_path = OUTPUT / (args.mode + '_analysis.json')
    if report_path.exists() or output.exists():
        raise RuntimeError('기존 분석 결과를 덮어쓰지 않습니다.')
    binary = SOURCE / 'GameAssembly.dll'
    metadata = SOURCE / 'Alaska Gold Fever_Data/il2cpp_data/Metadata/global-metadata.dat'
    inputs = {str(path.relative_to(ROOT)): {'size': path.stat().st_size, 'sha256': sha(path)}
              for path in [binary, metadata, TOOL, Path(__file__)]}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / 'working_private/ALASKA_GOLD_FEVER/tool_runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment['DOTNET_BUNDLE_EXTRACT_BASE_DIR'] = str(runtime)
    command = [str(TOOL), '--force-binary-path', str(binary),
               '--force-metadata-path', str(metadata), '--force-unity-version', '6000.0.62f1',
               '--output-as', 'dummydll' if args.mode == 'dummy' else 'isil',
               '--output-to', str(output)]
    if args.mode == 'dummy':
        command += ['--use-processor', 'attributeinjector']
    else:
        command += ['--use-processor', 'callanalyzer']
    started = datetime.now(timezone.utc).isoformat()
    log = OUTPUT / (args.mode + '.log')
    with log.open('wb') as stream:
        completed = subprocess.run(command, cwd=OUTPUT, env=environment,
                                   stdout=stream, stderr=subprocess.STDOUT, check=False)
    unchanged = all(sha(ROOT / name) == item['sha256'] for name, item in inputs.items())
    files = [{'path': str(path.relative_to(OUTPUT)), 'size': path.stat().st_size, 'sha256': sha(path)}
             for path in sorted(output.rglob('*')) if path.is_file()]
    report = {'game_id': 'ALASKA_GOLD_FEVER', 'build_id': '25782395',
              'status': 'PASS' if completed.returncode == 0 and unchanged and files else 'FAIL',
              'mode': args.mode, 'command': command, 'started_utc': started,
              'finished_utc': datetime.now(timezone.utc).isoformat(), 'exit_code': completed.returncode,
              'input_hashes_unchanged': unchanged, 'inputs': inputs,
              'log_sha256': sha(log), 'outputs': files}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'outputs': len(files), 'report': str(report_path)}, ensure_ascii=False))
    if report['status'] != 'PASS':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
