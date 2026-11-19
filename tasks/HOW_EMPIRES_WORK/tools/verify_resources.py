"""최종 후보 파일을 새 엔진 프로세스에서 열어 실제 값을 검사합니다."""
from common import *
import sys
candidate_id=sys.argv[1] if len(sys.argv)>1 else 'full_03'
B=WORK/candidate_id
config=read_json(WORK/'full_01/resource_config.json')
rows=read_json(WORK/'translation/canonical.json')
for entry in config['translations']:
    entry['messages']={r['key']:r['target'] for r in rows if r['file'].replace('.en.translation','.ko.translation')==entry['path']}
adjustments=read_json(WORK/'full_02/resource_adjustments.json')
config['themes']=[r['file'] for r in adjustments]
write_json(B/'verify_config.json',config)
report=B/'reopened_resources.json'
run_gdre(['--path',WORK/'full_01/resource_runtime','--script',Path(__file__).with_suffix('.gd'),'--',ROOT/'build_candidate'/GAME/candidate_id/PCK,B/'verify_config.json',report],B,'verify_resources')
result=read_json(report)
assert len(result['translations'])==34
assert all(r['locale']=='ko' and not r['failures'] and r['count']==r['expected_count'] for r in result['translations'])
assert len(result['fonts'])==30 and all(not r['missing'] and r['fallback_paths'][0]=='res://KoreanPatch/korean.fontdata' for r in result['fonts'])
assert all(r['tooltip_color']=='fff0d4ff' for r in result['themes'])
result.update(status='PASS',candidate_sha256=sha(ROOT/'build_candidate'/GAME/candidate_id/PCK),required_characters=len(config['characters']))
write_json(report,result)
print('PASS',len(result['translations']),'translations',len(result['fonts']),'fonts',len(result['themes']),'themes')
