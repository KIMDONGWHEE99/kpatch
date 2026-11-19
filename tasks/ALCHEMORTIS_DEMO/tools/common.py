"""설치기 시험에서 사용하는 동일 빌드의 경로와 기록 함수입니다."""
from pck_tools import ROOT,WORK,BASELINE
from pathlib import Path
import json,hashlib,shutil
GAME='ALCHEMORTIS_DEMO'
BASE=BASELINE
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(data):return hashlib.sha256(data).hexdigest()
