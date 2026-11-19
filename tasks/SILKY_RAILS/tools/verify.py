"""후보 번역표를 독립 재추출하여 모든 위치·열·서식과 실제 글꼴을 검사합니다."""
from common import *
import csv,io,re
from fontTools.ttLib import TTFont
candidate=ROOT/'build_candidate/SILKY_RAILS'/sys.argv[1]
ko=json.loads((WORK/'ko.json').read_text());env=UnityPy.load(str(candidate/DATA/'resources.assets'));original=UnityPy.load(str(BASE/DATA/'resources.assets'));seen={};tables=0
for obj in env.objects:
 if obj.type.name!='TextAsset':continue
 a=list(csv.reader(io.StringIO(original.file.objects[obj.path_id].read().m_Script.lstrip('\ufeff'))));b=list(csv.reader(io.StringIO(obj.read().m_Script.lstrip('\ufeff'))))
 if not a or 'key' not in a[0] or 'en' not in a[0]:continue
 tables+=1;assert len(a)==len(b);col=a[0].index('pt-BR');assert b[0][col]=='ko';assert a[0][:col]+a[0][col+1:]==b[0][:col]+b[0][col+1:]
 for before,after in zip(a[1:],b[1:]):
  if not before or not before[0] or before[0].startswith(('#','//')):continue
  assert before[:col]+before[col+1:]==after[:col]+after[col+1:]
  assert after[col]==ko[before[0]] and after[col].strip(),before[0]
  assert before[0] not in seen;seen[before[0]]=after[col]
assert seen==ko and tables==14,(len(seen),tables)
g=generator();fontenv=load(candidate/DATA/'sharedassets0.assets',g);font=fontenv.file.objects[800].read_typetree();ttf=TTFont(io.BytesIO(bytes(font['m_FontData'])));needed={ord(c) for c in ''.join(ko.values()) if c not in '\r\n\t'};assert needed<=set(ttf.getBestCmap())
fallback=fontenv.file.objects[116083].read_typetree();assert fallback['m_AtlasPopulationMode']==1 and fallback['m_IsMultiAtlasTexturesEnabled'] and fallback['m_SourceFontFile']=={'m_FileID':0,'m_PathID':800} and not fallback['m_FallbackFontAssetTable']
save(WORK/(sys.argv[1]+'_independent.json'),dict(status='PASS',tables=tables,keys=len(seen),font_characters=len(needed),missing_glyphs=[],translation_sha256=sha((WORK/'ko.json').read_bytes()),resources_sha256=sha((candidate/DATA/'resources.assets').read_bytes())))
print('독립 검사: 번역표',tables,'개, 키',len(seen),'개, 글꼴 누락 0')
