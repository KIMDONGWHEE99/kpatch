"""게임 텍스처를 동일 이미지별로 묶어 눈으로 읽을 검수판을 만듭니다."""
from common import *
from PIL import Image,ImageDraw
items=[];byhash={};source=json.loads((EXTRACT/'media.json').read_text(encoding='utf8'))
for row in source:
    if row['type']!='Texture2D':continue
    p=EXTRACT/'textures'/f"{row['file']}_{row['path_id']}.png"
    if not p.exists():continue
    h=sha(p.read_bytes())
    if h in byhash:byhash[h]['locations'].append(row);continue
    item=dict(id=len(items),path=str(p),sha256=h,locations=[row]);byhash[h]=item;items.append(item)
out=WORK/'media';out.mkdir(exist_ok=True)
for start in range(0,len(items),64):
    sheet=Image.new('RGB',(2048,2048),'#35353a');draw=ImageDraw.Draw(sheet)
    for j,item in enumerate(items[start:start+64]):
        im=Image.open(item['path']).convert('RGBA');im.thumbnail((244,210),Image.Resampling.NEAREST)
        x=j%8*256;y=j//8*256;sheet.paste(im,(x+(256-im.width)//2,y+24),im)
        draw.text((x+4,y+3),str(item['id'])+' '+item['locations'][0]['name'][:24],fill='white')
        draw.text((x+4,y+238),str(Image.open(item['path']).size),fill='white')
    sheet.save(out/f'sheet_{start//64:02d}.png')
save(out/'index.json',items);print('고유 이미지',len(items),'검수판',(len(items)+63)//64)
