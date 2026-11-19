"""격리된 실행 사본에 소규모 한국어·신규 글자 시험만 추가합니다."""
from extract_localization import ROOT, BASE, BUNDLES, OUT, save
from risk_probe import save_preserving_layout
from catalog import update_catalog, bundle_crc, catalog_hash
import UnityPy
import hashlib
import json
import shutil

QA = ROOT / 'working_private/ALASKA_GOLD_FEVER/risk_runtime/game'
PROBE = ROOT / 'working_private/ALASKA_GOLD_FEVER/risk_probe/localized_probe'

def main():
    if not (QA.parent / 'isolation.json').exists():
        raise RuntimeError('실행 격리 증거가 먼저 필요합니다.')
    aa = QA / 'Alaska Gold Fever_Data/StreamingAssets/aa'
    records, changes = [], []
    tables = json.loads((OUT / 'tables.json').read_text('utf-8'))
    shared = json.loads((OUT / 'shared.json').read_text('utf-8'))
    settings_id = next(r['m_Id'] for r in shared['UtilitiesTranslations']['tree']['m_Entries'] if r['m_Key'] == 'settings')
    for path in BUNDLES.glob('localization-string-tables-korean*.bundle'):
        input_path = PROBE / path.name
        env = UnityPy.load(str(input_path))
        for obj in env.objects:
            if obj.type.name != 'MonoBehaviour':
                continue
            tree = obj.read_typetree()
            if tree.get('m_Name') == 'UtilitiesTranslations_ko':
                entry = next(r for r in tree['m_TableData'] if r['m_Id'] == settings_id)
                records.append({'bundle':path.name,'path_id':obj.path_id,'id':settings_id,'before':entry['m_Localized'],'after':'설정 · 붐 꽂 쐐'})
                entry['m_Localized'] = '설정 · 붐 꽂 쐐'
                obj.save_typetree(tree)
        output = save_preserving_layout(env)
        (aa / 'StandaloneWindows64' / path.name).write_bytes(output)
        changes.append({'name':path.name,'source_size':path.stat().st_size,'candidate_bytes':output,'candidate_crc':bundle_crc(output)})
    original_catalog = (BASE / 'Alaska Gold Fever_Data/StreamingAssets/aa/catalog.bin').read_bytes()
    catalog, report = update_catalog(original_catalog, changes)
    (aa / 'catalog.bin').write_bytes(catalog)
    (aa / 'catalog.hash').write_text(catalog_hash(catalog), encoding='ascii')
    font = ROOT / 'working_private/ALASKA_GOLD_FEVER/font_audit/probe_v3/resources.assets'
    shutil.copy2(font, QA / 'Alaska Gold Fever_Data/resources.assets')
    files = []
    for path in [*(aa / 'StandaloneWindows64').glob('localization-string-tables-korean*.bundle'), aa / 'catalog.bin',aa / 'catalog.hash',QA / 'Alaska Gold Fever_Data/resources.assets']:
        files.append({'path':path.relative_to(QA).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    save(QA.parent / 'loading_probe.json', {'stage':'G1','status':'NOT_RUN','sample_changes':records,'files':files,'catalog':report})
    print('로딩·새 한글 시험 사본 준비',len(files),'파일')

if __name__ == '__main__':
    main()
