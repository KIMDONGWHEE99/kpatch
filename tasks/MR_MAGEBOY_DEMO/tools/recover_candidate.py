"""완성 후보 PCK에서 조사 도구를 다시 실행해 독립 검수용 원문을 만듭니다."""
import json
import os
import subprocess
import sys
from pathlib import Path
from pck_tools import ROOT, EXTRACTED, WORK

candidate = sys.argv[1]
source = ROOT / 'build_candidate/MR_MAGEBOY_DEMO' / candidate / 'MR MAGEBOY DEMO.pck'
destination = EXTRACTED / 'candidate_recovery' / candidate
stage = WORK / candidate / 'independent_recovery'
assert source.is_file() and not destination.exists()
assert not (stage / 'execution.json').exists()
stage.mkdir(parents=True, exist_ok=True)
environment = os.environ.copy()
for key, folder in (('APPDATA', 'roaming'), ('LOCALAPPDATA', 'local'), ('TEMP', 'temp'), ('TMP', 'temp')):
    path = stage / folder
    path.mkdir(exist_ok=True)
    environment[key] = str(path)
command = [str(ROOT / 'tools/gdre_2.6.4/bin/gdre_tools.exe'), '--headless', '--recover=' + str(source), '--output=' + str(destination)]
process = subprocess.run(command, cwd=stage, env=environment, stdout=(stage / 'stdout.log').open('wb'), stderr=(stage / 'stderr.log').open('wb'))
(stage / 'execution.json').write_text(json.dumps({'command': command, 'exit_code': process.returncode}, ensure_ascii=False, indent=2), encoding='utf-8')
assert process.returncode == 0
print('독립 후보 재추출 완료:', destination)
