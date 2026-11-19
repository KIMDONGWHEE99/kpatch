"""게임에 등록된 순서대로 중복 키와 문구 참조를 해석합니다."""
from common import *
from pck_tools import read_settings, variant
import struct,re

def project_translation_paths(data):
    raw=read_settings(data)['internationalization/locale/translations']
    kind,count=struct.unpack_from('<II',raw)
    assert kind==28
    pos=8;paths=[]
    for _ in range(count):
        typ,length=struct.unpack_from('<II',raw,pos)
        assert typ==4
        pos+=8
        paths.append(raw[pos:pos+length].decode('utf8').rstrip('\0'))
        pos+=length+(-length%4)
    assert pos==len(raw)
    return paths

def locale_tables():
    rows=read_json(WORK/'translation/canonical.json')
    groups={}
    for row in rows:groups.setdefault(row['file'],[]).append(row)
    paths=project_translation_paths((EXTRACTED/'raw/project.binary').read_bytes())
    en={};ko={};ordered=[]
    for path in paths:
        file=path.removeprefix('res://')
        if file not in groups:continue
        ordered.append(file)
        for r in groups[file]:
            en.setdefault(r['key'],r['source'])
            ko.setdefault(r['key'],r['target'])
    assert len(ordered)==len(groups)
    return en,ko,ordered

def expand(value,table,depth=0):
    if '{@' not in value:return value
    if depth>=8:raise ValueError(('순환·깊이 제한',value))
    def replace(match):
        key=match[1]
        if key not in table:raise KeyError(key)
        return expand(table[key],table,depth+1)
    return re.sub(r'\{@([^}]+)\}',replace,value)

def encode_settings_raw(settings):
    out=bytearray(b'ECFG'+struct.pack('<I',len(settings)))
    for key,value in settings.items():
        raw=key.encode('utf8')
        out.extend(struct.pack('<I',len(raw))+raw+struct.pack('<I',len(value))+value)
    return bytes(out)
