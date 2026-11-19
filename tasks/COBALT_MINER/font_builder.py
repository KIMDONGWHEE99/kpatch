"""한글 글꼴 연결 전체와 메뉴 한 문구를 바꾸는 위험 시험 후보입니다."""
from __future__ import annotations

import io
import json
import struct
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tasks/THE_HORDE_OF_GORAK'))
from dat_container import DatFile, encode_block, sha, u32, utf16z

SOURCE = ROOT / 'source_original/COBALT_MINER/steam_24347666/COBALT MINER.dat'
SEMANTIC = ROOT / 'extracted_private/COBALT_MINER/steam_24347666/nebula_01'
OUT = ROOT / 'working_private/COBALT_MINER/font_smoke_01'
FONT = ROOT / 'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf'
LICENSE = FONT.parent / 'OFL.txt'
FAMILY = 'Cobalt Noto Sans KR'
CHARSET = 129

def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f'기존 산출물과 다름: {path}')
    if not path.exists():
        path.write_bytes(data)

def make_font(weight):
    font = TTFont(FONT, recalcTimestamp=False)
    font = instantiateVariableFont(font, {'wght': weight}, inplace=True)
    style = 'Bold' if weight == 700 else 'Regular'
    replacements = {1: FAMILY, 2: style, 3: f'Cobalt-NotoSansKR-{style}-2.004',
                    4: f'{FAMILY} {style}', 6: f'CobaltNotoSansKR-{style}', 16: FAMILY, 17: style}
    font['name'].names = [n for n in font['name'].names if n.nameID not in replacements]
    for ident, value in replacements.items():
        font['name'].setName(value, ident, 3, 1, 0x409)
        font['name'].setName(value, ident, 1, 0, 0)
    font['OS/2'].usWeightClass = weight
    font['OS/2'].fsSelection = (font['OS/2'].fsSelection & ~(0x20 | 0x40)) | (0x20 if weight == 700 else 0x40)
    font['head'].macStyle = (font['head'].macStyle & ~1) | (1 if weight == 700 else 0)
    output = io.BytesIO()
    font.save(output)
    font.close()
    return output.getvalue()

def inspect_font(data, required):
    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    cmap = font.getBestCmap()
    missing = sorted(c for c in required if c not in cmap or cmap[c] == '.notdef')
    result = {'sha256': sha(data), 'family': font['name'].getDebugName(1),
              'style': font['name'].getDebugName(2), 'weight': font['OS/2'].usWeightClass,
              'embedding_flags': font['OS/2'].fsType, 'cmap_count': len(cmap),
              'variable': 'fvar' in font, 'required_count': len(required), 'missing': missing}
    assert result['family'] == FAMILY and not result['variable'] and not missing
    assert result['embedding_flags'] == 0
    font.close()
    return result

def change_logfont(data, offset):
    result = bytearray(data)
    assert offset >= 0 and offset + 92 <= len(result)
    weight = 700 if u32(result, offset + 16) >= 600 else 400
    struct.pack_into('<I', result, offset + 16, weight)
    result[offset + 23] = CHARSET
    result[offset + 28:offset + 92] = (FAMILY.encode('utf-16le') + b'\0\0').ljust(64, b'\0')
    return bytes(result), weight

def apply_fonts(dat, fonts):
    package = json.loads((SEMANTIC / 'package.json').read_text(encoding='utf-8-sig'))
    font_meta = json.loads((SEMANTIC / 'fonts.json').read_text(encoding='utf-8-sig'))
    old_blocks = DatFile._blocks(dat.one(0x2259).decoded)
    assert len(old_blocks) == len(font_meta['embedded'])
    bank, offset_map, embedded = bytearray(), {}, []
    for block, meta in zip(old_blocks, font_meta['embedded']):
        assert sha(block.decoded) == meta['sha256']
        original_font = TTFont(io.BytesIO(block.decoded))
        weight = 700 if original_font['OS/2'].usWeightClass >= 600 else 400
        original_font.close()
        offset_map[block.offset] = len(bank)
        embedded.append({'index': block.index, 'original_offset': block.offset, 'offset': len(bank),
                         'weight': weight, 'original_sha256': sha(block.decoded), 'sha256': sha(fonts[weight])})
        bank += encode_block(fonts[weight])
    dat.one(0x2259).replacement = bytes(bank)
    info = dat.one(0x2258).decoded
    assert len(info) % 96 == 0
    new_info, mappings = bytearray(), []
    for offset in range(0, len(info), 96):
        before = info[offset:offset + 96]
        after, weight = change_logfont(before, 0)
        new_offset = offset_map[u32(before, 92)]
        assert next(b['weight'] for b in embedded if b['offset'] == new_offset) == weight
        new_info += after[:92] + struct.pack('<I', new_offset)
        mappings.append({'index': offset // 96, 'weight': weight, 'ttf_offset': new_offset})
    dat.one(0x2258).replacement = bytes(new_info)
    assert len(dat.fonts) == len(font_meta['logical']['Fonts'])
    for block in dat.fonts:
        block.replacement, _ = change_logfont(block.decoded, 12)
    buttons = []
    for key, obj in package['FrameItems']['Items'].items():
        if obj['Header']['Type'] != 33:
            continue
        handle = int(key)
        # Type은 확장 표의 Handle + 32이며 ExtensionID는 저장된 내부 값이다.
        extension_meta = package['Extensions']['Exts'][str(obj['Header']['Type'] - 32)]
        assert extension_meta['FileName'].lower() == 'kcboxa.mfx'
        block = dat.objects[handle]
        raw = block.decoded if block.replacement is None else block.replacement
        start = struct.unpack_from('<H', raw, 12)[0] + 20
        extension = (SEMANTIC / f'extension_blobs/{handle:04d}.bin').read_bytes()
        assert raw[start:start + len(extension)] == extension
        text_size = u32(extension, 208)
        assert len(extension) == 212 + text_size + 8
        assert utf16z(extension, 212)[1] == 212 + text_size
        old_name = utf16z(extension, 64)[0]
        block.replacement, weight = change_logfont(raw, start + 36)
        buttons.append({'object': handle, 'name_offset': start + 64, 'weight': weight,
                        'original_name': old_name, 'original_object_sha256': sha(raw)})
    return embedded, mappings, buttons

def build():
    assert sha(FONT.read_bytes()) == '194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252'
    assert sha(LICENSE.read_bytes()) == '1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9'
    original = DatFile.load(SOURCE)
    dat = DatFile.load(SOURCE)
    fonts = {weight: make_font(weight) for weight in (400, 700)}
    required = set(range(0xAC00, 0xD7A4)) | set(range(0x1100, 0x1200)) | set(range(0x3131, 0x318F)) | set(range(32, 127))
    reports = {weight: inspect_font(data, required) for weight, data in fonts.items()}
    embedded, mappings, buttons = apply_fonts(dat, fonts)
    dat.patch_utf16('object:60', 348, 'NEW GAME', '새 게임')
    output = dat.serialize()
    candidate = DatFile(output)
    assert candidate.serialize() == output
    assert candidate.integrity_summary()['status'] == 'PASS'
    reread = DatFile._blocks(candidate.one(0x2259).decoded)
    assert len(reread) == len(embedded)
    for block, expected in zip(reread, embedded):
        assert block.offset == expected['offset'] and sha(block.decoded) == expected['sha256']
        inspect_font(block.decoded, required)
    for offset in range(0, len(candidate.one(0x2258).decoded), 96):
        row = candidate.one(0x2258).decoded[offset:offset + 96]
        ttf = next(block for block in reread if block.offset == u32(row, 92))
        report = inspect_font(ttf.decoded, required)
        assert utf16z(row, 28)[0] == report['family'] and row[23] == CHARSET and u32(row, 16) == report['weight']
    for block in candidate.fonts:
        assert utf16z(block.decoded, 40)[0] == FAMILY and block.decoded[35] == CHARSET
    for item in buttons:
        data = candidate.objects[item['object']].decoded
        assert utf16z(data, item['name_offset'])[0] == FAMILY and data[item['name_offset'] - 5] == CHARSET
    assert utf16z(candidate.objects[60].decoded, 348)[0] == '새 게임'
    changed = [f'0x{a.chunk_id:04x}' for a, b in zip(original.chunks, candidate.chunks) if a.decoded != b.decoded]
    assert set(changed) <= {'0x2259', '0x2258', '0x2256', '0x2257', '0x2242', '0x6667', '0x5556'}
    for weight, data in fonts.items():
        write_new(OUT / 'fonts' / f'CobaltNotoSansKR-{weight}.ttf', data)
    write_new(OUT / 'fonts/OFL.txt', LICENSE.read_bytes())
    write_new(OUT / 'COBALT MINER.dat', output)
    result = {'source_sha256': sha(original.original), 'candidate_sha256': sha(output), 'candidate_bytes': len(output),
              'builder_sha256': sha(Path(__file__).read_bytes()), 'font_source_sha256': sha(FONT.read_bytes()),
              'license_sha256': sha(LICENSE.read_bytes()), 'fonts': reports, 'embedded': embedded, 'mappings': mappings,
              'button_changes': buttons, 'logical_fonts': len(candidate.fonts), 'changed_chunks': changed,
              'integrity': candidate.integrity_summary(), 'cmap_and_offsets': 'PASS', 'runtime_qa': 'NOT_RUN',
              'scope': '전체 글꼴 연결과 첫 메뉴 NEW GAME 한 문구만 바꾸는 위험 시험. 실제 한글 출력·줄높이는 미검증.'}
    write_new(OUT / 'build_report.json', (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'candidate': str(OUT / 'COBALT MINER.dat'), 'sha256': sha(output),
                      'embedded': len(embedded), 'mappings': len(mappings), 'buttons': len(buttons), 'static_status': 'PASS'}))

if __name__ == '__main__':
    build()
