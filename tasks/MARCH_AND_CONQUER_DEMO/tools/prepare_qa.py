"""정식 후보의 문구·글꼴을 유지하며 검수 저장 위치만 분리합니다."""
from common import *
build=sys.argv[1];run=WORK/sys.argv[2];game=run/'game';candidate=ROOT/'build_candidate'/GAME/build/'game'
assert not game.exists();shutil.copytree(candidate,game)
a=(game/DATA/'globalgamemanagers').read_bytes();company=b'KoreanQA008';product=b'MarchConquerQA_0000008'
assert len(company)==len(b'PhilipMaxey') and len(product)==len(b'March and Conquer Demo')
assert a.count(b'PhilipMaxey')==a.count(b'March and Conquer Demo')==1
b=a.replace(b'PhilipMaxey',company).replace(b'March and Conquer Demo',product)
assert len(a)==len(b);(game/DATA/'globalgamemanagers').write_bytes(b)
(game/DATA/'app.info').write_bytes(company+b'\r\n'+product+b'\r\n')
save(run/'qa_manifest.json',dict(game_id=GAME,candidate=build,candidate_manifest_sha256=sha((candidate.parent/'build.json').read_bytes()),overrides=[dict(file='globalgamemanagers',path_id=1,fields=['companyName','productName']),dict(file='app.info',fields=['company','product'])],files=[dict(path=p.relative_to(game).as_posix(),sha256=sha(p.read_bytes())) for p in game.rglob('*') if p.is_file()]))
print(game)
