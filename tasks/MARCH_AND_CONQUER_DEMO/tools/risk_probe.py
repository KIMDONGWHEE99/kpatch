"""대량 번역 전 재저장·한글 글꼴·저장 격리를 시험합니다."""
from common import *
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import winreg
g=generator();run=WORK/'probe_001';game=run/'game'
assert not game.exists()
shutil.copytree(BASE,game)
report=[]
for name in ('globalgamemanagers','globalgamemanagers.assets','level0','resources.assets','sharedassets0.assets'):
    env=load(BASE/DATA/name,g);out=env.file.save();check=UnityPy.load(out)
    assert set(env.file.objects)==set(check.file.objects)
    assert [str(e) for e in env.file.externals]==[str(e) for e in check.file.externals]
    for obj in env.objects: assert obj.get_raw_data()==check.file.objects[obj.path_id].get_raw_data()
    report.append(dict(file=name,original_sha256=sha((BASE/DATA/name).read_bytes()),saved_sha256=sha(out),object_count=len(env.objects)))
    (run/'roundtrip').mkdir(exist_ok=True);(run/'roundtrip'/name).write_bytes(out)
font_source=ROOT/'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf'
font=instantiateVariableFont(TTFont(font_source),{'wght':400},inplace=True)
font_path=WORK/'NotoSansKR-Regular.ttf';font.save(font_path)
env=load(game/DATA/'sharedassets0.assets',g)
obj=env.file.objects[333];tree=obj.read_typetree();print('FONT_FIELDS',list(tree))
tree['m_FontData']=list(font_path.read_bytes());tree['m_Name']='Noto Sans KR';obj.save_typetree(tree)
obj=env.file.objects[1415];tree=obj.read_typetree();tree['m_IsMultiAtlasTexturesEnabled']=True;obj.save_typetree(tree)
obj=env.file.objects[1712];tree=obj.read_typetree();tree['languageDisplayName']='한국어'
probe={'new_game':'새 게임','options':'설정','exit':'종료','continue':'이어하기','start_message_title':'정복의 여정이 시작됩니다...'}
for e in tree['entries']:
    if e['key'] in probe:e['value']=probe[e['key']]
obj.save_typetree(tree);(game/DATA/'sharedassets0.assets').write_bytes(env.file.save())
env=load(game/DATA/'globalgamemanagers',g)
obj=env.file.objects[1];raw=obj.get_raw_data();a=b'PhilipMaxey';b=b'March and Conquer Demo'
assert raw.count(a)==raw.count(b)==1
obj.set_raw_data(raw.replace(a,b'KoreanQA001').replace(b,b'MarchConquerQA_000001'))
# 제품명의 바이트 길이를 유지하여 알 수 없는 후행 설정까지 원본대로 보존합니다.
assert len(obj.get_raw_data())==len(raw)
(game/DATA/'globalgamemanagers').write_bytes(env.file.save())
(game/DATA/'app.info').write_text('KoreanQA001\nMarchConquerQA_000001',encoding='utf-8')
save(run/'roundtrip.json',report)
save(run/'isolation.json',dict(company='KoreanQA001',product='MarchConquerQA_000001',original_company='PhilipMaxey',original_product='March and Conquer Demo',save_code='SaveSystem uses Application.persistentDataPath exclusively; settings use PlayerPrefs; no Steam API or networking references in Assembly-CSharp',source_font_sha256=sha(font_source.read_bytes()),probe_font_sha256=sha(font_path.read_bytes())))
print(game)
