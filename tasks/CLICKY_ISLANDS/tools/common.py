"""자료 저장과 격리한 분석 도구 실행을 지원합니다.

AGROMATIC_DEMO의 common.py를 복사해 게임 이름·빌드·대상 파일만 바꿨습니다.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import struct

ROOT = Path(__file__).resolve().parents[3]
GAME = 'CLICKY_ISLANDS'
BUILD = 'steam_26701014'
PCK_NAME = 'Clicky Islands.pck'
EXE_NAME = 'Clicky Islands.exe'
BASE = ROOT / 'source_original' / GAME / BUILD
EXTRACTED = ROOT / 'extracted_private' / GAME / BUILD
RECOVERED = EXTRACTED / 'recovered'
PACK = EXTRACTED / 'pack'
WORK = ROOT / 'working_private' / GAME
CANDIDATE = ROOT / 'build_candidate' / GAME
TOOL = ROOT / 'tools/gdre_2.6.4/bin/gdre_tools.exe'


def read_settings(data):
    if data[:4] != b'ECFG':
        raise ValueError('설정 형식 불일치')
    count = struct.unpack_from('<I', data, 4)[0]
    pos, values = 8, {}
    for _ in range(count):
        length = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        key = data[pos:pos + length].decode('utf-8')
        pos += length
        length = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        if key in values or pos + length > len(data):
            raise ValueError('설정 위치 불일치')
        values[key] = data[pos:pos + length]
        pos += length
    if pos != len(data):
        raise ValueError('설정 끝 불일치')
    return values


def patch_settings(data, changes):
    values = read_settings(data)
    for key, value in changes.items():
        if isinstance(value, bool):
            raw = struct.pack('<II', 1, int(value))
        elif isinstance(value, str):
            text = value.encode('utf-8')
            raw = struct.pack('<II', 4, len(text)) + text + b'\0' * (-len(text) % 4)
        elif isinstance(value, int):
            raw = struct.pack('<Ii', 2, value)
        else:
            raise TypeError(value)
        values[key] = raw
    result = bytearray(b'ECFG' + struct.pack('<I', len(values)))
    for key, value in values.items():
        text = key.encode('utf-8')
        result.extend(struct.pack('<I', len(text)) + text + struct.pack('<I', len(value)) + value)
    reopened = read_settings(bytes(result))
    if reopened != values:
        raise ValueError('설정 재열기 실패')
    return bytes(result)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def run_gdre(arguments, label, timeout=1200):
    runtime = WORK / 'tool_runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['APPDATA'] = str(runtime / 'roaming')
    env['LOCALAPPDATA'] = str(runtime / 'local')
    command = [str(TOOL), '--headless'] + list(map(str, arguments))
    result = subprocess.run(command, env=env, cwd=ROOT, capture_output=True, timeout=timeout)
    (runtime / (label + '.stdout.log')).write_bytes(result.stdout)
    (runtime / (label + '.stderr.log')).write_bytes(result.stderr)
    save(runtime / (label + '.command.json'), {'command': command, 'exit_code': result.returncode,
         'tool_sha256': sha(TOOL)})
    # 출력 전문은 위 로그 파일에 남기고, 화면에는 실패했을 때만 끝부분을 보여 줍니다.
    if result.returncode:
        print(label, result.returncode, result.stdout.decode('utf-8', errors='replace')[-3000:],
              result.stderr.decode('utf-8', errors='replace')[-1500:])
        raise RuntimeError(label)
    return result


if __name__ == '__main__':
    run_gdre(['--recover=' + str(BASE / PCK_NAME),
              '--output=' + str(RECOVERED)], 'recover')
