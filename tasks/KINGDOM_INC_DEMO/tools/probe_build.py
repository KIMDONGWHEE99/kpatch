"""대량 번역 전 작은 한글 문구로 재저장·글꼴을 시험합니다."""
from common import *
from font_patch import apply_fonts
import shutil

probe_name = sys.argv[1] if len(sys.argv) > 1 else "probe"
target = WORK / probe_name / "game"
assert not target.exists(), "이전 시험 후보는 덮어쓰지 않습니다."
shutil.copytree(SOURCE, target)
changes = apply_fonts(target)
source = (EXTRACT / "textassets/resources.assets_21_en-US.txt").read_text(encoding="utf-8")
mapping = {"MMContinue":"계속하기", "MMNewGame":"새 게임", "MMLoadGame":"불러오기",
           "MMOptions":"설정", "MMKeyBindings":"키 설정", "MMExit":"게임 종료"}
lines = []
for line in source.splitlines():
    if "=" in line and not line.lstrip().startswith(";"):
        key = line.split("=", 1)[0].strip()
        if key in mapping:
            line = f"{key} = {mapping[key]}"
    lines.append(line)
(target / "language.ini").write_text("\n".join(lines), encoding="utf-8")
write_json(WORK / probe_name / "build.json", {"changes": changes, "font_sha256":sha(WORK/"fonts/NotoSansKR-Regular.ttf"),
                                       "candidate":str(target), "baseline_sha256":sha(EXTRACT/"baseline.json")})
print(str(target))
