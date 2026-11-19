"""비공개 원본에서 그림·영상·Odin 저장 노드와 추가 문자열을 조사합니다."""
from common import *
from PIL import Image,ImageDraw,ImageFont
from collections import Counter
import re

def walk(v,path=()):
    if isinstance(v,dict):
        for k,c in v.items():yield from walk(c,path+(k,))
    elif isinstance(v,list):
        if v and all(isinstance(c,int) for c in v):return
        for i,c in enumerate(v):yield from walk(c,path+(i,))
    elif isinstance(v,str) and v.strip():yield list(path),v

def main():
    folder=EXTRACT/'media';folder.mkdir(exist_ok=True)
    g=generator();media=[];extra=[];odin=[];errors=[];objects=[]
    for p in containers():
        file_hash=sha(p)
        env=UnityPy.load(str(p));env.typetree_generator=g
        for obj in env.objects:
            cls=obj.type.name;head=dict(file=p.name,file_sha256=file_hash,path_id=obj.path_id,type=cls,raw_sha256=hashlib.sha256(obj.get_raw_data()).hexdigest())
            objects.append(head)
            if cls=='Texture2D':
                try:
                    data=obj.read();im=data.image.convert('RGBA');index=len(media)
                    name=f'{p.name}_{obj.path_id}.png';im.save(folder/name)
                    media.append(dict(**head,index=index,name=data.m_Name,path=name,width=im.width,height=im.height,image_sha256=sha(folder/name),classification='UNKNOWN'))
                except Exception as e:errors.append(dict(**head,error=str(e)))
            elif cls=='VideoClip':
                data=obj.read();save_json(folder/f'{p.name}_{obj.path_id}.json',obj.read_typetree())
            if cls=='MonoBehaviour':
                try:
                    tree=obj.read_typetree()
                    if 'serializationData' in tree:
                        data=tree['serializationData']
                        odin.append(dict(**head,cls=script(obj)[0],data=data))
                except Exception:pass
            elif cls not in ['Texture2D','Shader','Mesh','Font','Sprite','AudioClip','VideoClip','TextAsset']:
                try:
                    tree=obj.read_typetree()
                    for path,s in walk(tree):extra.append(dict(**head,field=path,source=s))
                except Exception as e:errors.append(dict(**head,error=str(e)))
        print(p.name,flush=True)
    save_json(EXTRACT/'object_manifest.json',objects);save_json(EXTRACT/'media_manifest.json',media)
    save_json(EXTRACT/'extra_native_strings.json',extra);save_json(EXTRACT/'odin_payloads.json',odin);save_json(EXTRACT/'extra_errors.json',errors)
    for start in range(0,len(media),24):
        sheet=Image.new('RGB',(1440,1040),(45,45,50));d=ImageDraw.Draw(sheet)
        for n,row in enumerate(media[start:start+24]):
            im=Image.open(folder/row['path']);im.thumbnail((230,224))
            x=(n%6)*240;y=(n//6)*260
            sheet.paste(im,(x+(240-im.width)//2,y+10),im)
            d.text((x+5,y+235),f"{row['index']} {row['name'][:26]}",fill='white')
        sheet.save(folder/f'sheet_{start//24:02}.jpg')
    print('MEDIA',len(media),'EXTRA',len(extra),'ODIN',len(odin),'ERRORS',len(errors))

if __name__=='__main__':main()
