"""해시별 원본 이미지를 모은 육안 검수판을 만듭니다."""
from baseline import *
sys.path.insert(0,str(ROOT/'tools/python_deps'))
from PIL import Image,ImageDraw,ImageFont
files=sorted((EXTRACT/'textures').glob('*.png'));items=[]
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',13)
for i,p in enumerate(files):
    im=Image.open(p).convert('RGBA');items.append(dict(id=i,file=p.name,width=im.width,height=im.height,sha256=sha(p.read_bytes())))
out=WORK/'media';out.mkdir(exist_ok=True)
for start in range(0,len(items),24):
    sheet=Image.new('RGB',(1200,1040),'#808080');d=ImageDraw.Draw(sheet)
    for j,r in enumerate(items[start:start+24]):
        im=Image.open(EXTRACT/'textures'/r['file']).convert('RGBA');im.thumbnail((285,220))
        x=(j%4)*300;y=(j//4)*173
        im.thumbnail((290,142));sheet.paste(im,(x+(300-im.width)//2,y),im)
        d.text((x+5,y+144),f"{r['id']}: {r['file']}",font=font,fill='white')
        d.text((x+5,y+157),f"{r['width']} x {r['height']}",font=font,fill='white')
    sheet.save(out/f'sheet_{start//24:02d}.png')
save(out/'index.json',items);print('이미지',len(items),'검수판',(len(items)+23)//24)
