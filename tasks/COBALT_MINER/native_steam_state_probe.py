"""상태 표현식의 등록 위치와 EDIF 원시 제목을 연결하는 읽기 전용 보조 조사입니다."""
import json
import re
from pathlib import Path
import pefile
import native_inventory as inv
from native_inspect import disassemble


def main():
    path = inv.BASE / 'Modules/Steamworks.mfx'
    data = path.read_bytes()
    pe = pefile.PE(data=data)
    resources = [l for t in pe.DIRECTORY_ENTRY_RESOURCE.entries for n in t.directory.entries
                 for l in n.directory.entries if str(t.name) == 'EDIF' and n.id == 102]
    assert len(resources) == 1
    descriptor = resources[0].data.struct
    raw = pe.get_data(descriptor.OffsetToData, descriptor.Size)
    text = raw.decode('utf-8-sig')
    # 전체 JSON의 비표준 이스케이프를 고치지 않고 Expressions 배열의 Title 토큰만 원시 순서로 읽습니다.
    expression_text = text.split('"Expressions":', 1)[1]
    titles = re.findall(r'"Title"\s*:\s*("(?:\\.|[^"\\])*")', expression_text)
    title = json.loads(titles[26])
    result = {'module_sha256': inv.sha(data), 'resource_sha256': inv.sha(raw),
              'resource_offset': pe.get_offset_from_rva(descriptor.OffsetToData),
              'expression_index': 26, 'expression_title': title,
              'status_start': '0x10008614', 'function_table_offset': '0x68',
              'instructions': disassemble(path, 0x100085c9, 0x2c3),
              'registration': disassemble(path, 0x10015eea, 0xf)}
    inv.save('steam_status_probe.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('instructions', 'registration')}))


if __name__ == '__main__':
    main()
