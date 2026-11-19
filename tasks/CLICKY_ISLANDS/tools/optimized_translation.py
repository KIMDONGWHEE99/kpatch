"""Godot 압축 언어표(OptimizedTranslation)를 칸 단위로 읽고 다시 만드는 도구.

이 형식은 키 이름을 저장하지 않고 키의 해시(지문)만 저장합니다. 그래서 키 이름을 모르는
문구도 "해시 표 칸 → 묶음 → 원소" 위치로 정확히 가리킬 수 있습니다.
구조는 Godot 4.5 core/string/optimized_translation.cpp 기준입니다.
  hash_table[h(0,key) % size] = 묶음 시작 위치(없으면 0xFFFFFFFF)
  묶음 = [원소 수, 함수 씨앗, (키 해시, 문자열 위치, 압축 크기, 원래 크기) × 원소 수]
  압축 크기 == 원래 크기이면 압축하지 않은 UTF-8 그대로 읽습니다.
"""
EMPTY = 0xFFFFFFFF
MASK = 0xFFFFFFFF


def godot_hash(seed, text):
    """OptimizedTranslation::hash 와 같은 계산입니다."""
    value = seed if seed else 0x1000193
    for byte in text.encode('utf-8'):
        if byte == 0:
            break
        value = ((value * 0x1000193) & MASK) ^ byte
    return value


def parse(hash_table, bucket_table, messages):
    """칸 순서대로 원소를 나열합니다. messages는 엔진이 같은 순서로 돌려준 문구입니다."""
    table = [v & MASK for v in hash_table]
    buckets = [v & MASK for v in bucket_table]
    slots, index = [], 0
    for position, pointer in enumerate(table):
        if pointer == EMPTY:
            continue
        size, seed = buckets[pointer], buckets[pointer + 1]
        for element in range(size):
            base = pointer + 2 + element * 4
            key_hash, offset, comp, uncomp = buckets[base:base + 4]
            slots.append({'slot': f'{position}:{element}', 'table_index': position, 'element': element,
                          'seed': seed, 'key_hash': key_hash, 'offset': offset, 'comp_size': comp,
                          'uncomp_size': uncomp, 'message': messages[index] if messages is not None else None})
            index += 1
    if messages is not None and index != len(messages):
        raise ValueError(f'문구 수 불일치: 칸 {index}, 문구 {len(messages)}')
    return slots


def find(slots_by_index, table_size, key):
    """키 문자열이 가리키는 칸을 찾습니다. 없으면 None."""
    position = godot_hash(0, key) % table_size
    for slot in slots_by_index.get(position, []):
        if slot['key_hash'] == godot_hash(slot['seed'], key):
            return slot
    return None


def index_slots(slots):
    result = {}
    for slot in slots:
        result.setdefault(slot['table_index'], []).append(slot)
    return result


def build(table_size, entries):
    """entries: [{'table_index', 'seed', 'key_hash', 'text'}] → (hash_table, bucket_table, strings).

    문자열은 압축하지 않은 UTF-8로 넣습니다(압축 크기 == 원래 크기).
    엔진이 만든 원본과 같게 끝에 NUL 1바이트를 붙이고 크기에 포함합니다. 빈 문구는 NUL 1바이트입니다.
    같은 칸의 원소는 같은 씨앗을 써야 하고 키 해시가 서로 달라야 합니다.
    """
    grouped = {}
    for entry in entries:
        grouped.setdefault(entry['table_index'], []).append(entry)
    hash_table = [EMPTY] * table_size
    bucket_table, strings = [], bytearray()
    for position in sorted(grouped):
        group = grouped[position]
        seeds = {e['seed'] for e in group}
        hashes = [e['key_hash'] for e in group]
        if len(seeds) != 1 or len(set(hashes)) != len(hashes):
            raise ValueError(f'칸 {position}의 씨앗 또는 키 해시가 충돌합니다.')
        hash_table[position] = len(bucket_table)
        bucket_table += [len(group), group[0]['seed']]
        for entry in group:
            data = entry['text'].encode('utf-8')
            if b'\0' in data:
                raise ValueError('NUL이 든 문구는 넣을 수 없습니다.')
            data += b'\0'
            bucket_table += [entry['key_hash'], len(strings), len(data), len(data)]
            strings += data
    return hash_table, bucket_table, bytes(strings)


def add_key(entries, table_size, key, text):
    """새 키를 추가합니다. 같은 칸에 이미 묶음이 있으면 그 씨앗을 그대로 씁니다."""
    position = godot_hash(0, key) % table_size
    same = [e for e in entries if e['table_index'] == position]
    seed = same[0]['seed'] if same else 1
    key_hash = godot_hash(seed, key)
    for entry in same:
        if entry['key_hash'] == key_hash:
            if entry.get('key') == key:
                raise ValueError('이미 있는 키입니다: ' + key)
            raise ValueError('키 해시 충돌(씨앗을 바꿀 수 없는 칸): ' + key)
    entry = {'table_index': position, 'seed': seed, 'key_hash': key_hash, 'text': text, 'key': key, 'added': True}
    entries.append(entry)
    return entry


def signed(values):
    """Godot PackedInt32Array에 넣을 부호 있는 32비트 값으로 바꿉니다."""
    return [v - 0x100000000 if v >= 0x80000000 else v for v in values]
