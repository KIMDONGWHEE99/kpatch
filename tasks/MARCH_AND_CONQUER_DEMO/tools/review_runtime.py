"""실제 GPU에서 저장한 화면과 표시 문구를 검수판으로 묶습니다."""
from common import *
from PIL import Image,ImageDraw
from collections import Counter
run=WORK/sys.argv[1];captures=run/'captures';out=run/'review';out.mkdir(exist_ok=True)
records=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(captures.glob('*.json'))]
assert (captures/'completed.txt').exists()
assert all(r['device']=='NVIDIA GeForce RTX 4060 Ti' and r['product']=='MarchConquerQA_0000008' and r['textCount']>0 for r in records)
over={}
for r in records:
    for t in r['texts']:
        if t['overflowing']:over.setdefault((t['path'],t['text']),dict(t,stages=[]))['stages'].append(r['stage'])
save(out/'overflow.json',list(over.values()))
nodes=sorted(captures.glob('node_*.png'))
for page,start in enumerate(range(0,len(nodes),16)):
    sheet=Image.new('RGB',(1280,960),'#222222');draw=ImageDraw.Draw(sheet)
    for i,p in enumerate(nodes[start:start+16]):
        crop=Image.open(p).crop((780,138,1100,352));x=i%4*320;y=i//4*240
        sheet.paste(crop,(x,y+24));draw.text((x+5,y+5),p.stem[:48],fill='white')
    sheet.save(out/f'nodes_{page:02}.png')
units=sorted(captures.glob('unit_*.png'))
for page,start in enumerate(range(0,len(units),20)):
    sheet=Image.new('RGB',(1280,900),'#222222');draw=ImageDraw.Draw(sheet)
    for i,p in enumerate(units[start:start+20]):
        crop=Image.open(p).crop((150,235,470,385));x=i%4*320;y=i//4*180
        sheet.paste(crop,(x,y+24));draw.text((x+5,y+5),p.stem[:48],fill='white')
    sheet.save(out/f'units_{page:02}.png')
summary=dict(frames=len(records),nodes=len(nodes),units=len(units),main=len(list(captures.glob('0*.png'))),overflow_variants=len(over),font_names=dict(Counter(t['font'] for r in records for t in r['texts'])),visible_text_variants=len({t['text'] for r in records for t in r['texts']}))
save(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=True))
