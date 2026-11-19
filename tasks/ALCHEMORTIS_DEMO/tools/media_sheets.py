"""모든 이미지의 검토용 축소 모음을 원본 해시와 연결한다."""
from pck_tools import ROOT,EXTRACTED,WORK
import sys,json,hashlib
sys.path.insert(0,str(ROOT/'tools/python_deps'))
from PIL import Image,ImageDraw,ImageFont
root=EXTRACTED/'recovered';out=WORK/'media';out.mkdir(exist_ok=True)
paths=sorted(root.rglob('*.png'));rows=[]
for start in range(0,len(paths),70):
    sheet=Image.new('RGB',(1400,1100),(38,38,42));draw=ImageDraw.Draw(sheet)
    for index,path in enumerate(paths[start:start+70],start):
        im=Image.open(path).convert('RGBA');size=im.size
        im.thumbnail((184,82),Image.Resampling.NEAREST)
        x=((index-start)%7)*200;y=((index-start)//7)*110
        sheet.paste(im,(x+(200-im.width)//2,y),im)
        draw.text((x+4,y+84),f'{index:04} {path.stem[:26]}',fill='white')
        rows.append({'index':index,'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':size,'sheet':f'sheet_{start//70:02}.jpg','status':'UNKNOWN'})
    sheet.save(out/f'sheet_{start//70:02}.jpg',quality=92)
(out/'inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(len(rows),'이미지',len(list(out.glob('sheet_*.jpg'))),'검토판')
