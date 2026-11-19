"""설치기의 Windows 호환성 수정만 반영하고 동일한 차이 파일로 ZIP을 고정합니다."""
from common import *
import shutil,zipfile
release=ROOT/'release_output/COMBOLANDS_KOREAN_PATCH_1.0.0'
scratch=WORK/'package_1.0.0'
previous=json.loads((scratch/'package_validation.json').read_text(encoding='utf8'))
manifest=json.loads((release/'manifest.json').read_text(encoding='utf8'))
assert sha(release/'manifest.json')==previous['manifest_sha256']
for row in manifest['payload']:assert sha(release/row['path'])==row['sha256']
archive=release.parent/(release.name+'.zip')
assert sha(archive)==previous['zip_sha256']
shutil.copy2(archive,scratch/'initial_final_zip.zip')
(release/'Patch.ps1').write_text((ROOT/'tasks/COMBOLANDS/release_template/Patch.ps1').read_text(encoding='utf8'),encoding='utf-8-sig')
for row in manifest['payload']:
    if row['path']=='Patch.ps1':row.update(sha256=sha(release/row['path']),size=(release/row['path']).stat().st_size)
    else:assert sha(release/row['path'])==row['sha256']
save_json(release/'manifest.json',manifest)
allowed={r['path'] for r in manifest['payload']}|{'manifest.json'}
assert {p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()}==allowed
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for rel in sorted(allowed):z.write(release/rel,rel)
out=scratch/'from_final_zip_fixed';assert not out.exists()
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist())==allowed and z.testzip() is None
    z.extractall(out)
for rel in allowed:assert sha(out/rel)==sha(release/rel)
save_json(scratch/'final_package_validation.json',dict(status='PASS',zip_sha256=sha(archive),manifest_sha256=sha(release/'manifest.json'),files=len(allowed),changes=len(manifest['changes']),delta_roundtrip_evidence_sha256=sha(scratch/'package_validation.json'),delta_payload_unchanged=True,tool_sha256=sha(__file__),extracted=str(out)))
print('최종 ZIP',archive.stat().st_size,sha(archive))
