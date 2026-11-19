"""Boreworks 비공개 작업 경로와 원본 보존 PCK 도구."""
from pathlib import Path
import hashlib
import json
import struct
import os
import subprocess
import re
import collections

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'working_private/BOREWORKS_DEMO'
BASE = ROOT / 'source_original/BOREWORKS_DEMO/steam_23942533'
EXTRACT = ROOT / 'extracted_private/BOREWORKS_DEMO/steam_23942533'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def verify_translation(source, expected, observed):
    assert observed == expected and set(expected) == set(source)
    retained=[]
    for key,value in observed.items():
        before=source[key]
        assert value.strip() or value == before == ' '
        assert collections.Counter(re.findall(r'\{[^{}]+\}',before)) == collections.Counter(re.findall(r'\{[^{}]+\}',value))
        assert value.count('\n') == before.count('\n')
        pattern=r'</?[^>]+>|\[/?(?:b|i|color|font|img)[^\]]*\]'
        assert re.findall(pattern,before) == re.findall(pattern,value)
        if value==before:retained.append(key)
    return retained

def read_pack(path):
    data = Path(path).read_bytes()
    assert data[:4] == b'GDPC' and struct.unpack_from('<I', data, 4)[0] == 3
    base, directory = struct.unpack_from('<QQ', data, 24)
    count = struct.unpack_from('<I', data, directory)[0]
    pos = directory + 4
    entries = {}
    for _ in range(count):
        size = struct.unpack_from('<I', data, pos)[0]; pos += 4
        raw = data[pos:pos+size]; pos += size
        name = raw.rstrip(b'\0').decode('utf-8')
        offset, length = struct.unpack_from('<QQ', data, pos); pos += 16
        digest = data[pos:pos+16]; pos += 16
        flags = struct.unpack_from('<I', data, pos)[0]; pos += 4
        payload = data[base+offset:base+offset+length]
        assert flags == 0 and hashlib.md5(payload).digest() == digest and name not in entries
        entries[name] = dict(raw=raw, offset=offset, size=length, md5=digest, flags=flags, data=payload)
    assert pos == len(data)
    return data, base, directory, entries

def patch_pack(source, target, changes):
    data, base, directory, entries = read_pack(source)
    result = bytearray(data[:directory])
    for name, payload in changes.items():
        assert not name.startswith('/') and '..' not in Path(name).parts
        if name not in entries:
            raw = name.encode('utf-8'); raw += b'\0' * (-len(raw) % 4)
            entries[name] = dict(raw=raw, flags=0)
        result.extend(b'\0' * (-len(result) % 16))
        entries[name].update(offset=len(result)-base, size=len(payload), md5=hashlib.md5(payload).digest())
        result.extend(payload)
    if changes:
        result.extend(b'\0' * (-len(result) % 16))
    struct.pack_into('<Q', result, 32, len(result))
    result.extend(struct.pack('<I', len(entries)))
    for entry in entries.values():
        result.extend(struct.pack('<I', len(entry['raw'])) + entry['raw'])
        result.extend(struct.pack('<QQ', entry['offset'], entry['size']) + entry['md5'] + struct.pack('<I', entry['flags']))
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_bytes(result)
    checked = read_pack(target)[3]
    originals = read_pack(source)[3]
    assert set(checked) == set(originals) | set(changes)
    for name, entry in checked.items():
        assert entry['data'] == (changes[name] if name in changes else originals[name]['data']), name

def godot(script, args, label):
    runtime = WORK / 'resource_probe'
    env = os.environ.copy()
    env['APPDATA'] = str(runtime/'roaming')
    env['LOCALAPPDATA'] = str(runtime/'local')
    command = [str(ROOT/'tools/gdre_2.6.4/bin/gdre_tools.exe'), '--headless', '--path', str(runtime), '--log-file', str(runtime/(label+'.log')), '--script', str(script), '--'] + list(map(str,args))
    p = subprocess.run(command, env=env, capture_output=True, timeout=90)
    (runtime/(label+'.stdout.log')).write_bytes(p.stdout)
    (runtime/(label+'.stderr.log')).write_bytes(p.stderr)
    assert p.returncode == 0, (label, p.returncode, p.stderr[-2000:])
    print(p.stdout.decode('utf-8',errors='replace').strip())
