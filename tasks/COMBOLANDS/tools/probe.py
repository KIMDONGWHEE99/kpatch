"""대량 번역 전에 재저장과 소량 한글·글꼴을 시험합니다."""
from common import *
import shutil
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

def main():
    out = WORK / 'probe_game_v3'
    if out.exists():
        raise RuntimeError('기존 시험 사본을 덮어쓰지 않습니다.')
    shutil.copytree(SOURCE, out)
    font_path = WORK / 'NotoSansKR-SemiBold.ttf'
    if not font_path.exists():
        ft = TTFont(ROOT / 'tasks/TFC2/third_party/NotoSansKR/NotoSansKR[wght].ttf')
        instantiateVariableFont(ft, {'wght':600}, inplace=True)
        ft.save(font_path)
    font_bytes = font_path.read_bytes()
    g = generator()
    report = []
    for p in containers():
        env = UnityPy.load(str(p)); env.typetree_generator = g
        changes = []
        source_fonts = [o.path_id for o in env.objects if o.type.name == 'Font']
        for obj in env.objects:
            if obj.type.name == 'PlayerSettings':
                raw = obj.get_raw_data()
                assert raw.count(b'Combolands') == 1 and raw.count(b'Crux Games') == 1
                obj.set_raw_data(raw.replace(b'Combolands', b'ComboQA_06').replace(b'Crux Games', b'Crux QAaaa'))
                changes.append([obj.path_id,'QA PlayerSettings'])
            elif obj.type.name == 'Font':
                t=obj.read_typetree(); t['m_FontData']=list(font_bytes)
                obj.save_typetree(t); changes.append([obj.path_id,'Font'])
            elif obj.type.name == 'MonoBehaviour':
                cls,_,_=script(obj)
                if cls not in {'LocalizedStringAsset','TextMeshProUGUI','TextMeshPro','TMP_FontAsset'}: continue
                t=obj.read_typetree(); raw=obj.get_raw_data()
                obj.save_typetree(t)
                if raw != obj.data: raise RuntimeError(f'무변경 재저장 불일치: {p.name}:{obj.path_id}')
                changed=False
                if cls=='LocalizedStringAsset' and t.get('_originalString') in ['New Game','Settings','Quit','Play']:
                    t['_originalString']={'New Game':'새 게임','Settings':'설정','Quit':'종료','Play':'시작'}[t['_originalString']]; changed=True
                if cls=='TMP_FontAsset':
                    if not source_fonts: raise RuntimeError('글꼴 원본 없음')
                    if not t['m_SourceFontFile']['m_PathID']: t['m_SourceFontFile']={'m_FileID':0,'m_PathID':source_fonts[0]}
                    t['m_AtlasPopulationMode']=1
                    t['m_IsMultiAtlasTexturesEnabled']=1
                    changed=True
                if changed:
                    obj.save_typetree(t); changes.append([obj.path_id,cls])
        if changes:
            target=out/'Combolands_Data'/p.name
            target.write_bytes(env.file.save())
            reopened=UnityPy.load(str(target));reopened.typetree_generator=g
            assert {o.path_id for o in reopened.objects}=={o.path_id for o in env.objects}
            for obj in reopened.objects:
                expected=env.file.objects[obj.path_id]
                assert obj.get_raw_data()==(expected.data if expected.data is not None else expected.get_raw_data()), (p.name,obj.path_id)
            report.append(dict(file=p.name,changes=changes,sha256=sha(target)))
    save_json(WORK/'probe_build.json',report)
    print('PROBE',out)

if __name__=='__main__': main()
