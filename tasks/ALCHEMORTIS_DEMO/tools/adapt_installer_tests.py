"""검증된 설치기 실패 시험을 현재 게임의 두 변경 파일에 맞춘다."""
from pck_tools import ROOT
folder=ROOT/'tasks/ALCHEMORTIS_DEMO/tools'
for filename in ['test_installer.py','test_installer_edges.py']:
    text=(ROOT/'tasks/MARCH_AND_CONQUER_DEMO/tools'/filename).read_text(encoding='utf-8')
    replacements=[
        ('build_candidate/MARCH_AND_CONQUER_DEMO/ko_v005/game','build_candidate/ALCHEMORTIS_DEMO/ko_1.0.0_c07'),
        ('build_candidate/MARCH_AND_CONQUER_DEMO/ko_v003/game','build_candidate/ALCHEMORTIS_DEMO/ko_1.0.0_c02'),
        ('MARCH_AND_CONQUER_DEMO','ALCHEMORTIS_DEMO'),
        ('March and Conquer Demo_Data/resources.assets','data_Alchemortis_windows_x86_64/Alchemortis.dll'),
        ('March and Conquer Demo_Data/sharedassets0.assets','Alchemortis Demo.pck'),
        ('March and Conquer Demo_Data/level0','data_Alchemortis_windows_x86_64/Alchemortis.dll'),
        ('March and Conquer Demo_Data','data_Alchemortis_windows_x86_64'),
        ('March and Conquer Demo','Alchemortis Demo'),
        ('UnityPlayer.dll','data_Alchemortis_windows_x86_64/GodotSharp.dll'),
        ('MarchConquerKoreanPatch','AlchemortisKoreanPatch'),
        ('package_v2','package_v2'),('.march-korean-new','.alchemortis-korean-new'),('5203110','4974580'),
        ("json.loads((WORK/'baseline.json').read_text(encoding='utf-8'))['files']","json.loads((WORK/'discovery/baseline_manifest.json').read_text(encoding='utf-8'))"),
    ]
    for before,after in replacements:text=text.replace(before,after)
    assert 'March' not in text and 'MARCH_' not in text
    (folder/filename).write_text(text,encoding='utf-8')
print('현재 게임 전용 설치기 시험 구성 완료')
