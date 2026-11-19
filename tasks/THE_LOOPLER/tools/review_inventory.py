"""문구의 필드별 검토 자료와 픽셀 자산의 직접 관찰 자료를 생성합니다."""
from common import *
import json, collections, re
from PIL import Image, ImageDraw, ImageFont

records=json.loads((EXTRACT/'objects.json').read_text('utf-8'))
objects={r['id']:r for r in records}
texts=json.loads((EXTRACT/'strings.json').read_text('utf-8'))
canonical=json.loads((WORK/'translation_canonical.json').read_text('utf-8'))
translations={r['source']:r['translation'] for r in canonical}
review=WORK/'review';review.mkdir(parents=True,exist_ok=True)
groups=collections.defaultdict(list)
for row in texts:
    obj=objects[row['object_id']]
    if obj['file'].endswith('data.unity3d'):
        field=re.sub(r'/\d+(?=/|$)','/*',row['field'])
        groups[(obj.get('script',obj['type']),field)].append(row)
lines=[]
for (script,field),rows in sorted(groups.items()):
    values=list(dict.fromkeys(r['source'] for r in rows))
    lines.append(f'\n{script} {field} ({len(rows)} locations, {len(values)} unique)')
    for value in values:
        lines.append(('MATCH ' if value in translations else 'CHECK ')+json.dumps(value,ensure_ascii=False))
(review/'direct_fields.txt').write_text('\n'.join(lines),encoding='utf-8')

media=json.loads((EXTRACT/'media.json').read_text('utf-8'))
texture_rows=[r for r in media if r['type']=='Texture2D']
environments={}
index=[];images=[]
for n,row in enumerate(texture_rows):
    path=row['file']
    if path not in environments:environments[path]=UnityPy.load(str(SOURCE/path))
    obj=next(o for o in environments[path].objects if o.assets_file.name==row['asset'] and o.path_id==row['path_id'])
    entry={**row,'review_index':n}
    try:
        if row['width']==0 or row['height']==0:
            entry['extraction']='EMPTY_RUNTIME_TEXTURE';index.append(entry);continue
        im=obj.read().image.convert('RGBA')
        dest=review/'media'/f'{n:03}_{row["path_id"]}.png';dest.parent.mkdir(exist_ok=True)
        im.save(dest);entry['image']=str(dest.relative_to(WORK));entry['image_sha256']=sha(dest)
        entry['extraction']='PASS';images.append((n,row['name'],im))
    except Exception as e:entry['extraction']='FAIL';entry['error']=str(e)
    index.append(entry)
write_json(review/'media_index.json',index)
for page,start in enumerate(range(0,len(images),20)):
    sheet=Image.new('RGB',(1600,1100),(38,38,42));draw=ImageDraw.Draw(sheet)
    for slot,(n,name,im) in enumerate(images[start:start+20]):
        x=(slot%4)*400;y=(slot//4)*220
        draw.text((x+6,y+4),f'{n:03} {name}',fill='white')
        im.thumbnail((388,190),Image.Resampling.NEAREST)
        sheet.paste(im,(x+6,y+25),im)
    sheet.save(review/f'media_sheet_{page:02}.png')
print('groups',len(groups),'media',len(index),'errors',[r for r in index if r['extraction']=='FAIL'])
