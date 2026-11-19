"""부제에 필요한 글자만 담은 도트 글꼴을 만들고 원본·허용 범위를 기록합니다."""
from pathlib import Path
import hashlib
import json
import sys
from pck_tools import ROOT, WORK

sys.path.insert(0, str(ROOT / 'tools/python_deps'))
from fontTools.ttLib import TTFont
from fontTools import subset

source = ROOT / 'tasks/MR_MAGEBOY_DEMO/third_party/Galmuri/Galmuri11-Bold.ttf'
license_path = source.with_name('LICENSE.txt')
output = WORK / 'typography'
output.mkdir(exist_ok=True)
title = '채집 마법사'
font = TTFont(source)
required = {ord(c) for c in title}
assert required.issubset(font.getBestCmap())
options = subset.Options()
options.name_IDs = ['*']
options.name_languages = ['*']
builder = subset.Subsetter(options=options)
builder.populate(unicodes=required)
builder.subset(font)
# 파생 글꼴은 원본 이름을 사용하지 않고 출처는 별도 라이선스로 제공합니다.
for name in font['name'].names:
    if name.nameID in (1, 2, 3, 4, 6, 16, 17):
        value = 'Bold' if name.nameID in (2, 17) else 'MageboyKoreanTitle'
        name.string = value.encode(name.getEncoding())
font['head'].macStyle |= 1
font['OS/2'].fsSelection = (font['OS/2'].fsSelection | 32) & ~64
font.recalcTimestamp = False
destination = output / 'TitlePixel.ttf'
font.save(destination)
checked = TTFont(destination)
assert required.issubset(checked.getBestCmap())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
record = {'source_url': 'https://github.com/quiple/galmuri/blob/main/dist/Galmuri11-Bold.ttf',
          'source_sha256': sha(source), 'license_sha256': sha(license_path), 'output_sha256': sha(destination),
          'output_size': destination.stat().st_size, 'title': title, 'characters': sorted(title),
          'required_missing': [], 'font_size': 12, 'antialiasing': 'NONE', 'scope': '메인·일시정지 부제 Label 2개만 적용',
          'reserved_name_handling': '파생 글꼴 가족 이름을 MageboyKoreanTitle로 변경', 'status': 'PASS'}
(output / 'title_font_manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'output': str(destination), 'size': destination.stat().st_size, 'sha256': sha(destination)}))
