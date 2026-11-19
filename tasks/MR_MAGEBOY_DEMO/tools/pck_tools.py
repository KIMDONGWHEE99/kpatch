"""Godot PCK v4 원본 보존 추출·추가 방식 패킹 도구."""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[3]
GAME = 'MR_MAGEBOY_DEMO'
BASELINE = ROOT / 'source_original' / GAME / 'steam_25734075'
EXTRACTED = ROOT / 'extracted_private' / GAME / 'steam_25734075'
WORK = ROOT / 'working_private' / GAME


def read_pack(path):
    data = Path(path).read_bytes()
    assert data[:4] == b'GDPC' and struct.unpack_from('<I', data, 4)[0] == 4
    base, directory = struct.unpack_from('<QQ', data, 24)
    count = struct.unpack_from('<I', data, directory)[0]
    pos = directory + 4
    entries = []
    seen = set()
    for _ in range(count):
        size = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        raw = data[pos:pos + size]
        name = raw.rstrip(b'\0').decode('utf-8')
        pos += size
        offset, length = struct.unpack_from('<QQ', data, pos)
        pos += 16
        digest = data[pos:pos + 16]
        pos += 16
        flags = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        payload = data[base + offset:base + offset + length]
        assert flags == 0 and hashlib.md5(payload).digest() == digest, name
        assert name not in seen and not name.startswith('/') and '..' not in Path(name).parts, name
        assert base + offset + length <= directory, name
        seen.add(name)
        entries.append(dict(name=name, raw=raw, offset=offset, size=length, md5=digest, flags=flags, data=payload))
    assert pos == len(data)
    return data, base, directory, entries


def patch_pack(source, destination, changes):
    data, base, directory, entries = read_pack(source)
    if not changes:
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(data)
        return
    result = bytearray(data[:directory])
    by_name = {e['name']: e for e in entries}
    originals = {e['name']: e['data'] for e in entries}
    for name, payload in changes.items():
        assert not name.startswith('/') and '..' not in Path(name).parts
        if name not in by_name:
            raw = name.encode('utf-8')
            raw += b'\0' * (-len(raw) % 4)
            entry = dict(name=name, raw=raw, flags=0)
            entries.append(entry)
            by_name[name] = entry
        entry = by_name[name]
        result.extend(b'\0' * (-len(result) % 16))
        entry.update(offset=len(result) - base, size=len(payload), md5=hashlib.md5(payload).digest())
        result.extend(payload)
    result.extend(b'\0' * (-len(result) % 16))
    struct.pack_into('<Q', result, 32, len(result))
    result.extend(struct.pack('<I', len(entries)))
    for e in entries:
        result.extend(struct.pack('<I', len(e['raw'])) + e['raw'])
        result.extend(struct.pack('<QQ', e['offset'], e['size']) + e['md5'] + struct.pack('<I', e['flags']))
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(result)
    _, _, _, checked = read_pack(dest)
    assert {e['name'] for e in checked} == set(originals) | set(changes)
    for e in checked:
        expected = changes[e['name']] if e['name'] in changes else originals[e['name']]
        assert e['data'] == expected, e['name']


def variant(value):
    if isinstance(value, bool):
        return struct.pack('<II', 1, int(value))
    if isinstance(value, str):
        data = value.encode('utf-8')
        return struct.pack('<II', 4, len(data)) + data + b'\0' * (-len(data) % 4)
    if isinstance(value, int):
        return struct.pack('<Ii', 2, value)
    raise TypeError(value)


def read_settings(data):
    assert data[:4] == b'ECFG'
    count = struct.unpack_from('<I', data, 4)[0]
    pos = 8
    settings = {}
    for _ in range(count):
        length = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        key = data[pos:pos + length].decode('utf-8')
        pos += length
        length = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        settings[key] = data[pos:pos + length]
        pos += length
    assert pos == len(data)
    return settings


def patch_settings(data, changes):
    settings = read_settings(data)
    settings.update({k: variant(v) for k, v in changes.items()})
    out = bytearray(b'ECFG' + struct.pack('<I', len(settings)))
    for key, val in settings.items():
        raw = key.encode('utf-8')
        out.extend(struct.pack('<I', len(raw)) + raw + struct.pack('<I', len(val)) + val)
    return bytes(out)

