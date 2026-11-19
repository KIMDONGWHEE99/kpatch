"""게임 영상의 모든 프레임을 비공개로 추출해 검토판을 만듭니다."""
from common import *
from PIL import Image,ImageDraw
import subprocess
sys.path.insert(0,str(WORK/'media_deps'))
import imageio_ffmpeg

folder=EXTRACT/'video';folder.mkdir(exist_ok=True)
meta=json.loads((EXTRACT/'media/sharedassets1.assets_3.json').read_text(encoding='utf8'))
resource=meta['m_ExternalResources']
with (DATA/resource['m_Source']).open('rb') as f:
    f.seek(resource['m_Offset']);blob=f.read(resource['m_Size'])
assert len(blob)==resource['m_Size']
video=folder/'splash.m4v';video.write_bytes(blob)
decoder=imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([decoder,'-hide_banner','-loglevel','error','-i',str(video),'-q:v','3','-y',str(folder/'frame_%03d.jpg')],check=True)
frames=sorted(folder.glob('frame_*.jpg'));assert len(frames)==meta['m_FrameCount']
for start in range(0,len(frames),36):
    sheet=Image.new('RGB',(1920,1200),(30,30,30));draw=ImageDraw.Draw(sheet)
    for i,p in enumerate(frames[start:start+36]):
        im=Image.open(p);im.thumbnail((320,180));x=i%6*320;y=i//6*200
        sheet.paste(im,(x,y));draw.text((x+4,y+182),str(start+i),fill='white')
    sheet.save(folder/f'sheet_{start//36}.jpg')
save_json(folder/'manifest.json',dict(source=str(resource),video_sha256=sha(video),decoder_sha256=sha(decoder),frames=[dict(path=p.name,sha256=sha(p)) for p in frames]))
print('영상 전체 프레임',len(frames))
