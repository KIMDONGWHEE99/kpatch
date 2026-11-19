"""공식 Google Fonts 저장소의 공개 글꼴과 라이선스를 함께 보존합니다."""
from common import *
import urllib.request,urllib.parse

root=ROOT/'tasks/HOW_EMPIRES_WORK/third_party'
records=[]
for folder,name in [('notoemoji','NotoEmoji[wght].ttf'),('notosanssymbols2','NotoSansSymbols2-Regular.ttf')]:
    out=root/folder;out.mkdir(parents=True,exist_ok=True)
    for file in [name,'OFL.txt']:
        url='https://raw.githubusercontent.com/google/fonts/main/ofl/'+folder+'/'+urllib.parse.quote(file)
        data=urllib.request.urlopen(url,timeout=30).read()
        if file.endswith('.ttf'):assert data[:4] in (b'\x00\x01\x00\x00',b'OTTO')
        else:assert b'SIL OPEN FONT LICENSE' in data
        (out/file).write_bytes(data)
        records.append({'url':url,'file':str(out/file),'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)})
write_json(root/'font_sources.json',records)
print([(Path(r['file']).name,r['size']) for r in records])
