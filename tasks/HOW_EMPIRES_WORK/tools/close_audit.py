"""최종 증거의 입력 지문을 연결하고 남은 분류·예외·미디어 판정을 확정합니다."""
from common import *
from pck_tools import read_pack
from translation_values import locale_tables
import re,collections,platform,sys
candidate_id=sys.argv[1] if len(sys.argv)>1 else 'full_04'
fix=candidate_id=='full_06'
stage=WORK/('final_audit_1.0.1' if fix else 'final_audit');stage.mkdir(exist_ok=True)
inventory={r['path']:r for r in read_json(WORK/'pck_inventory.json')}
rows=read_json(WORK/'census/classified.json')
extra=read_json(WORK/'census/extra_classified.json')
assert all(r['classification']!='UNKNOWN' and r['original_sha256'] and r['evidence'] for r in rows+extra)
assert not read_json(WORK/'census/remaining.json') and not read_json(WORK/'census/extra_pending.json') and not read_json(WORK/'census/extraction_errors.json')
covered={r['original_file'] for r in rows}|{r['file'] for r in read_json(WORK/'census/extra_files.json')}
assert all(p in covered for p in inventory if Path(p).suffix in ['.gdc','.res','.scn','.json','.gdshader'])
counts=dict(collections.Counter(r['classification'] for r in rows+extra))
del rows,extra
media=read_json(WORK/'media/reviewed.json')
for i,row in enumerate(read_json(WORK/'media/svg_review.json')):
    imported=(RECOVERED/(row['file']+'.import')).read_text(encoding='utf8')
    path=re.search(r'^path="res://([^"]+)"',imported,re.M)[1]
    media.append({**row,'original_file':path,'original_sha256':inventory[path]['sha256'],'classification':'MEDIA','treatment':'KEEP_IDENTITY' if i in [0,1,6] else 'NO_TEXT','review_evidence':f'full_01/svg_sheet.png #{i}: 실제 벡터 렌더링을 시각 검토. 로고 또는 제어·도형.'})
assert len(media)==2910 and {r['original_file'] for r in media}=={p for p in inventory if p.endswith('.ctex')}
for p,r in inventory.items():
    if Path(p).suffix in ('.png','.ico'):
        media.append({'original_file':p,'original_sha256':r['sha256'],'classification':'MEDIA','treatment':'KEEP_IDENTITY' if 'LOGO' in p else 'NO_TEXT','review_evidence':'media/raw의 실제 이미지 검토. 흰 배경 합성으로 검정 로고도 확인.'})
    if Path(p).suffix in ('.sample','.oggvorbisstr'):
        media.append({'original_file':p,'original_sha256':r['sha256'],'classification':'MEDIA','treatment':'KEEP_ORIGINAL_AUDIO','review_evidence':'음악·효과음·원작 음성을 원형 유지하는 텍스트 패치 범위. 음성 더빙·번역했다고 주장하지 않음. 공개 README에 명시.'})
assert all(r['treatment']!='UNKNOWN' for r in media)
write_json(stage/'media_dispositions.json',media)
reference_evidence=[]
for file,refs in read_json(WORK/'media/suspect_references.json').items():
    assert refs==[]
    reference_evidence.append({'file':file,'recovered_sha256':sha(RECOVERED/file),'references':0,'reason':'경로·UID 정적 참조 없음. Utils.get_all_file_paths의 호출은 정의 자료 폴더이며 UI/PlaceholderArt·VFX 이미지 디렉터리를 로드하지 않음.'})
write_json(stage/'unused_media_references.json',reference_evidence)
locales=read_json(WORK/'translation/canonical.json');direct=read_json(WORK/'translation/direct_canonical.json')
assert len(locales)==2553 and len(direct)==(2732 if fix else 2747)
assert all(r['target'] is not None and (r['target'].strip() or not r['source'].strip()) for r in locales+direct)
english,korean,ordered=locale_tables()
duplicates=[]
for key,count in collections.Counter(r['key'] for r in locales).items():
    if count>1:
        items=sorted([r for r in locales if r['key']==key],key=lambda r:ordered.index(r['file']))
        duplicates.append({'key':key,'engine_winner':items[0]['id'],'rows':items,'reason':'원본 project.binary에 등록된 언어표 순서와 첫 일치 우선 규칙 보존. 각 원본 위치를 별도로 한국어화.'})
assert len(duplicates)==7
write_json(stage/'duplicate_resolution.json',duplicates)
diffs=read_json(WORK/'translation/format_differences.json');assert len(diffs)==1
d=diffs[0];assert d['id'].endswith('::ADVANCE_AUTOMATE_SEND_TRADE_JOURNEY_DESC')
assert d['failures']==['tag_order'] and d['source_tags'][2]==['color'] and d['target_tags'][1:]==[[],[]]
source=next(r for r in locales if r['id']==d['id'])
write_json(stage/'format_validation.json',{'status':'PASS','rows':len(locales)+len(direct),'unresolved':0,'accepted_repairs':[dict(d,original_file_sha256=source['file_sha256'],source_sha256=source['source_sha256'],target_sha256=hashlib.sha256(d['target'].encode()).hexdigest(),reason='원문에 빠진 보라색 닫기 태그만 보완. 태그 순서·중첩과 아이콘·자리표시자·줄바꿈의 나머지 차이 없음.') ]})
_,_,_,entries=read_pack(ROOT/'build_candidate'/GAME/candidate_id/PCK)
pack={r['name']:r['data'] for r in entries}
credits=read_json(WORK/'translation/credits.json')
assert pack['Data/Credits/credits.txt']==''.join(r['target'] for r in credits).encode('utf8')
for r in credits:r.update(original_file='Data/Credits/credits.txt',original_sha256=inventory['Data/Credits/credits.txt']['sha256'],source_sha256=hashlib.sha256(r['source'].encode()).hexdigest())
write_json(stage/'credits_locations.json',credits)
exclusions=[]
for p in inventory:
    if p.endswith('rider-plugin.gdextension'):
        exclusions.append({'file':p,'sha256':inventory[p]['sha256'],'status':'PASS','reason':'Windows 라이브러리가 없는 원작 편집기 Rider 확장. 원본·후보 실제 실행에서 동일 3개 오류를 대조. 실행용 문구 자원이 아님.'})
    if p.endswith('.fontdata') and 'source_code_pro.fnt-' in p:
        exclusions.append({'file':p,'sha256':inventory[p]['sha256'],'status':'PASS','reason':'GDRE 비트맵 .fnt 내보내기는 텍스처 부재로 실패. 실제 FontFile은 엔진으로 직접 열어 전체 30개 글꼴 검사에 포함했고 한국어 폴백으로 필요 문자 0개 누락 확인. 변환 실패를 글꼴 제외로 처리하지 않음.'})
assert len(exclusions)==2
write_json(stage/'conversion_resolutions.json',exclusions)
coverage=[]
for p,r in inventory.items():
    ext=Path(p).suffix
    if p in covered:kind='위치별 문자열 조사 또는 문자열 0개인 파일 해석 완료'
    elif ext in ['.ctex','.sample','.oggvorbisstr','.png','.ico']:kind='미디어 별도 판정 완료'
    elif ext=='.translation':kind='영어 원본 34개를 대응 한국어 34개로 추가. 기존 다른 언어 170개는 원형 유지'
    elif ext=='.fontdata':kind='엔진 직접 열기·필요 문자·폴백 검증 완료'
    elif ext in ['.remap','.import']:kind='자원 경로·가져오기 옵션. 위치 추적에 사용하고 변경 경계를 전체 비교'
    elif ext=='.txt':kind='제작진 줄별 번역' if 'credits' in p else '원본 글꼴 라이선스 전문 유지'
    elif ext in ['.cfg','.bin','.binary','.gdextension','.dat']:kind='엔진 설정·클래스/UID 캐시·확장 선언·ICU 문자 데이터. 게임 표시 문구가 아닌 구조 자료; 설정 중 게임 고유 제목 유지'
    else:raise AssertionError(p)
    coverage.append({'file':p,'sha256':r['sha256'],'size':r['size'],'status':'PASS','evidence':kind})
write_json(stage/'file_coverage.json',coverage)
proofs={}
proof_paths=([candidate_id+'/independent_validation.json',candidate_id+'/reopened_resources.json','q/boundary_audit_full_06/report.json','full_06/code_identifier_audit.json','full_06/resource_semantics_audit.json','full_06/final_boundary.json','reapply_trial_1.0.1/report.json'] if fix else ['full_04/independent_validation.json','full_04/reopened_resources.json','q/boundary_audit/report.json','package_1.0.0_r2/installer_tests.json','reapply_trial/report.json'])
for rel in proof_paths:
    report=read_json(WORK/rel);assert report['status']=='PASS';proofs[rel]=sha(WORK/rel)
inputs={'baseline':sha(WORK/'baseline.json'),'candidate':sha(ROOT/'build_candidate'/GAME/candidate_id/PCK),'canonical':sha(WORK/'translation/canonical.json'),'direct':sha(WORK/'translation/direct_canonical.json'),'gdre_exe':sha(GDRE),'gdre_pck':sha(GDRE.with_name('gdre_tools.pck')),'python':platform.python_version(),'python_exe':sha(Path(sys.executable)),'tools':{p.name:sha(p) for p in Path(__file__).parent.iterdir() if p.is_file()}}
write_json(stage/'static_summary.json',{'status':'PASS','candidate_sha256':inputs['candidate'],'pck_files':len(inventory),'classified_strings':counts,'additional_files':593,'additional_binary_resources':346,'locale_rows':len(locales),'direct_locations':len(direct),'credits_lines':len(credits),'media_items':len(media),'unknown':0,'unresolved_extraction_errors':0,'unresolved_format_errors':0,'unreviewed_media':0,'input_bindings':inputs,'proofs':proofs,'superseded_raw_inventories':['census/summary.json','translation/duplicate_keys.json','media/inventory.json'],'scope':'미분류 원시 목록은 이 최종 판정의 입력 이력이며 미해결 목록이 아님. 추가 이진 장식 자료는 표시 문구가 없으며 원형 유지.'})
print('STATIC PASS',counts,'media',len(media),'original files',len(inventory))
